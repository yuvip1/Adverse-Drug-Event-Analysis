# FAERS Adverse Drug Event Analysis

An MVP pharmacovigilance data pipeline and analytical framework for FDA Adverse
Event Reporting System (FAERS) data. The completed scope currently covers
setup, streaming ingestion, SQL Server staging and star-schema modeling,
cleaning and quality logging, SQL analysis, signal screening, forecasting,
seriousness classification, and interactive reporting.

The repository currently processes one 12,000-report sample file. API,
authentication, Docker, CI, and deployment remain out of scope.

## Architecture

The implemented data flow is:

```text
FAERS ZIP
  -> src/ingest.py
  -> SQL Server stg.* tables
  -> src/clean.py
  -> src/transform.py
  -> dbo.dim_* and dbo.fact_*
  -> sql/03_views.sql
  -> src/stats.py / src/pareto.py / src/cycle_time.py
  -> results/*.json and powerbi/data/*.csv
  -> Power BI Desktop
```

## Setup

Prerequisites:

- Windows and PowerShell
- Python 3.11 or newer
- SQL Server Developer Edition with Windows Authentication
- ODBC Driver 18 for SQL Server

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run tests with the same activated environment:

```powershell
python -m pytest
```

If the virtual environment is not activated, use its interpreter explicitly:

```powershell
.venv\Scripts\python.exe -m pytest
```

Create `.env` in the project root:

```env
SQLSERVER_CONNECTION="DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=faers;Trusted_Connection=yes;Encrypt=No"
```

Start the Streamlit application from the repository root. Use the persistent
sidebar to move between the reporting overview, signal explorer, forecasting,
and seriousness classification pages:

```powershell
streamlit run app.py
```

The page calls `services.analytics_service.get_reporting_summary()` and
`services.signal_service.explore_signals()`,
`services.forecast_service.forecast_reporting_volume()`, and
`services.classifier_service.classify_new_report()` and returns aggregate or
inference-only results. It does not run ingestion, transformation, model
training, batch signal generation, or write JSON artifacts. Classification
uses the persisted `results/model/seriousness_classifier.joblib` artifact and
does not write hypothetical reports to SQL Server.

## Pipeline

Create the database, staging tables, star schema, and views:

```powershell
python sql/run_ddl.py sql/01_create_database.sql
python sql/run_ddl.py sql/02_star_schema.sql
python sql/run_ddl.py sql/03_views.sql
python sql/run_ddl.py sql/04_signal_views.sql
```

Load and transform the compressed FAERS file:

```powershell
python src/ingest.py C:\path\to\drug-event-0001-of-0031.json.zip
python src/clean.py
python src/transform.py
```

Generate analytics, Power BI exports, and the Stage 7 report:

```powershell
python src/stats.py
python src/pareto.py
python src/cycle_time.py
python src/trend.py
python src/forecast.py
python src/signal_analysis.py --top-drugs 100 --min-pair-count 3
python src/ml_classifier.py
python src/export_powerbi.py
python src/build_metrics.py
```

`build_metrics.py` reads the generated JSON outputs and writes the authoritative
[`results/metrics.json`](results/metrics.json) plus
[`docs/RESULTS.md`](docs/RESULTS.md). The report is generated from pipeline
outputs rather than manually maintained figures.

## Power BI

- Follow [`powerbi/BUILD_GUIDE.md`](powerbi/BUILD_GUIDE.md) to create the report.
- Import [`powerbi/theme.json`](powerbi/theme.json) for the visual theme.
- Use [`powerbi/measures.dax`](powerbi/measures.dax) for measures.
- CSV exports are stored in [`powerbi/data/`](powerbi/data/).

## Current status and limitations

Stages 0 through 8 plus the Phase 1 reporting service, Phase 2 reporting page,
Phase 3 signal explorer, Phase 4 reporting-volume forecasting, and Phase 5
seriousness classification are complete or prepared: setup, ingestion/modeling,
cleaning and quality logging, SQL analysis, Power BI preparation, generated
results documentation, PRR/ROR signal screening, and seriousness classification
with local MLflow tracking. The current dataset is one 12,000-report
sample from a source set of 370,540 reports.

The current forecast compares seasonal naive, ETS, and SARIMA using rolling-origin
backtesting and produces 12-month prediction intervals. The latest observed
month is excluded from training as potentially incomplete. Signal, forecast,
classifier, reporting service, reporting page, signal explorer, forecasting
page, and persisted-model classification page are implemented; API,
authentication, Docker, CI, and deployment remain later roadmap work.
FAERS is a
spontaneous-reporting system, so report counts do not estimate incidence or
causality. Manufacturer and dosage-form outputs are product/reporting quality
analytics, not supply-chain or demand forecasts.

## Results

See [`docs/RESULTS.md`](docs/RESULTS.md) for the generated Stage 7 report and
[`results/metrics.json`](results/metrics.json) for machine-readable metrics.
The project map in [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md) records the
environment and implementation status.
