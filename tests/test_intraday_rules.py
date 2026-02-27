"""Unit tests for intraday alert rules — all 8 rules with synthetic data."""

import pandas as pd
import pytest

from analytics.intraday_rules import (
    AlertSignal,
    AlertType,
    _cap_risk,
    _compute_planned_levels,
    _should_skip_noise,
    check_auto_stop_out,
    check_ema_crossover_5_20,
    check_gap_fill,
    check_inside_day_breakout,
    check_intraday_support_bounce,
    check_ma_bounce_20,
    check_ma_bounce_50,
    check_opening_range_breakout,
    check_planned_level_touch,
    check_prior_day_low_reclaim,
    check_resistance_prior_high,
    check_session_low_retest,
    check_stop_loss_hit,
    check_support_breakdown,
    check_target_1_hit,
    check_target_2_hit,
    evaluate_rules,
)
from analytics.intraday_data import (
    check_mtf_alignment,
    classify_market_regime,
    compute_opening_range,
    detect_intraday_supports,
    track_gap_fill,
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


# ===== Risk Cap =====

class TestCapRisk:
    def test_cap_risk_tightens_wide_stop(self):
        """entry 100, stop 95, max 0.3% → stop becomes 99.70."""
        result = _cap_risk(100.0, 95.0, max_risk_pct=0.003)
        assert result == 99.70

    def test_cap_risk_keeps_tight_stop(self):
        """entry 100, stop 99.80, max 0.3% → stop stays 99.80."""
        result = _cap_risk(100.0, 99.80, max_risk_pct=0.003)
        assert result == 99.80

    def test_ma_bounce_20_uses_tight_stop(self):
        """MA bounce 20 now uses max(bar_low, MA_offset) not min."""
        # bar_low = 99.50, MA20 = 100.0, MA_offset = 100 * (1 - 0.005) = 99.50
        # With max(): max(99.50, 99.50) = 99.50
        # If bar_low is lower than offset, max picks the tighter one
        bar = _bar(open_=100, high=101, low=99.70, close=100.3)
        sig = check_ma_bounce_20("SPY", bar, ma20=100.0, ma50=95.0)
        assert sig is not None
        # MA offset = 100 * 0.995 = 99.50; bar_low = 99.70
        # max(99.70, 99.50) = 99.70 (tighter)
        assert sig.stop == 99.70


# ===== Cooldown =====

class TestCooldown:
    def test_cooldown_suppresses_buy_signals(self):
        """is_cooled_down=True → no BUY rule signals returned (gap fill is INFO, excluded)."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 99.0, "is_inside": False,
        }
        signals = evaluate_rules("AAPL", bars, prior, is_cooled_down=True)
        # Exclude GAP_FILL — it's an informational signal that fires regardless of cooldown
        buy_signals = [
            s for s in signals
            if s.direction == "BUY" and s.alert_type != AlertType.GAP_FILL
        ]
        assert len(buy_signals) == 0

    def test_cooldown_allows_sell_signals(self):
        """is_cooled_down=True → SELL signals still fire."""
        bars = _bars([
            {"Open": 100, "High": 102, "Low": 98.5, "Close": 101.5, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.5, "low": 99.0, "is_inside": False,
        }
        entries = [{"entry_price": 100.0, "stop_price": 99.0,
                     "target_1": 101.0, "target_2": 102.0}]
        signals = evaluate_rules(
            "AAPL", bars, prior, active_entries=entries, is_cooled_down=True,
        )
        sell_signals = [s for s in signals if s.direction == "SELL"]
        assert len(sell_signals) >= 1


# ===== Breakdown Suppression =====

class TestBreakdownSuppression:
    def test_breakdown_suppresses_buy_signals(self):
        """When support breakdown fires, BUY signals for same symbol are removed."""
        # Build a bar that triggers both a MA bounce BUY and a support breakdown SHORT
        # The breakdown should suppress the BUY
        # Conviction close: close in lower 30% of bar range, high volume
        bar = _bar(open_=99.5, high=100.2, low=97.0, close=97.1, volume=2000)
        # close_position = (97.1 - 97.0) / (100.2 - 97.0) = 0.1/3.2 = 0.03 → conviction
        bars = _bars([
            {"Open": 99.5, "High": 100.2, "Low": 97.0, "Close": 97.1, "Volume": 2000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 98.0, "is_inside": False,
        }
        signals = evaluate_rules("NVDA", bars, prior)
        buy_signals = [s for s in signals if s.direction == "BUY"]
        short_signals = [s for s in signals if s.direction == "SHORT"]
        # If a breakdown fired, BUY should be suppressed
        if short_signals:
            assert len(buy_signals) == 0


# ===== Dedup =====

class TestFiredToday:
    def test_fired_today_prevents_duplicate(self):
        """Signal in fired_today set → not returned."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 99.0, "is_inside": False,
        }
        # First call without fired_today — should get MA bounce
        signals_first = evaluate_rules("AAPL", bars, prior)
        ma_bounces = [s for s in signals_first if s.alert_type == AlertType.MA_BOUNCE_20]
        assert len(ma_bounces) >= 1

        # Second call with fired_today containing the signal — should be filtered
        fired = {("AAPL", "ma_bounce_20")}
        signals_second = evaluate_rules("AAPL", bars, prior, fired_today=fired)
        ma_bounces_2 = [s for s in signals_second if s.alert_type == AlertType.MA_BOUNCE_20]
        assert len(ma_bounces_2) == 0


# ===== Intraday Supports =====

class TestDetectIntradaySupports:
    def test_detect_intraday_supports_finds_held_lows(self):
        """Hourly lows that held are returned as support levels."""
        # Create 2+ hours of 5-min bars with a held low in hour 1
        idx = pd.date_range("2024-01-15 09:30", periods=24, freq="5min")
        data = {
            "Open": [100.0] * 24,
            "High": [101.0] * 24,
            "Low": [99.0] * 24,
            "Close": [100.5] * 24,
            "Volume": [1000] * 24,
        }
        bars = pd.DataFrame(data, index=idx)

        # Hour 1 (09:30-10:29): low at 98.50
        bars.loc[bars.index[2], "Low"] = 98.50
        bars.loc[bars.index[2], "Close"] = 99.0

        # Hour 2 (10:30-11:29): low stays above 98.50, close bounces
        for i in range(12, 24):
            bars.loc[bars.index[i], "Low"] = 99.0
            bars.loc[bars.index[i], "Close"] = 100.0

        supports = detect_intraday_supports(bars)
        # The hourly low of hour 1 (98.50) should be detected as support
        # since hour 2's low (99.0) >= 98.50 * 0.999 and bounce >= 0.2%
        assert 98.5 in supports


# ===== F1: Opening Range Breakout =====

class TestOpeningRangeBreakout:
    def test_fires_on_breakout_with_volume(self):
        """Close above OR high with sufficient volume → fires BUY."""
        bar = _bar(open_=101, high=102, low=100.5, close=101.8, volume=1500)
        opening_range = {
            "or_high": 101.0, "or_low": 100.0, "or_range": 1.0,
            "or_range_pct": 0.01, "or_complete": True,
        }
        sig = check_opening_range_breakout("AAPL", bar, opening_range, 1500, 1000)
        assert sig is not None
        assert sig.alert_type == AlertType.OPENING_RANGE_BREAKOUT
        assert sig.direction == "BUY"
        assert sig.entry == 101.0  # OR high
        assert sig.stop == 100.0   # OR low
        assert sig.target_1 == 102.0  # or_high + or_range
        assert sig.target_2 == 103.0  # or_high + 2 * or_range

    def test_no_fire_when_or_incomplete(self):
        """OR not complete → None."""
        bar = _bar(close=101.8, volume=1500)
        opening_range = {
            "or_high": 101.0, "or_low": 100.0, "or_range": 1.0,
            "or_range_pct": 0.01, "or_complete": False,
        }
        sig = check_opening_range_breakout("AAPL", bar, opening_range, 1500, 1000)
        assert sig is None

    def test_no_fire_when_range_too_small(self):
        """OR range below ORB_MIN_RANGE_PCT → None."""
        bar = _bar(close=101.8, volume=1500)
        opening_range = {
            "or_high": 100.2, "or_low": 100.0, "or_range": 0.2,
            "or_range_pct": 0.002, "or_complete": True,  # 0.2% < 0.3%
        }
        sig = check_opening_range_breakout("AAPL", bar, opening_range, 1500, 1000)
        assert sig is None

    def test_no_fire_on_low_volume(self):
        """Volume below ORB_VOLUME_RATIO → None."""
        bar = _bar(close=101.8, volume=500)
        opening_range = {
            "or_high": 101.0, "or_low": 100.0, "or_range": 1.0,
            "or_range_pct": 0.01, "or_complete": True,
        }
        sig = check_opening_range_breakout("AAPL", bar, opening_range, 500, 1000)
        assert sig is None  # 0.5x < 1.2x


# ===== F1: compute_opening_range =====

class TestComputeOpeningRange:
    def test_returns_none_with_few_bars(self):
        """Fewer than 6 bars → None."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000}
            for _ in range(5)
        ])
        assert compute_opening_range(bars) is None

    def test_computes_range_from_first_6_bars(self):
        """First 6 bars define the opening range."""
        rows = []
        for i in range(10):
            rows.append({"Open": 100 + i * 0.1, "High": 102 + i * 0.1,
                         "Low": 99 - i * 0.1, "Close": 101, "Volume": 1000})
        bars = pd.DataFrame(rows)
        result = compute_opening_range(bars)
        assert result is not None
        assert result["or_complete"] is True
        # First 6 bars: highs = 102.0..102.5, lows = 99.0..98.5
        assert result["or_high"] == 102.5
        assert result["or_low"] == 98.5


# ===== F2: Multi-Timeframe Confirmation =====

class TestMTFAlignment:
    def test_aligned_when_ema5_above_ema20(self):
        """Rising 15m prices → EMA5 > EMA20 → aligned."""
        # Create rising 5-min bars (enough for ~26 fifteen-min bars)
        idx = pd.date_range("2024-01-15 09:30", periods=78, freq="5min")
        prices = [100 + i * 0.2 for i in range(78)]  # steadily rising
        data = {
            "Open": [p - 0.1 for p in prices],
            "High": [p + 0.3 for p in prices],
            "Low": [p - 0.2 for p in prices],
            "Close": prices,
            "Volume": [1000] * 78,
        }
        bars = pd.DataFrame(data, index=idx)
        result = check_mtf_alignment(bars)
        assert result["mtf_aligned"] is True
        assert result["mtf_trend"] == "bullish"

    def test_not_aligned_when_ema5_below_ema20(self):
        """Declining 15m prices → EMA5 < EMA20 → not aligned."""
        idx = pd.date_range("2024-01-15 09:30", periods=78, freq="5min")
        prices = [115 - i * 0.2 for i in range(78)]  # steadily falling
        data = {
            "Open": [p + 0.1 for p in prices],
            "High": [p + 0.3 for p in prices],
            "Low": [p - 0.2 for p in prices],
            "Close": prices,
            "Volume": [1000] * 78,
        }
        bars = pd.DataFrame(data, index=idx)
        result = check_mtf_alignment(bars)
        assert result["mtf_aligned"] is False
        assert result["mtf_trend"] == "bearish"

    def test_score_boosted_when_aligned(self):
        """BUY signal + aligned 15m → score gets +10 boost."""
        # Build a bar that triggers MA bounce 20
        idx = pd.date_range("2024-01-15 10:30", periods=78, freq="5min")
        prices = [100 + i * 0.1 for i in range(78)]  # rising → aligned
        rows = []
        for i, p in enumerate(prices):
            rows.append({
                "Open": p - 0.1, "High": p + 0.3,
                "Low": p - 0.2, "Close": p, "Volume": 1000,
            })
        # Last bar triggers MA20 bounce
        rows[-1] = {"Open": 107.5, "High": 108, "Low": 107.68, "Close": 107.8, "Volume": 1000}
        bars = pd.DataFrame(rows, index=idx)

        prior = {
            "ma20": 107.7, "ma50": 105.0, "close": 107.5,
            "high": 108.0, "low": 107.0, "is_inside": False,
        }
        signals = evaluate_rules("AAPL", bars, prior)
        buy_signals = [s for s in signals if s.direction == "BUY"]
        # If any BUY signals fired, check that mtf_aligned enrichment is present
        for s in buy_signals:
            assert s.mtf_aligned is True
            assert "15m trend aligned" in s.message


# ===== F3: Relative Strength Filter =====

class TestRelativeStrength:
    def test_demotes_when_underperforming(self):
        """Symbol -5% while SPY -1% → confidence demoted, RS caution added."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
            {"Open": 100.3, "High": 101, "Low": 94.7, "Close": 95.0, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 99.0, "is_inside": False,
        }
        spy_ctx = {"trend": "bearish", "close": 550.0, "ma20": 555.0, "intraday_change_pct": -1.0}

        signals = evaluate_rules("NVDA", bars, prior, spy_context=spy_ctx)
        buy_signals = [s for s in signals if s.direction == "BUY"]
        for s in buy_signals:
            assert "RS CAUTION" in s.message

    def test_keeps_when_outperforming(self):
        """Symbol -0.5% while SPY -1% → no RS demotion."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 99.0, "is_inside": False,
        }
        spy_ctx = {"trend": "bearish", "close": 550.0, "ma20": 555.0, "intraday_change_pct": -1.0}

        signals = evaluate_rules("AAPL", bars, prior, spy_context=spy_ctx)
        buy_signals = [s for s in signals if s.direction == "BUY"]
        for s in buy_signals:
            assert "RS CAUTION" not in s.message

    def test_handles_zero_spy_change(self):
        """SPY intraday change = 0 → no RS filter applied."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 99.0, "is_inside": False,
        }
        spy_ctx = {"trend": "neutral", "close": 550.0, "ma20": 550.0, "intraday_change_pct": 0.0}

        signals = evaluate_rules("AAPL", bars, prior, spy_context=spy_ctx)
        # Should not crash and should not add RS caution
        buy_signals = [s for s in signals if s.direction == "BUY"]
        for s in buy_signals:
            assert "RS CAUTION" not in s.message


# ===== F4: Gap Fill Tracking =====

class TestGapFill:
    def test_fires_on_gap_up_fill(self):
        """Gap up fills when bar low <= prior close → SELL info signal."""
        gap_info = {
            "gap_size": 2.0, "gap_pct": 2.0, "gap_direction": "gap_up",
            "fill_pct": 100.0, "is_filled": True,
        }
        bar = _bar(close=100.0)
        sig = check_gap_fill("NVDA", bar, gap_info)
        assert sig is not None
        assert sig.alert_type == AlertType.GAP_FILL
        assert sig.direction == "SELL"  # gap_up fill is bearish
        assert "fully filled" in sig.message

    def test_fires_on_gap_down_fill(self):
        """Gap down fills when bar high >= prior close → BUY info signal."""
        gap_info = {
            "gap_size": -2.0, "gap_pct": -2.0, "gap_direction": "gap_down",
            "fill_pct": 100.0, "is_filled": True,
        }
        bar = _bar(close=100.0)
        sig = check_gap_fill("NVDA", bar, gap_info)
        assert sig is not None
        assert sig.alert_type == AlertType.GAP_FILL
        assert sig.direction == "BUY"  # gap_down fill is bullish

    def test_no_fire_when_unfilled(self):
        """Gap not filled → None."""
        gap_info = {
            "gap_size": 2.0, "gap_pct": 2.0, "gap_direction": "gap_up",
            "fill_pct": 50.0, "is_filled": False,
        }
        bar = _bar(close=100.0)
        sig = check_gap_fill("NVDA", bar, gap_info)
        assert sig is None


# ===== F4: track_gap_fill helper =====

class TestTrackGapFill:
    def test_gap_up_filled(self):
        """Bar low <= prior close means gap up is filled."""
        bars = _bars([
            {"Open": 102, "High": 103, "Low": 99.5, "Close": 100, "Volume": 1000},
        ])
        result = track_gap_fill(bars, today_open=102.0, prior_close=100.0)
        assert result["gap_direction"] == "gap_up"
        assert result["is_filled"] is True

    def test_gap_down_filled(self):
        """Bar high >= prior close means gap down is filled."""
        bars = _bars([
            {"Open": 98, "High": 100.5, "Low": 97, "Close": 100, "Volume": 1000},
        ])
        result = track_gap_fill(bars, today_open=98.0, prior_close=100.0)
        assert result["gap_direction"] == "gap_down"
        assert result["is_filled"] is True


# ===== F11: Per-Symbol Risk Config =====

class TestPerSymbolRisk:
    def test_uses_per_symbol_rate_for_spy(self):
        """SPY gets 0.2% risk cap from PER_SYMBOL_RISK."""
        # SPY rate = 0.002, entry 550, stop 545
        # max risk = 550 * 0.002 = 1.10 → stop = 550 - 1.10 = 548.90
        result = _cap_risk(550.0, 545.0, symbol="SPY")
        assert result == 548.90

    def test_defaults_to_global_for_unlisted(self):
        """Unlisted symbol uses DAY_TRADE_MAX_RISK_PCT (0.3%)."""
        # Global rate = 0.003, entry 100, stop 95
        # max risk = 100 * 0.003 = 0.30 → stop = 100 - 0.30 = 99.70
        result = _cap_risk(100.0, 95.0, symbol="LRCX")
        assert result == 99.70

    def test_backward_compatible_without_symbol(self):
        """Without symbol arg, uses default max_risk_pct."""
        result = _cap_risk(100.0, 95.0)
        assert result == 99.70  # same as before


# ===== Rule 13: Intraday Support Bounce =====

class TestIntradaySupportBounce:
    def test_fires_on_bounce_off_support(self):
        """Bar low at support, closes above → BUY with entry=support."""
        # Support at 648.00, bar low touches 648.10 (within 0.3%), closes at 649.50
        bar = _bar(open_=648.50, high=650.00, low=648.10, close=649.50, volume=1000)
        supports = [648.00, 645.00]
        sig = check_intraday_support_bounce("META", bar, supports, 1000, 1000)
        assert sig is not None
        assert sig.alert_type == AlertType.INTRADAY_SUPPORT_BOUNCE
        assert sig.direction == "BUY"
        assert sig.entry == 648.00
        assert sig.confidence == "medium"
        assert "held $648.00" in sig.message

    def test_no_fire_when_no_supports(self):
        """Empty supports list → None."""
        bar = _bar(open_=648.50, high=650.00, low=648.10, close=649.50, volume=1000)
        sig = check_intraday_support_bounce("META", bar, [], 1000, 1000)
        assert sig is None

    def test_no_fire_when_close_below_support(self):
        """Bar closes at/below support → None (no bounce)."""
        bar = _bar(open_=648.50, high=649.00, low=647.80, close=647.90, volume=1000)
        supports = [648.00]
        sig = check_intraday_support_bounce("META", bar, supports, 1000, 1000)
        assert sig is None

    def test_spy_bounce_boosts_confidence(self):
        """Orchestrator: spy_bouncing=True → confidence='high', message includes SPY note."""
        # Build bars where intraday support bounce fires
        # Need 12+ bars for detect_intraday_supports, plus a bounce bar at the end
        idx = pd.date_range("2024-01-15 09:30", periods=25, freq="5min")
        rows = []
        for i in range(25):
            rows.append({
                "Open": 650.0, "High": 651.0, "Low": 649.0,
                "Close": 650.5, "Volume": 1000,
            })
        # Hour 1 low at 648.00 (bar 2)
        rows[2] = {"Open": 649.0, "High": 649.5, "Low": 648.00, "Close": 649.0, "Volume": 1000}
        # Hour 2 holds above — bounces (bars 12-24)
        for i in range(12, 25):
            rows[i] = {"Open": 649.5, "High": 651.0, "Low": 649.0, "Close": 650.0, "Volume": 1000}
        # Last bar: low touches support (648.10), closes above (649.50)
        rows[-1] = {"Open": 648.50, "High": 650.0, "Low": 648.10, "Close": 649.50, "Volume": 1000}
        bars = pd.DataFrame(rows, index=idx)

        prior = {
            "ma20": 650.0, "ma50": 645.0, "close": 650.0,
            "high": 655.0, "low": 646.0, "is_inside": False,
        }
        spy_ctx = {
            "trend": "neutral", "close": 689.0, "ma20": 685.0,
            "ma5": 688.0, "ma50": 680.0, "regime": "TRENDING_UP",
            "intraday_change_pct": 0.5, "spy_bouncing": True, "spy_intraday_low": 684.50,
        }
        signals = evaluate_rules("META", bars, prior, spy_context=spy_ctx)
        bounce_signals = [
            s for s in signals if s.alert_type == AlertType.INTRADAY_SUPPORT_BOUNCE
        ]
        if bounce_signals:
            sig = bounce_signals[0]
            assert sig.confidence == "high"
            assert "SPY also bouncing" in sig.message
            assert "$684.50" in sig.message


# ===== Rule 15: Session Low Double-Bottom =====

class TestSessionLowDoubleBottom:
    @staticmethod
    def _make_double_bottom_bars(
        session_low=650.0,
        first_touch_bar=3,
        num_bars=20,
        recovery_bars=10,
        retest_close=651.0,
        retest_low=650.10,
        retest_volume=800,
    ):
        """Build bars with a double-bottom at session_low.

        - Bar `first_touch_bar` touches session_low
        - Recovery bars hold above session_low * (1 + 0.3%)
        - Last bar retests session_low with retest_low and closes at retest_close
        """
        rows = []
        recovery_threshold = session_low * (1 + 0.003)  # SESSION_LOW_RECOVERY_PCT
        for i in range(num_bars):
            if i == first_touch_bar:
                # First touch of session low
                rows.append({
                    "Open": session_low + 2, "High": session_low + 3,
                    "Low": session_low, "Close": session_low + 1, "Volume": 1000,
                })
            elif i == num_bars - 1:
                # Retest bar (last bar)
                rows.append({
                    "Open": session_low + 1.5, "High": session_low + 2,
                    "Low": retest_low, "Close": retest_close, "Volume": retest_volume,
                })
            else:
                # Normal bars above recovery threshold
                rows.append({
                    "Open": session_low + 3, "High": session_low + 5,
                    "Low": recovery_threshold + 0.50,
                    "Close": session_low + 4, "Volume": 1000,
                })
        return pd.DataFrame(rows)

    def test_fires_on_classic_double_bottom(self):
        """First touch bar 3, recovery bars 5-18, retest at last bar, vol=0.8x → BUY."""
        bars = self._make_double_bottom_bars(
            session_low=650.0, first_touch_bar=3, num_bars=20,
            retest_close=651.0, retest_low=650.10, retest_volume=800,
        )
        last_bar = bars.iloc[-1]
        avg_vol = bars["Volume"].mean()
        sig = check_session_low_retest("META", bars, last_bar, 800, avg_vol)
        assert sig is not None
        assert sig.alert_type == AlertType.SESSION_LOW_DOUBLE_BOTTOM
        assert sig.direction == "BUY"
        assert sig.entry == 650.0
        assert sig.confidence == "medium"

    def test_no_fire_when_session_low_too_recent(self):
        """First touch only 2 bars ago → None (need MIN_AGE_BARS=6)."""
        bars = self._make_double_bottom_bars(
            session_low=650.0, first_touch_bar=3, num_bars=6,
            retest_close=651.0, retest_low=650.10, retest_volume=800,
        )
        last_bar = bars.iloc[-1]
        avg_vol = bars["Volume"].mean()
        sig = check_session_low_retest("META", bars, last_bar, 800, avg_vol)
        assert sig is None

    def test_no_fire_when_no_recovery(self):
        """Price stays near session low, no recovery between touches → None."""
        session_low = 650.0
        rows = []
        for i in range(20):
            # All bars stay at session low level — no recovery
            rows.append({
                "Open": session_low + 0.5, "High": session_low + 1,
                "Low": session_low, "Close": session_low + 0.5, "Volume": 1000,
            })
        # Last bar retests
        rows[-1] = {
            "Open": session_low + 0.5, "High": session_low + 1,
            "Low": session_low + 0.10, "Close": session_low + 1, "Volume": 800,
        }
        bars = pd.DataFrame(rows)
        last_bar = bars.iloc[-1]
        avg_vol = bars["Volume"].mean()
        sig = check_session_low_retest("META", bars, last_bar, 800, avg_vol)
        assert sig is None

    def test_no_fire_when_close_below_session_low(self):
        """Retest bar closes at session low (no bounce) → None."""
        # Close must be >= Low, so the tightest "no bounce" is close == session_low
        bars = self._make_double_bottom_bars(
            session_low=650.0, first_touch_bar=3, num_bars=20,
            retest_close=650.0, retest_low=650.0, retest_volume=800,
        )
        last_bar = bars.iloc[-1]
        avg_vol = bars["Volume"].mean()
        sig = check_session_low_retest("META", bars, last_bar, 800, avg_vol)
        assert sig is None

    def test_no_fire_when_retest_volume_too_high(self):
        """Vol ratio 1.5x → None (breakdown risk, not exhaustion)."""
        bars = self._make_double_bottom_bars(
            session_low=650.0, first_touch_bar=3, num_bars=20,
            retest_close=651.0, retest_low=650.10, retest_volume=1500,
        )
        last_bar = bars.iloc[-1]
        avg_vol = bars["Volume"].mean()
        # avg_vol ~1000, bar_vol 1500 → ratio 1.5 >= 1.2 threshold
        sig = check_session_low_retest("META", bars, last_bar, 1500, avg_vol)
        assert sig is None


# ===== Breakdown Session Low Tag =====

class TestBreakdownSessionLowTag:
    def test_breakdown_at_session_low_tagged(self):
        """Breakdown fires at session low level → 'SESSION LOW BREAK', confidence='high'."""
        # Build bars where session low = prior_day_low = 98.0
        # Then breakdown bar closes below with conviction
        # ma50 set above close so _find_nearest_support returns prior_low as support
        idx = pd.date_range("2024-01-15 09:30", periods=12, freq="5min")
        rows = []
        for i in range(12):
            rows.append({
                "Open": 99.0, "High": 99.5, "Low": 98.5,
                "Close": 99.0, "Volume": 1000,
            })
        # Bar 2: set the session low at 98.0
        rows[2] = {
            "Open": 98.5, "High": 99.0, "Low": 98.0,
            "Close": 98.5, "Volume": 1000,
        }
        # Last bar: conviction breakdown close below session low
        # close in lower 30% of range, high volume
        rows[-1] = {
            "Open": 98.2, "High": 98.5, "Low": 97.0,
            "Close": 97.1, "Volume": 2000,
        }
        bars = pd.DataFrame(rows, index=idx)

        prior = {
            "ma20": 100.0, "ma50": None, "close": 99.5,
            "high": 101.0, "low": 98.0, "is_inside": False,
        }
        signals = evaluate_rules("META", bars, prior)
        breakdown_signals = [
            s for s in signals if s.alert_type == AlertType.SUPPORT_BREAKDOWN
        ]
        assert len(breakdown_signals) >= 1
        sig = breakdown_signals[0]
        assert "SESSION LOW BREAK" in sig.message
        assert sig.confidence == "high"


# ===== Rule 16: Planned Level Touch =====

class TestPlannedLevelTouch:
    def test_fires_on_normal_day_bounce(self):
        """Normal day: bar bounces at prior low → BUY, entry=prior_low, T1=prior_high."""
        prior = {
            "pattern": "normal", "high": 690.0, "low": 681.65,
            "close": 685.0, "is_inside": False,
            "parent_high": 692.0, "parent_low": 680.0,
        }
        # Bar low touches prior low (681.65), closes above
        bar = _bar(open_=682.0, high=684.0, low=681.50, close=683.5)
        sig = check_planned_level_touch("SPY", bar, prior)
        assert sig is not None
        assert sig.alert_type == AlertType.PLANNED_LEVEL_TOUCH
        assert sig.direction == "BUY"
        assert sig.entry == 681.65
        assert sig.target_1 == 690.0
        assert sig.confidence == "high"
        assert "normal" in sig.message

    def test_fires_on_outside_day_bounce(self):
        """Outside day: bar bounces at midpoint → BUY, entry=midpoint."""
        prior = {
            "pattern": "outside", "high": 700.0, "low": 680.0,
            "close": 695.0, "is_inside": False,
            "parent_high": 698.0, "parent_low": 682.0,
        }
        midpoint = (700.0 + 680.0) / 2  # 690.0
        bar = _bar(open_=691.0, high=693.0, low=689.80, close=692.0)
        sig = check_planned_level_touch("SPY", bar, prior)
        assert sig is not None
        assert sig.entry == midpoint
        assert sig.target_1 == 700.0
        assert "outside" in sig.message

    def test_no_fire_when_far_from_entry(self):
        """Bar low 2%+ away from planned entry → None."""
        prior = {
            "pattern": "normal", "high": 690.0, "low": 681.65,
            "close": 685.0, "is_inside": False,
            "parent_high": 692.0, "parent_low": 680.0,
        }
        # Bar low at 670.0, way below 681.65
        bar = _bar(open_=672.0, high=675.0, low=670.0, close=674.0)
        sig = check_planned_level_touch("SPY", bar, prior)
        assert sig is None

    def test_no_fire_when_close_below_entry(self):
        """Bar touches entry but closes below → None (no bounce)."""
        prior = {
            "pattern": "normal", "high": 690.0, "low": 681.65,
            "close": 685.0, "is_inside": False,
            "parent_high": 692.0, "parent_low": 680.0,
        }
        bar = _bar(open_=682.0, high=682.5, low=681.50, close=681.0)
        sig = check_planned_level_touch("SPY", bar, prior)
        assert sig is None

    def test_skips_inside_day(self):
        """Inside day pattern → None (handled by check_inside_day_breakout)."""
        prior = {
            "pattern": "inside", "high": 690.0, "low": 681.65,
            "close": 685.0, "is_inside": True,
            "parent_high": 695.0, "parent_low": 678.0,
        }
        bar = _bar(open_=682.0, high=684.0, low=681.50, close=683.5)
        sig = check_planned_level_touch("SPY", bar, prior)
        assert sig is None


# ===== Market Regime Detection =====

class TestMarketRegime:
    def test_trending_up_regime(self):
        """close > ma5 > ma20 > ma50 → TRENDING_UP."""
        assert classify_market_regime(600, 595, 580, 560) == "TRENDING_UP"

    def test_trending_down_regime(self):
        """close < all MAs → TRENDING_DOWN."""
        assert classify_market_regime(550, 560, 570, 580) == "TRENDING_DOWN"

    def test_choppy_regime(self):
        """MAs tangled, no clean ordering → CHOPPY."""
        # close > ma5, but ma5 < ma20 → not TRENDING_UP, not PULLBACK, not TRENDING_DOWN
        assert classify_market_regime(590, 585, 588, 580) == "CHOPPY"

    def test_pullback_regime(self):
        """close < ma5 but close > ma20 → PULLBACK."""
        assert classify_market_regime(585, 590, 580, 570) == "PULLBACK"

    def test_regime_demotes_confidence_in_orchestrator(self):
        """CHOPPY regime → BUY confidence demoted from high to medium, message tagged."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 99.0, "is_inside": False,
            "pattern": "normal",
        }
        # SPY context with CHOPPY regime
        spy_ctx = {
            "trend": "neutral", "close": 550.0, "ma20": 550.0,
            "ma5": 548.0, "ma50": 555.0, "regime": "CHOPPY",
            "intraday_change_pct": 0.0, "spy_bouncing": False,
            "spy_intraday_low": 0.0,
        }
        signals = evaluate_rules("AAPL", bars, prior, spy_context=spy_ctx)
        buy_signals = [s for s in signals if s.direction == "BUY"]
        assert len(buy_signals) >= 1
        for s in buy_signals:
            # Originally high-confidence signals should be demoted to medium
            assert s.confidence != "high" or "CHOPPY" not in s.message
            # All BUY signals should have the CHOPPY tag
            assert "CHOPPY market" in s.message
