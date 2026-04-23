"""Phase 2 (2026-04-23) — volume confirmation on bounces + VWAP time-gate.

These cover the two smaller filters from the Phase 2 spec:
- `_bounce_volume_verdict`: returns 'pass' / 'demote' / 'skip' based on
  last-bar volume vs prior-bar mean.
- `_is_before_vwap_reliable_time`: True if last bar timestamp is before
  10:00 ET. Equity VWAP rules skip in that window.

And integration tests that the MA bounce rules actually consult the
verdict (skip hard, demote HIGH→MEDIUM).
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from analytics.intraday_rules import (
    AlertType,
    _bounce_volume_verdict,
    _is_before_vwap_reliable_time,
    check_ma_bounce_20,
)


def _bars_index_et(rows, start="2026-04-23 09:35:00"):
    """Helper: attach an ET-naive DatetimeIndex to the test bars."""
    idx = pd.date_range(start=start, periods=len(rows), freq="5min")
    return pd.DataFrame(rows, index=idx)


class TestBounceVolumeVerdict:
    def test_high_volume_passes(self):
        bars = _bars_index_et([
            {"Open": 100, "High": 100.5, "Low": 99.5, "Close": 100.2, "Volume": 1000},
            {"Open": 100.2, "High": 100.7, "Low": 99.9, "Close": 100.5, "Volume": 1000},
            {"Open": 100.5, "High": 101, "Low": 100.3, "Close": 100.8, "Volume": 1000},
            {"Open": 100.8, "High": 101.2, "Low": 100.6, "Close": 101.0, "Volume": 1500},  # 1.5x
        ])
        assert _bounce_volume_verdict(bars) == "pass"

    def test_at_threshold_passes(self):
        """Exactly 1.0x avg should pass (boundary)."""
        bars = _bars_index_et([
            {"Open": 100, "High": 100.5, "Low": 99.5, "Close": 100.2, "Volume": 1000},
            {"Open": 100.2, "High": 100.7, "Low": 99.9, "Close": 100.5, "Volume": 1000},
            {"Open": 100.5, "High": 101, "Low": 100.3, "Close": 100.8, "Volume": 1000},
            {"Open": 100.8, "High": 101.2, "Low": 100.6, "Close": 101.0, "Volume": 1000},
        ])
        assert _bounce_volume_verdict(bars) == "pass"

    def test_moderate_volume_demotes(self):
        bars = _bars_index_et([
            {"Open": 100, "High": 100.5, "Low": 99.5, "Close": 100.2, "Volume": 1000},
            {"Open": 100.2, "High": 100.7, "Low": 99.9, "Close": 100.5, "Volume": 1000},
            {"Open": 100.5, "High": 101, "Low": 100.3, "Close": 100.8, "Volume": 1000},
            {"Open": 100.8, "High": 101.2, "Low": 100.6, "Close": 101.0, "Volume": 700},  # 0.7x
        ])
        assert _bounce_volume_verdict(bars) == "demote"

    def test_low_volume_skips(self):
        bars = _bars_index_et([
            {"Open": 100, "High": 100.5, "Low": 99.5, "Close": 100.2, "Volume": 1000},
            {"Open": 100.2, "High": 100.7, "Low": 99.9, "Close": 100.5, "Volume": 1000},
            {"Open": 100.5, "High": 101, "Low": 100.3, "Close": 100.8, "Volume": 1000},
            {"Open": 100.8, "High": 101.2, "Low": 100.6, "Close": 101.0, "Volume": 300},  # 0.3x
        ])
        assert _bounce_volume_verdict(bars) == "skip"

    def test_too_few_bars_passes_fail_open(self):
        """< 3 bars = no reliable avg, don't gate."""
        bars = _bars_index_et([
            {"Open": 100, "High": 101, "Low": 99, "Close": 100.5, "Volume": 100},
        ])
        assert _bounce_volume_verdict(bars) == "pass"

    def test_zero_avg_volume_fail_open(self):
        bars = _bars_index_et([
            {"Open": 100, "High": 100.5, "Low": 99.5, "Close": 100.2, "Volume": 0},
            {"Open": 100.2, "High": 100.7, "Low": 99.9, "Close": 100.5, "Volume": 0},
            {"Open": 100.5, "High": 101, "Low": 100.3, "Close": 100.8, "Volume": 0},
            {"Open": 100.8, "High": 101.2, "Low": 100.6, "Close": 101.0, "Volume": 500},
        ])
        assert _bounce_volume_verdict(bars) == "pass"


class TestMABounce20VolumeIntegration:
    """Verify check_ma_bounce_20 respects the verdict end-to-end."""

    def _make_bars_bouncing(self, last_volume: int):
        """Build bars where price touches MA20=100 then bounces above."""
        # Prior bars volume 1000 each, last bar has variable volume
        return _bars_index_et([
            {"Open": 100.3, "High": 100.5, "Low": 99.95, "Close": 100.3, "Volume": 1000},
            {"Open": 100.3, "High": 100.5, "Low": 99.95, "Close": 100.3, "Volume": 1000},
            {"Open": 100.3, "High": 100.5, "Low": 99.95, "Close": 100.3, "Volume": 1000},
            {"Open": 100.3, "High": 100.7, "Low": 100.0, "Close": 100.5, "Volume": last_volume},
        ])

    def test_high_volume_keeps_high_confidence(self):
        bars = self._make_bars_bouncing(last_volume=1500)
        sig = check_ma_bounce_20("AAPL", bars, ma20=100.0, ma50=95.0)
        assert sig is not None
        assert sig.alert_type == AlertType.MA_BOUNCE_20
        assert sig.confidence == "high"

    def test_moderate_volume_demotes_to_medium(self):
        bars = self._make_bars_bouncing(last_volume=700)  # 0.7x
        sig = check_ma_bounce_20("AAPL", bars, ma20=100.0, ma50=95.0)
        assert sig is not None
        assert sig.confidence == "medium"

    def test_low_volume_skips_entirely(self):
        bars = self._make_bars_bouncing(last_volume=300)  # 0.3x
        sig = check_ma_bounce_20("AAPL", bars, ma20=100.0, ma50=95.0)
        assert sig is None


class TestVWAPTimeGate:
    """_is_before_vwap_reliable_time returns True when last bar time < 10:00 ET."""

    def test_bar_at_9_35_is_pre_10am(self):
        bars = _bars_index_et([
            {"Open": 100, "High": 100.5, "Low": 99.5, "Close": 100.2, "Volume": 1000},
            {"Open": 100.2, "High": 100.7, "Low": 99.9, "Close": 100.5, "Volume": 1000},
        ], start="2026-04-23 09:35:00")
        assert _is_before_vwap_reliable_time(bars) is True

    def test_bar_at_9_50_is_pre_10am(self):
        # start 9:50 + 2 bars @ 5min each → last bar at 9:55
        bars = _bars_index_et([
            {"Open": 100, "High": 100.5, "Low": 99.5, "Close": 100.2, "Volume": 1000},
            {"Open": 100.2, "High": 100.7, "Low": 99.9, "Close": 100.5, "Volume": 1000},
        ], start="2026-04-23 09:50:00")
        assert _is_before_vwap_reliable_time(bars) is True

    def test_bar_at_10_00_is_not_pre_10am(self):
        """10:00 exactly = not before 10 (inclusive of the hour)."""
        bars = _bars_index_et([
            {"Open": 100, "High": 100.5, "Low": 99.5, "Close": 100.2, "Volume": 1000},
            {"Open": 100.2, "High": 100.7, "Low": 99.9, "Close": 100.5, "Volume": 1000},
        ], start="2026-04-23 10:00:00")
        assert _is_before_vwap_reliable_time(bars) is False

    def test_bar_at_10_30_is_not_pre_10am(self):
        bars = _bars_index_et([
            {"Open": 100, "High": 100.5, "Low": 99.5, "Close": 100.2, "Volume": 1000},
            {"Open": 100.2, "High": 100.7, "Low": 99.9, "Close": 100.5, "Volume": 1000},
        ], start="2026-04-23 10:30:00")
        assert _is_before_vwap_reliable_time(bars) is False

    def test_bar_at_14_00_is_not_pre_10am(self):
        bars = _bars_index_et([
            {"Open": 100, "High": 100.5, "Low": 99.5, "Close": 100.2, "Volume": 1000},
            {"Open": 100.2, "High": 100.7, "Low": 99.9, "Close": 100.5, "Volume": 1000},
        ], start="2026-04-23 14:00:00")
        assert _is_before_vwap_reliable_time(bars) is False

    def test_empty_bars_fail_open(self):
        assert _is_before_vwap_reliable_time(pd.DataFrame()) is False

    def test_non_datetime_index_fail_open(self):
        """If index lacks .time(), don't gate — fail open."""
        bars = pd.DataFrame([
            {"Open": 100, "High": 100.5, "Low": 99.5, "Close": 100.2, "Volume": 1000},
        ])
        assert _is_before_vwap_reliable_time(bars) is False
