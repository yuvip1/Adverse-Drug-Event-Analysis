from datetime import date

import pandas as pd
import pytest

from services.signal_service import explore_signals


def _candidate_fetcher(sql: str, params: list[object]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "drug_key": 1,
            "reaction_key": 2,
            "drug_name": "ASPIRIN",
            "reaction": "HEADACHE",
            "pair_count": 10,
            "drug_total": 20,
            "reaction_total": 50,
            "total_reports": 1000,
        }
    ])


def test_signal_service_reuses_calculation_and_returns_aggregate_metrics():
    result = explore_signals(fetcher=_candidate_fetcher)

    signal = result["signals"][0]
    assert result["candidate_count"] == 1
    assert result["signal_count"] == 1
    assert signal["pair_count"] == 10
    assert signal["prr"] == pytest.approx(12.25)
    assert signal["ror"] == pytest.approx(23.5)
    assert signal["chi_square"] == pytest.approx(77.6047261, rel=1e-6)
    assert "report_key" not in str(result)
    assert "drug_key" not in signal
    assert "reaction_key" not in signal


def test_signal_service_parameterizes_filters_and_limit():
    calls: list[tuple[str, list[object]]] = []

    def recording_fetcher(sql: str, params: list[object]) -> pd.DataFrame:
        calls.append((sql, params))
        return _candidate_fetcher(sql, params)

    explore_signals(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 2, 29),
        drug_name=" aspirin ",
        reaction_name=" headache ",
        country_code="us",
        serious_only=True,
        min_pair_count=5,
        limit=25,
        fetcher=recording_fetcher,
    )

    sql, params = calls[0]
    assert "ASPIRIN" not in sql
    assert "HEADACHE" not in sql
    assert "US" not in sql
    assert params == [
        date(2024, 1, 1),
        date(2024, 2, 29),
        "US",
        25,
        5,
        "ASPIRIN",
        "HEADACHE",
    ]
    assert "?" in sql
    assert "fr.is_serious = 1" in sql


def test_signal_service_handles_empty_results():
    def empty_fetcher(sql: str, params: list[object]) -> pd.DataFrame:
        return pd.DataFrame()

    result = explore_signals(fetcher=empty_fetcher)

    assert result["candidate_count"] == 0
    assert result["signal_count"] == 0
    assert result["signals"] == []


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"start_date": date(2025, 1, 1), "end_date": date(2024, 1, 1)}, "start_date"),
        ({"min_pair_count": 0}, "min_pair_count"),
        ({"min_prr": -1}, "min_prr"),
        ({"min_chi_square": -1}, "min_chi_square"),
        ({"limit": 0}, "limit"),
        ({"country_code": "USA"}, "country_code"),
    ],
)
def test_signal_service_rejects_invalid_filters(kwargs, message):
    with pytest.raises((ValueError, TypeError), match=message):
        explore_signals(fetcher=_candidate_fetcher, **kwargs)
