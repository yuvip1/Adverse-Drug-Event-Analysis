from __future__ import annotations

import os
from collections.abc import Sequence

import pandas as pd
import pyodbc
from dotenv import load_dotenv

# The top-drug aggregate can take several seconds on the warehouse because it
# deduplicates report-level drug rows before grouping. Keep a bounded timeout
# that allows the complete overview request to finish without hanging forever.
DEFAULT_QUERY_TIMEOUT_SECONDS = 120


def get_connection(
    *,
    connection_string: str | None = None,
    timeout_seconds: int = DEFAULT_QUERY_TIMEOUT_SECONDS,
) -> pyodbc.Connection:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if connection_string is None:
        load_dotenv()
        connection_string = os.environ.get("SQLSERVER_CONNECTION")
    if not connection_string:
        raise RuntimeError("SQLSERVER_CONNECTION is not configured")
    connection = pyodbc.connect(connection_string, timeout=timeout_seconds)
    connection.timeout = timeout_seconds
    return connection


def fetch_dataframe(
    sql: str,
    params: Sequence[object] = (),
    *,
    timeout_seconds: int = DEFAULT_QUERY_TIMEOUT_SECONDS,
) -> pd.DataFrame:
    """Execute one parameterized SELECT and return its rows as a DataFrame."""
    with get_connection(timeout_seconds=timeout_seconds) as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(sql, tuple(params))
            columns = [column[0] for column in cursor.description or ()]
            return pd.DataFrame.from_records(cursor.fetchall(), columns=columns)
        finally:
            cursor.close()
