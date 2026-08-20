# Azure Cost Visibility Dashboard
 
An end-to-end cloud cost monitoring pipeline built on native Azure services — ingesting daily spend data, storing it in a relational warehouse, visualizing it in Power BI, and alerting automatically when costs cross a threshold.
 
## Overview
 
This project was built as a hands-on portfolio piece to demonstrate practical Azure data engineering skills: API ingestion, SQL data modeling, BI visualization, and workflow automation — all using free-tier, native Azure services (no Data Factory, no Fabric).
 
## Architecture
 
```
Azure Cost Management API
        │
        ▼
Azure Function (Python, timer-triggered)
        │
        ▼
Azure SQL Database (CostData table + views)
        │
        ├──────────────► Power BI Desktop (dashboard)
        │
        └──────────────► Logic App (daily check + email alert)
```
 
**Flow:**
1. A timer-triggered Azure Function runs daily, calling the Azure Cost Management API and writing results into `CostData` in Azure SQL Database.
2. Three SQL views (`vw_DailyTotalCost`, `vw_MonthToDateByResourceGroup`, `vw_Top30DayServices`) transform the raw data for reporting.
3. Power BI Desktop connects via DirectQuery for a live dashboard: total spend KPI, daily trend line, spend by resource group, and top services.
4. A Logic App runs daily, queries `vw_DailyTotalCost` for the latest cost, and sends an email alert if it exceeds a configured threshold.
## Tech Stack
 
- **Azure Functions** (Python, timer trigger) — data ingestion
- **Azure SQL Database** — storage and view-based transformation
- **Power BI Desktop** — dashboard and visualization (DirectQuery)
- **Azure Logic Apps** (Consumption) — scheduled monitoring and email alerting
- **Azure Cost Management API** — data source
## Features
 
- Daily automated ingestion of Azure cost data — no manual updates
- Live Power BI dashboard with 4 core visuals: total spend, daily trend, resource group breakdown, top services
- Automated email alerting when daily spend crosses a set threshold
- Entirely built on free-tier Azure resources
## Repository Contents
 
| File | Description |
|---|---|
| `function_app.py` | Azure Function ingestion logic — pulls cost data from the Cost Management API and writes to SQL |
| `host.json` | Azure Functions host configuration |
| `requirements.txt` | Python dependencies |
| `schema.sql` | Table and view definitions for the SQL database |
| `Function app.png`, `SQL CostData.png`, `Success Count.png` | Verification screenshots of the pipeline running end-to-end |
 
> Note: `local.settings.json` (containing connection strings/keys) and the `.pbix` Power BI file are excluded from this repo for security and size reasons. Dashboard screenshots are included below instead.
 
## Dashboard
 
<img width="1277" height="712" alt="Dashboard" src="https://github.com/user-attachments/assets/be60dfcd-3a12-4b33-8d67-d288ede622a6" />

 
## What I'd Improve Next
 
- Add historical backfill for cost data older than the ingestion start date
- Support multiple subscriptions/resource groups with configurable filters
- Move `local.settings.json` secrets to Azure Key Vault for production-grade secret management
- Publish the Power BI report to Power BI Service for shareable web access
## Author
 
Jitesh Shivanand Bagale 
 
