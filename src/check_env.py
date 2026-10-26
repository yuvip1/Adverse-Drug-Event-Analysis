"""Environment validator for the FAERS project.

Checks Python version, ODBC Driver 18 availability, and SQL Server
connectivity using the connection string from .env.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"


def check_python() -> bool:
    ok = sys.version_info >= (3, 11)
    print(f"Python: {sys.version.split()[0]} (need >=3.11) -> {'OK' if ok else 'FAIL'}")
    return ok


def check_odbc() -> bool:
    try:
        import pyodbc  # type: ignore
    except ImportError as exc:
        print("pyodbc import: FAIL (install via requirements.txt)")
        return False

    drivers = list(pyodbc.drivers())
    has_18 = any("ODBC Driver 18 for SQL Server" in d for d in drivers)
    print(f"pyodbc: OK; drivers={drivers}")
    print(f"ODBC Driver 18 for SQL Server: {'OK' if has_18 else 'FAIL'}")
    return has_18


def read_env() -> dict[str, Any]:
    env: dict[str, Any] = {}
    if not ENV_FILE.exists():
        return env
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def check_sqlserver() -> bool:
    env = read_env()
    conn_str = env.get("SQLSERVER_CONNECTION")
    if not conn_str:
        print("SQL Server: SKIP (no SQLSERVER_CONNECTION in .env)")
        return False
    try:
        import pyodbc  # type: ignore
    except ImportError:
        print("SQL Server: SKIP (pyodbc unavailable)")
        return False
    try:
        with pyodbc.connect(conn_str, timeout=5) as conn:
            cur = conn.execute("SELECT @@VERSION AS v")
            version = cur.fetchone().v
        print(f"SQL Server connection: OK -> {version.splitlines()[0]}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"SQL Server connection: FAIL -> {exc!r}")
        return False


def main() -> int:
    print(f"Project root: {ROOT}")
    ok = check_python() and check_odbc() and check_sqlserver()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())