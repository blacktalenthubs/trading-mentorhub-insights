"""Phase 3b (2026-04-23 evening) — EMA8 + EMA21 bounce rules.

Trader directive: rule-base focuses on EMA (8/21/50/100/200) as support /
resistance. Phase 3b adds two new rule functions:

- `check_ema_bounce_8`  — fast pullback to EMA8 (uptrend filter: EMA8 > EMA21)
- `check_ema_bounce_21` — medium-trend pullback to EMA21 (filter: EMA21 > EMA50)

Both follow the same proximity / hold / staleness / volume mechanics as the
existing 20-period version. EMA_RECLAIM_8 / EMA_RECLAIM_21 reuse the generic
`check_ma_ema_reclaim` helper — covered by existing reclaim tests via
parametrization in evaluate_rules.

Tests here cover the two new bounce functions end-to-end with fixture bars.
"""
from __future__ import annotations

import pandas as pd

from analytics.intraday_rules import (
    AlertType,
    check_ema_bounce_8,
    check_ema_bounce_21,
)


def _bars_index_et(rows, start="2026-04-23 13:30:00"):
    """ET-naive datetime index — matches what intraday_data fetchers produce."""
    idx = pd.date_range(start=start, periods=len(rows), freq="5min")
    return pd.DataFrame(rows, index=idx)


def _make_bouncing_bars(level: float, last_volume: int = 1500):
    """Bars where Low touches `level` then last bar closes above it.

    Standard volume profile: prior bars all 1000, last bar parameterized so
    we can flip between pass / demote / skip verdicts.
    """
    return _bars_index_et([
        {"Open": level + 0.30, "High": level + 0.50, "Low": level - 0.05,
         "Close": level + 0.30, "Volume": 1000},
        {"Open": level + 0.30, "High": level + 0.50, "Low": level - 0.05,
         "Close": level + 0.30, "Volume": 1000},
        {"Open": level + 0.30, "High": level + 0.50, "Low": level - 0.05,
         "Close": level + 0.30, "Volume": 1000},
        {"Open": level + 0.30, "High": level + 0.70, "Low": level + 0.00,
         "Close": level + 0.50, "Volume": last_volume},
    ])


# -----------------------------------------------------------------------------
# check_ema_bounce_21
# -----------------------------------------------------------------------------


class TestEmaBounce21:
    def test_fires_in_uptrend(self):
        bars = _make_bouncing_bars(level=100.0)
        sig = check_ema_bounce_21("AAPL", bars, ema21=100.0, ema50=95.0)
        assert sig is not None
        assert sig.alert_type == AlertType.EMA_BOUNCE_21
        assert sig.direction == "BUY"
        assert sig.entry == 100.0
        # T1 = entry + risk, T2 = entry + 2*risk; risk = entry * MA_STOP_OFFSET
        assert sig.target_1 > sig.entry
        assert sig.target_2 > sig.target_1
        assert "EMA bounce 21" in sig.message

    def test_does_not_fire_when_ema21_below_ema50(self):
        """Trend filter: EMA21 must be above EMA50."""
        bars = _make_bouncing_bars(level=100.0)
        sig = check_ema_bounce_21("AAPL", bars, ema21=100.0, ema50=105.0)
        assert sig is None

    def test_does_not_fire_when_ema21_equals_ema50(self):
        """Strict greater-than required for trend confirmation."""
        bars = _make_bouncing_bars(level=100.0)
        sig = check_ema_bounce_21("AAPL", bars, ema21=100.0, ema50=100.0)
        assert sig is None

    def test_does_not_fire_when_close_below_ema21(self):
        bars = _bars_index_et([
            {"Open": 99, "High": 99.5, "Low": 98, "Close": 99,
             "Volume": 1000},
            {"Open": 99, "High": 99.5, "Low": 98, "Close": 99,
             "Volume": 1000},
            {"Open": 99, "High": 99.5, "Low": 98, "Close": 99,
             "Volume": 1000},
            {"Open": 99, "High": 99.8, "Low": 98.5, "Close": 99.5,
             "Volume": 1500},  # still below 100 EMA21
        ])
        sig = check_ema_bounce_21("AAPL", bars, ema21=100.0, ema50=95.0)
        assert sig is None

    def test_skips_when_volume_too_low(self):
        bars = _make_bouncing_bars(level=100.0, last_volume=300)  # 0.3x
        sig = check_ema_bounce_21("AAPL", bars, ema21=100.0, ema50=95.0)
        assert sig is None  # skipped per Phase 2 volume verdict

    def test_demotes_when_volume_moderate(self):
        bars = _make_bouncing_bars(level=100.0, last_volume=700)  # 0.7x
        sig = check_ema_bounce_21("AAPL", bars, ema21=100.0, ema50=95.0)
        assert sig is not None
        assert sig.confidence == "medium"

    def test_returns_none_when_inputs_missing(self):
        bars = _make_bouncing_bars(level=100.0)
        assert check_ema_bounce_21("AAPL", bars, ema21=None, ema50=95.0) is None
        assert check_ema_bounce_21("AAPL", bars, ema21=100.0, ema50=None) is None
        assert check_ema_bounce_21("AAPL", bars, ema21=0, ema50=95.0) is None
        assert check_ema_bounce_21("AAPL", bars, ema21=100.0, ema50=0) is None

    def test_skips_when_price_too_far_above_ema21(self):
        """Staleness guard — bounce ran too far past EMA already."""
        # Last bar close 105 vs ema21 100 → 5% above, exceeds MA_BOUNCE_MAX_DISTANCE_PCT (2%)
        bars = _bars_index_et([
            {"Open": 100, "High": 100.5, "Low": 99.95, "Close": 100.2,
             "Volume": 1000},
            {"Open": 100.2, "High": 102, "Low": 100.0, "Close": 101.5,
             "Volume": 1000},
            {"Open": 101.5, "High": 104, "Low": 101, "Close": 103.5,
             "Volume": 1000},
            {"Open": 103.5, "High": 106, "Low": 103.3, "Close": 105.0,
             "Volume": 1500},
        ])
        sig = check_ema_bounce_21("AAPL", bars, ema21=100.0, ema50=95.0)
        assert sig is None


# -----------------------------------------------------------------------------
# check_ema_bounce_8
# -----------------------------------------------------------------------------


class TestEmaBounce8:
    def test_fires_in_fast_uptrend(self):
        bars = _make_bouncing_bars(level=100.0)
        sig = check_ema_bounce_8("AAPL", bars, ema8=100.0, ema21=98.0)
        assert sig is not None
        assert sig.alert_type == AlertType.EMA_BOUNCE_8
        assert sig.direction == "BUY"
        assert sig.entry == 100.0
        assert "EMA bounce 8" in sig.message

    def test_does_not_fire_when_ema8_below_ema21(self):
        """Fast trend filter: EMA8 > EMA21 required."""
        bars = _make_bouncing_bars(level=100.0)
        sig = check_ema_bounce_8("AAPL", bars, ema8=100.0, ema21=102.0)
        assert sig is None

    def test_does_not_fire_when_ema8_equals_ema21(self):
        bars = _make_bouncing_bars(level=100.0)
        sig = check_ema_bounce_8("AAPL", bars, ema8=100.0, ema21=100.0)
        assert sig is None

    def test_does_not_fire_when_close_below_ema8(self):
        bars = _bars_index_et([
            {"Open": 99, "High": 99.5, "Low": 98, "Close": 99,
             "Volume": 1000},
            {"Open": 99, "High": 99.5, "Low": 98, "Close": 99,
             "Volume": 1000},
            {"Open": 99, "High": 99.5, "Low": 98, "Close": 99,
             "Volume": 1000},
            {"Open": 99, "High": 99.8, "Low": 98.5, "Close": 99.5,
             "Volume": 1500},  # close 99.5 < EMA8 100
        ])
        sig = check_ema_bounce_8("AAPL", bars, ema8=100.0, ema21=98.0)
        assert sig is None

    def test_skips_when_volume_too_low(self):
        bars = _make_bouncing_bars(level=100.0, last_volume=300)
        sig = check_ema_bounce_8("AAPL", bars, ema8=100.0, ema21=98.0)
        assert sig is None

    def test_demotes_when_volume_moderate(self):
        bars = _make_bouncing_bars(level=100.0, last_volume=700)
        sig = check_ema_bounce_8("AAPL", bars, ema8=100.0, ema21=98.0)
        assert sig is not None
        assert sig.confidence == "medium"

    def test_returns_none_when_inputs_missing(self):
        bars = _make_bouncing_bars(level=100.0)
        assert check_ema_bounce_8("AAPL", bars, ema8=None, ema21=98.0) is None
        assert check_ema_bounce_8("AAPL", bars, ema8=100.0, ema21=None) is None
        assert check_ema_bounce_8("AAPL", bars, ema8=0, ema21=98.0) is None

    def test_high_confidence_on_close_proximity(self):
        """Tight touch (proximity <= 0.001) → HIGH confidence with full volume."""
        # Make low almost exactly equal to EMA level
        bars = _bars_index_et([
            {"Open": 100.30, "High": 100.50, "Low": 100.05,
             "Close": 100.30, "Volume": 1000},
            {"Open": 100.30, "High": 100.50, "Low": 100.05,
             "Close": 100.30, "Volume": 1000},
            {"Open": 100.30, "High": 100.50, "Low": 100.05,
             "Close": 100.30, "Volume": 1000},
            # Very tight low — within 0.05% of 100
            {"Open": 100.30, "High": 100.70, "Low": 100.005,
             "Close": 100.50, "Volume": 1500},
        ])
        sig = check_ema_bounce_8("AAPL", bars, ema8=100.0, ema21=98.0)
        assert sig is not None
        assert sig.confidence == "high"


# -----------------------------------------------------------------------------
# AlertType enum sanity
# -----------------------------------------------------------------------------


class TestNewAlertTypeEnums:
    def test_ema_bounce_8_enum(self):
        assert AlertType.EMA_BOUNCE_8.value == "ema_bounce_8"

    def test_ema_bounce_21_enum(self):
        assert AlertType.EMA_BOUNCE_21.value == "ema_bounce_21"

    def test_ema_reclaim_8_enum(self):
        assert AlertType.EMA_RECLAIM_8.value == "ema_reclaim_8"

    def test_ema_reclaim_21_enum(self):
        assert AlertType.EMA_RECLAIM_21.value == "ema_reclaim_21"

    def test_legacy_ema_20_enums_still_present(self):
        """DB compat — historical alert rows reference these strings."""
        assert AlertType.EMA_BOUNCE_20.value == "ema_bounce_20"
        assert AlertType.EMA_RECLAIM_20.value == "ema_reclaim_20"


# -----------------------------------------------------------------------------
# ENABLED_RULES contents
# -----------------------------------------------------------------------------


class TestEnabledRulesPhase3b:
    def test_ema_bounce_8_in_enabled_rules(self):
        from alert_config import ENABLED_RULES
        assert "ema_bounce_8" in ENABLED_RULES

    def test_ema_bounce_21_in_enabled_rules(self):
        from alert_config import ENABLED_RULES
        assert "ema_bounce_21" in ENABLED_RULES

    def test_ema_reclaim_8_in_enabled_rules(self):
        from alert_config import ENABLED_RULES
        assert "ema_reclaim_8" in ENABLED_RULES

    def test_ema_reclaim_21_in_enabled_rules(self):
        from alert_config import ENABLED_RULES
        assert "ema_reclaim_21" in ENABLED_RULES

    def test_ema_bounce_20_disabled(self):
        from alert_config import ENABLED_RULES
        assert "ema_bounce_20" not in ENABLED_RULES

    def test_ema_reclaim_20_disabled(self):
        from alert_config import ENABLED_RULES
        assert "ema_reclaim_20" not in ENABLED_RULES

    def test_ema_bounce_50_100_200_kept(self):
        from alert_config import ENABLED_RULES
        assert "ema_bounce_50" in ENABLED_RULES
        assert "ema_bounce_100" in ENABLED_RULES
        assert "ema_bounce_200" in ENABLED_RULES
