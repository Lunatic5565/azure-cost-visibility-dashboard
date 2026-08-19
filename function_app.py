"""
Azure Cost Visibility Dashboard - Data Ingestion Function
------------------------------------------------------------
Timer-triggered function that runs daily, pulls the previous day's
cost data from the Azure Cost Management API, and upserts it into
an Azure SQL Database table for Power BI to consume.

Auth model:
  - Cost Management API: system-assigned managed identity (no secrets)
  - Azure SQL: SQL authentication via connection string app setting

Required app settings (Function App > Configuration):
  SUBSCRIPTION_ID       - your Azure subscription GUID
  SQL_CONNECTION_STRING - pymssql-style connection string, e.g.
                           "server.database.windows.net:1433;DATABASE=CostDashboardDB;
                            UID=sqladmin;PWD=<password>"
"""

import os
import time
import logging
import datetime
import requests
import pymssql
import azure.functions as func

app = func.FunctionApp()

MGMT_API_BASE = "https://management.azure.com"
COST_QUERY_API_VERSION = "2023-11-01"
TOKEN_RESOURCE = "https://management.azure.com/"


def get_managed_identity_token() -> str:
    """Fetch an access token for the ARM/Cost Management API using the
    Function App's system-assigned managed identity via the local
    MSI endpoint that Azure injects into the function's environment."""
    identity_endpoint = os.environ["IDENTITY_ENDPOINT"]
    identity_header = os.environ["IDENTITY_HEADER"]

    resp = requests.get(
        identity_endpoint,
        headers={"X-IDENTITY-HEADER": identity_header},
        params={
            "resource": TOKEN_RESOURCE,
            "api-version": "2019-08-01",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_cost_data(subscription_id: str, token: str, target_date: datetime.date) -> list[dict]:
    """Query the Cost Management API for actual cost, grouped by
    resource group, service name, and meter category, for a single day."""
    url = (
        f"{MGMT_API_BASE}/subscriptions/{subscription_id}"
        f"/providers/Microsoft.CostManagement/query"
        f"?api-version={COST_QUERY_API_VERSION}"
    )

    date_str = target_date.isoformat()

    body = {
        "type": "ActualCost",
        "timeframe": "Custom",
        "timePeriod": {"from": date_str, "to": date_str},
        "dataset": {
            "granularity": "Daily",
            "aggregation": {
                "totalCost": {"name": "Cost", "function": "Sum"}
            },
            "grouping": [
                {"type": "Dimension", "name": "ResourceGroupName"},
                {"type": "Dimension", "name": "ServiceName"},
                {"type": "Dimension", "name": "MeterCategory"},
            ],
        },
    }

    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()

    columns = [c["name"] for c in payload["properties"]["columns"]]
    rows = payload["properties"]["rows"]

    return [dict(zip(columns, row)) for row in rows]


# Azure SQL error codes worth retrying: the database is a Serverless tier
# and may be paused. The first connection after idle time triggers an
# auto-resume that can take well over pymssql's default connect timeout,
# surfacing as error 40613 ("Database ... is not currently available").
# 40197 and 10928/10929 are other transient "service busy/throttled" codes
# that are also safe to retry.
RETRYABLE_SQL_ERROR_CODES = {40613, 40197, 10928, 10929}

MAX_CONNECT_ATTEMPTS = 4
INITIAL_BACKOFF_SECONDS = 5


def connect_with_retry(**connect_kwargs) -> "pymssql.Connection":
    """Connect to Azure SQL, retrying with exponential backoff if the
    database is waking up from a Serverless auto-pause (or is otherwise
    transiently unavailable). Non-retryable errors (bad credentials,
    unknown database, etc.) fail immediately instead of being retried."""
    delay = INITIAL_BACKOFF_SECONDS
    last_exc: Exception | None = None

    for attempt in range(1, MAX_CONNECT_ATTEMPTS + 1):
        try:
            return pymssql.connect(**connect_kwargs)
        except pymssql.OperationalError as exc:
            error_code = exc.args[0] if exc.args else None
            last_exc = exc

            if error_code not in RETRYABLE_SQL_ERROR_CODES:
                logging.error(f"Non-retryable SQL connection error ({error_code}): {exc}")
                raise

            if attempt == MAX_CONNECT_ATTEMPTS:
                logging.error(
                    f"SQL connection failed after {attempt} attempts "
                    f"(error {error_code}), giving up: {exc}"
                )
                raise

            logging.warning(
                f"SQL connection attempt {attempt}/{MAX_CONNECT_ATTEMPTS} failed "
                f"(error {error_code}, likely database waking from auto-pause). "
                f"Retrying in {delay}s..."
            )
            time.sleep(delay)
            delay *= 2  # exponential backoff: 5s, 10s, 20s

    # Should never reach here, but keeps type-checkers happy
    raise last_exc  # type: ignore[misc]


def upsert_rows(rows: list[dict], target_date: datetime.date) -> int:
    """Write parsed cost rows into Azure SQL. Deletes any existing rows
    for the target date first, so re-running the function is safe
    (idempotent) rather than creating duplicates."""
    conn_str = os.environ["SQL_CONNECTION_STRING"]
    parts = dict(
        p.split("=", 1) for p in conn_str.split(";") if "=" in p
    )
    server_part = conn_str.split(";")[0]
    host, port = (server_part.split(":") + ["1433"])[:2]

    conn = connect_with_retry(
        server=host,
        port=port,
        database=parts.get("DATABASE"),
        user=parts.get("UID"),
        password=parts.get("PWD"),
    )
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM CostData WHERE UsageDate = %s", (target_date,)
    )

    insert_sql = """
        INSERT INTO CostData
            (UsageDate, ResourceGroup, ServiceName, MeterCategory, Cost, Currency, IngestedAt)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    now = datetime.datetime.utcnow()
    count = 0
    for row in rows:
        cursor.execute(
            insert_sql,
            (
                target_date,
                row.get("ResourceGroupName", "unknown"),
                row.get("ServiceName", "unknown"),
                row.get("MeterCategory", "unknown"),
                float(row.get("Cost", 0) or 0),
                row.get("Currency", "USD"),
                now,
            ),
        )
        count += 1

    conn.commit()
    cursor.close()
    conn.close()
    return count


@app.function_name(name="DailyCostIngestion")
@app.timer_trigger(schedule="0 0 6 * * *", arg_name="mytimer", run_on_startup=False)
def daily_cost_ingestion(mytimer: func.TimerRequest) -> None:
    """Runs every day at 06:00 UTC. Pulls yesterday's cost data
    (billing data for 'today' is usually incomplete) and stores it."""
    subscription_id = os.environ["SUBSCRIPTION_ID"]
    target_date = datetime.date.today() - datetime.timedelta(days=1)

    logging.info(f"Starting cost ingestion for {target_date.isoformat()}")

    try:
        token = get_managed_identity_token()
        rows = fetch_cost_data(subscription_id, token, target_date)
        written = upsert_rows(rows, target_date)
        logging.info(f"Ingested {written} cost rows for {target_date.isoformat()}")
    except Exception as exc:
        logging.error(f"Cost ingestion failed for {target_date.isoformat()}: {exc}")
        raise
