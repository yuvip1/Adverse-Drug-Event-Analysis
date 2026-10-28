"""Stage 7 monthly forecast comparison with rolling-origin backtesting.

The latest observed month is excluded from training by default because FAERS
reporting can be incomplete near the data extract boundary.
"""
from __future__ import annotations

import json
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX

ROOT = Path(__file__).resolve().parent.parent
TREND_PATH = ROOT / "results" / "trend.json"
OUT = ROOT / "results" / "forecast.json"
HORIZON = 12
BACKTEST_ORIGINS = 12
MIN_TRAIN = 36


@dataclass(frozen=True)
class ModelResult:
    predictions: list[float]
    residual_std: float


def _seasonal_naive(values: np.ndarray, horizon: int) -> ModelResult:
    if len(values) < 12:
        raise ValueError("Seasonal naive requires at least 12 observations")
    predictions = [float(values[-12 + i % 12]) for i in range(horizon)]
    residuals = values[12:] - values[:-12]
    return ModelResult(predictions, float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0)


def _ets(values: np.ndarray, horizon: int) -> ModelResult:
    if len(values) < 24:
        raise ValueError("ETS requires at least 24 observations")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ExponentialSmoothing(
            values, trend="add", seasonal="add", seasonal_periods=12, initialization_method="estimated"
        ).fit(optimized=True)
    residuals = np.asarray(fit.resid, dtype=float)
    return ModelResult(fit.forecast(horizon).tolist(), float(np.std(residuals, ddof=1)))


def _sarima(values: np.ndarray, horizon: int) -> ModelResult:
    if len(values) < 36:
        raise ValueError("SARIMA requires at least 36 observations")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = SARIMAX(
            values,
            order=(1, 1, 1),
            seasonal_order=(1, 0, 1, 12),
            enforce_stationarity=False,
            enforce_invertibility=False,
        ).fit(disp=False)
    residuals = np.asarray(fit.resid, dtype=float)
    return ModelResult(fit.forecast(horizon).tolist(), float(np.std(residuals, ddof=1)))


MODELS: dict[str, Callable[[np.ndarray, int], ModelResult]] = {
    "seasonal_naive": _seasonal_naive,
    "ets": _ets,
    "sarima": _sarima,
}


def _smape(actual: np.ndarray, predicted: np.ndarray) -> float:
    denominator = np.abs(actual) + np.abs(predicted)
    values = np.divide(2 * np.abs(actual - predicted), denominator, out=np.zeros_like(actual), where=denominator != 0)
    return float(np.mean(values) * 100)


def _metrics(actual: list[float], predicted: list[float]) -> dict[str, float]:
    observed = np.asarray(actual, dtype=float)
    forecast = np.asarray(predicted, dtype=float)
    errors = observed - forecast
    return {
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "smape": _smape(observed, forecast),
    }


def _backtest(values: np.ndarray, model: Callable[[np.ndarray, int], ModelResult]) -> dict[str, float]:
    start = max(MIN_TRAIN, len(values) - BACKTEST_ORIGINS)
    actual: list[float] = []
    predicted: list[float] = []
    for origin in range(start, len(values)):
        try:
            result = model(values[:origin], 1)
        except (ValueError, np.linalg.LinAlgError):
            continue
        actual.append(float(values[origin]))
        predicted.append(max(0.0, result.predictions[0]))
    if not actual:
        raise ValueError("No successful rolling-origin backtest folds")
    return {"folds": len(actual), **_metrics(actual, predicted)}


def _next_month(year: int, month: int, steps: int) -> tuple[int, int]:
    index = year * 12 + month - 1 + steps
    return index // 12, index % 12 + 1


def _month_label(year: int, month: int, steps: int) -> str:
    next_year, next_month = _next_month(year, month, steps)
    return f"{next_year}-{next_month:02d}"


def _forecast_series(
    values: list[int],
    label: str,
    cutoff_label: str,
    horizon: int = HORIZON,
) -> dict:
    array = np.asarray(values, dtype=float)
    backtests: dict[str, dict[str, float] | dict[str, str]] = {}
    successful: dict[str, dict[str, float]] = {}
    for name, model in MODELS.items():
        try:
            result = _backtest(array, model)
            backtests[name] = result
            successful[name] = result
        except (ValueError, np.linalg.LinAlgError) as error:
            backtests[name] = {"error": str(error)}
    if not successful:
        raise RuntimeError(f"No forecast model succeeded for {label}")
    selected_name = min(successful, key=lambda name: (successful[name]["mae"], successful[name]["rmse"]))
    selected = MODELS[selected_name](array, horizon)
    return {
        "series": label,
        "training_cutoff": cutoff_label,
        "selected_model": selected_name,
        "backtest": backtests,
        "forecast": [
            {
                "year_month": month,
                "predicted_count": round(max(0.0, prediction), 2                ),
                "lower_95": round(max(0.0, prediction - 1.96 * selected.residual_std), 2),
                "upper_95": round(max(0.0, prediction + 1.96 * selected.residual_std), 2),
            }
            for prediction, month in zip(
                selected.predictions,
                [_month_label(*map(int, cutoff_label.split("-")), step) for step in range(1, HORIZON + 1)],
            )
        ],
    }


def main() -> None:
    trend = json.loads(TREND_PATH.read_text(encoding="utf-8"))
    monthly = trend["monthly_series"]
    if len(monthly) <= 1:
        raise ValueError("At least two monthly observations are required")
    training = monthly[:-1]
    cutoff_label = f"{training[-1]['year']}-{training[-1]['month']:02d}"
    total = [row["total_count"] for row in training]
    serious = [row["serious_count"] for row in training]
    output = {
        "method": "rolling-origin comparison of seasonal naive, ETS, and SARIMA",
        "latest_observed_month": f"{monthly[-1]['year']}-{monthly[-1]['month']:02d}",
        "excluded_latest_month_as_potentially_incomplete": True,
        "horizon_months": HORIZON,
        "backtest_origins": BACKTEST_ORIGINS,
        "total": _forecast_series(total, "total_reports", cutoff_label),
        "serious": _forecast_series(serious, "serious_reports", cutoff_label),
    }
    OUT.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"forecast.py: total={output['total']['selected_model']}, serious={output['serious']['selected_model']}")


if __name__ == "__main__":
    main()
