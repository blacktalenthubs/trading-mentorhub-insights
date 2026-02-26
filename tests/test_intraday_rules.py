"""Unit tests for intraday alert rules — all 8 rules with synthetic data."""

import pandas as pd
import pytest

from analytics.intraday_rules import (
    AlertSignal,
    AlertType,
    _should_skip_noise,
    check_auto_stop_out,
    check_ema_crossover_5_20,
    check_inside_day_breakout,
    check_ma_bounce_20,
    check_ma_bounce_50,
    check_prior_day_low_reclaim,
    check_resistance_prior_high,
    check_stop_loss_hit,
    check_support_breakdown,
    check_target_1_hit,
    check_target_2_hit,
    evaluate_rules,
)


def _bar(open_=100, high=101, low=99, close=100.5, volume=1000) -> pd.Series:
    """Create a synthetic OHLCV bar."""
    return pd.Series({
        "Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume,
    })


def _bars(rows: list[dict]) -> pd.DataFrame:
    """Create a synthetic DataFrame of OHLCV bars."""
    return pd.DataFrame(rows)


# ===== Rule 1: MA Bounce 20MA =====

class TestMABounce20:
    def test_fires_when_bar_low_touches_ma20_and_closes_above(self):
        bar = _bar(open_=100, high=101, low=99.98, close=100.3)
        sig = check_ma_bounce_20("AAPL", bar, ma20=100.0, ma50=95.0)
        assert sig is not None
        assert sig.alert_type == AlertType.MA_BOUNCE_20
        assert sig.direction == "BUY"
        assert sig.entry == 100.3

    def test_no_fire_when_close_below_ma20(self):
        bar = _bar(open_=100, high=101, low=99.98, close=99.8)
        sig = check_ma_bounce_20("AAPL", bar, ma20=100.0, ma50=95.0)
        assert sig is None

    def test_no_fire_when_not_in_uptrend(self):
        bar = _bar(open_=100, high=101, low=99.98, close=100.3)
        sig = check_ma_bounce_20("AAPL", bar, ma20=94.0, ma50=95.0)  # ma20 < ma50
        assert sig is None

    def test_no_fire_when_bar_low_too_far_from_ma20(self):
        bar = _bar(open_=100, high=101, low=98.0, close=100.3)
        sig = check_ma_bounce_20("AAPL", bar, ma20=100.0, ma50=95.0)
        assert sig is None

    def test_no_fire_when_ma_missing(self):
        bar = _bar()
        assert check_ma_bounce_20("X", bar, ma20=None, ma50=95.0) is None
        assert check_ma_bounce_20("X", bar, ma20=100.0, ma50=None) is None

    def test_high_confidence_when_very_close_to_ma(self):
        bar = _bar(open_=100, high=101, low=100.05, close=100.3)
        sig = check_ma_bounce_20("AAPL", bar, ma20=100.0, ma50=95.0)
        assert sig is not None
        assert sig.confidence == "high"

    def test_targets_are_1r_and_2r(self):
        bar = _bar(open_=100, high=101, low=99.98, close=100.3)
        sig = check_ma_bounce_20("AAPL", bar, ma20=100.0, ma50=95.0)
        assert sig is not None
        risk = sig.entry - sig.stop
        assert risk > 0
        assert abs(sig.target_1 - (sig.entry + risk)) < 0.01
        assert abs(sig.target_2 - (sig.entry + 2 * risk)) < 0.01


# ===== Rule 2: MA Bounce 50MA =====

class TestMABounce50:
    def test_fires_on_pullback_to_50ma(self):
        bar = _bar(open_=95, high=96, low=94.98, close=95.3)
        sig = check_ma_bounce_50("NVDA", bar, ma20=98.0, ma50=95.0, prior_close=96.0)
        assert sig is not None
        assert sig.alert_type == AlertType.MA_BOUNCE_50
        assert sig.direction == "BUY"

    def test_no_fire_when_prior_close_below_50ma(self):
        bar = _bar(open_=95, high=96, low=94.98, close=95.3)
        sig = check_ma_bounce_50("NVDA", bar, ma20=98.0, ma50=95.0, prior_close=94.0)
        assert sig is None  # breakdown, not pullback

    def test_no_fire_when_close_below_50ma(self):
        bar = _bar(open_=95, high=96, low=94.98, close=94.5)
        sig = check_ma_bounce_50("NVDA", bar, ma20=98.0, ma50=95.0, prior_close=96.0)
        assert sig is None

    def test_no_fire_when_ma50_missing(self):
        bar = _bar()
        assert check_ma_bounce_50("X", bar, ma20=100.0, ma50=None, prior_close=96.0) is None


# ===== Rule 3: Prior Day Low Reclaim =====

class TestPriorDayLowReclaim:
    def test_fires_on_dip_and_reclaim(self):
        bars = _bars([
            {"Open": 100, "High": 100.5, "Low": 98.5, "Close": 99.0, "Volume": 1000},
            {"Open": 99.0, "High": 100.2, "Low": 98.8, "Close": 100.1, "Volume": 1200},
        ])
        sig = check_prior_day_low_reclaim("META", bars, prior_day_low=99.0)
        assert sig is not None
        assert sig.alert_type == AlertType.PRIOR_DAY_LOW_RECLAIM
        assert sig.direction == "BUY"

    def test_no_fire_when_no_dip_below_prior_low(self):
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.5, "Close": 100.5, "Volume": 1000},
        ])
        sig = check_prior_day_low_reclaim("META", bars, prior_day_low=99.0)
        assert sig is None

    def test_no_fire_when_still_below_prior_low(self):
        bars = _bars([
            {"Open": 100, "High": 100.5, "Low": 98.0, "Close": 98.5, "Volume": 1000},
        ])
        sig = check_prior_day_low_reclaim("META", bars, prior_day_low=99.0)
        assert sig is None  # closed below, hasn't reclaimed

    def test_empty_bars_returns_none(self):
        assert check_prior_day_low_reclaim("X", pd.DataFrame(), prior_day_low=99.0) is None


# ===== Rule 4: Inside Day Breakout =====

class TestInsideDayBreakout:
    def test_fires_on_breakout_above_inside_high(self):
        bar = _bar(open_=50, high=51.5, low=49.5, close=51.2)
        prior = {
            "is_inside": True, "high": 50.5, "low": 49.0,
            "parent_high": 52.0, "parent_low": 48.0,
        }
        sig = check_inside_day_breakout("TSLA", bar, prior)
        assert sig is not None
        assert sig.alert_type == AlertType.INSIDE_DAY_BREAKOUT
        assert sig.direction == "BUY"
        assert sig.entry == 50.5  # inside high
        assert sig.stop == 49.0   # inside low

    def test_target_1_equals_inside_range(self):
        bar = _bar(open_=50, high=51.5, low=49.5, close=51.2)
        prior = {
            "is_inside": True, "high": 50.5, "low": 49.0,
            "parent_high": 52.0, "parent_low": 48.0,
        }
        sig = check_inside_day_breakout("TSLA", bar, prior)
        inside_range = 50.5 - 49.0
        assert abs(sig.target_1 - (50.5 + inside_range)) < 0.01

    def test_target_2_equals_parent_range(self):
        bar = _bar(open_=50, high=51.5, low=49.5, close=51.2)
        prior = {
            "is_inside": True, "high": 50.5, "low": 49.0,
            "parent_high": 52.0, "parent_low": 48.0,
        }
        sig = check_inside_day_breakout("TSLA", bar, prior)
        parent_range = 52.0 - 48.0
        assert abs(sig.target_2 - (50.5 + parent_range)) < 0.01

    def test_no_fire_when_not_inside_day(self):
        bar = _bar(open_=50, high=51.5, low=49.5, close=51.2)
        prior = {"is_inside": False, "high": 50.5, "low": 49.0,
                 "parent_high": 52.0, "parent_low": 48.0}
        assert check_inside_day_breakout("TSLA", bar, prior) is None

    def test_no_fire_when_close_below_inside_high(self):
        bar = _bar(open_=50, high=50.3, low=49.5, close=50.2)
        prior = {"is_inside": True, "high": 50.5, "low": 49.0,
                 "parent_high": 52.0, "parent_low": 48.0}
        assert check_inside_day_breakout("TSLA", bar, prior) is None

    def test_no_fire_when_prior_day_none(self):
        bar = _bar()
        assert check_inside_day_breakout("X", bar, None) is None


# ===== Rule 5: Resistance at Prior High =====

class TestResistancePriorHigh:
    def test_fires_when_near_prior_high_with_active_entry(self):
        bar = _bar(high=100.15)
        sig = check_resistance_prior_high("SPY", bar, prior_day_high=100.0, has_active_entry=True)
        assert sig is not None
        assert sig.alert_type == AlertType.RESISTANCE_PRIOR_HIGH
        assert sig.direction == "SELL"

    def test_no_fire_without_active_entry(self):
        bar = _bar(high=100.15)
        sig = check_resistance_prior_high("SPY", bar, prior_day_high=100.0, has_active_entry=False)
        assert sig is None

    def test_no_fire_when_too_far_from_prior_high(self):
        bar = _bar(high=99.0)
        sig = check_resistance_prior_high("SPY", bar, prior_day_high=100.0, has_active_entry=True)
        assert sig is None


# ===== Rule 6: Target 1 Hit =====

class TestTarget1Hit:
    def test_fires_when_high_reaches_target(self):
        bar = _bar(high=102.0)
        sig = check_target_1_hit("LRCX", bar, entry_price=100.0, target_1=101.5)
        assert sig is not None
        assert sig.alert_type == AlertType.TARGET_1_HIT
        assert sig.direction == "SELL"

    def test_no_fire_when_below_target(self):
        bar = _bar(high=101.0)
        sig = check_target_1_hit("LRCX", bar, entry_price=100.0, target_1=101.5)
        assert sig is None


# ===== Rule 7: Target 2 Hit =====

class TestTarget2Hit:
    def test_fires_when_high_reaches_target_2(self):
        bar = _bar(high=103.5)
        sig = check_target_2_hit("LRCX", bar, entry_price=100.0, target_2=103.0)
        assert sig is not None
        assert sig.alert_type == AlertType.TARGET_2_HIT

    def test_no_fire_when_below_target_2(self):
        bar = _bar(high=102.0)
        sig = check_target_2_hit("LRCX", bar, entry_price=100.0, target_2=103.0)
        assert sig is None


# ===== Rule 8: Stop Loss Hit =====

class TestStopLossHit:
    def test_fires_when_low_hits_stop(self):
        bar = _bar(low=98.5)
        sig = check_stop_loss_hit("AMD", bar, entry_price=100.0, stop_price=99.0)
        assert sig is not None
        assert sig.alert_type == AlertType.STOP_LOSS_HIT
        assert sig.direction == "SELL"

    def test_no_fire_when_above_stop(self):
        bar = _bar(low=99.5)
        sig = check_stop_loss_hit("AMD", bar, entry_price=100.0, stop_price=99.0)
        assert sig is None

    def test_message_includes_loss_amount(self):
        bar = _bar(low=98.5)
        sig = check_stop_loss_hit("AMD", bar, entry_price=100.0, stop_price=99.0)
        assert "$1.00" in sig.message


# ===== Orchestrator =====

class TestEvaluateRules:
    def test_returns_empty_on_empty_bars(self):
        assert evaluate_rules("X", pd.DataFrame(), {}) == []

    def test_returns_empty_on_none_prior_day(self):
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99, "Close": 100.5, "Volume": 1000},
        ])
        assert evaluate_rules("X", bars, None) == []

    def test_buy_signals_fire_without_active_entries(self):
        """MA bounce should fire even without active entries."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 99.0, "is_inside": False,
        }
        signals = evaluate_rules("AAPL", bars, prior)
        buy_signals = [s for s in signals if s.direction == "BUY"]
        assert len(buy_signals) >= 1

    def test_sell_signals_need_active_entries(self):
        """Target/stop rules should only fire with active entries."""
        bars = _bars([
            {"Open": 100, "High": 102, "Low": 99, "Close": 101.5, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.5, "low": 99.0, "is_inside": False,
        }
        # Without active entries — no sell signals from targets
        signals = evaluate_rules("AAPL", bars, prior, active_entries=None)
        sell_from_targets = [
            s for s in signals
            if s.alert_type in (AlertType.TARGET_1_HIT, AlertType.TARGET_2_HIT,
                                AlertType.STOP_LOSS_HIT)
        ]
        assert len(sell_from_targets) == 0

    def test_sell_signals_fire_with_active_entries(self):
        """Target hit should fire when active entry exists and price reaches target."""
        bars = _bars([
            {"Open": 100, "High": 103, "Low": 99.5, "Close": 102.5, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 102.0, "low": 99.0, "is_inside": False,
        }
        entries = [{"entry_price": 100.0, "stop_price": 99.0,
                     "target_1": 101.0, "target_2": 102.0}]
        signals = evaluate_rules("AAPL", bars, prior, active_entries=entries)
        types = {s.alert_type for s in signals}
        assert AlertType.TARGET_1_HIT in types
        assert AlertType.TARGET_2_HIT in types


# ===== Rule 9: Support Breakdown =====

class TestSupportBreakdown:
    def test_fires_on_high_volume(self):
        """Close below support, vol >= 1.5x, conviction close → fires SHORT."""
        bar = _bar(open_=99, high=99.5, low=97.5, close=97.6, volume=2000)
        sig = check_support_breakdown(
            "META", bar, prior_day_low=98.0, nearest_support=99.0,
            bar_volume=2000, avg_volume=1000,
        )
        assert sig is not None
        assert sig.alert_type == AlertType.SUPPORT_BREAKDOWN
        assert sig.direction == "SHORT"
        assert sig.stop == 98.0  # min(98, 99) = 98 = broken support
        assert sig.entry == 97.6

    def test_skips_low_volume(self):
        """Close below support but vol < 1.5x → None."""
        bar = _bar(open_=99, high=99.5, low=97.5, close=97.6, volume=500)
        sig = check_support_breakdown(
            "META", bar, prior_day_low=98.0, nearest_support=99.0,
            bar_volume=500, avg_volume=1000,
        )
        assert sig is None

    def test_skips_no_conviction(self):
        """Close below support, high vol, but close in upper range → None."""
        # Close in upper half of bar range (close_position > 0.30)
        bar = _bar(open_=99, high=99.5, low=97.0, close=98.5, volume=2000)
        # close_position = (98.5 - 97.0) / (99.5 - 97.0) = 1.5 / 2.5 = 0.60
        sig = check_support_breakdown(
            "META", bar, prior_day_low=99.0, nearest_support=0,
            bar_volume=2000, avg_volume=1000,
        )
        assert sig is None


# ===== Rule 10: EMA Crossover 5/20 =====

class TestEMACrossover:
    @staticmethod
    def _make_crossover_bars(num_bars=30, cross=True):
        """Build bars where EMA5 crosses above EMA20 at the last bar.

        Strategy: declining prices for most bars (EMA5 < EMA20 since it's
        faster to react), then a sharp reversal at the end to force crossover.
        """
        # Decline for first 25 bars so EMA5 << EMA20
        prices = [100.0 - 0.3 * i for i in range(num_bars)]
        if cross:
            # Sharp uptick on last 3 bars to force EMA5 above EMA20
            prices[-3] = prices[-4] + 3.0
            prices[-2] = prices[-3] + 3.0
            prices[-1] = prices[-2] + 4.0
        rows = []
        for p in prices:
            rows.append({
                "Open": p - 0.1, "High": p + 0.2, "Low": p - 0.3,
                "Close": p, "Volume": 1000,
            })
        return pd.DataFrame(rows)

    def test_fires_for_mega_cap(self):
        """EMA5 crosses above EMA20 on mega-cap → fires BUY."""
        bars = self._make_crossover_bars(num_bars=30, cross=True)
        sig = check_ema_crossover_5_20("AAPL", bars, is_mega_cap=True)
        assert sig is not None
        assert sig.alert_type == AlertType.EMA_CROSSOVER_5_20
        assert sig.direction == "BUY"
        assert sig.confidence == "high"

    def test_skips_non_mega_cap(self):
        """Crossover on non-mega-cap → None."""
        bars = self._make_crossover_bars(num_bars=30, cross=True)
        sig = check_ema_crossover_5_20("ONDS", bars, is_mega_cap=False)
        assert sig is None

    def test_skips_insufficient_bars(self):
        """Fewer than 25 bars → None."""
        bars = self._make_crossover_bars(num_bars=20, cross=True)
        sig = check_ema_crossover_5_20("AAPL", bars, is_mega_cap=True)
        assert sig is None


# ===== Rule 11: Auto Stop-Out =====

class TestAutoStopOut:
    def test_fires_when_stop_hit(self):
        """Bar low <= stop price → fires SELL."""
        bar = _bar(low=98.5)
        entry = {"entry_price": 100.0, "stop_price": 99.0, "alert_type": "ma_bounce_20"}
        sig = check_auto_stop_out("AMD", bar, entry)
        assert sig is not None
        assert sig.alert_type == AlertType.AUTO_STOP_OUT
        assert sig.direction == "SELL"
        assert "$1.00" in sig.message

    def test_skips_when_above_stop(self):
        """Bar low > stop price → None."""
        bar = _bar(low=99.5)
        entry = {"entry_price": 100.0, "stop_price": 99.0, "alert_type": "ma_bounce_20"}
        sig = check_auto_stop_out("AMD", bar, entry)
        assert sig is None


# ===== Noise Filter =====

class TestNoiseFilter:
    def test_skips_low_volume_buy(self):
        """BUY signal with vol ratio < 0.4 → filtered out."""
        sig = AlertSignal(
            symbol="X", alert_type=AlertType.MA_BOUNCE_20,
            direction="BUY", price=100.0,
        )
        assert _should_skip_noise(sig, vol_ratio=0.3) is True

    def test_keeps_sell_signals(self):
        """SELL signal with low volume → kept (not filtered)."""
        sig = AlertSignal(
            symbol="X", alert_type=AlertType.STOP_LOSS_HIT,
            direction="SELL", price=100.0,
        )
        assert _should_skip_noise(sig, vol_ratio=0.3) is False
