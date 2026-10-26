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

## Environment status (as of 2026-10-26)
- Python: 3.14.7 – OK (>=3.11 required).
- Virtual environment: `.venv/` created; dependencies installed (`pyodbc`, `SQLAlchemy`, `python-dotenv`, `pandas`, `numpy`, `pytest`, `ruff`, `ijson`).
- ODBC Driver 18 for SQL Server: **NOT INSTALLED** – free download from Microsoft.
- SQL Server Developer Edition: **NOT INSTALLED** – free download from Microsoft (install with Windows Authentication).
- Local SQL Server service: **NOT FOUND** (only MySQL80 / MySQL267 present).
- Compressed FAERS file: `C:/Users/yuvra/Downloads/drug-event-0001-of-0031.json.zip`
  - Single file inside: `drug-event-0001-of-0031.json` (1.04 GB raw, 209.6 MB compressed).
  - Streaming parse (ijson) counted **12,000 records** in this file.
  - `meta.results.total = 370,540` – this file is a **sample (first 12k of 370,540)**.

## Next steps
1. Install ODBC Driver 18 and SQL Server Developer Edition (free).
2. Confirm whether the full 370,540‑report dataset is available (or proceed with the 12k sample).
3. Begin ingestion plumbing (Stage 1).
