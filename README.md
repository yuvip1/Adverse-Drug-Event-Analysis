# FAERS Adverse Drug Event Analysis

An MVP pharmacovigilance data pipeline and analytical framework for FDA Adverse
Event Reporting System (FAERS) data. The completed scope currently covers setup,
streaming ingestion, SQL Server staging and star-schema modeling, cleaning and
quality logging, SQL analysis, Pareto/cycle-time analysis, and a Power BI
reporting package.

The repository currently processes one 12,000-report sample file. It does not
yet implement the later ML, API, Docker, CI, or validated forecasting stages.

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

Create `.env` in the project root:

```env
SQLSERVER_CONNECTION="DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=faers;Trusted_Connection=yes;Encrypt=No"
```

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
python src/signal.py --top-drugs 100 --min-pair-count 3
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

Stages 0 through 6 are complete or prepared: setup, ingestion/modeling,
cleaning and quality logging, SQL analysis, Power BI preparation, generated
results documentation, and PRR/ROR signal screening. The current dataset is one 12,000-report
sample from a source set of 370,540 reports.

The current forecast compares seasonal naive, ETS, and SARIMA using rolling-origin
backtesting and produces 12-month prediction intervals. The latest observed
month is excluded from training as potentially incomplete. ML, API, Streamlit,
Docker, CI, and broader automated tests remain later roadmap work. FAERS is a
spontaneous-reporting system, so report counts do not estimate incidence or
causality. Manufacturer and dosage-form outputs are product/reporting quality
analytics, not supply-chain or demand forecasts.

## Results

See [`docs/RESULTS.md`](docs/RESULTS.md) for the generated Stage 7 report and
[`results/metrics.json`](results/metrics.json) for machine-readable metrics.
The project map in [`docs/PROJECT_MAP.md`](docs/PROJECT_MAP.md) records the
environment and implementation status.
