"""Minimal SQL Server connectivity probe (Windows Authentication).

Run: .venv/Scripts/python sql/test_connection.py
"""
import pyodbc

CONN_STR = (
    "Driver={ODBC Driver 18 for SQL Server};"
    "Server=localhost;"
    "Database=master;"
    "Trusted_Connection=yes;"
    "Encrypt=No"
)

with pyodbc.connect(CONN_STR, timeout=5) as conn:
    cur = conn.execute(
        "SELECT @@VERSION AS v, "
        "SERVERPROPERTY(N'Edition') AS edition, "
        "SERVERPROPERTY(N'InstanceName') AS inst"
    )
    row = cur.fetchone()
    print("version :", row.v.splitlines()[0])
    print("edition :", row.edition)
    print("instance:", row.inst)

    cur = conn.execute("SELECT COUNT(*) AS dbs FROM sys.databases")
    print("databases:", cur.fetchone().dbs)
    print("CONNECTION OK")