"""Tests for analytics/premarket_gaps pure helpers (bucket / $-volume / filters)."""

from __future__ import annotations

from analytics.premarket_gaps import (
    bucket_for, pm_dollar_volume, passes_gap_filters,
    GAP_MIN_PCT, PM_DOLLAR_VOL_MIN, PRICE_MIN,
)

MOM = {"RKLB", "IONQ", "OKLO"}


class TestBucket:
    def test_momentum(self):
        assert bucket_for("RKLB", MOM) == "momentum"
        assert bucket_for("ionq", MOM) == "momentum"  # case-insensitive

    def test_clean(self):
        assert bucket_for("AAPL", MOM) == "clean"


class TestDollarVolume:
    def test_sum_close_times_volume(self):
        assert pm_dollar_volume([10.0, 11.0], [1000, 2000]) == 10.0 * 1000 + 11.0 * 2000

    def test_handles_none_and_mismatch(self):
        assert pm_dollar_volume([], []) == 0.0
        assert pm_dollar_volume([None, 5.0], [100, 200]) == 5.0 * 200


class TestFilters:
    def test_all_pass(self):
        assert passes_gap_filters(5.0, 1_000_000, 50.0) is True

    def test_gap_down_passes_on_abs(self):
        assert passes_gap_filters(-4.0, 1_000_000, 50.0) is True

    def test_gap_too_small(self):
        assert passes_gap_filters(GAP_MIN_PCT - 0.1, 1_000_000, 50.0) is False

    def test_illiquid_blocked(self):
        # Big gap but no premarket volume → the trap filter.
        assert passes_gap_filters(20.0, PM_DOLLAR_VOL_MIN - 1, 50.0) is False

    def test_penny_blocked(self):
        assert passes_gap_filters(20.0, 1_000_000, PRICE_MIN - 0.5) is False

    def test_none_inputs(self):
        assert passes_gap_filters(None, 1_000_000, 50.0) is False
        assert passes_gap_filters(5.0, 1_000_000, None) is False
