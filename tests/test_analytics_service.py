from datetime import date
from unittest.mock import Mock

import pandas as pd
import pytest

from services.analytics_service import get_reporting_summary


def _fetcher(sql: str, params: list[object]) -> pd.DataFrame:
    if "COALESCE(SUM(CAST(is_serious AS INT)), 0)" in sql and "GROUP BY" not in sql:
        return pd.DataFrame([{"report_count": 4, "serious_count": 2}])
    if "GROUP BY year, month" in sql:
        return pd.DataFrame([
            {"year": 2024, "month": 1, "report_count": 3, "serious_count": 1},
            {"year": 2024, "month": 2, "report_count": 1, "serious_count": 1},
        ])
    if "drug.drug_name" in sql:
        return pd.DataFrame([{"drug_name": "ASPIRIN", "report_count": 3, "serious_count": 2}])
    return pd.DataFrame([{"reaction": "HEADACHE", "report_count": 2, "serious_count": 1}])


def test_no_filters_returns_aggregate_structure():
    result = get_reporting_summary(fetcher=_fetcher)

    assert result["summary"] == {
        "report_count": 4,
        "serious_count": 2,
        "serious_pct": 50.0,
    }
    assert result["monthly_series"][0]["report_count"] == 3
    assert result["top_drugs"][0]["serious_pct"] == pytest.approx(66.67)
    assert result["top_reactions"][0]["reaction"] == "HEADACHE"
    assert "report_key" not in str(result)
    assert "safetyreportid" not in str(result)


def test_filters_are_parameterized_and_normalized():
    calls: list[tuple[str, list[object]]] = []

    def recording_fetcher(sql: str, params: list[object]) -> pd.DataFrame:
        calls.append((sql, params))
        return _fetcher(sql, params)

    get_reporting_summary(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 2, 29),
        drug_name=" aspirin ",
        reaction_name=" headache ",
        country_code="us",
        serious_only=True,
        limit=25,
        fetcher=recording_fetcher,
    )

    assert len(calls) == 4
    for sql, params in calls:
        assert "ASPIRIN" not in sql
        assert "HEADACHE" not in sql
        assert "US" not in sql
        assert date(2024, 1, 1) in params
        assert date(2024, 2, 29) in params
        assert "ASPIRIN" in params
        assert "HEADACHE" in params
        assert "US" in params
    expected_filters = [
        date(2024, 1, 1),
        date(2024, 2, 29),
        "US",
        "ASPIRIN",
        "HEADACHE",
    ]
    assert calls[2][1] == [*expected_filters, 25]
    assert calls[3][1] == [*expected_filters, 25]


def test_top_query_parameters_match_placeholder_order_without_filters():
    calls: list[tuple[str, list[object]]] = []

    def recording_fetcher(sql: str, params: list[object]) -> pd.DataFrame:
        calls.append((sql, params))
        return _fetcher(sql, params)

    get_reporting_summary(limit=7, fetcher=recording_fetcher)

    assert "SELECT TOP (?) drug.drug_name" in calls[2][0]
    assert "SELECT TOP (?) reaction.reaction_meddra_apt" in calls[3][0]
    assert calls[2][1] == [7]
    assert calls[3][1] == [7]
    assert "?" in calls[2][0]
    assert "?" in calls[3][0]


def test_empty_results_are_safe():
    def empty_fetcher(sql: str, params: list[object]) -> pd.DataFrame:
        if "COALESCE(SUM(CAST(is_serious AS INT)), 0)" in sql and "GROUP BY" not in sql:
            return pd.DataFrame([{"report_count": 0, "serious_count": 0}])
        return pd.DataFrame()

    result = get_reporting_summary(fetcher=empty_fetcher)

    assert result["summary"]["report_count"] == 0
    assert result["summary"]["serious_count"] == 0
    assert result["summary"]["serious_pct"] is None
    assert result["monthly_series"] == []
    assert result["top_drugs"] == []
    assert result["top_reactions"] == []


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"start_date": date(2025, 1, 1), "end_date": date(2024, 1, 1)}, "start_date"),
        ({"limit": 0}, "limit"),
        ({"limit": 1001}, "limit"),
        ({"country_code": "USA"}, "country_code"),
    ],
)
def test_invalid_inputs_are_rejected(kwargs, message):
    with pytest.raises((ValueError, TypeError), match=message):
        get_reporting_summary(fetcher=Mock(), **kwargs)


def test_serious_filter_is_part_of_query_not_post_processing():
    calls: list[tuple[str, list[object]]] = []

    def recording_fetcher(sql: str, params: list[object]) -> pd.DataFrame:
        calls.append((sql, params))
        return _fetcher(sql, params)

    get_reporting_summary(serious_only=True, fetcher=recording_fetcher)

    assert all("fr.is_serious = 1" in sql for sql, _ in calls)
