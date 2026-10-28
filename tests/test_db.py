from unittest.mock import Mock, patch

import pytest

from services.db import (
    DEFAULT_QUERY_TIMEOUT_SECONDS,
    fetch_dataframe,
    get_connection,
)


def test_default_query_timeout_allows_complete_overview_aggregation():
    assert DEFAULT_QUERY_TIMEOUT_SECONDS == 120


def test_fetch_dataframe_passes_parameters_and_closes_cursor():
    cursor = Mock(spec=["description", "fetchall", "execute", "close"])
    cursor.description = [("report_count",)]
    cursor.fetchall.return_value = [(2,)]
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=None)
    connection.cursor.return_value = cursor

    with patch("services.db.get_connection", return_value=connection) as factory:
        result = fetch_dataframe("SELECT ? AS report_count", [2], timeout_seconds=7)

    factory.assert_called_once_with(timeout_seconds=7)
    cursor.execute.assert_called_once_with("SELECT ? AS report_count", (2,))
    assert not hasattr(cursor, "timeout")
    cursor.close.assert_called_once_with()
    assert result.to_dict(orient="records") == [{"report_count": 2}]


def test_fetch_dataframe_closes_cursor_when_query_fails():
    cursor = Mock()
    cursor.description = []
    cursor.execute.side_effect = RuntimeError("query failed")
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=None)
    connection.cursor.return_value = cursor

    with patch("services.db.get_connection", return_value=connection), pytest.raises(
        RuntimeError, match="query failed"
    ):
        fetch_dataframe("SELECT 1")

    cursor.close.assert_called_once_with()


def test_get_connection_rejects_missing_configuration():
    with (
        patch("services.db.load_dotenv"),
        patch.dict("os.environ", {}, clear=True),
        pytest.raises(RuntimeError, match="SQLSERVER_CONNECTION"),
    ):
        get_connection()


def test_get_connection_configures_timeout_on_connection():
    connection = Mock()

    with patch("services.db.pyodbc.connect", return_value=connection) as connect:
        result = get_connection(
            connection_string="DRIVER=test;SERVER=test",
            timeout_seconds=11,
        )

    connect.assert_called_once_with(
        "DRIVER=test;SERVER=test",
        timeout=11,
    )
    assert result is connection
    assert connection.timeout == 11
