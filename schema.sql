-- Run this in the Azure SQL Database Query editor (or via SSMS/Azure Data Studio)
-- before deploying the function.

CREATE TABLE CostData (
    Id              INT IDENTITY(1,1) PRIMARY KEY,
    UsageDate       DATE           NOT NULL,
    ResourceGroup   NVARCHAR(200)  NOT NULL,
    ServiceName     NVARCHAR(200)  NOT NULL,
    MeterCategory   NVARCHAR(200)  NOT NULL,
    Cost            DECIMAL(18,4)  NOT NULL,
    Currency        NVARCHAR(10)   NOT NULL,
    IngestedAt      DATETIME2      NOT NULL
);

-- Speeds up date-range queries from Power BI
CREATE INDEX IX_CostData_UsageDate ON CostData (UsageDate);
CREATE INDEX IX_CostData_ResourceGroup ON CostData (ResourceGroup);

-- Convenience view: daily total spend across all resource groups/services
CREATE VIEW vw_DailyTotalCost AS
SELECT
    UsageDate,
    SUM(Cost) AS TotalCost,
    MAX(Currency) AS Currency
FROM CostData
GROUP BY UsageDate;

-- Convenience view: month-to-date spend by resource group
CREATE VIEW vw_MonthToDateByResourceGroup AS
SELECT
    ResourceGroup,
    SUM(Cost) AS TotalCost
FROM CostData
WHERE UsageDate >= DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)
GROUP BY ResourceGroup;

-- Convenience view: top services by cost, last 30 days
CREATE VIEW vw_Top30DayServices AS
SELECT
    ServiceName,
    SUM(Cost) AS TotalCost
FROM CostData
WHERE UsageDate >= DATEADD(DAY, -30, CAST(GETDATE() AS DATE))
GROUP BY ServiceName;
