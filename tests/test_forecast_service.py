from datetime import date

import pandas as pd
import pytest

from services import forecast_service


def _monthly_fetcher(sql: str, params: list[object]) -> pd.DataFrame:
    return pd.DataFrame([
        {"year": 2023, "month": 1, "total_count": 10, "serious_count": 2},
        {"year": 2024, "month": 1, "total_count": 12, "serious_count": 3},
    ])


def test_forecast_service_fills_missing_months_and_passes_query_parameters(
    monkeypatch,
):
    calls: list[tuple[str, list[object]]] = []

    def recording_fetcher(sql: str, params: list[object]) -> pd.DataFrame:
        calls.append((sql, params))
        return _monthly_fetcher(sql, params)

    def fake_forecast(values, label, cutoff_label, horizon):
        return {
            "series": label,
            "training_cutoff": cutoff_label,
            "selected_model": "seasonal_naive",
            "backtest": {"seasonal_naive": {"folds": 1, "mae": 1.0, "rmse": 1.0, "smape": 1.0}},
            "forecast": [
                {"year_month": "2023-04", "predicted_count": 1.0, "lower_95": 0.0, "upper_95": 2.0}
                for _ in range(horizon)
            ],
        }

    monkeypatch.setattr(forecast_service, "_forecast_series", fake_forecast)
    result = forecast_service.forecast_reporting_volume(
        start_date=date(2023, 1, 1),
        end_date=date(2023, 3, 31),
        country_code="us",
        horizon=2,
        fetcher=recording_fetcher,
    )

    assert calls[0][1] == [date(2023, 1, 1), date(2023, 3, 31), "US"]
    assert result["historical"][1]["total_count"] == 0
    assert len(result["historical"]) == 13
    assert result["horizon_months"] == 2
    assert result["total_reports"]["selected_model"] == "seasonal_naive"
    assert len(result["serious_reports"]["forecast"]) == 2


def test_forecast_service_rejects_invalid_horizon():
    with pytest.raises(ValueError, match="horizon"):
        forecast_service.forecast_reporting_volume(
            horizon=0,
            fetcher=_monthly_fetcher,
        )


def test_forecast_service_handles_insufficient_history():
    with pytest.raises(ValueError, match="At least two monthly observations"):
        forecast_service.forecast_reporting_volume(
            fetcher=lambda sql, params: pd.DataFrame([
                {"year": 2024, "month": 1, "total_count": 1, "serious_count": 0}
            ]),
        )


def test_forecast_service_requires_model_history():
    frame = pd.DataFrame([
        {"year": 2023, "month": month, "total_count": 10, "serious_count": 2}
        for month in range(1, 13)
    ])
    with pytest.raises(ValueError, match="monthly observations"):
        forecast_service.forecast_reporting_volume(
            fetcher=lambda sql, params: frame,
        )
