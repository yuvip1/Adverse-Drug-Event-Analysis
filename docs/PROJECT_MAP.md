# Project Map

## Overview
FAERS-Adverse-Drug-Event-Analysis – a portfolio project demonstrating end‑to‑end data engineering, analytics, forecasting, ML, and a FastAPI‑Streamlit stack on a Windows environment with SQL Server.

## Folder structure
- `src/` – Python modules (initially a small environment‑check script).
- `sql/` – DDL scripts for staging and star schema tables.
- `tests/` – pytest unit and integration tests (yet to be implemented).
- `docs/` – Project documentation, data dictionaries, quality metrics, and the project map.
- `results/` – JSON metrics and output files.
- `powerbi/` – Power BI build guide and DAX measures template.
- `data/` – Raw & processed FAERS data files (ignored by git).

## Environment status (verified 2026-10-26)
- Python 3.14.7 – OK (>=3.11 required).
- Virtual environment `.venv/` (Python 3.14.7) with deps: `pyodbc 5.3.0`, `SQLAlchemy 2.1.6`, `python-dotenv 1.2.4`, `pandas 3.1.0`, `numpy 2.5.4`, `pytest 9.1.1`, `ruff 0.17.2`, `ijson 3.6.0`.
- ODBC Driver 18 for SQL Server – **INSTALLED** (visible to both 32‑bit and 64‑bit; confirmed by `pyodbc.drivers()`).
- SQL Server 2025 Developer Edition – **RUNNING** as default instance `MSSQLSERVER` (service name `MSSQLSERVER`).
  - `SERVERPROPERTY('Edition')` = `Standard Developer Edition (64-bit)`.
  - Python → SQL Server probe: **OK** (see `sql/test_connection.py`).
- Connection string in `.env`: `Driver={ODBC Driver 18 for SQL Server};Server=localhost;Database=faers;Trusted_Connection=yes;Encrypt=No`
  - `Encrypt=No` is required because the local dev instance uses a self‑signed certificate.
  - Docker mode (Linux container) uses SQL auth: `UID=sa;PWD=...;Encrypt=Yes;TrustServerCertificate=yes`.
- Disk: ~190 GB free on C:.

## Data file
- `C:/Users/yuvra/Downloads/drug-event-0001-of-0031.json.zip` (209.6 MB compressed → 1.04 GB raw)
- Single file inside: `drug-event-0001-of-0031.json`
- Streaming parse (`ijson`) counted **12,000 records** in this file.
- `meta.results.total = 370,540` – this file is a **sample (first 12k of 370,540)**.

## Next steps
1. Confirm scope: proceed with the 12k sample (default) or download the full 31‑part dataset.
2. Create the `faers` database and staging/star‑schema DDL (Stage 1).
3. Stream‑parse the JSON and bulk‑load into staging tables.