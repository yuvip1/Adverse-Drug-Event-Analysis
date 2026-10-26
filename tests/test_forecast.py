import numpy as np
import pytest

from src.forecast import _metrics, _seasonal_naive


def test_metrics_calculate_mae_rmse_and_smape():
    metrics = _metrics([10, 20], [8, 24])

    assert metrics["mae"] == pytest.approx(3)
    assert metrics["rmse"] == pytest.approx(np.sqrt(10))
    assert metrics["smape"] == pytest.approx((2 * 2 / 18 + 2 * 4 / 44) / 2 * 100)


def test_seasonal_naive_repeats_previous_year():
    values = np.arange(24, dtype=float)

    result = _seasonal_naive(values, 3)

    assert result.predictions == [12.0, 13.0, 14.0]


def test_seasonal_naive_requires_one_year():
    with pytest.raises(ValueError, match="12 observations"):
        _seasonal_naive(np.arange(11, dtype=float), 1)
