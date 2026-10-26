"""Environment validator for the FAERS project.

Checks Python version, ODBC Driver 18 availability, and SQL Server
connectivity using the connection string from .env (falling back to
.env.example). The probe always targets the master database so it works
before the faers database itself exists.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
EXAMPLE_FILE = ROOT / ".env.example"


def check_python() -> bool:
    ok = sys.version_info >= (3, 11)
    print(f"Python: {sys.version.split()[0]} (need >=3.11) -> {'OK' if ok else 'FAIL'}")
    return ok


def check_odbc() -> bool:
    try:
        import pyodbc  # type: ignore
    except ImportError:
        print("pyodbc import: FAIL (install via requirements.txt)")
        return False

    drivers = list(pyodbc.drivers())
    has_18 = any("ODBC Driver 18 for SQL Server" in d for d in drivers)
    print(f"pyodbc: OK; drivers={drivers}")
    print(f"ODBC Driver 18 for SQL Server: {'OK' if has_18 else 'FAIL'}")
    return has_18


def read_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def read_env() -> dict[str, str]:
    """Prefer .env, fall back to .env.example so the check works pre-setup."""
    return read_env_file(ENV_FILE) or read_env_file(EXAMPLE_FILE)


def probe_sqlserver(conn_str: str) -> bool:
    try:
        import pyodbc  # type: ignore
    except ImportError:
        print("SQL Server: SKIP (pyodbc unavailable)")
        return False

    # Always probe master: the faers database may not exist yet.
    probe = re.sub(r"(?i)Database=[^;]+", "Database=master", conn_str)
    if "Encrypt=" not in probe:
        probe += ";Encrypt=No"

    try:
        with pyodbc.connect(probe, timeout=5) as conn:
            cur = conn.execute(
                "SELECT @@VERSION AS v, "
                "SERVERPROPERTY(N'Edition') AS edition, "
                "SERVERPROPERTY(N'InstanceName') AS inst"
            )
            row = cur.fetchone()
            print(f"SQL Server connection: OK")
            print(f"  version  : {row.v.splitlines()[0]}")
            print(f"  edition  : {row.edition}")
            print(f"  instance : {row.inst or '(default)'}")
            print(f"  probe    : {probe}")
            return True
    except Exception as exc:  # noqa: BLE001
        print(f"SQL Server connection: FAIL -> {exc!r}")
        return False


def check_sqlserver() -> bool:
    env = read_env()
    conn_str = env.get("SQLSERVER_CONNECTION")
    if not conn_str:
        print("SQL Server: SKIP (no SQLSERVER_CONNECTION in .env or .env.example)")
        return False
    return probe_sqlserver(conn_str)


def main() -> int:
    print(f"Project root: {ROOT}")
    ok = check_python() and check_odbc() and check_sqlserver()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())