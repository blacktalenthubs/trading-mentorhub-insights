"""Phase 1 (2026-04-23) — tests for breakout/breakdown confirmation helpers.

These helpers replaced the single-bar `close > level` check that caused the
AMD 04-22 `inside_day_breakout` misfire (alert fired at $291.48 while entry
level was $286.20, then re-fired again at $295.18). They enforce:

1. N consecutive 5-min bars on the correct side of the level.
2. Intrabar tolerance — the opposing wick cannot round-trip past the level
   by more than BREAKOUT_INTRABAR_TOLERANCE_PCT (0.2% default).
3. Staleness guard — if the last close is already >BREAKOUT_STALENESS_PCT
   (1.0% default) past the level, skip entirely.
"""
from __future__ import annotations

import pandas as pd

from analytics.intraday_rules import (
    _confirm_breakdown_below,
    _confirm_breakout_above,
)


def _bars(rows):
    return pd.DataFrame(rows)


class TestConfirmBreakoutAbove:
    def test_two_confirming_bars_passes(self):
        bars = _bars([
            {"Open": 100.5, "High": 101.3, "Low": 100.9, "Close": 101.2, "Volume": 1000},
            {"Open": 101.2, "High": 101.8, "Low": 101.0, "Close": 101.5, "Volume": 1000},
        ])
        assert _confirm_breakout_above(bars, level=101.0) is True

    def test_single_bar_fails(self):
        bars = _bars([
            {"Open": 101.0, "High": 102.0, "Low": 100.8, "Close": 101.5, "Volume": 1000},
        ])
        assert _confirm_breakout_above(bars, level=101.0) is False

    def test_only_last_bar_above_fails(self):
        """Classic single-bar breakout — previous bar still below level."""
        bars = _bars([
            {"Open": 100.0, "High": 100.8, "Low": 99.5, "Close": 100.5, "Volume": 1000},
            {"Open": 100.5, "High": 102.0, "Low": 100.2, "Close": 101.5, "Volume": 1500},
        ])
        assert _confirm_breakout_above(bars, level=101.0) is False

    def test_runaway_bar_past_staleness_fails(self):
        """Last close >1% above level → staleness guard returns False."""
        bars = _bars([
            {"Open": 101.0, "High": 102.5, "Low": 100.9, "Close": 102.2, "Volume": 1000},
            {"Open": 102.2, "High": 103.5, "Low": 102.0, "Close": 103.2, "Volume": 1000},
        ])
        assert _confirm_breakout_above(bars, level=101.0) is False

    def test_wick_below_tolerance_fails(self):
        """Intrabar wick below floor (level × 0.998) invalidates confirmation."""
        bars = _bars([
            {"Open": 101.0, "High": 101.5, "Low": 100.3, "Close": 101.3, "Volume": 1000},  # low 0.7% below
            {"Open": 101.3, "High": 102.0, "Low": 101.1, "Close": 101.5, "Volume": 1000},
        ])
        assert _confirm_breakout_above(bars, level=101.0) is False

    def test_wick_inside_tolerance_passes(self):
        """A wick <= 0.2% below level is tolerated (noise, not breakdown)."""
        bars = _bars([
            {"Open": 101.0, "High": 101.4, "Low": 100.82, "Close": 101.2, "Volume": 1000},  # 0.18% below
            {"Open": 101.2, "High": 101.8, "Low": 101.0, "Close": 101.5, "Volume": 1000},
        ])
        assert _confirm_breakout_above(bars, level=101.0) is True

    def test_empty_bars_returns_false(self):
        assert _confirm_breakout_above(pd.DataFrame(), level=101.0) is False

    def test_zero_level_returns_false(self):
        bars = _bars([
            {"Open": 1, "High": 1, "Low": 1, "Close": 1, "Volume": 1},
            {"Open": 1, "High": 1, "Low": 1, "Close": 1, "Volume": 1},
        ])
        assert _confirm_breakout_above(bars, level=0) is False

    def test_custom_n_bars_three(self):
        """With n_bars=3, 3 consecutive bars above required."""
        bars = _bars([
            {"Open": 101.0, "High": 101.3, "Low": 100.9, "Close": 101.2, "Volume": 1000},
            {"Open": 101.2, "High": 101.5, "Low": 101.0, "Close": 101.3, "Volume": 1000},
            {"Open": 101.3, "High": 101.6, "Low": 101.1, "Close": 101.4, "Volume": 1000},
        ])
        assert _confirm_breakout_above(bars, level=101.0, n_bars=3) is True
        assert _confirm_breakout_above(bars.head(2), level=101.0, n_bars=3) is False


class TestConfirmBreakdownBelow:
    def test_two_confirming_bars_passes(self):
        bars = _bars([
            {"Open": 100.0, "High": 100.1, "Low": 99.7, "Close": 99.8, "Volume": 1000},
            {"Open": 99.8, "High": 99.9, "Low": 99.5, "Close": 99.6, "Volume": 1000},
        ])
        assert _confirm_breakdown_below(bars, level=100.0) is True

    def test_single_bar_fails(self):
        bars = _bars([
            {"Open": 99.5, "High": 100.2, "Low": 99.4, "Close": 99.7, "Volume": 1000},
        ])
        assert _confirm_breakdown_below(bars, level=100.0) is False

    def test_runaway_bar_past_staleness_fails(self):
        """Last close more than 1% below level → stale."""
        bars = _bars([
            {"Open": 99.0, "High": 99.1, "Low": 98.5, "Close": 98.7, "Volume": 1000},
            {"Open": 98.7, "High": 98.8, "Low": 98.2, "Close": 98.5, "Volume": 1000},
        ])
        assert _confirm_breakdown_below(bars, level=100.0) is False

    def test_wick_above_tolerance_fails(self):
        """Intrabar high above ceiling (level × 1.002) invalidates."""
        bars = _bars([
            {"Open": 99.8, "High": 100.7, "Low": 99.6, "Close": 99.7, "Volume": 1000},  # high 0.7% above
            {"Open": 99.7, "High": 99.9, "Low": 99.5, "Close": 99.6, "Volume": 1000},
        ])
        assert _confirm_breakdown_below(bars, level=100.0) is False

    def test_empty_bars_returns_false(self):
        assert _confirm_breakdown_below(pd.DataFrame(), level=100.0) is False
