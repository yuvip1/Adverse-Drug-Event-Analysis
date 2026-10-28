import math

import pytest

from src.signal_analysis import calculate_signal


def test_hand_calculated_two_by_two_signal():
    metrics = calculate_signal(pair_count=10, drug_total=20, reaction_total=50, total_reports=1000)

    assert (metrics.a, metrics.b, metrics.c, metrics.d) == (10, 10, 40, 940)
    assert metrics.prr == pytest.approx(12.25)
    assert metrics.ror == pytest.approx(23.5)
    assert metrics.chi_square == pytest.approx(77.6047261, rel=1e-6)
    assert metrics.prr_lower_95 is not None
    assert metrics.prr_upper_95 is not None
    assert metrics.ror_lower_95 is not None
    assert metrics.ror_upper_95 is not None
    assert metrics.prr_lower_95 < metrics.prr < metrics.prr_upper_95
    assert metrics.ror_lower_95 < metrics.ror < metrics.ror_upper_95


def test_invalid_table_is_rejected():
    with pytest.raises(ValueError, match="Invalid 2x2 table"):
        calculate_signal(pair_count=20, drug_total=10, reaction_total=50, total_reports=100)


def test_zero_cell_keeps_ratio_unavailable():
    metrics = calculate_signal(pair_count=0, drug_total=20, reaction_total=50, total_reports=1000)

    assert metrics.prr is None
    assert metrics.ror is None
    assert math.isfinite(metrics.chi_square)
