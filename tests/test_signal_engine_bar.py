"""Tests for stale-bar fix in signal_engine.analyze_symbol().

Verifies that:
- After market close, today's completed bar is used (not dropped).
- During market hours, today's partial bar is dropped.
- When there is no today bar (e.g. weekend), nothing is dropped.
"""

from unittest.mock import patch

import pandas as pd

from analytics.signal_engine import analyze_symbol


def _make_hist(dates: list[str], closes: list[float]) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame for testing."""
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in dates])
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [c + 1 for c in closes],
            "Low": [c - 1 for c in closes],
            "Close": closes,
            "Volume": [1_000_000] * len(closes),
        },
        index=idx,
    )


class TestStaleBarFix:
    """Ensure today's bar is kept after close and dropped during market hours."""

    def test_after_close_uses_today_bar(self):
        """After market close, today's completed bar should be used."""
        today = pd.Timestamp.now().normalize()
        yesterday = today - pd.Timedelta(days=1)
        two_days_ago = today - pd.Timedelta(days=2)

        hist = _make_hist(
            [str(two_days_ago.date()), str(yesterday.date()), str(today.date())],
            [100.0, 102.0, 105.0],
        )

        with patch("analytics.signal_engine.is_market_hours", return_value=False):
            result = analyze_symbol(hist, "TEST")

        assert result is not None
        # Should use today's close (105), not yesterday's (102)
        assert result.last_close == 105.0

    def test_during_market_drops_today_bar(self):
        """During market hours, today's partial bar should be dropped."""
        today = pd.Timestamp.now().normalize()
        yesterday = today - pd.Timedelta(days=1)
        two_days_ago = today - pd.Timedelta(days=2)

        hist = _make_hist(
            [str(two_days_ago.date()), str(yesterday.date()), str(today.date())],
            [100.0, 102.0, 105.0],
        )

        with patch("analytics.signal_engine.is_market_hours", return_value=True):
            result = analyze_symbol(hist, "TEST")

        assert result is not None
        # Should drop today's bar and use yesterday's close (102)
        assert result.last_close == 102.0

    def test_no_today_bar_nothing_dropped(self):
        """When there is no today bar (e.g. weekend), nothing should be dropped."""
        today = pd.Timestamp.now().normalize()
        two_days_ago = today - pd.Timedelta(days=2)
        three_days_ago = today - pd.Timedelta(days=3)

        hist = _make_hist(
            [str(three_days_ago.date()), str(two_days_ago.date())],
            [100.0, 102.0],
        )

        with patch("analytics.signal_engine.is_market_hours", return_value=False):
            result = analyze_symbol(hist, "TEST")

        assert result is not None
        # Should use the most recent bar (102)
        assert result.last_close == 102.0
