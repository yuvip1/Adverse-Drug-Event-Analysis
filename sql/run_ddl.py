"""Run a T-SQL DDL script against SQL Server.

The script is split on GO batches. The faers database is created first,
so the rest of the script runs inside faers.

Usage: .venv/Scripts/python sql/run_ddl.py sql/01_create_database.sql
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pyodbc

ROOT = Path(__file__).resolve().parent.parent
CONN_STR = os.environ.get(
    "SQLSERVER_CONNECTION",
    "Driver={ODBC Driver 18 for SQL Server};Server=localhost;Database=master;"
    "Trusted_Connection=yes;Encrypt=No",
)


def _split_batches(sql: str) -> list[str]:
    """Split a T-SQL script on GO batch separators (case-insensitive, on its own line)."""
    return [b for b in sql.split("\nGO") if b.strip()]


def run_ddl(script_path: Path) -> None:
    batches = _split_batches(script_path.read_text(encoding="utf-8"))
    with pyodbc.connect(CONN_STR, timeout=30) as conn:
        cur = conn.cursor()
        # CREATE DATABASE cannot run inside an open transaction, so run the
        # first batch in autocommit mode, then switch back to explicit commits.
        conn.autocommit = True
        for batch in batches:
            stmt = batch.strip()
            if not stmt:
                continue
            cur.execute(stmt)
        conn.autocommit = False
        conn.commit()
        cur.execute(
            "SELECT TABLE_SCHEMA, TABLE_NAME "
            "FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA IN ('stg', 'dbo') "
            "ORDER BY TABLE_SCHEMA, TABLE_NAME"
        )
        print("Tables created:")
        for row in cur.fetchall():
            print(f"  {row.TABLE_SCHEMA}.{row.TABLE_NAME}")


if __name__ == "__main__":
    script = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "sql" / "01_create_database.sql"
    if not script.is_absolute():
        script = ROOT / script
    print(f"Running {script} ...")
    run_ddl(script)