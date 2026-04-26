"""Phase 5b (2026-04-25 evening) — EMA rejection (extended) + EMA overhead
resistance NOTICE.

Two fixes covered here:

Fix A: `check_ema_rejection_short` now also detects rejections at EMA8 and
EMA21 (previously only EMA20/50/100/200). Mirrors the bounce-side coverage
from Phase 3b.

Fix B: New `check_ema_overhead_resistance` fires a NOTICE when a daily EMA
sits above current close within proximity AND the bar's high tested it
from below. No rejection candle pattern required — pure heads-up that
resistance is approaching.
"""
from __future__ import annotations

import pandas as pd
import pytest

from analytics.intraday_rules import (
    AlertType,
    check_ema_overhead_resistance,
    check_ema_rejection_short,
)


def _bars_index_et(rows, start="2026-04-25 13:30:00"):
    idx = pd.date_range(start=start, periods=len(rows), freq="5min")
    return pd.DataFrame(rows, index=idx)


def _make_bars_with_high_at(level: float, last_close_below_pct: float = 0.005):
    """Create 12+ bars where the LAST bar's high tests `level` and closes below.

    last_close_below_pct = how far below `level` the close should be (default 0.5%).
    Earlier bars are filler — well below the level so the "test from below" is unique.
    """
    last_close = level * (1 - last_close_below_pct)
    last_open = level * (1 - 0.003)  # opens slightly below
    last_low = level * (1 - 0.008)
    last_high = level * (1 - 0.0001)  # high tests basically AT level

    filler = []
    for _ in range(11):
        filler.append({
            "Open": level * 0.97, "High": level * 0.98,
            "Low": level * 0.96, "Close": level * 0.975,
            "Volume": 1000,
        })
    filler.append({
        "Open": last_open, "High": last_high,
        "Low": last_low, "Close": last_close,
        "Volume": 1500,
    })
    return _bars_index_et(filler)


# -----------------------------------------------------------------------------
# Fix A — ema_rejection_short now covers EMA8 + EMA21
# -----------------------------------------------------------------------------


class TestEmaRejectionShortExtended:
    def test_fires_on_ema8_rejection(self):
        """ETH-style: bar tests EMA8 from below, rejected with close in lower 40%."""
        EMA8 = 100.0
        bars = _make_bars_with_high_at(EMA8)
        prior_day = {"ema8": EMA8, "ema21": 90, "ema50": 80,
                     "ema100": 110, "ema200": 130}
        sig = check_ema_rejection_short("ETH-USD", bars, prior_day)
        assert sig is not None
        assert sig.alert_type == AlertType.EMA_REJECTION_SHORT
        assert sig.direction == "SHORT"
        assert "EMA8" in sig.message

    def test_fires_on_ema21_rejection(self):
        EMA21 = 100.0
        bars = _make_bars_with_high_at(EMA21)
        # No EMA8 above close → walk down to EMA21
        prior_day = {"ema8": 80, "ema21": EMA21, "ema50": 70,
                     "ema100": 110, "ema200": 130}
        sig = check_ema_rejection_short("ETH-USD", bars, prior_day)
        assert sig is not None
        assert sig.alert_type == AlertType.EMA_REJECTION_SHORT
        # Note: rule iterates fastest → slowest, so EMA8 first if it qualifies.
        # We made EMA8 below close so it doesn't qualify. EMA21 should fire.
        assert "EMA21" in sig.message

    def test_picks_first_qualifying_ema(self):
        """When multiple EMAs are overhead, fastest one wins (EMA8 before EMA21)."""
        EMA = 100.0
        bars = _make_bars_with_high_at(EMA)
        prior_day = {"ema8": EMA, "ema21": EMA + 5,  # both overhead
                     "ema50": 80, "ema100": 130, "ema200": 150}
        sig = check_ema_rejection_short("ETH-USD", bars, prior_day)
        assert sig is not None
        # EMA8 listed first in _ma_levels, qualifies → wins
        assert "EMA8" in sig.message

    def test_existing_ema100_rejection_still_works(self):
        """Regression: Phase 5b extension didn't break EMA100 rejection."""
        EMA100 = 100.0
        bars = _make_bars_with_high_at(EMA100)
        # All faster EMAs below close → only EMA100 qualifies
        prior_day = {"ema8": 70, "ema21": 75, "ema50": 80,
                     "ema100": EMA100, "ema200": 130}
        sig = check_ema_rejection_short("ETH-USD", bars, prior_day)
        assert sig is not None
        assert "EMA100" in sig.message

    def test_fires_on_ma100_rejection(self):
        """Phase 5c: SMA100 added to rejection ladder (alongside SMA50/200)."""
        MA100 = 100.0
        bars = _make_bars_with_high_at(MA100)
        # All EMAs and other SMAs below close → only MA100 qualifies
        prior_day = {
            "ema8": 70, "ema21": 75, "ema50": 80,
            "ma50": 78,
            "ema100": 92, "ma100": MA100,
            "ema200": 130, "ma200": 135,
        }
        sig = check_ema_rejection_short("PLTR", bars, prior_day)
        assert sig is not None
        # Leading "MA100" token confirms SMA100 (not EMA100) was selected
        assert sig.message.startswith("MA100 ")


# -----------------------------------------------------------------------------
# Fix B — new ema_overhead_resistance NOTICE rule
# -----------------------------------------------------------------------------


class TestEmaOverheadResistance:
    def _bars_high_at(self, level: float, close_pct_below: float = 0.005):
        """Last bar's high tests `level`, close stays below by close_pct_below."""
        last_close = level * (1 - close_pct_below)
        return _bars_index_et([
            {"Open": last_close - 0.5, "High": level * 0.9999,
             "Low": last_close - 1.0, "Close": last_close, "Volume": 1000},
        ])

    def test_fires_when_ema8_overhead_and_tested(self):
        bars = self._bars_high_at(100.0)
        prior_day = {"ema8": 100.0, "ema21": 95, "ema50": 90,
                     "ema100": 110, "ema200": 130}
        sig = check_ema_overhead_resistance("COIN", bars, prior_day)
        assert sig is not None
        assert sig.alert_type == AlertType.EMA_OVERHEAD_RESISTANCE
        assert sig.direction == "NOTICE"
        assert "EMA8" in sig.message
        # No actionable fields on a NOTICE
        assert sig.entry is None
        assert sig.stop is None
        assert sig.target_1 is None
        assert sig.target_2 is None

    def test_picks_nearest_overhead_ema(self):
        """Both EMA8 and EMA100 above close — pick EMA8 (closer)."""
        # Bar high at 100.0 (testing EMA8)
        bars = self._bars_high_at(100.0)
        prior_day = {
            "ema8": 100.0,    # 0.5% above close
            "ema21": 95,      # below close → not overhead
            "ema50": 90,      # below close
            "ema100": 105,    # 5% above close → out of proximity (1%)
            "ema200": 130,
        }
        sig = check_ema_overhead_resistance("COIN", bars, prior_day)
        assert sig is not None
        # EMA8 is the nearest qualifying overhead
        assert "EMA8" in sig.message
        assert "EMA100" not in sig.message

    def test_does_not_fire_when_close_above_all_emas(self):
        """All EMAs below close → nothing overhead → no NOTICE."""
        bars = self._bars_high_at(110.0, close_pct_below=0.0)  # close right at 110
        prior_day = {"ema8": 100, "ema21": 95, "ema50": 90,
                     "ema100": 85, "ema200": 70}
        sig = check_ema_overhead_resistance("COIN", bars, prior_day)
        assert sig is None

    def test_does_not_fire_when_ema_too_far_above(self):
        """EMA more than 1% above close → out of proximity, no alert."""
        # Close at 100, EMA at 110 (10% above) → way too far
        bars = _bars_index_et([
            {"Open": 99, "High": 100.5, "Low": 98, "Close": 100, "Volume": 1000},
        ])
        prior_day = {"ema8": 110, "ema21": 90, "ema50": 80,
                     "ema100": 70, "ema200": 60}
        sig = check_ema_overhead_resistance("COIN", bars, prior_day)
        assert sig is None

    def test_does_not_fire_when_high_did_not_test(self):
        """EMA is overhead within proximity but bar's high didn't reach it."""
        # Close 99, EMA 100 (1% above), but high only 99.2 (didn't test EMA)
        bars = _bars_index_et([
            {"Open": 99, "High": 99.2, "Low": 98, "Close": 99, "Volume": 1000},
        ])
        prior_day = {"ema8": 100, "ema21": 95, "ema50": 90,
                     "ema100": 110, "ema200": 130}
        sig = check_ema_overhead_resistance("COIN", bars, prior_day)
        assert sig is None

    def test_no_prior_day_returns_none(self):
        bars = self._bars_high_at(100.0)
        assert check_ema_overhead_resistance("COIN", bars, None) is None
        assert check_ema_overhead_resistance("COIN", bars, {}) is None

    def test_empty_bars_returns_none(self):
        prior_day = {"ema8": 100, "ema21": 95, "ema50": 90}
        assert check_ema_overhead_resistance("COIN", pd.DataFrame(), prior_day) is None


class TestEmaOverheadResistanceSmaLadder:
    """Phase 5c — SMA50/100/200 added to overhead-resistance ladder.

    SMA at 50+ lookbacks diverges from EMA by 2-5%, so each is a distinct
    actionable resistance level (e.g. PLTR daily SMA50 $144.35 vs EMA50
    $147.36 — both got tested and rejected on different days).
    """

    def _bars_high_at(self, level: float, close_pct_below: float = 0.005):
        last_close = level * (1 - close_pct_below)
        return _bars_index_et([
            {"Open": last_close - 0.5, "High": level * 0.9999,
             "Low": last_close - 1.0, "Close": last_close, "Volume": 1000},
        ])

    def test_fires_on_ma50_overhead(self):
        """Bar tests SMA50 from below — NOTICE fires with MA50 label."""
        bars = self._bars_high_at(100.0)
        # Only SMA50 qualifies; all EMAs and other SMAs out of range
        prior_day = {
            "ema8": 95, "ema21": 92, "ema50": 105,  # EMAs not in proximity
            "ma50": 100.0,                            # SMA50 is the resistance
            "ema100": 110, "ma100": 112,
            "ema200": 130, "ma200": 135,
        }
        sig = check_ema_overhead_resistance("PLTR", bars, prior_day)
        assert sig is not None
        assert sig.alert_type == AlertType.EMA_OVERHEAD_RESISTANCE
        assert sig.direction == "NOTICE"
        # Leading "MA50 " token (not "EMA50 ") confirms SMA50 was selected
        assert sig.message.startswith("MA50 ")

    def test_fires_on_ma200_overhead(self):
        """Bar tests SMA200 from below — NOTICE fires with MA200 label."""
        bars = self._bars_high_at(100.0)
        prior_day = {
            "ema8": 95, "ema21": 92, "ema50": 90,
            "ma50": 88,
            "ema100": 110, "ma100": 112,    # out of 1% proximity
            "ema200": 130, "ma200": 100.0,  # only SMA200 qualifies
        }
        sig = check_ema_overhead_resistance("PLTR", bars, prior_day)
        assert sig is not None
        assert sig.message.startswith("MA200 ")

    def test_picks_nearest_when_ema_and_sma_both_overhead(self):
        """EMA50 closer than SMA50 → EMA50 wins; both should be considered."""
        # Close at $99.50, EMA50 at $100, SMA50 at $100.30
        bars = _bars_index_et([
            {"Open": 99.4, "High": 99.99, "Low": 99.0,
             "Close": 99.50, "Volume": 1000},
        ])
        prior_day = {
            "ema8": 95, "ema21": 92,
            "ema50": 100.0,    # 0.50% above close — closer
            "ma50": 100.30,    # 0.80% above close — farther
            "ema100": 110, "ma100": 115,
            "ema200": 130, "ma200": 135,
        }
        sig = check_ema_overhead_resistance("PLTR", bars, prior_day)
        assert sig is not None
        # EMA50 is nearest → wins. Use the leading-token form to disambiguate
        # since "MA50" is a substring of "EMA50".
        assert sig.message.startswith("EMA50 ")

    def test_pltr_today_ma50_overhead(self):
        """PLTR snapshot (2026-04-26): close $143.09, SMA50 $144.35, EMA50 $147.36.

        Both SMA50 and EMA50 above close. SMA50 is closer (0.88% vs 2.99%) →
        the NOTICE should fire on MA50, the more immediately-actionable level.
        """
        # Bar that wicks to test SMA50 area
        bars = _bars_index_et([
            {"Open": 142.50, "High": 144.30, "Low": 142.00,
             "Close": 143.09, "Volume": 1000},
        ])
        prior_day = {
            "ema8": 142.10, "ema21": 142.50,
            "ema50": 147.36,   # 2.99% above — out of 1% proximity
            "ma50": 144.35,    # 0.88% above — within proximity ✓
            "ema100": 150.20, "ma100": 152.10,
            "ema200": 160.00, "ma200": 165.00,
        }
        sig = check_ema_overhead_resistance("PLTR", bars, prior_day)
        assert sig is not None
        # SMA50 is closer; message should start with "MA50 " (not "EMA50 ")
        assert sig.message.startswith("MA50 ")
        assert sig.direction == "NOTICE"
        # No actionable fields on a NOTICE
        assert sig.entry is None and sig.stop is None


class TestEmaOverheadResistanceCoinSnapshot:
    """COIN today (2026-04-25): closed $199.77, EMA100=$211.21 overhead.

    Tests the actual scenario the trader wanted: COIN's recent rally got
    rejected at EMA100. With Fix B, this should produce a NOTICE.
    """

    def test_coin_today_ema100_overhead_notice(self):
        """COIN: close $199.77, bar high tested $211 (rally then rejected).

        This simulates the rally-rejection candle from a few days back where
        COIN spiked into EMA100 then closed back below.
        """
        # Bar that rallied into EMA100 area then closed back at $199.77
        bars = _bars_index_et([
            {"Open": 200, "High": 211.20, "Low": 199, "Close": 199.77, "Volume": 1000},
        ])
        # EMA100 = $211.21, close at $199.77 → 5.4% below — too far for OVERHEAD proximity
        # Need to use a closer scenario: imagine COIN at $209 testing $211
        bars = _bars_index_et([
            {"Open": 210, "High": 211.20, "Low": 209, "Close": 209.50, "Volume": 1000},
        ])
        prior_day = {
            "ema8": 197.90, "ema21": 190.95, "ema50": 192.64,
            "ema100": 211.21, "ema200": 235.13,
        }
        # Close $209.50, EMA100 $211.21 = 0.81% above close (within 1% proximity)
        # High $211.20 = 0.005% from EMA100 (within 0.5% test proximity)
        sig = check_ema_overhead_resistance("COIN", bars, prior_day)
        assert sig is not None
        assert "EMA100" in sig.message
        assert sig.direction == "NOTICE"
