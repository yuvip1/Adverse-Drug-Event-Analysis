import pandas as pd
import pytest

from src.ml_classifier import _evaluate, _split


def test_time_split_keeps_later_periods_in_test():
    frame = pd.DataFrame([
        {"report_year": 2024, "report_month": 1, "is_serious": 0},
        {"report_year": 2024, "report_month": 2, "is_serious": 1},
        {"report_year": 2024, "report_month": 3, "is_serious": 0},
        {"report_year": 2024, "report_month": 4, "is_serious": 1},
        {"report_year": 2024, "report_month": 5, "is_serious": 0},
        {"report_year": 2024, "report_month": 6, "is_serious": 1},
        {"report_year": 2024, "report_month": 7, "is_serious": 0},
        {"report_year": 2024, "report_month": 8, "is_serious": 1},
        {"report_year": 2024, "report_month": 9, "is_serious": 0},
        {"report_year": 2024, "report_month": 10, "is_serious": 1},
    ])

    train, test = _split(frame)

    assert train["report_month"].max() < test["report_month"].min()


def test_evaluation_returns_requested_metrics():
    metrics = _evaluate(pd.Series([0, 1, 1, 0]), [0.1, 0.8, 0.7, 0.2])

    assert metrics["roc_auc"] == pytest.approx(1.0)
    assert metrics["precision"] == pytest.approx(1.0)
    assert metrics["recall"] == pytest.approx(1.0)
    assert metrics["brier_score"] >= 0
