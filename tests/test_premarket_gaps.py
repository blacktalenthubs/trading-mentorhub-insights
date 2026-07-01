"""Tests for analytics/premarket_gaps pure helpers (bucket / $-volume / filters)."""

from __future__ import annotations

from analytics.premarket_gaps import (
    bucket_for, pm_dollar_volume, passes_gap_filters,
    passes_market_cap, is_ai_space,
    GAP_MIN_PCT, PM_DOLLAR_VOL_MIN, PRICE_MIN,
)

MOM = {"RKLB", "IONQ", "OKLO"}
TRUSTED = {"AAPL", "MSFT", "NVDA"}


class TestMarketCap:
    def test_trusted_always_passes(self):
        assert passes_market_cap("AAPL", None, TRUSTED, floor=3e9) is True

    def test_below_floor_dropped(self):
        assert passes_market_cap("JEM", 5e8, TRUSTED, floor=3e9) is False

    def test_at_or_above_floor_passes(self):
        assert passes_market_cap("PLTR", 3e9, TRUSTED, floor=3e9) is True
        assert passes_market_cap("PLTR", 9e9, TRUSTED, floor=3e9) is True

    def test_unknown_non_trusted_fail_closed(self):
        assert passes_market_cap("XYZ", None, TRUSTED, floor=3e9) is False

    def test_floor_zero_disables_gate(self):
        assert passes_market_cap("XYZ", None, TRUSTED, floor=0) is True


class TestAiSpace:
    def test_ai_industries(self):
        assert is_ai_space("Semiconductors") is True
        assert is_ai_space("Technology") is True
        assert is_ai_space("Software") is True

    def test_non_ai(self):
        assert is_ai_space("Beverages") is False
        assert is_ai_space("Oil & Gas") is False
        assert is_ai_space(None) is False


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
