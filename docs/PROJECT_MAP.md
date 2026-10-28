# Project Map

## Overview

This repository is an MVP FAERS analytics pipeline on Windows and SQL Server.
Stages 0 through 8 are complete or prepared: ingestion, modeling, cleaning,
SQL analysis, Power BI preparation, generated results documentation, signal
screening, rolling-origin forecasting, and seriousness classification. Later
API, Docker, and CI stages remain planned.

## Data flow

```text
FAERS ZIP
  -> src/ingest.py
  -> stg.reports / stg.drugs / stg.reactions
  -> src/clean.py
  -> src/transform.py
  -> dbo.dim_* / dbo.fact_*
  -> sql/03_views.sql
  -> src/stats.py, pareto.py, cycle_time.py, trend.py, forecast.py
  -> results/*.json
  -> src/signal_analysis.py -> results/signals.json
  -> src/ml_classifier.py -> results/ml_metrics.json, results/model/,
     results/mlflow.db
  -> src/build_metrics.py
  -> results/metrics.json and docs/RESULTS.md
  -> powerbi/data/*.csv -> Power BI Desktop
  -> services/analytics_service.py -> reporting aggregates
  -> services/signal_service.py -> filtered aggregate signal metrics
  -> services/forecast_service.py -> read-only monthly history and forecasts
  -> services/classifier_service.py -> persisted-model report inference
  -> app.py -> Streamlit reporting, signal, forecasting, and classifier pages
```

## Important files

- `src/ingest.py` – streams JSON from a ZIP and bulk-loads the staging tables.
- `src/clean.py` – validates dates, cleans age/weight, removes older versions,
  writes quarantine rows, and logs quality checks.
- `src/transform.py` – creates dimensions and facts from staging data.
- `src/stats.py` – writes summary counts to `results/stats.json`.
- `src/pareto.py` – writes 80/20 tables to `results/pareto.json`.
- `src/cycle_time.py` – writes date-lag metrics to `results/cycle_time.json`.
- `src/trend.py` and `src/forecast.py` – write complete total/serious monthly
  series and compare seasonal-naive, ETS, and SARIMA forecasts.
- `src/signal_analysis.py` – calculates PRR, ROR, confidence intervals, and
  Yates-corrected chi-square for screened drug-reaction pairs.
- `src/ml_classifier.py` – extracts report-level features, trains/evaluates
  classifiers, logs MLflow runs locally, and saves the selected model.
- `src/export_powerbi.py` – exports SQL tables/views to `powerbi/data/`.
- `src/build_metrics.py` – combines analytical JSON outputs into the
  authoritative `results/metrics.json` and generated `docs/RESULTS.md`.
- `services/db.py` – executes parameterized SQL Server SELECT queries with
  timeouts and reliable connection cleanup.
- `services/analytics_service.py` – applies receivedate-based filters and
  returns report-grain aggregate analytics without report identifiers.
- `services/signal_service.py` – builds one filtered report population,
  derives distinct drug/reaction contingency counts, and reuses
  `calculate_signal()` without writing batch artifacts.
- `services/forecast_service.py` – queries bounded monthly report aggregates,
  fills missing months, and reuses Stage 7 model comparison and backtesting.
- `services/classifier_service.py` – validates and caches the persisted Stage 8
  pipeline, derives its fitted categorical contract, prepares exact
  hypothetical-report features, and returns in-memory predictions.
- `app.py` – Phase 2 reporting analytics, Phase 3 signal explorer, Phase 4
  reporting-volume forecasting, and Phase 5 seriousness classification; calls
  the service layer and displays aggregate or inference-only results.
- `sql/01_create_database.sql` – database and staging DDL.
- `sql/02_star_schema.sql` – dimensions, facts, keys, and indexes.
- `sql/03_views.sql` – Stage 3 analytical views.
- `sql/04_signal_views.sql` – report-level suspect drug/reaction pair counts
  for Stage 6.
- `powerbi/BUILD_GUIDE.md` – manual Power BI Desktop construction guide.
- `tests/` – focused tests for signal calculations, forecasting helpers,
  classifier helpers, database cleanup, reporting-service aggregation, and
  interactive signal filtering.

## Environment status

Verified 2026-10-26:

- Python 3.14.7 and the project virtual environment are available.
- ODBC Driver 18 for SQL Server is installed.
- SQL Server 2025 Developer Edition is running as the default instance.
- Python-to-SQL Server connectivity was verified with `sql/test_connection.py`.

## Dataset scope

- Input: `C:\Users\yuvra\Downloads\drug-event-0001-of-0031.json.zip`
- The ZIP contains one JSON file with 12,000 records.
- `meta.results.total` reports 370,540 records in the complete source set.
- Current results describe the 12,000-record sample, not all 31 files.

## Current next steps

1. Add the later API, Streamlit, Docker, CI, and broader test stages.
