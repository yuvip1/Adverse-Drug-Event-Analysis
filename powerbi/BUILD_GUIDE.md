# Power BI Build Guide & DAX Measures Template

This guide outlines how to build the Power BI Desktop report package (`powerbi/faers_analytics.pbix`) from the SQL Server star schema and Stage 3 analytical views.

---

## 1. Connection Setup
1. Open Power BI Desktop.
2. Select **Get Data** -> **SQL Server database**.
3. **Server:** `localhost` (or your SQL Server instance).
4. **Database:** `faers`.
5. **Data Connectivity mode:** **Import**.
6. **Authentication:** Windows Authentication (integrated security).

---

## 2. Tables & Views to Import
Import the following tables and views from the `faers` database:
- **Dimensions:** `dbo.dim_date`, `dbo.dim_country`, `dbo.dim_age_group`, `dbo.dim_drug`, `dbo.dim_reaction`, `dbo.dim_reporter`
- **Facts:** `dbo.fact_report`, `dbo.fact_drug`, `dbo.fact_reaction`
- **Analytical Views (Stage 3):**
  - `dbo.vw_top_drugs`
  - `dbo.vw_top_reactions`
  - `dbo.vw_serious_by_age`
  - `dbo.vw_serious_by_sex`
  - `dbo.vw_serious_by_country`
  - `dbo.vw_serious_by_reporter`
  - `dbo.vw_outcomes`
  - `dbo.vw_manufacturer_quality`
  - `dbo.vw_dosage_route_quality`

---

## 3. Relationships Model
- `fact_report[date_key]` -> `dim_date[date_key]` (Active)
- `fact_report[receipt_date_key]` -> `dim_date[date_key]` (Inactive - use USERELATIONSHIP for receipt date lag)
- `fact_report[country_key]` -> `dim_country[country_key]` (Active)
- `fact_report[age_group_key]` -> `dim_age_group[age_group_key]` (Active)
- `fact_report[reporter_key]` -> `dim_reporter[reporter_key]` (Active)
- `fact_drug[report_key]` -> `fact_report[report_key]` (Active, One-to-Many)
- `fact_drug[drug_key_dim]` -> `dim_drug[drug_key]` (Active, Many-to-One)
- `fact_reaction[report_key]` -> `fact_report[report_key]` (Active, One-to-Many)
- `fact_reaction[reaction_key_dim]` -> `dim_reaction[reaction_key]` (Active, Many-to-One)

---

## 4. DAX Measures Template

Create a dedicated measure table named `_Measures` and add the following DAX calculations:

```dax
// Total Report Count
Total Reports = COUNTROWS(fact_report)

// Total Serious Reports
Serious Reports = CALCULATE(COUNTROWS(fact_report), fact_report[is_serious] = 1)

// Serious Rate (%)
Serious Rate % = DIVIDE([Serious Reports], [Total Reports], 0) * 100

// Suspect Drug Report Count
Suspect Drug Reports = CALCULATE(COUNTROWS(fact_drug), fact_drug[is_suspect] = 1)

// YoY Report Count Growth
Reports PY = CALCULATE([Total Reports], SAMEPERIODLASTYEAR(dim_date[full_date]))

Reports YoY Growth % = DIVIDE([Total Reports] - [Reports PY], [Reports PY], 0) * 100
```

---

## 5. Report Pages
1. **Overview:** KPI cards (Total Reports, Serious Rate %), monthly trend line chart, top countries bar chart.
2. **Drugs and Reactions:** Top suspect drugs and MedDRA preferred terms with serious rate highlights.
3. **Demographics:** Serious rate breakdown by age group, sex, and reporter qualification.
4. **Safety Signals:** Placeholder page for Phase B statistical signal scores (PRR/ROR).
5. **Product & Manufacturer Quality:** Manufacturer volume and seriousness distribution, dosage form x route quality heatmap.
6. **Data Quality:** Quarantine logs, missingness breakdown, and version deduplication metrics.

---

## 6. Theme Application
Apply the custom color palette and typography using **View** -> **Themes** -> **Browse for themes** and select `powerbi/theme.json`.
