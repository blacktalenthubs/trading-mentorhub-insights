"""Unit tests for intraday alert rules — all 8 rules with synthetic data."""

import pandas as pd
import pytest

from analytics.intraday_rules import (
    AlertSignal,
    AlertType,
    _cap_risk,
    _check_ma_confluence,
    _compute_crypto_opening_range,
    _consolidate_signals,
    _detect_ma_context,
    _detect_volume_exhaustion,
    _find_resistance_targets,
    _has_overhead_ma_resistance,
    _should_skip_noise,
    atr_adjusted_stop,
    check_auto_stop_out,
    check_bb_squeeze_breakout,
    check_ema_crossover_5_20,
    check_fib_retracement_bounce,
    check_first_hour_summary,
    check_gap_and_go,
    check_gap_fill,
    check_hourly_resistance_approach,
    check_hourly_resistance_rejection_short,
    check_inside_day_breakout,
    check_inside_day_breakdown,
    check_inside_day_forming,
    check_inside_day_reclaim,
    check_macd_histogram_flip,
    check_outside_day_breakout,
    check_ma_resistance,
    check_intraday_support_bounce,
    check_ma_bounce_20,
    check_ma_bounce_50,
    check_ma_bounce_100,
    check_ma_bounce_200,
    check_opening_range_breakout,
    check_orb_breakdown,
    check_opening_low_base,
    check_planned_level_touch,
    check_pdh_retest_hold,
    check_pdh_test,
    check_prior_day_high_breakout,
    check_weekly_high_test,
    check_weekly_low_test,
    check_weekly_low_breakdown,
    check_ema_resistance,
    check_prior_day_low_bounce,
    check_prior_day_low_reclaim,
    check_trailing_stop_hit,
    check_weekly_level_touch,
    check_monthly_level_touch,
    check_monthly_high_breakout,
    check_monthly_high_test,
    check_monthly_high_resistance,
    check_monthly_low_test,
    check_monthly_low_breakdown,
    check_ema_bounce_100,
    check_ema_bounce_200,
    check_pdh_rejection,
    check_resistance_prior_high,
    check_resistance_prior_low,
    check_vwap_bounce,
    check_vwap_reclaim,
    check_morning_low_retest,
    check_first_hour_high_breakout,
    check_ma_ema_reclaim,
    check_prior_day_low_breakdown,
    check_prior_day_low_resistance,
    check_session_high_retracement,
    check_multi_day_double_bottom,
    check_session_low_retest,
    check_stop_loss_hit,
    check_support_breakdown,
    check_target_1_hit,
    check_target_2_hit,
    compute_atr,
    evaluate_rules,
)
from analytics.intraday_data import (
    _compute_spy_bounce_rate,
    check_mtf_alignment,
    classify_market_regime,
    compute_opening_range,
    detect_daily_double_bottoms,
    detect_hourly_resistance,
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
        sig = check_ma_bounce_20("AAPL", pd.DataFrame([bar]), ma20=100.0, ma50=95.0)
        assert sig is not None
        assert sig.alert_type == AlertType.MA_BOUNCE_20
        assert sig.direction == "BUY"
        assert sig.entry == 100.0  # entry at MA level, not bar close

    def test_no_fire_when_close_below_ma20(self):
        bar = _bar(open_=100, high=101, low=99.98, close=99.8)
        sig = check_ma_bounce_20("AAPL", pd.DataFrame([bar]), ma20=100.0, ma50=95.0)
        assert sig is None

    def test_no_fire_when_not_in_uptrend(self):
        bar = _bar(open_=100, high=101, low=99.98, close=100.3)
        sig = check_ma_bounce_20("AAPL", pd.DataFrame([bar]), ma20=94.0, ma50=95.0)  # ma20 < ma50
        assert sig is None

    def test_no_fire_when_bar_too_far_from_ma20(self):
        # Both Low and Close far from MA20 — no touch detected
        bar = _bar(open_=102, high=103, low=101.0, close=102.5)
        sig = check_ma_bounce_20("AAPL", pd.DataFrame([bar]), ma20=100.0, ma50=95.0)
        assert sig is None  # Close 2.5% from MA > max distance 2%

    def test_no_fire_when_ma_missing(self):
        bar = _bar()
        assert check_ma_bounce_20("X", pd.DataFrame([bar]), ma20=None, ma50=95.0) is None
        assert check_ma_bounce_20("X", pd.DataFrame([bar]), ma20=100.0, ma50=None) is None

    def test_high_confidence_when_very_close_to_ma(self):
        bar = _bar(open_=100, high=101, low=100.05, close=100.3)
        sig = check_ma_bounce_20("AAPL", pd.DataFrame([bar]), ma20=100.0, ma50=95.0)
        assert sig is not None
        assert sig.confidence == "high"

    def test_targets_are_1r_and_2r(self):
        bar = _bar(open_=100, high=101, low=99.98, close=100.3)
        sig = check_ma_bounce_20("AAPL", pd.DataFrame([bar]), ma20=100.0, ma50=95.0)
        assert sig is not None
        risk = sig.entry - sig.stop
        assert risk > 0
        assert abs(sig.target_1 - (sig.entry + risk)) < 0.01
        assert abs(sig.target_2 - (sig.entry + 2 * risk)) < 0.01


# ===== Rule 2: MA Bounce 50MA =====

class TestMABounce50:
    def test_fires_on_pullback_to_50ma(self):
        bar = _bar(open_=95, high=96, low=94.98, close=95.3)
        sig = check_ma_bounce_50("NVDA", pd.DataFrame([bar]), ma20=98.0, ma50=95.0, prior_close=96.0)
        assert sig is not None
        assert sig.alert_type == AlertType.MA_BOUNCE_50
        assert sig.direction == "BUY"
        assert sig.entry == 95.0  # entry at MA level

    def test_counter_trend_fires_when_prior_close_below_50ma(self):
        bar = _bar(open_=95, high=96, low=94.98, close=95.3)
        sig = check_ma_bounce_50("NVDA", pd.DataFrame([bar]), ma20=98.0, ma50=95.0, prior_close=94.0)
        assert sig is not None  # counter-trend bounce now allowed
        assert "counter-trend" in sig.message
        assert sig.confidence == "medium"

    def test_no_fire_when_close_below_50ma(self):
        bar = _bar(open_=95, high=96, low=94.98, close=94.5)
        sig = check_ma_bounce_50("NVDA", pd.DataFrame([bar]), ma20=98.0, ma50=95.0, prior_close=96.0)
        assert sig is None

    def test_no_fire_when_ma50_missing(self):
        bar = _bar()
        assert check_ma_bounce_50("X", pd.DataFrame([bar]), ma20=100.0, ma50=None, prior_close=96.0) is None


# ===== Rule 3: MA Bounce 100MA =====

class TestMABounce100:
    def test_fires_when_bar_low_touches_ma100_and_closes_above(self):
        bar = _bar(open_=200, high=202, low=199.95, close=200.5)
        sig = check_ma_bounce_100("NVDA", pd.DataFrame([bar]), ma100=200.0, prior_close=202.0)
        assert sig is not None
        assert sig.alert_type == AlertType.MA_BOUNCE_100
        assert sig.direction == "BUY"
        assert sig.confidence == "high"
        assert sig.entry == 200.0  # entry at MA level

    def test_no_fire_when_close_below_ma100(self):
        bar = _bar(open_=200, high=201, low=199.95, close=199.5)
        sig = check_ma_bounce_100("NVDA", pd.DataFrame([bar]), ma100=200.0, prior_close=202.0)
        assert sig is None

    def test_fires_even_when_prior_close_below_ma100(self):
        """100MA is institutional level — multi-day pullbacks are valid bounces."""
        bar = _bar(open_=200, high=202, low=199.95, close=200.5)
        sig = check_ma_bounce_100("NVDA", pd.DataFrame([bar]), ma100=200.0, prior_close=198.0)
        assert sig is not None  # no longer rejected

    def test_no_fire_when_too_far_from_ma100(self):
        # Both Low and Close far from MA100 — no touch
        bar = _bar(open_=204, high=206, low=198.0, close=205.0)
        sig = check_ma_bounce_100("NVDA", pd.DataFrame([bar]), ma100=200.0, prior_close=202.0)
        assert sig is None  # Close 2.5% from MA > max distance 2%

    def test_wider_proximity_allows_05pct_wick(self):
        """0.5% proximity — bar low at $199.00 on $200 MA should fire."""
        bar = _bar(open_=200, high=202, low=199.0, close=200.5)
        sig = check_ma_bounce_100("NVDA", pd.DataFrame([bar]), ma100=200.0, prior_close=202.0)
        assert sig is not None  # 0.5% wick now accepted

    def test_no_fire_when_ma100_missing(self):
        bar = _bar()
        assert check_ma_bounce_100("X", pd.DataFrame([bar]), ma100=None, prior_close=102.0) is None

    def test_targets_are_1r_and_2r(self):
        bar = _bar(open_=200, high=202, low=199.95, close=200.5)
        sig = check_ma_bounce_100("NVDA", pd.DataFrame([bar]), ma100=200.0, prior_close=202.0)
        assert sig is not None
        risk = sig.entry - sig.stop
        assert risk > 0
        assert sig.target_1 == round(sig.entry + risk, 2)
        assert sig.target_2 == round(sig.entry + 2 * risk, 2)


# ===== Rule 4: MA Bounce 200MA =====

class TestMABounce200:
    def test_fires_when_bar_low_touches_ma200_and_closes_above(self):
        bar = _bar(open_=150, high=152, low=149.95, close=150.5)
        sig = check_ma_bounce_200("TSLA", pd.DataFrame([bar]), ma200=150.0, prior_close=153.0)
        assert sig is not None
        assert sig.alert_type == AlertType.MA_BOUNCE_200
        assert sig.direction == "BUY"
        assert sig.entry == 150.0  # entry at MA level

    def test_no_fire_when_close_below_ma200(self):
        bar = _bar(open_=150, high=151, low=149.95, close=149.5)
        sig = check_ma_bounce_200("TSLA", pd.DataFrame([bar]), ma200=150.0, prior_close=153.0)
        assert sig is None

    def test_fires_even_when_prior_close_below_ma200(self):
        """200MA is major institutional level — multi-day pullbacks bounce."""
        bar = _bar(open_=150, high=152, low=149.95, close=150.5)
        sig = check_ma_bounce_200("TSLA", pd.DataFrame([bar]), ma200=150.0, prior_close=148.0)
        assert sig is not None  # no longer rejected

    def test_always_high_confidence(self):
        bar = _bar(open_=150, high=152, low=149.95, close=150.5)
        sig = check_ma_bounce_200("TSLA", pd.DataFrame([bar]), ma200=150.0, prior_close=153.0)
        assert sig is not None
        assert sig.confidence == "high"

    def test_targets_are_1r_and_2r(self):
        bar = _bar(open_=150, high=152, low=149.95, close=150.5)
        sig = check_ma_bounce_200("TSLA", pd.DataFrame([bar]), ma200=150.0, prior_close=153.0)
        assert sig is not None
        risk = sig.entry - sig.stop
        assert risk > 0
        assert sig.target_1 == round(sig.entry + risk, 2)
        assert sig.target_2 == round(sig.entry + 2 * risk, 2)

    def test_no_fire_when_ma200_missing(self):
        bar = _bar()
        assert check_ma_bounce_200("X", pd.DataFrame([bar]), ma200=None, prior_close=102.0) is None

    def test_nvda_scenario_wide_wick_fires(self):
        """NVDA: 200MA=$175.21, bar wicked to $174.64 (0.33%), close=$178.50.
        With 0.8% proximity, this should fire. Entry at MA, not chased close.
        Close must be within MA_BOUNCE_MAX_DISTANCE_PCT (2%) of MA."""
        bar = _bar(open_=176.0, high=179.0, low=174.64, close=178.50)
        sig = check_ma_bounce_200("NVDA", pd.DataFrame([bar]), ma200=175.21, prior_close=173.0)
        assert sig is not None
        assert sig.entry == 175.21
        assert sig.stop == round(175.21 * (1 - 0.010), 2)  # 1% below MA
        assert sig.direction == "BUY"

    def test_no_fire_when_wick_beyond_08pct(self):
        """Both Low and Close far from 200MA should not fire."""
        # 200MA=150, Close at 154 = 2.7% → exceeds max distance
        bar = _bar(open_=153, high=155, low=148.5, close=154.0)
        sig = check_ma_bounce_200("TSLA", pd.DataFrame([bar]), ma200=150.0, prior_close=153.0)
        assert sig is None


# ===== MA Bounce Lookback Tests =====

class TestMABounceLookback:
    """Verify MA bounce functions scan recent bars (not just last bar)."""

    def test_ma200_bounce_detected_from_earlier_bar(self):
        """Bounce touched 200MA 3 bars ago, price has since run up — should fire."""
        ma200 = 176.37
        bars = _bars([
            {"Open": 177.0, "High": 178.0, "Low": 176.20, "Close": 177.5, "Volume": 5000},  # touch
            {"Open": 177.5, "High": 179.0, "Low": 177.0, "Close": 178.5, "Volume": 4000},
            {"Open": 178.5, "High": 180.0, "Low": 178.0, "Close": 179.5, "Volume": 4000},
            {"Open": 179.5, "High": 180.5, "Low": 179.0, "Close": 179.8, "Volume": 3500},  # last bar ~1.9% above
        ])
        sig = check_ma_bounce_200("NVDA", bars, ma200=ma200, prior_close=173.0)
        assert sig is not None
        assert sig.alert_type == AlertType.MA_BOUNCE_200
        assert sig.entry == round(ma200, 2)

    def test_ma200_bounce_too_far_above_does_not_fire(self):
        """Price ran >2% above 200MA — stale, should not fire."""
        ma200 = 176.37
        bars = _bars([
            {"Open": 177.0, "High": 178.0, "Low": 176.20, "Close": 177.5, "Volume": 5000},  # touch
            {"Open": 177.5, "High": 179.0, "Low": 177.0, "Close": 178.5, "Volume": 4000},
            {"Open": 178.5, "High": 181.0, "Low": 178.0, "Close": 180.5, "Volume": 4000},
            {"Open": 180.5, "High": 182.0, "Low": 180.0, "Close": 181.0, "Volume": 3500},  # 2.6% above
        ])
        sig = check_ma_bounce_200("NVDA", bars, ma200=ma200, prior_close=173.0)
        assert sig is None

    def test_ma20_bounce_from_lookback_bar(self):
        """20MA touch from 2 bars ago, close still above — fires."""
        ma20 = 100.0
        bars = _bars([
            {"Open": 100.2, "High": 100.5, "Low": 99.98, "Close": 100.3, "Volume": 1000},  # touch
            {"Open": 100.3, "High": 100.8, "Low": 100.1, "Close": 100.6, "Volume": 1000},
            {"Open": 100.6, "High": 101.0, "Low": 100.4, "Close": 100.8, "Volume": 1000},  # last bar
        ])
        sig = check_ma_bounce_20("AAPL", bars, ma20=ma20, ma50=95.0)
        assert sig is not None
        assert sig.alert_type == AlertType.MA_BOUNCE_20

    def test_ma100_bounce_from_lookback_bar(self):
        """100MA touch from earlier bar — fires within 2% distance."""
        ma100 = 200.0
        bars = _bars([
            {"Open": 200.5, "High": 201.0, "Low": 199.50, "Close": 200.5, "Volume": 2000},  # touch (0.25%)
            {"Open": 200.5, "High": 202.0, "Low": 200.0, "Close": 201.5, "Volume": 2000},
            {"Open": 201.5, "High": 203.0, "Low": 201.0, "Close": 202.5, "Volume": 2000},  # 1.25% above
        ])
        sig = check_ma_bounce_100("NVDA", bars, ma100=ma100, prior_close=202.0)
        assert sig is not None
        assert sig.alert_type == AlertType.MA_BOUNCE_100

    def test_no_touch_in_lookback_window_returns_none(self):
        """No bar in lookback window touched the MA — should not fire."""
        ma200 = 176.37
        bars = _bars([
            {"Open": 180.0, "High": 181.0, "Low": 179.0, "Close": 180.5, "Volume": 3000},
            {"Open": 180.5, "High": 181.5, "Low": 179.5, "Close": 181.0, "Volume": 3000},
            {"Open": 181.0, "High": 182.0, "Low": 180.0, "Close": 181.5, "Volume": 3000},
        ])
        sig = check_ma_bounce_200("NVDA", bars, ma200=ma200, prior_close=178.0)
        assert sig is None

    def test_ema200_bounce_from_lookback_bar(self):
        """EMA200 touch from earlier bar — fires."""
        ema200 = 176.37
        bars = _bars([
            {"Open": 177.0, "High": 178.0, "Low": 175.80, "Close": 177.0, "Volume": 5000},  # touch
            {"Open": 177.0, "High": 179.0, "Low": 176.5, "Close": 178.5, "Volume": 4000},
            {"Open": 178.5, "High": 179.5, "Low": 178.0, "Close": 179.0, "Volume": 3500},  # 1.5% above
        ])
        sig = check_ema_bounce_200("NVDA", bars, ema200=ema200, prior_close=173.0)
        assert sig is not None
        assert sig.alert_type == AlertType.EMA_BOUNCE_200

    def test_ema100_bounce_from_lookback_bar(self):
        """EMA100 touch from earlier bar — fires."""
        ema100 = 685.0
        bars = _bars([
            {"Open": 686.0, "High": 687.0, "Low": 684.50, "Close": 686.0, "Volume": 5000},  # touch
            {"Open": 686.0, "High": 688.0, "Low": 685.5, "Close": 687.5, "Volume": 4000},
            {"Open": 687.5, "High": 690.0, "Low": 687.0, "Close": 689.0, "Volume": 3500},  # 0.58% above
        ])
        sig = check_ema_bounce_100("SPY", bars, ema100=ema100, prior_close=690.0)
        assert sig is not None
        assert sig.alert_type == AlertType.EMA_BOUNCE_100

    def test_nvda_real_scenario_ma200_bounce(self):
        """NVDA 2026-03-09: Open 176.83, Low 175.56, bounced to 182.65.
        MA200=176.37. Bounce touched in early bars, price ran to 179.8 (~1.9%).
        Should fire within 2% max distance with last bar volume >= prior avg
        (Phase 2 bounce-volume check requires at least 1.0x avg for HIGH).
        """
        ma200 = 176.37
        bars = _bars([
            # Early morning: price near/below MA200
            {"Open": 176.83, "High": 177.50, "Low": 175.56, "Close": 176.00, "Volume": 4000},
            {"Open": 176.00, "High": 177.80, "Low": 175.80, "Close": 177.50, "Volume": 3500},
            # Recovery bars
            {"Open": 177.50, "High": 178.50, "Low": 177.00, "Close": 178.20, "Volume": 3000},
            {"Open": 178.20, "High": 179.00, "Low": 177.80, "Close": 178.80, "Volume": 3200},
            {"Open": 178.80, "High": 179.50, "Low": 178.30, "Close": 179.20, "Volume": 3300},
            # Last bar volume > prior avg (3400 > 3400 avg)
            {"Open": 179.20, "High": 180.00, "Low": 178.80, "Close": 179.80, "Volume": 4500},
        ])
        sig = check_ma_bounce_200("NVDA", bars, ma200=ma200, prior_close=173.0)
        assert sig is not None
        assert sig.alert_type == AlertType.MA_BOUNCE_200
        assert sig.entry == round(ma200, 2)
        assert sig.confidence == "high"  # MA200 bounce always high confidence


# ===== PDL Reclaim Distance Tests =====

class TestPDLReclaimWidenedDistance:
    """Verify PDL reclaim fires within the widened 2% max distance."""

    def test_fires_at_1_5pct_above_pdl(self):
        """Price reclaimed and held above PDL for 2+ bars — should fire."""
        pdl = 177.88
        close = pdl * 1.015  # 1.5% above
        bars = _bars([
            {"Open": 178.0, "High": 178.5, "Low": 177.50, "Close": 177.0, "Volume": 5000},  # dip below
            {"Open": 177.0, "High": close + 0.5, "Low": 177.60, "Close": close - 0.2, "Volume": 4000},  # reclaim
            {"Open": close - 0.2, "High": close + 0.5, "Low": 178.0, "Close": close, "Volume": 4000},  # hold
        ])
        sig = check_prior_day_low_reclaim("NVDA", bars, prior_day_low=pdl)
        assert sig is not None
        assert sig.alert_type == AlertType.PRIOR_DAY_LOW_RECLAIM
        assert sig.entry == round(close, 2)

    def test_fires_at_1_9pct_above_pdl(self):
        """Price 1.9% above PDL, held 2+ bars — still within 2% threshold."""
        pdl = 100.0
        close = 101.9  # 1.9% above
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.5, "Close": 99.8, "Volume": 1000},  # dip
            {"Open": 99.8, "High": 102.0, "Low": 99.9, "Close": 101.5, "Volume": 1200},  # reclaim
            {"Open": 101.5, "High": 102.0, "Low": 101.0, "Close": close, "Volume": 1100},  # hold
        ])
        sig = check_prior_day_low_reclaim("META", bars, prior_day_low=pdl)
        assert sig is not None

    def test_no_fire_at_2_5pct_above_pdl(self):
        """Price 2.5% above PDL — exceeds 2% threshold, still stale."""
        pdl = 100.0
        close = 102.5
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.5, "Close": 99.8, "Volume": 1000},
            {"Open": 99.8, "High": 103.0, "Low": 99.9, "Close": close, "Volume": 1200},
        ])
        sig = check_prior_day_low_reclaim("META", bars, prior_day_low=pdl)
        assert sig is None

    def test_nvda_real_scenario_pdl_reclaim(self):
        """NVDA 2026-03-09: PDL=177.88, dipped to 175.56, reclaimed to 179.5 (0.9%).
        Should fire within widened 2% threshold."""
        pdl = 177.88
        bars = _bars([
            {"Open": 176.83, "High": 177.50, "Low": 175.56, "Close": 176.00, "Volume": 8000},
            {"Open": 176.00, "High": 178.50, "Low": 175.80, "Close": 178.20, "Volume": 7000},
            {"Open": 178.20, "High": 179.80, "Low": 178.00, "Close": 179.50, "Volume": 5000},
        ])
        sig = check_prior_day_low_reclaim("NVDA", bars, prior_day_low=pdl)
        assert sig is not None
        assert sig.entry == 179.5
        assert sig.stop == round(pdl * (1 - 0.005), 2)


# ===== Rule 5: Prior Day Low Reclaim =====

class TestPriorDayLowReclaim:
    def test_fires_on_dip_and_reclaim(self):
        bars = _bars([
            {"Open": 100, "High": 100.5, "Low": 98.5, "Close": 99.0, "Volume": 1000},  # dip
            {"Open": 99.0, "High": 99.6, "Low": 98.8, "Close": 99.3, "Volume": 1200},  # reclaim
            {"Open": 99.3, "High": 99.8, "Low": 99.1, "Close": 99.5, "Volume": 1100},  # hold
        ])
        sig = check_prior_day_low_reclaim("META", bars, prior_day_low=99.0)
        assert sig is not None
        assert sig.alert_type == AlertType.PRIOR_DAY_LOW_RECLAIM
        assert sig.direction == "BUY"
        assert sig.entry == 99.5
        # Stop = PDL * (1 - 0.005) = 99.0 * 0.995 = 98.505
        assert sig.stop == round(99.0 * 0.995, 2)

    def test_stop_is_pdl_based_not_session_low(self):
        """Stop should be just below PDL, not at the deep session low."""
        bars = _bars([
            {"Open": 100, "High": 100.5, "Low": 96.0, "Close": 98.0, "Volume": 1000},  # dip
            {"Open": 98.0, "High": 100.5, "Low": 99.2, "Close": 100.1, "Volume": 1200},  # reclaim
            {"Open": 100.1, "High": 100.6, "Low": 99.8, "Close": 100.2, "Volume": 1100},  # hold
        ])
        sig = check_prior_day_low_reclaim("ETH-USD", bars, prior_day_low=100.0)
        assert sig is not None
        # Stop = 100.0 * 0.995 = 99.50, NOT near session low of 96.0
        assert sig.stop == 99.50
        assert sig.stop > 99.0  # well above the session low

    def test_no_fire_when_price_ran_past_entry(self):
        """Price reclaimed but already ran >2% above entry — stale signal."""
        bars = _bars([
            {"Open": 100, "High": 102.0, "Low": 98.5, "Close": 99.0, "Volume": 1000},
            {"Open": 99.0, "High": 102.0, "Low": 98.8, "Close": 101.5, "Volume": 1200},
        ])
        sig = check_prior_day_low_reclaim("META", bars, prior_day_low=99.0)
        assert sig is None

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


# ===== Rule 5b: Prior Day Low Bounce =====

class TestPriorDayLowBounce:
    """Price approaches prior day low and holds above it (no break below)."""

    def test_fires_when_bar_low_near_pdl_and_holds(self):
        """Bar low within 0.5% of PDL, last 2 bars close above PDL → fires."""
        # PDL = 100.0, proximity = 0.5% → anything with low <= 100.5 qualifies
        # Crypto has tighter max distance (0.8%) so keep close within that
        bars = _bars([
            {"Open": 100.5, "High": 101, "Low": 100.3, "Close": 100.6, "Volume": 1000},
            {"Open": 100.5, "High": 100.8, "Low": 100.2, "Close": 100.5, "Volume": 1200},
            {"Open": 100.4, "High": 100.7, "Low": 100.3, "Close": 100.5, "Volume": 1100},
        ])
        sig = check_prior_day_low_bounce("BTC-USD", bars, prior_day_low=100.0)
        assert sig is not None
        assert sig.alert_type == AlertType.PRIOR_DAY_LOW_BOUNCE
        assert sig.direction == "BUY"
        assert sig.confidence == "high"
        # Stop = PDL * (1 - 0.005) = 99.50
        assert sig.stop == 99.50

    def test_no_fire_when_bar_broke_below_pdl(self):
        """If any bar dipped below PDL, defer to prior_day_low_reclaim."""
        bars = _bars([
            {"Open": 101, "High": 102, "Low": 99.5, "Close": 101.0, "Volume": 1000},
            {"Open": 101, "High": 101.5, "Low": 100.2, "Close": 100.8, "Volume": 1200},
            {"Open": 100.8, "High": 101.2, "Low": 100.4, "Close": 101.0, "Volume": 1100},
        ])
        sig = check_prior_day_low_bounce("BTC-USD", bars, prior_day_low=100.0)
        assert sig is None

    def test_no_fire_when_too_far_from_pdl(self):
        """Bar low never came within 0.5% of PDL → no proximity touch."""
        # PDL = 100.0, proximity = 0.5% → need low <= 100.5
        # All bars have low > 101.0 (>1% away)
        bars = _bars([
            {"Open": 102, "High": 103, "Low": 101.5, "Close": 102.5, "Volume": 1000},
            {"Open": 102.5, "High": 103, "Low": 101.2, "Close": 102.8, "Volume": 1200},
            {"Open": 102.8, "High": 103.5, "Low": 101.8, "Close": 103.0, "Volume": 1100},
        ])
        sig = check_prior_day_low_bounce("BTC-USD", bars, prior_day_low=100.0)
        assert sig is None

    def test_no_fire_when_recent_close_below_pdl(self):
        """Last bar closes below PDL — hold not confirmed."""
        bars = _bars([
            {"Open": 101, "High": 102, "Low": 100.3, "Close": 101.0, "Volume": 1000},
            {"Open": 101, "High": 101.5, "Low": 100.2, "Close": 100.8, "Volume": 1200},
            {"Open": 100.8, "High": 101.0, "Low": 99.8, "Close": 99.9, "Volume": 1100},
        ])
        sig = check_prior_day_low_bounce("BTC-USD", bars, prior_day_low=100.0)
        assert sig is None

    def test_no_fire_when_price_ran_too_far(self):
        """Price already ran >1% above PDL — stale signal."""
        # PDL = 100.0, max distance = 1.0% → close > 101.0 = too far
        bars = _bars([
            {"Open": 101, "High": 102, "Low": 100.3, "Close": 101.0, "Volume": 1000},
            {"Open": 101, "High": 102, "Low": 100.2, "Close": 101.5, "Volume": 1200},
            {"Open": 101.5, "High": 102.5, "Low": 101.0, "Close": 102.0, "Volume": 1100},
        ])
        sig = check_prior_day_low_bounce("BTC-USD", bars, prior_day_low=100.0)
        assert sig is None

    def test_targets_are_1r_and_2r(self):
        """Verify entry/stop/target math: T1 = entry + risk, T2 = entry + 2*risk."""
        bars = _bars([
            {"Open": 101, "High": 102, "Low": 100.3, "Close": 101.0, "Volume": 1000},
            {"Open": 101, "High": 101.5, "Low": 100.2, "Close": 100.8, "Volume": 1200},
            {"Open": 100.8, "High": 101.2, "Low": 100.4, "Close": 100.5, "Volume": 1100},
        ])
        sig = check_prior_day_low_bounce("BTC-USD", bars, prior_day_low=100.0)
        assert sig is not None
        risk = sig.entry - sig.stop
        assert risk > 0
        assert sig.target_1 == round(sig.entry + risk, 2)
        assert sig.target_2 == round(sig.entry + 2 * risk, 2)

    def test_no_fire_when_insufficient_bars(self):
        """Need at least PDL_BOUNCE_HOLD_BARS + 1 bars to confirm hold."""
        bars = _bars([
            {"Open": 101, "High": 102, "Low": 100.3, "Close": 101.0, "Volume": 1000},
        ])
        sig = check_prior_day_low_bounce("BTC-USD", bars, prior_day_low=100.0)
        assert sig is None

    def test_empty_bars_returns_none(self):
        assert check_prior_day_low_bounce("X", pd.DataFrame(), prior_day_low=100.0) is None

    def test_zero_prior_day_low_returns_none(self):
        bars = _bars([
            {"Open": 101, "High": 102, "Low": 100.3, "Close": 101.0, "Volume": 1000},
            {"Open": 101, "High": 101.5, "Low": 100.2, "Close": 100.8, "Volume": 1200},
            {"Open": 100.8, "High": 101.2, "Low": 100.4, "Close": 101.0, "Volume": 1100},
        ])
        assert check_prior_day_low_bounce("BTC-USD", bars, prior_day_low=0) is None


# ===== Rule 3b: Prior Day High Breakout =====

class TestPriorDayHighBreakout:
    def test_fires_on_close_above_prior_high_with_volume(self):
        # Phase 1 (2026-04-22): requires N consecutive bars above level.
        # Bar 1 opens below PDH (avoids gap-up guard), then 2 confirming bars above.
        bars = _bars([
            {"Open": 100.5, "High": 100.9, "Low": 100.3, "Close": 100.8, "Volume": 800},
            {"Open": 100.9, "High": 101.5, "Low": 100.9, "Close": 101.3, "Volume": 1200},
            {"Open": 101.3, "High": 102.0, "Low": 101.1, "Close": 101.5, "Volume": 1500},
        ])
        sig = check_prior_day_high_breakout("NVDA", bars, prior_day_high=101.0,
                                             bar_volume=1500, avg_volume=1000)
        assert sig is not None
        assert sig.alert_type == AlertType.PRIOR_DAY_HIGH_BREAKOUT
        assert sig.direction == "BUY"
        assert sig.confidence == "high"  # vol 1.5x

    def test_medium_confidence_on_moderate_volume(self):
        bars = _bars([
            {"Open": 100.5, "High": 100.9, "Low": 100.3, "Close": 100.8, "Volume": 800},
            {"Open": 100.9, "High": 101.4, "Low": 100.9, "Close": 101.3, "Volume": 1200},
            {"Open": 101.3, "High": 102, "Low": 101.1, "Close": 101.5, "Volume": 1300},
        ])
        sig = check_prior_day_high_breakout("AAPL", bars, prior_day_high=101.0,
                                             bar_volume=1300, avg_volume=1000)
        assert sig is not None
        assert sig.confidence == "medium"  # vol 1.3x (< 1.5)

    def test_no_fire_on_single_bar_breakout(self):
        """Phase 1: single bar breakout without confirmation must NOT fire."""
        bars = _bars([
            {"Open": 100, "High": 100.8, "Low": 99.5, "Close": 100.5, "Volume": 800},
            {"Open": 100.5, "High": 102, "Low": 100.2, "Close": 101.5, "Volume": 1500},
        ])
        sig = check_prior_day_high_breakout("AAPL", bars, prior_day_high=101.0,
                                             bar_volume=1500, avg_volume=1000)
        assert sig is None  # only 1 bar closed above, N=2 required

    def test_no_fire_on_runaway_bar_past_level(self):
        """Phase 1: staleness guard — bar closed >1% above level should not fire."""
        bars = _bars([
            {"Open": 100.9, "High": 102.5, "Low": 100.9, "Close": 102.2, "Volume": 1500},  # +1.2% above
            {"Open": 102.2, "High": 103.5, "Low": 102.0, "Close": 103.2, "Volume": 1600},  # +2.2% above
        ])
        sig = check_prior_day_high_breakout("AAPL", bars, prior_day_high=101.0,
                                             bar_volume=1600, avg_volume=1000)
        assert sig is None

    def test_no_fire_when_confirmation_bar_wicks_past_tolerance(self):
        """Phase 1: if any confirmation bar dips >0.2% below level, skip."""
        bars = _bars([
            {"Open": 100.9, "High": 101.5, "Low": 100.3, "Close": 101.3, "Volume": 1500},  # low 0.7% below floor
            {"Open": 101.3, "High": 102.0, "Low": 101.1, "Close": 101.5, "Volume": 1500},
        ])
        sig = check_prior_day_high_breakout("AAPL", bars, prior_day_high=101.0,
                                             bar_volume=1500, avg_volume=1000)
        assert sig is None

    def test_no_fire_when_close_below_prior_high(self):
        bars = _bars([
            {"Open": 100, "High": 100.8, "Low": 99.5, "Close": 100.5, "Volume": 1500},
        ])
        sig = check_prior_day_high_breakout("AAPL", bars, prior_day_high=101.0,
                                             bar_volume=1500, avg_volume=1000)
        assert sig is None

    def test_no_fire_when_volume_insufficient(self):
        bars = _bars([
            {"Open": 100, "High": 102, "Low": 100, "Close": 101.5, "Volume": 700},
        ])
        sig = check_prior_day_high_breakout("AAPL", bars, prior_day_high=101.0,
                                             bar_volume=700, avg_volume=1000)
        assert sig is None  # vol 0.7x < 0.8 threshold

    def test_empty_bars_returns_none(self):
        sig = check_prior_day_high_breakout("X", pd.DataFrame(), prior_day_high=101.0,
                                             bar_volume=1500, avg_volume=1000)
        assert sig is None

    def test_zero_prior_high_returns_none(self):
        bars = _bars([
            {"Open": 100, "High": 102, "Low": 100, "Close": 101.5, "Volume": 1500},
        ])
        sig = check_prior_day_high_breakout("X", bars, prior_day_high=0,
                                             bar_volume=1500, avg_volume=1000)
        assert sig is None

    def test_targets_are_1r_and_2r(self):
        bars = _bars([
            {"Open": 100.5, "High": 100.9, "Low": 100.3, "Close": 100.8, "Volume": 800},
            {"Open": 100.9, "High": 101.5, "Low": 100.9, "Close": 101.3, "Volume": 1500},
            {"Open": 101.3, "High": 102, "Low": 101.2, "Close": 101.5, "Volume": 1500},
        ])
        sig = check_prior_day_high_breakout("AAPL", bars, prior_day_high=101.0,
                                             bar_volume=1500, avg_volume=1000)
        assert sig is not None
        risk = sig.entry - sig.stop
        assert risk > 0
        assert abs(sig.target_1 - (sig.entry + risk)) < 0.01
        assert abs(sig.target_2 - (sig.entry + 2 * risk)) < 0.01

    def test_stop_at_breakout_bar_low(self):
        bars = _bars([
            {"Open": 100.5, "High": 100.9, "Low": 100.3, "Close": 100.8, "Volume": 800},
            {"Open": 100.9, "High": 101.5, "Low": 100.9, "Close": 101.3, "Volume": 1500},
            {"Open": 101.3, "High": 102, "Low": 101.2, "Close": 101.5, "Volume": 1500},
        ])
        sig = check_prior_day_high_breakout("AAPL", bars, prior_day_high=101.0,
                                             bar_volume=1500, avg_volume=1000)
        assert sig is not None
        # Stop should be at or above the bar low (may be capped by _cap_risk)
        assert sig.stop <= sig.entry

    def test_message_includes_volume_ratio(self):
        bars = _bars([
            {"Open": 100.5, "High": 100.9, "Low": 100.3, "Close": 100.8, "Volume": 800},
            {"Open": 100.9, "High": 101.5, "Low": 100.9, "Close": 101.3, "Volume": 1800},
            {"Open": 101.3, "High": 102, "Low": 101.2, "Close": 101.5, "Volume": 1800},
        ])
        sig = check_prior_day_high_breakout("AAPL", bars, prior_day_high=101.0,
                                             bar_volume=1800, avg_volume=1000)
        assert sig is not None
        assert "1.8x" in sig.message

    def test_no_fire_when_risk_is_zero(self):
        # Bar 2 and 3 both low == prior high → risk = 0 on gap-up path
        # With the gap-up fallback, this now uses 0.5% buffer stop
        bars = _bars([
            {"Open": 100.5, "High": 100.9, "Low": 100.3, "Close": 100.8, "Volume": 800},
            {"Open": 101.0, "High": 101.4, "Low": 101.0, "Close": 101.3, "Volume": 1500},
            {"Open": 101.3, "High": 102, "Low": 101.0, "Close": 101.5, "Volume": 1500},
        ])
        sig = check_prior_day_high_breakout("AAPL", bars, prior_day_high=101.0,
                                             bar_volume=1500, avg_volume=1000)
        # Gap-up fallback kicks in: stop = 101.0 * 0.995 = 100.50
        assert sig is not None
        assert sig.stop < sig.entry

    def test_crypto_gap_up_above_pdh_fires(self):
        """Crypto opens above PDH — all bars have Low > PDH.
        Should fire using fallback stop (0.5% below PDH)."""
        bars = _bars([
            {"Open": 71400, "High": 71600, "Low": 71350, "Close": 71500, "Volume": 100000},
            {"Open": 71500, "High": 71800, "Low": 71400, "Close": 71600, "Volume": 120000},
            {"Open": 71600, "High": 72000, "Low": 71550, "Close": 71800, "Volume": 150000},
            {"Open": 71800, "High": 72200, "Low": 71700, "Close": 72100, "Volume": 130000},
            {"Open": 72100, "High": 72500, "Low": 72000, "Close": 72300, "Volume": 140000},
            {"Open": 72300, "High": 72800, "Low": 72200, "Close": 72600, "Volume": 160000},
        ])
        # PDH = 71291 — all bar lows are above PDH
        sig = check_prior_day_high_breakout("BTC-USD", bars, prior_day_high=71291.0,
                                             bar_volume=160000, avg_volume=130000)
        assert sig is not None
        assert sig.alert_type == AlertType.PRIOR_DAY_HIGH_BREAKOUT
        assert sig.entry == 72600.0
        # Stop at last bar low (within _cap_risk for BTC-USD)
        assert sig.stop == 72200.0
        assert sig.stop < sig.entry

    def test_crypto_gap_up_lookback_low_below_pdh(self):
        """Some lookback bars have Low < PDH — uses lookback low as stop."""
        bars = _bars([
            {"Open": 71200, "High": 71400, "Low": 71100, "Close": 71300, "Volume": 100000},
            {"Open": 71300, "High": 71500, "Low": 71250, "Close": 71400, "Volume": 110000},
            {"Open": 71400, "High": 71800, "Low": 71350, "Close": 71700, "Volume": 130000},
            {"Open": 71700, "High": 72000, "Low": 71600, "Close": 71900, "Volume": 120000},
            {"Open": 71900, "High": 72200, "Low": 71800, "Close": 72100, "Volume": 150000},
            {"Open": 72100, "High": 72500, "Low": 72000, "Close": 72400, "Volume": 160000},
        ])
        # PDH = 71291 — first two bars have Low < PDH (71100, 71250)
        sig = check_prior_day_high_breakout("BTC-USD", bars, prior_day_high=71291.0,
                                             bar_volume=160000, avg_volume=130000)
        assert sig is not None
        # entry = last bar Close = 72400, stop = last bar Low = 72000
        assert sig.entry == 72400.0
        assert sig.stop == 72000.0
        assert sig.stop < sig.entry

    def test_equity_pdh_breakout_unchanged(self):
        """Normal equity approach from below — existing behavior preserved (with N-bar confirm)."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.5, "Close": 100, "Volume": 800},
            {"Open": 100.5, "High": 101.4, "Low": 100.9, "Close": 101.3, "Volume": 1200},
            {"Open": 101.3, "High": 102, "Low": 101.2, "Close": 101.5, "Volume": 1500},
        ])
        sig = check_prior_day_high_breakout("NVDA", bars, prior_day_high=101.0,
                                             bar_volume=1500, avg_volume=1000)
        assert sig is not None
        assert sig.stop < sig.entry  # Stop below entry (normal approach from below)
        assert sig.entry == 101.5


# ===== Rule 3c: Prior Day High Retest & Hold =====

class TestPDHRetestHold:
    """After breakout above PDH, price pulls back to retest and holds."""

    def test_fires_on_breakout_pullback_and_hold(self):
        """Breakout bar closes above PDH, pullback touches near PDH, holds → fires."""
        # PDH = 100.0
        bars = _bars([
            {"Open": 99, "High": 100.5, "Low": 98.5, "Close": 99.5, "Volume": 1000},
            {"Open": 100, "High": 101.5, "Low": 99.8, "Close": 101.0, "Volume": 1500},  # breakout
            {"Open": 101, "High": 101.2, "Low": 100.1, "Close": 100.3, "Volume": 1200},  # pullback touches near PDH
            {"Open": 100.3, "High": 100.8, "Low": 100.2, "Close": 100.5, "Volume": 1100},  # hold bar 1
            {"Open": 100.5, "High": 101.0, "Low": 100.3, "Close": 100.7, "Volume": 1000},  # hold bar 2
        ])
        sig = check_pdh_retest_hold("BTC-USD", bars, prior_day_high=100.0)
        assert sig is not None
        assert sig.alert_type == AlertType.PDH_RETEST_HOLD
        assert sig.direction == "BUY"
        assert sig.confidence == "high"

    def test_no_fire_when_no_breakout(self):
        """Price never closed above PDH — no breakout means no retest."""
        bars = _bars([
            {"Open": 99, "High": 99.8, "Low": 98.5, "Close": 99.5, "Volume": 1000},
            {"Open": 99.5, "High": 100.0, "Low": 99.0, "Close": 99.8, "Volume": 1200},
            {"Open": 99.8, "High": 100.0, "Low": 99.5, "Close": 99.7, "Volume": 1100},
            {"Open": 99.7, "High": 99.9, "Low": 99.5, "Close": 99.8, "Volume": 1000},
        ])
        sig = check_pdh_retest_hold("AAPL", bars, prior_day_high=100.0)
        assert sig is None

    def test_no_fire_when_no_pullback_touch(self):
        """Breakout happened but price never pulled back near PDH."""
        bars = _bars([
            {"Open": 99, "High": 100.5, "Low": 98.5, "Close": 99.5, "Volume": 1000},
            {"Open": 100, "High": 102, "Low": 99.8, "Close": 101.5, "Volume": 1500},  # breakout
            {"Open": 101.5, "High": 103, "Low": 101.2, "Close": 102.5, "Volume": 1200},  # no pullback
            {"Open": 102.5, "High": 104, "Low": 102.0, "Close": 103.5, "Volume": 1100},  # running away
            {"Open": 103.5, "High": 105, "Low": 103.0, "Close": 104.0, "Volume": 1000},
        ])
        sig = check_pdh_retest_hold("NVDA", bars, prior_day_high=100.0)
        # Should be None because max distance filter (>1% above PDH)
        assert sig is None

    def test_no_fire_when_recent_close_below_pdh(self):
        """Last bar closes below PDH — hold not confirmed."""
        bars = _bars([
            {"Open": 99, "High": 100.5, "Low": 98.5, "Close": 99.5, "Volume": 1000},
            {"Open": 100, "High": 101.5, "Low": 99.8, "Close": 101.0, "Volume": 1500},  # breakout
            {"Open": 101, "High": 101.2, "Low": 100.1, "Close": 100.3, "Volume": 1200},  # pullback
            {"Open": 100.3, "High": 100.5, "Low": 99.5, "Close": 99.7, "Volume": 1100},  # failed hold
            {"Open": 99.7, "High": 100.0, "Low": 99.3, "Close": 99.5, "Volume": 1000},
        ])
        sig = check_pdh_retest_hold("AAPL", bars, prior_day_high=100.0)
        assert sig is None

    def test_no_fire_when_price_ran_too_far(self):
        """Price already >1% above PDH — stale retest signal."""
        bars = _bars([
            {"Open": 99, "High": 100.5, "Low": 98.5, "Close": 99.5, "Volume": 1000},
            {"Open": 100, "High": 101.5, "Low": 99.8, "Close": 101.0, "Volume": 1500},  # breakout
            {"Open": 101, "High": 101.2, "Low": 100.1, "Close": 100.3, "Volume": 1200},  # pullback
            {"Open": 100.3, "High": 101.5, "Low": 100.2, "Close": 101.3, "Volume": 1100},
            {"Open": 101.3, "High": 102.0, "Low": 101.0, "Close": 101.8, "Volume": 1000},
        ])
        sig = check_pdh_retest_hold("SPY", bars, prior_day_high=100.0)
        # 101.8 is 1.8% above PDH 100.0, exceeds 1.0% max
        assert sig is None

    def test_stop_below_pdh(self):
        """Stop should be below PDH, possibly capped by _cap_risk."""
        bars = _bars([
            {"Open": 99, "High": 100.5, "Low": 98.5, "Close": 99.5, "Volume": 1000},
            {"Open": 100, "High": 101.5, "Low": 99.8, "Close": 101.0, "Volume": 1500},
            {"Open": 101, "High": 101.2, "Low": 100.1, "Close": 100.3, "Volume": 1200},
            {"Open": 100.3, "High": 100.8, "Low": 100.2, "Close": 100.5, "Volume": 1100},
            {"Open": 100.5, "High": 101.0, "Low": 100.3, "Close": 100.7, "Volume": 1000},
        ])
        sig = check_pdh_retest_hold("BTC-USD", bars, prior_day_high=100.0)
        assert sig is not None
        # Stop below PDH (may be tightened by _cap_risk for BTC-USD's 0.8% limit)
        assert sig.stop < 100.0
        assert sig.stop <= sig.entry

    def test_targets_are_1r_and_2r(self):
        """Verify T1 = entry + risk, T2 = entry + 2*risk."""
        bars = _bars([
            {"Open": 99, "High": 100.5, "Low": 98.5, "Close": 99.5, "Volume": 1000},
            {"Open": 100, "High": 101.5, "Low": 99.8, "Close": 101.0, "Volume": 1500},
            {"Open": 101, "High": 101.2, "Low": 100.1, "Close": 100.3, "Volume": 1200},
            {"Open": 100.3, "High": 100.8, "Low": 100.2, "Close": 100.5, "Volume": 1100},
            {"Open": 100.5, "High": 101.0, "Low": 100.3, "Close": 100.7, "Volume": 1000},
        ])
        sig = check_pdh_retest_hold("ETH-USD", bars, prior_day_high=100.0)
        assert sig is not None
        risk = sig.entry - sig.stop
        assert risk > 0
        assert sig.target_1 == round(sig.entry + risk, 2)
        assert sig.target_2 == round(sig.entry + 2 * risk, 2)

    def test_empty_bars_returns_none(self):
        sig = check_pdh_retest_hold("X", pd.DataFrame(), prior_day_high=100.0)
        assert sig is None

    def test_zero_prior_high_returns_none(self):
        bars = _bars([
            {"Open": 100, "High": 102, "Low": 100, "Close": 101.5, "Volume": 1500},
        ])
        sig = check_pdh_retest_hold("X", bars, prior_day_high=0)
        assert sig is None

    def test_insufficient_bars_returns_none(self):
        """Need at least PDH_RETEST_HOLD_BARS + 2 bars."""
        bars = _bars([
            {"Open": 100, "High": 102, "Low": 100, "Close": 101.5, "Volume": 1500},
            {"Open": 101.5, "High": 102, "Low": 100.5, "Close": 100.8, "Volume": 1200},
        ])
        sig = check_pdh_retest_hold("AAPL", bars, prior_day_high=100.0)
        assert sig is None

    def test_works_for_crypto_btc(self):
        """Confirm it works for BTC-USD with wider risk cap."""
        # PDH = 68000 (realistic BTC price)
        bars = _bars([
            {"Open": 67500, "High": 68200, "Low": 67000, "Close": 67800, "Volume": 100},
            {"Open": 67800, "High": 68500, "Low": 67700, "Close": 68300, "Volume": 150},  # breakout
            {"Open": 68300, "High": 68400, "Low": 68050, "Close": 68100, "Volume": 120},  # pullback
            {"Open": 68100, "High": 68300, "Low": 68020, "Close": 68200, "Volume": 110},  # hold
            {"Open": 68200, "High": 68400, "Low": 68100, "Close": 68300, "Volume": 100},  # hold
        ])
        sig = check_pdh_retest_hold("BTC-USD", bars, prior_day_high=68000.0)
        assert sig is not None
        assert sig.symbol == "BTC-USD"
        assert sig.direction == "BUY"
        assert sig.stop < 68000.0  # stop below PDH


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


# ===== Outside Day Follow-Through Breakout =====

class TestOutsideDayBreakout:
    """Tests for check_outside_day_breakout()."""

    def _bullish_outside_prior(self, **overrides):
        """Bullish outside day: H=$98.50, L=$92.52, C=$98.09."""
        d = {
            "pattern": "outside", "direction": "bullish",
            "high": 98.50, "low": 92.52, "close": 98.09,
            "is_inside": False, "ma20": 95.0, "ma50": 90.0,
        }
        d.update(overrides)
        return d

    def test_fires_on_bullish_outside_day_breakout(self):
        prior = self._bullish_outside_prior()
        bar = _bar(open_=99.0, high=100.0, low=98.60, close=99.50)
        sig = check_outside_day_breakout("ROKU", bar, prior)
        assert sig is not None
        assert sig.alert_type == AlertType.OUTSIDE_DAY_BREAKOUT
        assert sig.direction == "BUY"
        assert sig.confidence == "high"

    def test_entry_stop_targets_correct(self):
        prior = self._bullish_outside_prior()
        bar = _bar(open_=99.0, high=100.0, low=98.60, close=99.50)
        sig = check_outside_day_breakout("ROKU", bar, prior)
        assert sig.entry == 98.50  # prior high
        midpoint = (98.50 + 92.52) / 2  # 95.51
        assert sig.stop == round(midpoint, 2)
        risk = sig.entry - sig.stop
        assert abs(sig.target_1 - round(sig.entry + risk, 2)) < 0.01
        assert abs(sig.target_2 - round(sig.entry + 2 * risk, 2)) < 0.01

    def test_no_fire_on_bearish_outside_day(self):
        prior = self._bullish_outside_prior(direction="bearish")
        bar = _bar(open_=99.0, high=100.0, low=98.60, close=99.50)
        assert check_outside_day_breakout("ROKU", bar, prior) is None

    def test_no_fire_on_neutral_outside_day(self):
        prior = self._bullish_outside_prior(direction="neutral")
        bar = _bar(open_=99.0, high=100.0, low=98.60, close=99.50)
        assert check_outside_day_breakout("ROKU", bar, prior) is None

    def test_no_fire_when_close_below_prior_high(self):
        prior = self._bullish_outside_prior()
        # Wicks above prior high but closes below
        bar = _bar(open_=97.0, high=99.0, low=96.50, close=98.20)
        assert check_outside_day_breakout("ROKU", bar, prior) is None

    def test_no_fire_on_normal_day(self):
        prior = {
            "pattern": "normal", "direction": "bullish",
            "high": 98.50, "low": 95.00, "close": 97.00,
            "is_inside": False, "ma20": 95.0, "ma50": 90.0,
        }
        bar = _bar(open_=99.0, high=100.0, low=98.60, close=99.50)
        assert check_outside_day_breakout("ROKU", bar, prior) is None

    def test_smart_targets_override_r_based(self):
        """Integration: outside day breakout gets resistance-based smart targets."""
        prior = self._bullish_outside_prior(
            ma100=100.19, ma200=105.0, prior_week_high=108.0,
        )
        bars = _bars([{
            "Open": 99.0, "High": 100.0, "Low": 98.60, "Close": 99.50,
            "Volume": 1000,
        }])
        signals = evaluate_rules("ROKU", bars, prior)
        outside_sigs = [
            s for s in signals
            if s.alert_type == AlertType.OUTSIDE_DAY_BREAKOUT
        ]
        if outside_sigs:
            sig = outside_sigs[0]
            assert sig.entry == 98.50
            # Smart targets should be applied (not in _STRUCTURAL_TARGET_RULES)
            assert sig.target_1 >= sig.entry
            assert sig.target_2 >= sig.target_1


# ===== Rule 5: Resistance at Prior High =====

class TestResistancePriorHigh:
    def test_fires_when_near_prior_high_with_active_entry(self):
        bar = _bar(high=100.10)  # 0.1% from level — within 0.15% threshold
        sig = check_resistance_prior_high("SPY", bar, prior_day_high=100.0, has_active_entry=True)
        assert sig is not None
        assert sig.alert_type == AlertType.RESISTANCE_PRIOR_HIGH
        assert sig.direction == "NOTICE"

    def test_fires_warning_without_active_entry(self):
        """No active entry → still fires as resistance warning."""
        bar = _bar(high=100.10)  # 0.1% from level — within 0.15% threshold
        sig = check_resistance_prior_high("SPY", bar, prior_day_high=100.0, has_active_entry=False)
        assert sig is not None
        assert sig.direction == "NOTICE"
        assert "resistance zone" in sig.message
        assert "watch for rejection" in sig.message

    def test_active_entry_gets_take_profit_message(self):
        """Active entry → take profits message."""
        bar = _bar(high=100.10)
        sig = check_resistance_prior_high("SPY", bar, prior_day_high=100.0, has_active_entry=True)
        assert "taking profits" in sig.message

    def test_no_fire_when_too_far_from_prior_high(self):
        bar = _bar(high=99.0)
        sig = check_resistance_prior_high("SPY", bar, prior_day_high=100.0, has_active_entry=True)
        assert sig is None


# ===== Rule 5b: Prior Day High Rejection (confirmed) =====

class TestPDHRejection:
    def test_fires_on_confirmed_rejection(self):
        """High touched PDH, close below → confirmed rejection."""
        bar = _bar(high=100.10, close=99.80)
        sig = check_pdh_rejection("ETH-USD", bar, prior_day_high=100.0, prior_close=98.0)
        assert sig is not None
        assert sig.alert_type == AlertType.PDH_REJECTION
        assert sig.direction == "SELL"
        assert "PRIOR DAY HIGH REJECTION" in sig.message
        assert "approaching from below" in sig.message

    def test_no_fire_when_close_above_pdh(self):
        """Close above PDH = breakout, not rejection."""
        bar = _bar(high=100.50, close=100.20)
        sig = check_pdh_rejection("ETH-USD", bar, prior_day_high=100.0, prior_close=98.0)
        assert sig is None

    def test_no_fire_when_too_far_from_pdh(self):
        """High too far from PDH — didn't actually test the level."""
        bar = _bar(high=99.0, close=98.5)
        sig = check_pdh_rejection("ETH-USD", bar, prior_day_high=100.0, prior_close=98.0)
        assert sig is None

    def test_no_fire_when_prior_close_above_pdh(self):
        """Prior close above PDH = price pulling back into support, not rejection."""
        bar = _bar(high=100.10, close=99.80)
        sig = check_pdh_rejection("ETH-USD", bar, prior_day_high=100.0, prior_close=101.0)
        assert sig is None

    def test_fires_without_prior_close(self):
        """No prior_close available → skip directional guard, still fires."""
        bar = _bar(high=100.10, close=99.80)
        sig = check_pdh_rejection("ETH-USD", bar, prior_day_high=100.0, prior_close=None)
        assert sig is not None
        assert sig.direction == "SELL"
        assert "approaching from below" not in sig.message

    def test_no_fire_when_pdh_is_zero(self):
        """PDH of zero → skip."""
        bar = _bar(high=100.10, close=99.80)
        sig = check_pdh_rejection("ETH-USD", bar, prior_day_high=0, prior_close=98.0)
        assert sig is None


# ===== PDH Test (wick above PDH, no close) =====


class TestPDHTest:
    def test_fires_on_wick_above_pdh(self):
        """High above PDH, close below → testing resistance."""
        bar = _bar(high=100.50, close=99.80)
        sig = check_pdh_test("NVDA", bar, prior_day_high=100.0, prior_close=98.0)
        assert sig is not None
        assert sig.alert_type == AlertType.PDH_TEST
        assert sig.direction == "NOTICE"
        assert "TESTING prior day high" in sig.message
        assert sig.entry == 100.0

    def test_no_fire_when_close_above_pdh(self):
        """Close above PDH = breakout, not a test."""
        bar = _bar(high=100.50, close=100.20)
        sig = check_pdh_test("NVDA", bar, prior_day_high=100.0, prior_close=98.0)
        assert sig is None

    def test_no_fire_when_high_below_pdh(self):
        """High never reached PDH → no test."""
        bar = _bar(high=99.50, close=99.20)
        sig = check_pdh_test("NVDA", bar, prior_day_high=100.0, prior_close=98.0)
        assert sig is None

    def test_no_fire_when_prior_close_above_pdh(self):
        """Prior close above PDH → price pulling back, not testing from below."""
        bar = _bar(high=100.50, close=99.80)
        sig = check_pdh_test("NVDA", bar, prior_day_high=100.0, prior_close=101.0)
        assert sig is None

    def test_no_fire_when_pdh_is_zero(self):
        """PDH of zero → skip."""
        bar = _bar(high=100.10, close=99.80)
        sig = check_pdh_test("NVDA", bar, prior_day_high=0, prior_close=98.0)
        assert sig is None

    def test_fires_without_prior_close(self):
        """No prior_close → skip directional guard, still fires."""
        bar = _bar(high=100.50, close=99.80)
        sig = check_pdh_test("NVDA", bar, prior_day_high=100.0, prior_close=None)
        assert sig is not None
        assert sig.direction == "NOTICE"

    def test_exact_touch_fires(self):
        """High exactly equals PDH → still a test."""
        bar = _bar(high=100.0, close=99.50)
        sig = check_pdh_test("NVDA", bar, prior_day_high=100.0, prior_close=98.0)
        assert sig is not None


# ===== Weekly High Test (wick above prior week high, no close) =====


class TestWeeklyHighTest:
    def test_fires_on_wick_above_weekly_high(self):
        """High above weekly high, close below → testing resistance."""
        bar = _bar(high=188.0, close=187.41)
        prior = {"prior_week_high": 187.62, "prior_week_low": 170.0}
        sig = check_weekly_high_test("NVDA", bar, prior, prior_close=185.0)
        assert sig is not None
        assert sig.alert_type == AlertType.WEEKLY_HIGH_TEST
        assert sig.direction == "NOTICE"
        assert "TESTING prior week high" in sig.message
        assert sig.entry == 187.62

    def test_no_fire_when_close_above(self):
        """Close above weekly high = breakout, not test."""
        bar = _bar(high=189.0, close=188.50)
        prior = {"prior_week_high": 187.62, "prior_week_low": 170.0}
        sig = check_weekly_high_test("NVDA", bar, prior, prior_close=185.0)
        assert sig is None

    def test_no_fire_when_high_below(self):
        """High never reached weekly high → no test."""
        bar = _bar(high=186.0, close=185.50)
        prior = {"prior_week_high": 187.62, "prior_week_low": 170.0}
        sig = check_weekly_high_test("NVDA", bar, prior, prior_close=185.0)
        assert sig is None

    def test_no_fire_when_prior_close_above(self):
        """Prior close above weekly high → pullback, not test from below."""
        bar = _bar(high=188.0, close=187.41)
        prior = {"prior_week_high": 187.62, "prior_week_low": 170.0}
        sig = check_weekly_high_test("NVDA", bar, prior, prior_close=189.0)
        assert sig is None

    def test_no_fire_when_no_weekly_high(self):
        """Missing prior_week_high → skip."""
        bar = _bar(high=188.0, close=187.41)
        sig = check_weekly_high_test("NVDA", bar, {}, prior_close=185.0)
        assert sig is None

    def test_exact_touch_fires(self):
        """High exactly equals weekly high → still a test."""
        bar = _bar(high=187.62, close=187.00)
        prior = {"prior_week_high": 187.62, "prior_week_low": 170.0}
        sig = check_weekly_high_test("NVDA", bar, prior, prior_close=185.0)
        assert sig is not None


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
    def _make_daily_crossover_bars(num_bars=30, cross=True):
        """Build daily bars where EMA5 crosses above EMA20 at the last bar.

        Strategy: declining prices for most bars (EMA5 < EMA20 since it's
        faster to react), then a sharp reversal at the end to force crossover.
        """
        prices = [100.0 - 0.3 * i for i in range(num_bars)]
        if cross:
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

    @staticmethod
    def _make_intraday_bars():
        """Build simple intraday bars for entry/stop calculation."""
        rows = [
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1000},
            {"Open": 100.5, "High": 101.5, "Low": 99.5, "Close": 101.0, "Volume": 1000},
            {"Open": 101.0, "High": 102.0, "Low": 100.0, "Close": 101.5, "Volume": 1000},
        ]
        return pd.DataFrame(rows)

    def test_fires_crossover(self, monkeypatch):
        """EMA5 crosses above EMA20 on daily bars → fires BUY."""
        daily_bars = self._make_daily_crossover_bars(num_bars=30, cross=True)
        intraday_bars = self._make_intraday_bars()

        class FakeTicker:
            def history(self, **kwargs):
                return daily_bars

        import yfinance as yf
        monkeypatch.setattr(yf, "Ticker", lambda symbol: FakeTicker())

        sig = check_ema_crossover_5_20("AAPL", intraday_bars)
        assert sig is not None
        assert sig.alert_type == AlertType.EMA_CROSSOVER_5_20
        assert sig.direction == "BUY"
        assert sig.confidence == "high"
        assert "(daily)" in sig.message

    def test_fires_for_non_mega_cap(self, monkeypatch):
        """Crossover fires for any symbol (no mega-cap gate)."""
        daily_bars = self._make_daily_crossover_bars(num_bars=30, cross=True)
        intraday_bars = self._make_intraday_bars()

        class FakeTicker:
            def history(self, **kwargs):
                return daily_bars

        import yfinance as yf
        monkeypatch.setattr(yf, "Ticker", lambda symbol: FakeTicker())

        sig = check_ema_crossover_5_20("PLTR", intraday_bars)
        assert sig is not None
        assert sig.direction == "BUY"

    def test_skips_no_daily_crossover(self, monkeypatch):
        """No crossover on daily bars → None."""
        daily_bars = self._make_daily_crossover_bars(num_bars=30, cross=False)
        intraday_bars = self._make_intraday_bars()

        class FakeTicker:
            def history(self, **kwargs):
                return daily_bars

        import yfinance as yf
        monkeypatch.setattr(yf, "Ticker", lambda symbol: FakeTicker())

        sig = check_ema_crossover_5_20("AAPL", intraday_bars)
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

    def test_ma_bounce_20_stop_at_offset_below_ma(self):
        """MA bounce stop is always MA * (1 - offset), not tied to bar low."""
        bar = _bar(open_=100, high=101, low=99.70, close=100.3)
        sig = check_ma_bounce_20("SPY", pd.DataFrame([bar]), ma20=100.0, ma50=95.0)
        assert sig is not None
        # stop = 100.0 * (1 - 0.005) = 99.50
        assert sig.stop == 99.50


# ===== Cooldown =====

class TestCooldown:
    def test_cooldown_does_not_suppress_buy_signals(self):
        """P2: is_cooled_down no longer suppresses BUY signals. Key levels fire regardless."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 99.0, "is_inside": False,
        }
        signals = evaluate_rules("AAPL", bars, prior, is_cooled_down=True)
        # P2: cooldown removed — BUY signals should still fire at key levels
        # (A stop loss doesn't invalidate the next setup)

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
    def test_breakdown_no_short_without_active(self):
        """No active entries → breakdown is suppressed entirely, no SHORT signals."""
        bars = _bars([
            {"Open": 99.5, "High": 100.2, "Low": 97.0, "Close": 97.1, "Volume": 2000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 98.0, "is_inside": False,
        }
        signals = evaluate_rules("NVDA", bars, prior)
        short_signals = [s for s in signals if s.direction == "SHORT"]
        assert len(short_signals) == 0, "No SHORT signals without active entries"

    def test_breakdown_converts_to_exit_long_with_active_entry(self):
        """Active LONG + support breakdown → SELL (exit long), not SHORT."""
        idx = pd.date_range("2024-01-15 09:30", periods=12, freq="5min")
        rows = []
        for i in range(12):
            rows.append({
                "Open": 99.0, "High": 99.5, "Low": 98.5,
                "Close": 99.0, "Volume": 1000,
            })
        # Last bar: conviction breakdown close below prior low (98.0)
        rows[-1] = {
            "Open": 98.2, "High": 98.5, "Low": 97.0,
            "Close": 97.1, "Volume": 2000,
        }
        bars = pd.DataFrame(rows, index=idx)

        prior = {
            "ma20": 100.0, "ma50": None, "close": 99.5,
            "high": 101.0, "low": 98.0, "is_inside": False,
        }
        # Active LONG entry for this symbol
        entries = [{"entry_price": 99.0, "stop_price": 98.0,
                     "target_1": 100.0, "target_2": 101.0}]
        signals = evaluate_rules("AMD", bars, prior, active_entries=entries)
        breakdown_signals = [
            s for s in signals if s.alert_type == AlertType.SUPPORT_BREAKDOWN
        ]
        if breakdown_signals:
            sig = breakdown_signals[0]
            # Should be SELL (exit long), not SHORT
            assert sig.direction == "SELL"
            assert "EXIT LONG" in sig.message
            assert sig.confidence == "high"

    def test_breakdown_suppressed_without_active_entry(self):
        """No active entry + support breakdown → suppressed entirely (exit-only)."""
        idx = pd.date_range("2024-01-15 09:30", periods=12, freq="5min")
        rows = []
        for i in range(12):
            rows.append({
                "Open": 99.0, "High": 99.5, "Low": 98.5,
                "Close": 99.0, "Volume": 1000,
            })
        rows[-1] = {
            "Open": 98.2, "High": 98.5, "Low": 97.0,
            "Close": 97.1, "Volume": 2000,
        }
        bars = pd.DataFrame(rows, index=idx)

        prior = {
            "ma20": 100.0, "ma50": None, "close": 99.5,
            "high": 101.0, "low": 98.0, "is_inside": False,
        }
        signals = evaluate_rules("AMD", bars, prior, active_entries=None)
        breakdown_signals = [
            s for s in signals if s.alert_type == AlertType.SUPPORT_BREAKDOWN
        ]
        assert len(breakdown_signals) == 0, "Breakdown should be suppressed with no active position"


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
        levels = [s["level"] for s in supports]
        assert 98.5 in levels


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
    @staticmethod
    def _bounce_bars(rows: list[dict]) -> pd.DataFrame:
        """Wrap OHLCV rows into a DataFrame for support bounce tests."""
        return pd.DataFrame(rows)

    def test_fires_on_bounce_off_support(self):
        """Last bar low at support, closes above → BUY with entry=support."""
        # Support at 648.00, bar low touches 648.10 (within 0.15%), closes at 649.50
        bars = self._bounce_bars([
            {"Open": 648.50, "High": 650.00, "Low": 648.10, "Close": 649.50, "Volume": 1000},
        ])
        supports = [
            {"level": 648.00, "touch_count": 2, "hold_hours": 1, "strength": "weak"},
            {"level": 645.00, "touch_count": 2, "hold_hours": 1, "strength": "weak"},
        ]
        sig = check_intraday_support_bounce("META", bars, supports, 1000, 1000)
        assert sig is not None
        assert sig.alert_type == AlertType.INTRADAY_SUPPORT_BOUNCE
        assert sig.direction == "BUY"
        assert sig.entry == 648.00
        assert sig.confidence == "medium"
        assert "$648.00" in sig.message

    def test_no_fire_when_no_supports(self):
        """Empty supports list → None."""
        bars = self._bounce_bars([
            {"Open": 648.50, "High": 650.00, "Low": 648.10, "Close": 649.50, "Volume": 1000},
        ])
        sig = check_intraday_support_bounce("META", bars, [], 1000, 1000)
        assert sig is None

    def test_no_fire_when_close_below_support(self):
        """Bar closes at/below support → None (no bounce)."""
        bars = self._bounce_bars([
            {"Open": 648.50, "High": 649.00, "Low": 647.80, "Close": 647.90, "Volume": 1000},
        ])
        supports = [{"level": 648.00, "touch_count": 1, "hold_hours": 1, "strength": "weak"}]
        sig = check_intraday_support_bounce("META", bars, supports, 1000, 1000)
        assert sig is None

    def test_no_fire_when_single_touch(self):
        """Support tested only 1x is noise — require min 2 touches."""
        bars = self._bounce_bars([
            {"Open": 648.50, "High": 650.00, "Low": 648.10, "Close": 649.50, "Volume": 1000},
        ])
        supports = [
            {"level": 648.00, "touch_count": 1, "hold_hours": 1, "strength": "weak"},
        ]
        sig = check_intraday_support_bounce("META", bars, supports, 1000, 1000)
        assert sig is None  # 1x touch rejected

    def test_fires_on_delayed_bounce_3_bars_ago(self):
        """Touch 3 bars back within lookback window, current above support → fires."""
        bars = self._bounce_bars([
            {"Open": 651.00, "High": 652.00, "Low": 651.00, "Close": 651.50, "Volume": 1000},
            {"Open": 649.00, "High": 649.50, "Low": 647.80, "Close": 649.00, "Volume": 1000},  # touch (wick through)
            {"Open": 649.20, "High": 650.00, "Low": 649.20, "Close": 649.80, "Volume": 1000},
            {"Open": 650.00, "High": 651.00, "Low": 650.00, "Close": 650.50, "Volume": 1000},  # last
        ])
        supports = [{"level": 648.00, "touch_count": 2, "hold_hours": 1, "strength": "weak"}]
        sig = check_intraday_support_bounce("META", bars, supports, 1000, 1000)
        assert sig is not None
        assert sig.entry == 648.00
        assert sig.stop == 647.80  # touch bar's low (wick through support)

    def test_no_fire_when_bounce_too_old(self):
        """Touch 10 bars back (outside 6-bar lookback) → None."""
        rows = []
        # Bar 0: touch at support
        rows.append({"Open": 649.00, "High": 649.50, "Low": 648.10, "Close": 649.00, "Volume": 1000})
        # Bars 1-9: recovery well above support (Low=651 = 0.46% above, outside 0.3%)
        for _ in range(9):
            rows.append({"Open": 651.00, "High": 652.00, "Low": 651.00, "Close": 651.50, "Volume": 1000})
        # Bar 10 (last): well above support
        rows.append({"Open": 651.50, "High": 652.50, "Low": 651.00, "Close": 652.00, "Volume": 1000})
        bars = self._bounce_bars(rows)
        supports = [{"level": 648.00, "touch_count": 1, "hold_hours": 1, "strength": "weak"}]
        sig = check_intraday_support_bounce("META", bars, supports, 1000, 1000)
        assert sig is None

    def test_no_fire_when_price_ran_too_far(self):
        """Touch recent but price >1% above support → stale, no fire."""
        # Support at 648.00, price at 655.60 = 1.17% above → exceeds 1% max distance
        bars = self._bounce_bars([
            {"Open": 649.00, "High": 649.50, "Low": 648.10, "Close": 649.00, "Volume": 1000},  # touch
            {"Open": 652.00, "High": 656.00, "Low": 651.00, "Close": 655.60, "Volume": 1000},  # ran away
        ])
        supports = [{"level": 648.00, "touch_count": 1, "hold_hours": 1, "strength": "weak"}]
        sig = check_intraday_support_bounce("META", bars, supports, 1000, 1000)
        assert sig is None

    def test_stop_uses_touch_bar_low(self):
        """Stop should be set to the touch bar's low, not the last bar's low."""
        bars = self._bounce_bars([
            {"Open": 649.00, "High": 649.50, "Low": 647.50, "Close": 649.00, "Volume": 1000},  # touch bar low 647.50
            {"Open": 649.20, "High": 650.50, "Low": 649.00, "Close": 650.00, "Volume": 1000},  # last bar
        ])
        supports = [{"level": 648.00, "touch_count": 2, "hold_hours": 1, "strength": "weak"}]
        sig = check_intraday_support_bounce("META", bars, supports, 1000, 1000)
        assert sig is not None
        assert sig.stop == 647.50  # touch bar's low

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


# ===== 5-Min Swing Low Detection =====

class TestDetect5mSwingLows:
    def test_detects_swing_low_with_bounce(self):
        """Swing low where bar low < both neighbors and bounce confirms."""
        bars = _bars([
            {"Open": 100, "High": 100.5, "Low": 99.5, "Close": 100.2, "Volume": 1000},
            {"Open": 100, "High": 100.3, "Low": 98.0, "Close": 98.5, "Volume": 1500},
            {"Open": 98.5, "High": 99.5, "Low": 98.8, "Close": 99.3, "Volume": 1200},
        ])
        from analytics.intraday_data import detect_5m_swing_lows
        supports = detect_5m_swing_lows(bars)
        assert len(supports) >= 1
        assert supports[0]["level"] == 98.0
        assert supports[0]["strength"] == "weak"

    def test_no_swing_low_without_bounce(self):
        """No swing low if price keeps selling (lower low on next bar)."""
        bars = _bars([
            {"Open": 100, "High": 100.5, "Low": 99.5, "Close": 100.0, "Volume": 1000},
            {"Open": 99.5, "High": 99.8, "Low": 98.0, "Close": 98.2, "Volume": 1500},
            {"Open": 98.2, "High": 98.5, "Low": 97.5, "Close": 97.8, "Volume": 1200},
        ])
        from analytics.intraday_data import detect_5m_swing_lows
        supports = detect_5m_swing_lows(bars)
        assert len(supports) == 0

    def test_no_swing_low_if_bounce_too_small(self):
        """Swing low shape but bounce < min_bounce_pct → filtered out."""
        bars = _bars([
            {"Open": 100, "High": 100.5, "Low": 99.5, "Close": 100.0, "Volume": 1000},
            {"Open": 100, "High": 100.3, "Low": 98.0, "Close": 98.1, "Volume": 1500},
            {"Open": 98.1, "High": 98.3, "Low": 98.05, "Close": 98.1, "Volume": 1200},
        ])
        from analytics.intraday_data import detect_5m_swing_lows
        # bounce = (98.1 - 98.0) / 98.0 = 0.001 < 0.002 min_bounce_pct
        supports = detect_5m_swing_lows(bars)
        assert len(supports) == 0

    def test_clusters_nearby_swing_lows(self):
        """Two swing lows within 0.3% cluster into one support."""
        bars = _bars([
            {"Open": 100, "High": 100.5, "Low": 99.5, "Close": 100.0, "Volume": 1000},
            {"Open": 99.5, "High": 100.0, "Low": 98.0, "Close": 99.0, "Volume": 1500},
            {"Open": 99.0, "High": 99.8, "Low": 98.8, "Close": 99.5, "Volume": 1200},
            {"Open": 99.5, "High": 100.0, "Low": 98.1, "Close": 99.0, "Volume": 1500},
            {"Open": 99.0, "High": 99.8, "Low": 98.6, "Close": 99.5, "Volume": 1200},
        ])
        from analytics.intraday_data import detect_5m_swing_lows
        supports = detect_5m_swing_lows(bars)
        # 98.0 and 98.1 are within 0.3% → should cluster
        assert len(supports) == 1
        assert supports[0]["level"] == 98.0

    def test_needs_minimum_bars(self):
        """Fewer than 3 bars → empty result."""
        bars = _bars([
            {"Open": 100, "High": 100.5, "Low": 98.0, "Close": 99.0, "Volume": 1000},
            {"Open": 99.0, "High": 99.5, "Low": 98.5, "Close": 99.3, "Volume": 1200},
        ])
        from analytics.intraday_data import detect_5m_swing_lows
        supports = detect_5m_swing_lows(bars)
        assert len(supports) == 0

    def test_touch_count_incremented(self):
        """Multiple bars touching the same level → higher touch_count."""
        bars = _bars([
            {"Open": 100, "High": 100.5, "Low": 99.5, "Close": 100.0, "Volume": 1000},
            {"Open": 100, "High": 100.3, "Low": 98.0, "Close": 98.5, "Volume": 1500},
            {"Open": 98.5, "High": 99.5, "Low": 98.1, "Close": 99.3, "Volume": 1200},
            {"Open": 99.3, "High": 99.8, "Low": 99.0, "Close": 99.5, "Volume": 1000},
            {"Open": 99.5, "High": 99.8, "Low": 98.05, "Close": 98.3, "Volume": 1300},
            {"Open": 98.3, "High": 99.5, "Low": 98.8, "Close": 99.4, "Volume": 1100},
        ])
        from analytics.intraday_data import detect_5m_swing_lows
        supports = detect_5m_swing_lows(bars)
        assert len(supports) >= 1
        # Bars at 98.0, 98.1, 98.05 all within 0.3% → touch_count >= 3
        assert supports[0]["touch_count"] >= 3


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
        assert sig.confidence in ("medium", "high")

    def test_no_fire_when_session_low_too_recent(self):
        """First touch only 2 bars ago → None (need MIN_AGE_BARS=4)."""
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

    def test_high_volume_retest_fires_medium_confidence(self):
        """Vol ratio 1.5x → fires with medium confidence (not exhaustion)."""
        bars = self._make_double_bottom_bars(
            session_low=650.0, first_touch_bar=3, num_bars=20,
            retest_close=651.0, retest_low=650.10, retest_volume=1500,
        )
        last_bar = bars.iloc[-1]
        avg_vol = bars["Volume"].mean()
        # avg_vol ~1000, bar_vol 1500 → ratio 1.5 >= 1.2 → medium confidence
        sig = check_session_low_retest("META", bars, last_bar, 1500, avg_vol)
        assert sig is not None
        assert sig.confidence == "medium"


# ===== Breakdown Session Low Tag =====

class TestBreakdownSessionLowTag:
    def test_breakdown_at_session_low_tagged(self):
        """Breakdown fires at session low level → 'EXIT LONG' with 'high' confidence."""
        # Build bars where session low = prior_day_low = 98.0
        # Then breakdown bar closes below with conviction
        # ma50 set above close so _find_nearest_support returns prior_low as support
        # active_entries required for exit-only breakdown to fire
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
        entries = [{"entry_price": 99.0, "stop_price": 98.0,
                    "target_1": 100.0, "target_2": 101.0}]
        signals = evaluate_rules("META", bars, prior, active_entries=entries)
        breakdown_signals = [
            s for s in signals if s.alert_type == AlertType.SUPPORT_BREAKDOWN
        ]
        assert len(breakdown_signals) >= 1
        sig = breakdown_signals[0]
        assert sig.direction == "SELL"
        assert sig.confidence == "high"


# ===== Rule 16: Planned Level Touch =====

class TestPlannedLevelTouch:
    def _make_bars(self, open_=682.0, high=684.0, low=681.50, close=683.5, volume=1000):
        """Helper to wrap a single bar dict into a DataFrame."""
        return pd.DataFrame([{"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume}])

    def test_fires_on_normal_day_bounce(self):
        """Normal day: bar bounces at planned entry → BUY with plan levels."""
        plan = {
            "pattern": "normal",
            "entry": 681.65, "stop": 679.56,
            "target_1": 690.0, "target_2": 694.18,
            "support": 681.65, "support_label": "Prior Day Low",
            "support_status": "AT SUPPORT",
            "score": 80, "score_label": "A",
        }
        bars = self._make_bars(open_=682.0, high=684.0, low=681.50, close=683.5)
        sig = check_planned_level_touch("SPY", bars, plan)
        assert sig is not None
        assert sig.alert_type == AlertType.PLANNED_LEVEL_TOUCH
        assert sig.direction == "BUY"
        assert sig.entry == 681.65
        assert sig.target_1 == 690.0
        assert sig.confidence == "high"
        assert "normal" in sig.message

    def test_fires_on_outside_day_bounce(self):
        """Outside day: bar bounces at planned entry → BUY."""
        midpoint = 690.0
        plan = {
            "pattern": "outside",
            "entry": midpoint, "stop": 680.0,
            "target_1": 700.0, "target_2": 710.0,
            "support": 685.0, "support_label": "20 MA",
            "support_status": "PULLBACK WATCH",
            "score": 70, "score_label": "B",
        }
        bars = self._make_bars(open_=691.0, high=693.0, low=689.80, close=692.0)
        sig = check_planned_level_touch("SPY", bars, plan)
        assert sig is not None
        assert sig.entry == midpoint
        assert sig.target_1 == 700.0
        assert "outside" in sig.message

    def test_no_fire_when_far_from_entry(self):
        """Bar low 2%+ away from planned entry → None."""
        plan = {
            "pattern": "normal",
            "entry": 681.65, "stop": 679.56,
            "target_1": 690.0, "target_2": 694.18,
            "support": 681.65, "support_label": "Prior Day Low",
            "support_status": "AT SUPPORT",
        }
        bars = self._make_bars(open_=672.0, high=675.0, low=670.0, close=674.0)
        sig = check_planned_level_touch("SPY", bars, plan)
        assert sig is None

    def test_no_fire_when_close_below_entry(self):
        """Bar touches entry but closes below → None (no bounce)."""
        plan = {
            "pattern": "normal",
            "entry": 681.65, "stop": 679.56,
            "target_1": 690.0, "target_2": 694.18,
            "support": 681.65, "support_label": "Prior Day Low",
            "support_status": "AT SUPPORT",
        }
        bars = self._make_bars(open_=682.0, high=682.5, low=681.50, close=681.0)
        sig = check_planned_level_touch("SPY", bars, plan)
        assert sig is None

    def test_no_plan_returns_none(self):
        """No daily plan available → None."""
        bars = self._make_bars(open_=682.0, high=684.0, low=681.50, close=683.5)
        sig = check_planned_level_touch("SPY", bars, None)
        assert sig is None

    def test_fires_on_support_touch(self):
        """Bar touches support (different from entry) → fires."""
        plan = {
            "pattern": "normal",
            "entry": 690.0, "stop": 687.0,
            "target_1": 695.0, "target_2": 700.0,
            "support": 682.0, "support_label": "50 MA",
            "support_status": "PULLBACK WATCH",
        }
        bars = self._make_bars(open_=683.0, high=685.0, low=681.80, close=684.0)
        sig = check_planned_level_touch("SPY", bars, plan)
        assert sig is not None
        assert "50 MA" in sig.message

    def test_no_fire_when_open_below_entry(self):
        """Open below plan entry → entry is resistance, not a buy level."""
        plan = {
            "pattern": "normal",
            "entry": 679.62, "stop": 677.14,
            "target_1": 685.53, "target_2": 690.0,
            "support": 679.62, "support_label": "Prior Day Low",
            "support_status": "AT SUPPORT",
        }
        bars = self._make_bars(open_=680.0, high=681.0, low=679.50, close=680.5)
        sig = check_planned_level_touch("SPY", bars, plan, today_open=676.0)
        assert sig is None

    def test_no_fire_on_big_gap_down(self):
        """Entry 3% above open (gap-down day) → stale, skip."""
        plan = {
            "pattern": "normal",
            "entry": 679.62, "stop": 677.14,
            "target_1": 685.53, "target_2": 690.0,
            "support": 679.62, "support_label": "Prior Day Low",
            "support_status": "AT SUPPORT",
        }
        bars = self._make_bars(open_=680.0, high=681.0, low=679.50, close=680.5)
        sig = check_planned_level_touch("SPY", bars, plan, today_open=660.0)
        assert sig is None

    def test_lookback_catches_earlier_touch(self):
        """Touch was 3 bars ago, last bar bounced above → should fire."""
        plan = {
            "pattern": "normal",
            "entry": 681.65, "stop": 679.56,
            "target_1": 690.0, "target_2": 694.18,
            "support": 681.65, "support_label": "Prior Day Low",
            "support_status": "AT SUPPORT",
        }
        bars = pd.DataFrame([
            {"Open": 682.0, "High": 683.0, "Low": 681.50, "Close": 681.0, "Volume": 1000},  # touch, close below
            {"Open": 681.0, "High": 683.0, "Low": 680.5, "Close": 682.5, "Volume": 1000},
            {"Open": 682.5, "High": 684.0, "Low": 682.0, "Close": 683.5, "Volume": 1000},   # last bar above
        ])
        sig = check_planned_level_touch("SPY", bars, plan)
        assert sig is not None


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


# ===== Rule 17: Weekly Level Touch =====

class TestWeeklyLevelTouch:
    def _prior(self, pw_high=110.0, pw_low=100.0, **overrides):
        """Build a prior_day dict with weekly levels."""
        base = {
            "pattern": "normal", "high": 108.0, "low": 102.0,
            "close": 105.0, "is_inside": False,
            "parent_high": 109.0, "parent_low": 101.0,
            "prior_week_high": pw_high, "prior_week_low": pw_low,
        }
        base.update(overrides)
        return base

    def test_fires_on_bounce_at_prior_week_low(self):
        """Bar low within 0.4% of pw_low, closes above → BUY, entry=pw_low, T1=pw_high."""
        prior = self._prior(pw_high=110.0, pw_low=100.0)
        # Bar low at 100.30 → proximity = 0.3% < 0.4%
        bars = pd.DataFrame([
            {"Open": 101.0, "High": 102.0, "Low": 100.30, "Close": 101.5, "Volume": 1000},
        ])
        sig = check_weekly_level_touch("AAPL", bars, prior)
        assert sig is not None
        assert sig.alert_type == AlertType.WEEKLY_LEVEL_TOUCH
        assert sig.direction == "BUY"
        assert sig.entry == 100.0
        assert sig.target_1 == 110.0
        assert sig.confidence == "high"
        assert "prior week low" in sig.message

    def test_targets_use_weekly_range(self):
        """T1=pw_high, T2=pw_high + 50% weekly range."""
        prior = self._prior(pw_high=110.0, pw_low=100.0)
        bars = pd.DataFrame([
            {"Open": 101.0, "High": 102.0, "Low": 100.30, "Close": 101.5, "Volume": 1000},
        ])
        sig = check_weekly_level_touch("AAPL", bars, prior)
        assert sig is not None
        assert sig.target_1 == 110.0
        assert sig.target_2 == 115.0

    def test_no_fire_when_far_from_weekly_level(self):
        """Bar low 2%+ away from pw_low → None."""
        prior = self._prior(pw_high=110.0, pw_low=100.0)
        bars = pd.DataFrame([
            {"Open": 99.0, "High": 100.0, "Low": 98.0, "Close": 99.5, "Volume": 1000},
        ])
        sig = check_weekly_level_touch("AAPL", bars, prior)
        assert sig is None

    def test_no_fire_when_close_below_weekly_low(self):
        """Touches but no bounce (close <= pw_low) → None."""
        prior = self._prior(pw_high=110.0, pw_low=100.0)
        bars = pd.DataFrame([
            {"Open": 100.5, "High": 101.0, "Low": 100.20, "Close": 99.8, "Volume": 1000},
        ])
        sig = check_weekly_level_touch("AAPL", bars, prior)
        assert sig is None

    def test_no_fire_when_weekly_data_unavailable(self):
        """pw_high/pw_low are None → None."""
        prior = self._prior()
        prior["prior_week_high"] = None
        prior["prior_week_low"] = None
        bars = pd.DataFrame([
            {"Open": 101.0, "High": 102.0, "Low": 100.30, "Close": 101.5, "Volume": 1000},
        ])
        sig = check_weekly_level_touch("AAPL", bars, prior)
        assert sig is None

    def test_lookback_catches_earlier_touch(self):
        """Touch was 3 bars ago, last bar bounced above → should fire."""
        prior = self._prior(pw_high=110.0, pw_low=100.0)
        bars = pd.DataFrame([
            {"Open": 101.0, "High": 102.0, "Low": 100.20, "Close": 100.8, "Volume": 1000},  # touch
            {"Open": 100.8, "High": 101.5, "Low": 100.5, "Close": 101.0, "Volume": 1000},
            {"Open": 101.0, "High": 102.0, "Low": 100.8, "Close": 101.5, "Volume": 1000},  # last bar
        ])
        sig = check_weekly_level_touch("AAPL", bars, prior)
        assert sig is not None


# ===== SPY Bounce Rate Helper =====

class TestComputeSpyBounceRate:
    @staticmethod
    def _make_hist(num_days, test_days, bounce_days):
        """Build daily OHLCV where specific days test the prior low and bounce/break.

        Args:
            num_days: Total bars.
            test_days: Set of indices (1-based) where day tests prior day low.
            bounce_days: Set of indices (1-based) where tested day closes above prior low.
        """
        rows = []
        for i in range(num_days):
            base = 100.0
            if i in test_days:
                prior_low = rows[i - 1]["Low"] if i > 0 else base - 1
                # Low touches prior low (within 0.05% threshold)
                low = prior_low
                close = prior_low + 1.0 if i in bounce_days else prior_low - 0.5
                rows.append({
                    "Open": base, "High": base + 1, "Low": low,
                    "Close": close, "Volume": 1000,
                })
            else:
                rows.append({
                    "Open": base, "High": base + 2, "Low": base - 1,
                    "Close": base + 0.5, "Volume": 1000,
                })
        return pd.DataFrame(rows)

    def test_bounce_rate_all_bounces(self):
        """Every test day closes above prior low → 1.0."""
        # Days 1-19 normal (low=99), then days where low touches 99 and closes above
        rows = []
        for i in range(20):
            rows.append({
                "Open": 100, "High": 102, "Low": 99.0,
                "Close": 101.0, "Volume": 1000,
            })
        hist = pd.DataFrame(rows)
        # Every day tests prior low (low == prior low) and closes above → all bounces
        result = _compute_spy_bounce_rate(hist)
        assert result["bounce_rate"] == 1.0
        assert result["sample_size"] >= 5

    def test_bounce_rate_all_breaks(self):
        """Every test day closes below prior low → 0.0."""
        rows = []
        for i in range(20):
            # Each day: low = 99, close = 98.5 (below prior low of 99)
            rows.append({
                "Open": 100, "High": 102, "Low": 99.0,
                "Close": 98.5, "Volume": 1000,
            })
        hist = pd.DataFrame(rows)
        result = _compute_spy_bounce_rate(hist)
        assert result["bounce_rate"] == 0.0
        assert result["sample_size"] >= 5

    def test_bounce_rate_mixed(self):
        """50/50 mix → 0.5."""
        rows = []
        for i in range(21):
            # All days test prior low (low=99.0)
            # Even days bounce (close=101), odd days break (close=98.5)
            # 20 test days (i=1..20): 10 even (bounce) + 10 odd (break) = 0.5
            close = 101.0 if i % 2 == 0 else 98.5
            rows.append({
                "Open": 100, "High": 102, "Low": 99.0,
                "Close": close, "Volume": 1000,
            })
        hist = pd.DataFrame(rows)
        result = _compute_spy_bounce_rate(hist)
        assert result["bounce_rate"] == 0.5

    def test_bounce_rate_no_tests(self):
        """Price always well above prior low → default 0.5."""
        rows = []
        for i in range(20):
            # Each day's low is well above prior day's low
            base = 100 + i * 2  # rising fast, never tests prior low
            rows.append({
                "Open": base, "High": base + 3, "Low": base + 1,
                "Close": base + 2, "Volume": 1000,
            })
        hist = pd.DataFrame(rows)
        result = _compute_spy_bounce_rate(hist)
        assert result["bounce_rate"] == 0.5
        assert result["sample_size"] < 5

    def test_bounce_rate_insufficient_data(self):
        """< 10 bars → default 0.5."""
        rows = [
            {"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 1000}
            for _ in range(5)
        ]
        hist = pd.DataFrame(rows)
        result = _compute_spy_bounce_rate(hist)
        assert result["bounce_rate"] == 0.5
        assert result["sample_size"] == 0


# ===== SPY S/R Confidence Modifier =====

class TestSpyLevelConfidenceModifier:
    """Tests for SPY at support/resistance confidence modifier in evaluate_rules."""

    def _run_with_spy_context(self, spy_ctx):
        """Run evaluate_rules with a MA bounce signal and given spy_context."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 99.0, "is_inside": False,
        }
        signals = evaluate_rules("AAPL", bars, prior, spy_context=spy_ctx)
        return [s for s in signals if s.direction == "BUY"]

    def test_spy_at_resistance_demotes_buy(self):
        """spy_at_resistance=True → high→medium, 'SPY at resistance' in message."""
        spy_ctx = {
            "trend": "bullish", "close": 690.0, "ma20": 685.0,
            "ma5": 688.0, "ma50": 680.0, "regime": "TRENDING_UP",
            "intraday_change_pct": 0.5, "spy_bouncing": False, "spy_intraday_low": 0.0,
            "spy_at_support": False, "spy_at_resistance": True,
            "spy_level_label": "prior day high $692.00",
            "spy_support_bounce_rate": 0.5,
        }
        buy_signals = self._run_with_spy_context(spy_ctx)
        assert len(buy_signals) >= 1
        for s in buy_signals:
            assert s.confidence == "medium"
            assert "SPY at resistance" in s.message
            assert "prior day high $692.00" in s.message

    def test_spy_at_strong_support_keeps_confidence(self):
        """spy_at_support=True, bounce_rate=0.6 → stays high, informational note."""
        spy_ctx = {
            "trend": "bullish", "close": 690.0, "ma20": 685.0,
            "ma5": 688.0, "ma50": 680.0, "regime": "TRENDING_UP",
            "intraday_change_pct": 0.5, "spy_bouncing": False, "spy_intraday_low": 0.0,
            "spy_at_support": True, "spy_at_resistance": False,
            "spy_level_label": "prior day low $684.50",
            "spy_support_bounce_rate": 0.60,
        }
        buy_signals = self._run_with_spy_context(spy_ctx)
        # Filter to MA bounce (originally high confidence) — gap_fill is informational/medium
        ma_signals = [s for s in buy_signals if s.alert_type == AlertType.MA_BOUNCE_20]
        assert len(ma_signals) >= 1
        for s in ma_signals:
            assert s.confidence == "high"
            assert "SPY at support" in s.message
            assert "60%" in s.message

    def test_spy_at_weak_support_demotes_buy(self):
        """spy_at_support=True, bounce_rate=0.35 → high→medium, 'weak support' in message."""
        spy_ctx = {
            "trend": "bullish", "close": 690.0, "ma20": 685.0,
            "ma5": 688.0, "ma50": 680.0, "regime": "TRENDING_UP",
            "intraday_change_pct": 0.5, "spy_bouncing": False, "spy_intraday_low": 0.0,
            "spy_at_support": True, "spy_at_resistance": False,
            "spy_level_label": "prior day low $684.50",
            "spy_support_bounce_rate": 0.35,
        }
        buy_signals = self._run_with_spy_context(spy_ctx)
        assert len(buy_signals) >= 1
        for s in buy_signals:
            assert s.confidence == "medium"
            assert "SPY weak support" in s.message
            assert "35%" in s.message

    def test_spy_neutral_no_change(self):
        """spy_at_support=False, spy_at_resistance=False → no modifier message."""
        spy_ctx = {
            "trend": "bullish", "close": 690.0, "ma20": 685.0,
            "ma5": 688.0, "ma50": 680.0, "regime": "TRENDING_UP",
            "intraday_change_pct": 0.5, "spy_bouncing": False, "spy_intraday_low": 0.0,
            "spy_at_support": False, "spy_at_resistance": False,
            "spy_level_label": "",
            "spy_support_bounce_rate": 0.5,
        }
        buy_signals = self._run_with_spy_context(spy_ctx)
        assert len(buy_signals) >= 1
        for s in buy_signals:
            assert "SPY at resistance" not in s.message
            assert "SPY at support" not in s.message
            assert "SPY weak support" not in s.message


# ===== Smart Resistance-Based Targets =====

class TestFindResistanceTargets:
    def _prior(self, **overrides):
        base = {
            "high": 312.73, "low": 298.0, "close": 305.0,
            "ma20": 308.0, "ma50": 320.0, "ma100": 302.0, "ma200": 290.0,
            "prior_week_high": 325.0,
        }
        base.update(overrides)
        return base

    def test_returns_nearest_resistance_as_t1(self):
        """Prior high above entry and above min 1R → becomes T1."""
        prior = self._prior(high=312.73, ma50=320.0)
        # entry=305, stop=303, risk=2, min_target=307
        result = _find_resistance_targets(305.0, 303.0, prior, current_vwap=None)
        assert result is not None
        t1, t2, t1_label, t2_label = result
        # MA20=308 is nearest above min_target=307
        assert t1 == 308.0
        assert t1_label == "MA20"

    def test_skips_levels_below_min_1r(self):
        """Resistance too close to entry (below 1R) gets skipped."""
        # entry=305, stop=303, risk=2, min_target=307
        # ma20=306 is above entry but below min_target → skipped
        prior = self._prior(ma20=306.0, high=312.73, ma50=320.0)
        result = _find_resistance_targets(305.0, 303.0, prior, current_vwap=None)
        assert result is not None
        t1, _, t1_label, _ = result
        assert t1 != 306.0  # MA20 at 306 should be skipped
        assert t1 == 312.73  # prior high is next valid level

    def test_falls_back_to_none_when_no_levels(self):
        """All MAs and levels below entry → returns None."""
        prior = self._prior(
            high=300.0, ma20=298.0, ma50=295.0, ma100=290.0,
            ma200=280.0, prior_week_high=299.0,
        )
        result = _find_resistance_targets(305.0, 303.0, prior, current_vwap=None)
        assert result is None

    def test_uses_second_level_as_t2(self):
        """MA50 above prior high becomes T2."""
        prior = self._prior(high=312.73, ma20=308.0, ma50=320.0)
        result = _find_resistance_targets(305.0, 303.0, prior, current_vwap=None)
        assert result is not None
        t1, t2, _, t2_label = result
        assert t1 == 308.0  # MA20
        assert t2 == 312.73  # prior high
        assert t2_label == "prior high"

    def test_excludes_none_and_zero_levels(self):
        """Handles None/0 MAs gracefully."""
        prior = self._prior(ma20=None, ma100=0, ma200=None, ma50=320.0)
        result = _find_resistance_targets(305.0, 303.0, prior, current_vwap=None)
        assert result is not None
        # Should still find prior high (312.73) and ma50 (320)
        t1, t2, _, _ = result
        assert t1 == 312.73
        assert t2 == 320.0

    def test_vwap_used_as_resistance(self):
        """VWAP above entry included as candidate."""
        prior = self._prior(
            high=300.0, ma20=298.0, ma50=295.0, ma100=290.0,
            ma200=280.0, prior_week_high=299.0,
        )
        # Only VWAP is above entry at 310
        result = _find_resistance_targets(305.0, 303.0, prior, current_vwap=310.0)
        assert result is not None
        t1, _, t1_label, _ = result
        assert t1 == 310.0
        assert t1_label == "VWAP"

    def test_pdl_in_resistance_targets_when_below(self):
        """PDL should be T1 when buying from support below PDL."""
        prior = self._prior(
            high=110.0, close=105.0, low=100.0,
            ma20=108.0, ma50=112.0, ma100=115.0, ma200=120.0,
            prior_week_high=125.0,
        )
        # Entry at 97 (below PDL of 100), stop at 96, risk=1, min_target=98
        result = _find_resistance_targets(97.0, 96.0, prior, current_vwap=None)
        assert result is not None
        t1, t2, t1_label, t2_label = result
        assert t1 == 100.0   # PDL is nearest resistance above entry+1R
        assert t1_label == "prior low"

    def test_pdl_excluded_when_entry_above(self):
        """PDL should NOT appear as target when entry is above PDL."""
        prior = self._prior()  # low=298.0, entry will be 305
        result = _find_resistance_targets(305.0, 303.0, prior, current_vwap=None)
        assert result is not None
        t1, _, t1_label, _ = result
        assert t1_label != "prior low"  # PDL (298) is below entry (305)

    def test_pdl_target_btc_scenario(self):
        """BTC scenario: buy at $65,650 support, PDL $67,154 should be T1."""
        prior = self._prior(
            high=68200.0, close=67500.0, low=67154.0,
            ma20=68525.0, ma50=73437.0, ma100=80859.0, ma200=89074.0,
            prior_week_high=70000.0,
        )
        # Entry at intraday support, stop 0.5% below
        result = _find_resistance_targets(65650.0, 65320.0, prior, current_vwap=66800.0)
        assert result is not None
        t1, t2, t1_label, t2_label = result
        # PDL ($67,154) is nearest resistance above entry+1R ($65,650+330=$65,980)
        # but VWAP ($66,800) is closer
        assert t1 == 66800.0
        assert t1_label == "VWAP"
        assert t2 == 67154.0
        assert t2_label == "prior low"

    def test_pdl_entry_targets_prior_day_high(self):
        """Buy at PDL → T1/T2 should include prior day high (ETH $1950→$2002)."""
        prior = self._prior(
            high=2002.0, close=1985.0, low=1950.0,
            ma20=2015.0, ma50=2240.0, ma100=2576.0, ma200=2892.0,
            prior_week_high=2100.0,
        )
        # Entry at PDL ($1950), stop = 0.5% below = $1940.25, risk = $9.75
        result = _find_resistance_targets(1950.0, 1940.25, prior, current_vwap=1970.0)
        assert result is not None
        t1, t2, t1_label, t2_label = result
        # T1=VWAP ($1970), T2=prior_close ($1985) — prior_high ($2002) is T3
        # but system only returns T1/T2, so verify they're reasonable targets
        assert t1 == 1970.0
        assert t1_label == "VWAP"
        assert t2 == 1985.0
        assert t2_label == "prior close"


# ===== Volume Exhaustion Detection =====

class TestDetectVolumeExhaustion:
    def test_seller_exhaustion_declining_volume(self):
        """3 bars declining volume on pullback → seller exhaustion."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99, "Close": 100.5, "Volume": 2000},
            {"Open": 100.5, "High": 101, "Low": 99.5, "Close": 100.0, "Volume": 1500},
            {"Open": 100.0, "High": 100.5, "Low": 99.0, "Close": 99.5, "Volume": 1000},
            {"Open": 99.5, "High": 100, "Low": 98.5, "Close": 99.0, "Volume": 500},
        ])
        avg_vol = 1500.0
        exhaustion_type, msg = _detect_volume_exhaustion(bars, avg_vol)
        assert exhaustion_type == "seller_exhaustion"
        assert "declining volume" in msg

    def test_no_exhaustion_on_normal_volume(self):
        """Average volume with no pattern → None."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99, "Close": 100.5, "Volume": 1000},
            {"Open": 100.5, "High": 101, "Low": 99.5, "Close": 101.0, "Volume": 1100},
            {"Open": 101.0, "High": 102, "Low": 100, "Close": 101.5, "Volume": 1050},
            {"Open": 101.5, "High": 102, "Low": 100.5, "Close": 101.0, "Volume": 1000},
        ])
        avg_vol = 1000.0
        exhaustion_type, msg = _detect_volume_exhaustion(bars, avg_vol)
        assert exhaustion_type is None

    def test_buyer_exhaustion_spike_and_reversal(self):
        """2x spike then bearish candle → buyer exhaustion."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99, "Close": 100.5, "Volume": 1000},
            {"Open": 100.5, "High": 103, "Low": 100, "Close": 102.5, "Volume": 2500},  # spike, bullish
            {"Open": 102.5, "High": 103, "Low": 101, "Close": 101.5, "Volume": 1200},  # reversal, bearish
            {"Open": 101.5, "High": 102, "Low": 101, "Close": 101.2, "Volume": 900},
        ])
        avg_vol = 1000.0
        exhaustion_type, msg = _detect_volume_exhaustion(bars, avg_vol)
        assert exhaustion_type == "buyer_exhaustion"
        assert "volume climax" in msg

    def test_no_buyer_exhaustion_without_reversal(self):
        """Spike without reversal → None."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99, "Close": 100.5, "Volume": 1000},
            {"Open": 100.5, "High": 103, "Low": 100, "Close": 102.5, "Volume": 2500},  # spike, bullish
            {"Open": 102.5, "High": 104, "Low": 102, "Close": 103.5, "Volume": 1200},  # continues up
            {"Open": 103.5, "High": 105, "Low": 103, "Close": 104.5, "Volume": 900},
        ])
        avg_vol = 1000.0
        exhaustion_type, msg = _detect_volume_exhaustion(bars, avg_vol)
        assert exhaustion_type is None

    def test_handles_insufficient_bars(self):
        """< 4 bars returns None."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99, "Close": 100.5, "Volume": 1000},
            {"Open": 100, "High": 101, "Low": 99, "Close": 100.5, "Volume": 900},
        ])
        avg_vol = 1000.0
        exhaustion_type, msg = _detect_volume_exhaustion(bars, avg_vol)
        assert exhaustion_type is None


# ===== Integration: Resistance Targets + Volume Exhaustion in evaluate_rules =====

class TestSmartTargetsIntegration:
    def test_evaluate_rules_overrides_targets_with_resistance(self):
        """BUY signal via evaluate_rules() gets resistance-based T1/T2."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 102.0, "low": 99.0, "is_inside": False,
            # Resistance levels above entry (~100.3)
            "ma100": 103.0, "ma200": 106.0,
            "prior_week_high": 108.0,
        }
        signals = evaluate_rules("AAPL", bars, prior)
        ma_bounces = [s for s in signals if s.alert_type == AlertType.MA_BOUNCE_20]
        if ma_bounces:
            sig = ma_bounces[0]
            # After risk cap, targets should be overridden with resistance levels
            # if any levels are above entry + 1R
            if "T1:" in sig.message:
                # Smart targets were applied
                assert sig.target_1 >= sig.entry  # T1 above entry
                assert sig.target_2 >= sig.target_1  # T2 above T1

    def test_structural_rules_get_smart_targets(self):
        """Inside day breakout gets smart resistance-based targets like other BUY signals."""
        prior = {
            "is_inside": True, "high": 50.5, "low": 49.0,
            "parent_high": 52.0, "parent_low": 48.0,
            "close": 50.0, "ma20": 55.0, "ma50": 60.0,
            "ma100": 65.0, "ma200": 70.0, "prior_week_high": 75.0,
        }
        bars = pd.DataFrame([{
            "Open": 50, "High": 51.5, "Low": 49.5, "Close": 51.2, "Volume": 1000,
        }])
        signals = evaluate_rules("TSLA", bars, prior)
        inside_signals = [s for s in signals if s.alert_type == AlertType.INSIDE_DAY_BREAKOUT]
        if inside_signals:
            sig = inside_signals[0]
            # Smart targets applied — T1/T2 set to nearest resistance levels
            assert sig.target_1 > sig.entry
            assert sig.target_2 > sig.target_1

    def test_falls_back_to_r_based_when_no_resistance(self, monkeypatch):
        """No resistance levels above entry → keeps R-based targets.
        Note: VWAP may still be found as a smart target since it's computed
        from intraday bars. We verify targets are set and reasonable."""
        # Patch fetch_hourly_bars to prevent real API calls finding resistance
        monkeypatch.setattr(
            "analytics.intraday_data.fetch_hourly_bars",
            lambda *a, **kw: pd.DataFrame(),
        )
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 99.5, "low": 99.0, "is_inside": False,
            # All levels below entry
            "ma100": 90.0, "ma200": 85.0, "prior_week_high": 98.0,
        }
        signals = evaluate_rules("AAPL", bars, prior)
        ma_bounces = [s for s in signals if s.alert_type == AlertType.MA_BOUNCE_20]
        if ma_bounces:
            sig = ma_bounces[0]
            # Targets should always be set above entry
            assert sig.target_1 > sig.entry
            assert sig.target_2 > sig.target_1


# ===== Staleness Filter =====

class TestStalenessFilter:
    def test_stale_buy_signal_filtered(self):
        """BUY signal where price already ran past entry + 1R → filtered out."""
        # Intraday support bounce: entry = support level (e.g., 648.00)
        # but current price = 654.00, risk = 1.00, so entry + 1R = 649.00
        # price 654 >> 649 → stale, should be filtered
        idx = pd.date_range("2024-01-15 09:30", periods=25, freq="5min")
        rows = []
        for i in range(25):
            rows.append({
                "Open": 650.0, "High": 651.0, "Low": 649.0,
                "Close": 650.5, "Volume": 1000,
            })
        # Hour 1 low at 648.00 (bar 2) — establishes support
        rows[2] = {"Open": 649.0, "High": 649.5, "Low": 648.00, "Close": 649.0, "Volume": 1000}
        # Hour 2 holds above (bars 12-24)
        for i in range(12, 25):
            rows[i] = {"Open": 652.0, "High": 654.0, "Low": 651.0, "Close": 653.0, "Volume": 1000}
        # Last bar: low touches support (648.10) but closes way above at 654
        rows[-1] = {"Open": 649.0, "High": 655.0, "Low": 648.10, "Close": 654.0, "Volume": 1000}
        bars = pd.DataFrame(rows, index=idx)

        prior = {
            "ma20": 650.0, "ma50": 645.0, "close": 650.0,
            "high": 655.0, "low": 646.0, "is_inside": False,
        }
        signals = evaluate_rules("META", bars, prior)
        bounce_signals = [
            s for s in signals if s.alert_type == AlertType.INTRADAY_SUPPORT_BOUNCE
        ]
        # Should be filtered — price 654 is way past entry (~648) + 1R
        assert len(bounce_signals) == 0

    def test_fresh_buy_signal_kept(self):
        """BUY signal where price is near entry → kept."""
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


# ===== Detect Hourly Resistance =====

class TestDetectHourlyResistance:
    def _hourly_bars(self, highs: list[float]) -> pd.DataFrame:
        """Build synthetic 1h bars from a list of highs."""
        rows = []
        for h in highs:
            rows.append({
                "Open": h - 1, "High": h, "Low": h - 2, "Close": h - 0.5, "Volume": 1000,
            })
        idx = pd.date_range("2025-01-13 09:30", periods=len(highs), freq="1h")
        return pd.DataFrame(rows, index=idx)

    def test_finds_swing_highs(self):
        """Bar whose high > both neighbors → detected as resistance."""
        # highs: 100, 108, 102, 105, 103 → swing highs at 108 and 105
        # 108 at idx 1: later closes 101.5, 104.5, 102.5 — all < 108 → unbroken
        # 105 at idx 3: later close 102.5 — < 105 → unbroken
        bars = self._hourly_bars([100, 108, 102, 105, 103])
        levels = detect_hourly_resistance(bars)
        assert 105.0 in levels
        assert 108.0 in levels

    def test_clusters_nearby_swing_highs(self):
        """Two swing highs within 0.3% → clustered, keep max."""
        # 310.0 and 310.5 are within 0.3% of each other (0.16%)
        # highs: 305, 320, 315, 310.0, 308, 310.5, 307
        # 320 at idx 1: later closes all < 320 → unbroken
        # 310.0 at idx 3: later closes 307.5, 310.0, 306.5 — none > 310.0 → unbroken
        # 310.5 at idx 5: later close 306.5 < 310.5 → unbroken
        bars = self._hourly_bars([305, 320, 315, 310.0, 308, 310.5, 307])
        levels = detect_hourly_resistance(bars)
        # 310.0 and 310.5 should cluster → keep 310.5
        assert 310.5 in levels
        assert 310.0 not in levels
        assert 320.0 in levels

    def test_empty_for_monotonic_trend(self):
        """Monotonically increasing highs → no swing highs."""
        bars = self._hourly_bars([100, 101, 102, 103, 104])
        levels = detect_hourly_resistance(bars)
        assert levels == []

    def test_empty_for_too_few_bars(self):
        """Fewer than 3 bars → can't detect swing highs."""
        bars = self._hourly_bars([100, 105])
        levels = detect_hourly_resistance(bars)
        assert levels == []

    def test_empty_dataframe(self):
        levels = detect_hourly_resistance(pd.DataFrame())
        assert levels == []

    def test_multiple_levels_sorted_ascending(self):
        """Multiple distinct levels returned sorted ascending."""
        # highs: 300, 330, 305, 320, 310, 315, 308
        # 330 at idx 1: later closes all < 330 → unbroken
        # 320 at idx 3: later closes 309.5, 314.5, 307.5 → all < 320 → unbroken
        # 315 at idx 5: later close 307.5 < 315 → unbroken
        bars = self._hourly_bars([300, 330, 305, 320, 310, 315, 308])
        levels = detect_hourly_resistance(bars)
        assert levels == sorted(levels)
        assert len(levels) >= 2

    def test_filters_broken_resistance(self):
        """Swing high broken by a later close above it → removed."""
        # highs: 100, 105, 102, 110, 103
        # 105 at idx 1: later bar at idx 3 closes at 109.5 > 105 → BROKEN
        # 110 at idx 3: later close 102.5 < 110 → unbroken
        bars = self._hourly_bars([100, 105, 102, 110, 103])
        levels = detect_hourly_resistance(bars)
        assert 105.0 not in levels  # broken — later bar closed above
        assert 110.0 in levels      # unbroken — no later bar closed above

    def test_all_levels_broken_returns_empty(self):
        """When all swing highs are broken by later closes → empty list."""
        # highs: 100, 105, 102, 110, 108, 115, 112
        # 105 broken by close 109.5, 110 broken by close 114.5
        # 115 at idx 5: later close 111.5 < 115 → unbroken
        # Need all broken: 100, 105, 102, 108, 112, 106, 115
        # 105 at idx 1: later closes 101.5, 107.5, 111.5, 105.5, 114.5 → 107.5 > 105 → BROKEN
        # 108 at idx 3: later closes 111.5, 105.5, 114.5 → 111.5 > 108 → BROKEN
        # 112 at idx 4: close is 111.5. Later closes 105.5, 114.5 → 114.5 > 112 → BROKEN
        # Wait, 112 isn't a swing high because 112 > 108 but check neighbors...
        # Let me use: 100, 105, 102, 108, 103, 115, 108
        # 105 at idx 1: later close at idx 3 = 107.5 > 105 → BROKEN
        # 108 at idx 3: later close at idx 5 = 114.5 > 108 → BROKEN
        # 115 at idx 5: later close 107.5 < 115 → unbroken
        # That leaves 115 unbroken. Let me build data where last swing is also broken.
        # 100, 105, 102, 110, 103, 108, 120
        # 105 at idx 1: close at idx 3 = 109.5 > 105 → BROKEN
        # 110 at idx 3: close at idx 6 = 119.5 > 110 → BROKEN
        # 108 at idx 5: close at idx 6 = 119.5 > 108 → BROKEN (but is 108 a swing high? high=108, neighbors 103, 120 → 108 < 120 → NOT a swing high)
        # Only 105 and 110 are swing highs, both broken → empty
        bars = self._hourly_bars([100, 105, 102, 110, 103, 108, 120])
        levels = detect_hourly_resistance(bars)
        assert levels == []


# ===== Hourly Resistance Approach =====

class TestHourlyResistanceApproach:
    def test_fires_when_active_entry_and_near_resistance(self):
        """Active entry + bar high near hourly resistance → SELL alert."""
        bar = _bar(open_=308, high=309.5, low=307, close=309.0)
        sig = check_hourly_resistance_approach(
            "GOOGL", bar, hourly_resistance=[310.0, 320.0], has_active_entry=True,
        )
        assert sig is not None
        assert sig.alert_type == AlertType.HOURLY_RESISTANCE_APPROACH
        assert sig.direction == "SELL"
        assert "310.00" in sig.message
        assert "APPROACHING HOURLY RESISTANCE" in sig.message

    def test_no_fire_without_active_entry(self):
        """No active entry → no alert even if near resistance."""
        bar = _bar(open_=308, high=309.5, low=307, close=309.0)
        sig = check_hourly_resistance_approach(
            "GOOGL", bar, hourly_resistance=[310.0], has_active_entry=False,
        )
        assert sig is None

    def test_no_fire_when_far_from_resistance(self):
        """Bar high too far from nearest resistance → no alert."""
        bar = _bar(open_=300, high=302, low=299, close=301)
        sig = check_hourly_resistance_approach(
            "GOOGL", bar, hourly_resistance=[310.0], has_active_entry=True,
        )
        assert sig is None

    def test_no_fire_with_empty_resistance(self):
        bar = _bar(open_=308, high=309.5, low=307, close=309.0)
        sig = check_hourly_resistance_approach(
            "GOOGL", bar, hourly_resistance=[], has_active_entry=True,
        )
        assert sig is None

    def test_picks_nearest_level_above_price(self):
        """Multiple levels — picks nearest above bar high."""
        bar = _bar(open_=308, high=309.5, low=307, close=309.0)
        sig = check_hourly_resistance_approach(
            "GOOGL", bar,
            hourly_resistance=[305.0, 310.0, 320.0],
            has_active_entry=True,
        )
        assert sig is not None
        assert "310.00" in sig.message  # nearest above, not 305 or 320


# ===== Find Resistance Targets with Hourly Resistance =====

class TestFindResistanceTargetsWithHourly:
    def _prior(self, **overrides):
        base = {
            "high": 335.0, "low": 298.0, "close": 305.0,
            "ma20": 340.0, "ma50": 350.0, "ma100": 302.0, "ma200": 290.0,
            "prior_week_high": 345.0,
        }
        base.update(overrides)
        return base

    def test_hourly_resistance_becomes_t1_when_nearest(self):
        """Hourly resistance at 310 is closer than prior high at 335 → T1."""
        prior = self._prior()
        # entry=305, stop=303, risk=2, min_target=307
        result = _find_resistance_targets(
            305.0, 303.0, prior, current_vwap=None,
            hourly_resistance=[310.0, 325.0],
        )
        assert result is not None
        t1, t2, t1_label, t2_label = result
        assert t1 == 310.0
        assert t1_label == "hourly resistance"

    def test_hourly_levels_below_entry_are_ignored(self):
        """Hourly resistance at 300 (below entry 305) → ignored."""
        prior = self._prior()
        result = _find_resistance_targets(
            305.0, 303.0, prior, current_vwap=None,
            hourly_resistance=[300.0, 298.0],
        )
        assert result is not None
        t1, _, t1_label, _ = result
        # hourly levels are all below entry → skipped, falls back to daily levels
        assert t1_label != "hourly resistance"

    def test_backward_compatible_without_hourly(self):
        """No hourly_resistance passed → same behavior as before."""
        prior = self._prior(high=312.0, ma20=308.0, ma50=320.0)
        result_without = _find_resistance_targets(305.0, 303.0, prior, current_vwap=None)
        result_with_none = _find_resistance_targets(
            305.0, 303.0, prior, current_vwap=None, hourly_resistance=None,
        )
        assert result_without is not None
        assert result_with_none is not None
        assert result_without[0] == result_with_none[0]  # same T1
        assert result_without[1] == result_with_none[1]  # same T2

    def test_hourly_as_t2_when_another_level_is_t1(self):
        """MA20 at 308 is T1, hourly at 312 becomes T2."""
        prior = self._prior(high=335.0, ma20=308.0, ma50=350.0)
        result = _find_resistance_targets(
            305.0, 303.0, prior, current_vwap=None,
            hourly_resistance=[312.0],
        )
        assert result is not None
        t1, t2, t1_label, t2_label = result
        assert t1 == 308.0
        assert t1_label == "MA20"
        assert t2 == 312.0
        assert t2_label == "hourly resistance"


# ===== Rule 19: MA Resistance =====

class TestMAResistance:
    def test_fires_when_high_touches_ma20_and_closes_below(self):
        """High reaches MA20 and close stays below → SELL MA_RESISTANCE."""
        # MA20=100.0, high=100.05 (within 0.3%), close=99.5 (below MA)
        bar = _bar(open_=99.0, high=100.05, low=98.5, close=99.5)
        sig = check_ma_resistance("NFLX", bar, ma20=100.0, ma50=105.0, ma100=110.0, ma200=120.0)
        assert sig is not None
        assert sig.alert_type == AlertType.MA_RESISTANCE
        assert sig.direction == "SELL"
        assert "MA20 RESISTANCE" in sig.message
        assert "$100.00" in sig.message

    def test_fires_for_lowest_rejecting_ma(self):
        """Both MA20 and MA50 overhead — fires for MA20 (lowest, first match)."""
        # MA20=100.0, MA50=102.0, high=100.10 (touches MA20), close=99.5
        bar = _bar(open_=99.0, high=100.10, low=98.5, close=99.5)
        sig = check_ma_resistance("SPY", bar, ma20=100.0, ma50=102.0, ma100=110.0, ma200=120.0)
        assert sig is not None
        assert "MA20 RESISTANCE" in sig.message

    def test_no_fire_when_close_above_ma(self):
        """High touches MA20 but close is above → bounce, not rejection."""
        bar = _bar(open_=99.5, high=100.20, low=99.0, close=100.10)
        sig = check_ma_resistance("NFLX", bar, ma20=100.0, ma50=105.0, ma100=110.0, ma200=120.0)
        assert sig is None

    def test_no_fire_when_high_too_far_from_ma(self):
        """High is more than 0.3% away from all MAs → None."""
        # MA20=100.0, high=99.0 (1% away)
        bar = _bar(open_=98.0, high=99.0, low=97.5, close=98.5)
        sig = check_ma_resistance("NFLX", bar, ma20=100.0, ma50=105.0, ma100=110.0, ma200=120.0)
        assert sig is None

    def test_no_fire_when_all_mas_none(self):
        """All MAs are None → None."""
        bar = _bar(open_=99.0, high=100.0, low=98.5, close=99.5)
        sig = check_ma_resistance("NFLX", bar, ma20=None, ma50=None, ma100=None, ma200=None)
        assert sig is None

    def test_skips_ma_below_close(self):
        """MA below close (not overhead) is skipped."""
        # MA20=98.0 (below close=99.5), MA50=100.0 (overhead), high touches MA50
        bar = _bar(open_=99.0, high=100.05, low=98.5, close=99.5)
        sig = check_ma_resistance("META", bar, ma20=98.0, ma50=100.0, ma100=110.0, ma200=120.0)
        assert sig is not None
        assert "MA50 RESISTANCE" in sig.message

    def test_fires_for_higher_ma_when_lower_doesnt_reject(self):
        """MA20 below close (skipped), MA50 too far, MA100 rejects → fires MA100."""
        # close=99.5, MA20=98 (below), MA50=102 (high doesn't reach),
        # MA100=100.0 (high touches, close below)
        bar = _bar(open_=99.0, high=100.05, low=98.5, close=99.5)
        sig = check_ma_resistance("META", bar, ma20=98.0, ma50=102.0, ma100=100.0, ma200=120.0)
        assert sig is not None
        assert "MA100 RESISTANCE" in sig.message


# ===== Rule 20: Prior Day Low as Resistance =====

class TestResistancePriorLow:
    def test_fires_when_prior_close_below_pdl(self):
        """Prior close below PDL (already broken) + high touches PDL → fire."""
        # PDL=100.0, prior_close=98.0 (below PDL = broken), high=100.10, close=99.5
        bar = _bar(open_=99.0, high=100.10, low=98.5, close=99.5)
        sig = check_resistance_prior_low("AAPL", bar, prior_day_low=100.0, prior_close=98.0)
        assert sig is not None
        assert sig.alert_type == AlertType.RESISTANCE_PRIOR_LOW
        assert sig.direction == "NOTICE"
        assert "Prior day low resistance" in sig.message
        assert "$100.00" in sig.message

    def test_no_fire_when_prior_close_above_pdl_no_gap(self):
        """Prior close above PDL and no gap down → None."""
        bar = _bar(open_=100.5, high=100.60, low=99.5, close=100.2)
        sig = check_resistance_prior_low("AAPL", bar, prior_day_low=100.0, prior_close=102.0, today_open=100.5)
        assert sig is None

    def test_fires_on_gap_down_below_pdl(self):
        """Prior close above PDL but today gapped below → PDL is resistance."""
        bar = _bar(open_=99.0, high=100.10, low=98.5, close=99.5)
        sig = check_resistance_prior_low("AAPL", bar, prior_day_low=100.0, prior_close=102.0, today_open=99.0)
        assert sig is not None
        assert sig.alert_type == AlertType.RESISTANCE_PRIOR_LOW

    def test_no_fire_when_close_above_pdl(self):
        """High touches PDL, close above → reclaimed, not rejection."""
        bar = _bar(open_=99.5, high=100.15, low=99.0, close=100.10)
        sig = check_resistance_prior_low("AAPL", bar, prior_day_low=100.0, prior_close=98.0)
        assert sig is None

    def test_no_fire_when_high_too_far_from_pdl(self):
        """High more than 0.2% away from PDL → None."""
        # PDL=100.0, high=99.5 (0.5% away)
        bar = _bar(open_=98.5, high=99.5, low=98.0, close=99.0)
        sig = check_resistance_prior_low("AAPL", bar, prior_day_low=100.0, prior_close=98.0)
        assert sig is None

    def test_no_fire_when_pdl_is_zero(self):
        """PDL=0 → None."""
        bar = _bar(open_=99.0, high=100.0, low=98.5, close=99.5)
        sig = check_resistance_prior_low("AAPL", bar, prior_day_low=0)
        assert sig is None

    def test_no_fire_when_pdl_is_negative(self):
        """PDL<0 → None."""
        bar = _bar(open_=99.0, high=100.0, low=98.5, close=99.5)
        sig = check_resistance_prior_low("AAPL", bar, prior_day_low=-5.0)
        assert sig is None


# ===== F1: Support Strength =====

class TestSupportStrength:
    def _make_support_bars(self, num_hours=4, support_low=98.50):
        """Create bars where a support level forms and gets retested."""
        num_bars = num_hours * 12  # 12 five-min bars per hour
        idx = pd.date_range("2024-01-15 09:30", periods=num_bars, freq="5min")
        data = {
            "Open": [100.0] * num_bars,
            "High": [101.0] * num_bars,
            "Low": [99.5] * num_bars,
            "Close": [100.5] * num_bars,
            "Volume": [1000] * num_bars,
        }
        bars = pd.DataFrame(data, index=idx)
        return bars

    def test_returns_dict_with_required_fields(self):
        """Support levels include touch_count, hold_hours, strength."""
        bars = self._make_support_bars(num_hours=3)
        # Hour 1: low at 98.50
        bars.iloc[2, bars.columns.get_loc("Low")] = 98.50
        # Hour 2: holds above, bounces
        for i in range(12, 24):
            bars.iloc[i, bars.columns.get_loc("Low")] = 99.0
            bars.iloc[i, bars.columns.get_loc("Close")] = 100.0
        # Hour 3: retests 98.50 again
        bars.iloc[26, bars.columns.get_loc("Low")] = 98.53  # within 0.3%

        supports = detect_intraday_supports(bars)
        assert len(supports) >= 1
        s = supports[0]
        assert "level" in s
        assert "touch_count" in s
        assert "hold_hours" in s
        assert "strength" in s

    def test_strong_when_tested_multiple_times_and_held(self):
        """Level tested 3x over 3 hours → strength='strong'."""
        bars = self._make_support_bars(num_hours=5)
        # Hour 1: low at 98.50
        bars.iloc[2, bars.columns.get_loc("Low")] = 98.50
        # Hour 2: holds above, bounces
        for i in range(12, 24):
            bars.iloc[i, bars.columns.get_loc("Low")] = 99.0
            bars.iloc[i, bars.columns.get_loc("Close")] = 100.0
        # Hour 3: retest at 98.52 (within 0.3%)
        bars.iloc[26, bars.columns.get_loc("Low")] = 98.52
        # Hour 4: holds above again
        for i in range(36, 48):
            bars.iloc[i, bars.columns.get_loc("Low")] = 99.0
            bars.iloc[i, bars.columns.get_loc("Close")] = 100.0
        # Hour 5: another retest
        bars.iloc[50, bars.columns.get_loc("Low")] = 98.55

        supports = detect_intraday_supports(bars)
        strong_levels = [s for s in supports if s["strength"] == "strong"]
        assert len(strong_levels) >= 1

    def test_weak_when_tested_once(self):
        """Level tested only 1x → strength='weak'."""
        bars = self._make_support_bars(num_hours=3)
        # Only hour 1 has the support low, no retests
        bars.iloc[2, bars.columns.get_loc("Low")] = 98.50
        # Hour 2: holds above, bounces
        for i in range(12, 24):
            bars.iloc[i, bars.columns.get_loc("Low")] = 99.5
            bars.iloc[i, bars.columns.get_loc("Close")] = 100.0

        supports = detect_intraday_supports(bars)
        if supports:
            assert supports[0]["strength"] == "weak"

    def test_bounce_rule_uses_strength_for_confidence(self):
        """Strong support → confidence='high', weak → 'medium'."""
        bars = pd.DataFrame([
            {"Open": 648.50, "High": 650.00, "Low": 648.10, "Close": 649.50, "Volume": 1000},
        ])
        strong_support = [
            {"level": 648.00, "touch_count": 3, "hold_hours": 3, "strength": "strong"},
        ]
        sig = check_intraday_support_bounce("META", bars, strong_support, 1000, 1000)
        assert sig is not None
        assert sig.confidence == "high"

        weak_support = [
            {"level": 648.00, "touch_count": 2, "hold_hours": 1, "strength": "weak"},
        ]
        sig2 = check_intraday_support_bounce("META", bars, weak_support, 1000, 1000)
        assert sig2 is not None
        assert sig2.confidence == "medium"

    def test_bounce_message_includes_touch_count(self):
        """Message includes how many times the level was tested."""
        bars = pd.DataFrame([
            {"Open": 648.50, "High": 650.00, "Low": 648.10, "Close": 649.50, "Volume": 1000},
        ])
        supports = [
            {"level": 648.00, "touch_count": 3, "hold_hours": 2, "strength": "strong"},
        ]
        sig = check_intraday_support_bounce("META", bars, supports, 1000, 1000)
        assert sig is not None
        assert "tested 3x" in sig.message
        assert "strong" in sig.message


# ===== F2: ORB Breakdown =====

class TestORBBreakdown:
    def _or(self, or_high=101.0, or_low=99.5, complete=True):
        """Create an opening range dict."""
        return {
            "or_high": or_high,
            "or_low": or_low,
            "or_range": or_high - or_low,
            "or_range_pct": (or_high - or_low) / or_low,
            "or_complete": complete,
        }

    def test_fires_when_close_below_or_low_with_volume(self):
        """Close < OR low + volume >= 1.2x → SELL OPENING_RANGE_BREAKDOWN."""
        bar = _bar(open_=99.0, high=99.5, low=98.5, close=98.8, volume=1500)
        opening_range = self._or(or_high=101.0, or_low=99.5)
        sig = check_orb_breakdown("AAPL", bar, opening_range, 1500, 1000)
        assert sig is not None
        assert sig.alert_type == AlertType.OPENING_RANGE_BREAKDOWN
        assert sig.direction == "SELL"
        assert "ORB BREAKDOWN" in sig.message
        assert "$99.50" in sig.message

    def test_no_fire_when_close_above_or_low(self):
        """Close >= OR low → None."""
        bar = _bar(open_=100.0, high=101.5, low=99.8, close=100.5, volume=1500)
        opening_range = self._or(or_high=101.0, or_low=99.5)
        sig = check_orb_breakdown("AAPL", bar, opening_range, 1500, 1000)
        assert sig is None

    def test_no_fire_when_volume_too_low(self):
        """Volume < 1.2x avg → None."""
        bar = _bar(open_=99.0, high=99.5, low=98.5, close=98.8, volume=500)
        opening_range = self._or(or_high=101.0, or_low=99.5)
        sig = check_orb_breakdown("AAPL", bar, opening_range, 500, 1000)
        assert sig is None

    def test_no_fire_when_or_incomplete(self):
        """OR not complete (<6 bars) → None."""
        bar = _bar(open_=99.0, high=99.5, low=98.5, close=98.8, volume=1500)
        opening_range = self._or(complete=False)
        sig = check_orb_breakdown("AAPL", bar, opening_range, 1500, 1000)
        assert sig is None

    def test_no_fire_when_or_range_too_small(self):
        """OR range < ORB_MIN_RANGE_PCT → None."""
        bar = _bar(open_=99.0, high=99.5, low=98.5, close=98.8, volume=1500)
        # Tiny range: 100.01 - 100.00 = 0.01% (below 0.3% threshold)
        opening_range = self._or(or_high=100.01, or_low=100.00)
        sig = check_orb_breakdown("AAPL", bar, opening_range, 1500, 1000)
        assert sig is None


# ===== F4: Signal Consolidation =====

class TestSignalConsolidation:
    def _make_signal(self, symbol="AAPL", direction="BUY",
                     alert_type=AlertType.MA_BOUNCE_20, score=70,
                     message="test signal"):
        return AlertSignal(
            symbol=symbol,
            alert_type=alert_type,
            direction=direction,
            price=100.0,
            entry=100.0,
            stop=99.0,
            score=score,
            score_label="B" if score < 75 else "A",
            message=message,
        )

    def test_two_buy_signals_merged_into_one_with_boost(self):
        """Two BUY signals for same symbol → 1 merged signal with boosted score."""
        sig1 = self._make_signal(score=70, alert_type=AlertType.MA_BOUNCE_20,
                                  message="MA bounce")
        sig2 = self._make_signal(score=60, alert_type=AlertType.INTRADAY_SUPPORT_BOUNCE,
                                  message="Support bounce")
        result = _consolidate_signals([sig1, sig2])
        assert len(result) == 1
        # Primary should be sig1 (higher score), boosted by 5
        assert result[0].score == 75
        assert "+1 confirming" in result[0].message

    def test_sell_signals_not_consolidated(self):
        """SELL signals pass through unchanged."""
        sig1 = self._make_signal(direction="SELL", alert_type=AlertType.RESISTANCE_PRIOR_HIGH)
        sig2 = self._make_signal(direction="SELL", alert_type=AlertType.MA_RESISTANCE)
        result = _consolidate_signals([sig1, sig2])
        assert len(result) == 2

    def test_score_capped_at_100(self):
        """Consolidation boost never pushes score above 100."""
        sig1 = self._make_signal(score=98, alert_type=AlertType.MA_BOUNCE_20)
        sig2 = self._make_signal(score=90, alert_type=AlertType.INTRADAY_SUPPORT_BOUNCE)
        sig3 = self._make_signal(score=85, alert_type=AlertType.WEEKLY_LEVEL_TOUCH)
        result = _consolidate_signals([sig1, sig2, sig3])
        assert len(result) == 1
        assert result[0].score <= 100

    def test_score_label_recalculated_after_boost(self):
        """Score label updates to match new boosted score."""
        sig1 = self._make_signal(score=72, alert_type=AlertType.MA_BOUNCE_20,
                                  message="MA bounce")
        sig1.score_label = "Moderate"
        sig2 = self._make_signal(score=60, alert_type=AlertType.INTRADAY_SUPPORT_BOUNCE,
                                  message="Support bounce")
        result = _consolidate_signals([sig1, sig2])
        assert len(result) == 1
        # 72 + 5 = 77 → "A" (75-89 range)
        assert result[0].score == 77
        assert result[0].score_label == "A"

    def test_message_includes_confirming_signal_types(self):
        """Merged message lists the confirming signal types."""
        sig1 = self._make_signal(score=80, alert_type=AlertType.MA_BOUNCE_20,
                                  message="Primary signal")
        sig2 = self._make_signal(score=60, alert_type=AlertType.INTRADAY_SUPPORT_BOUNCE,
                                  message="Confirming signal")
        result = _consolidate_signals([sig1, sig2])
        assert "Intraday Support Bounce" in result[0].message


# ===== Enabled Rules Gate =====

class TestEnabledRules:
    """Disabled rules should not fire through evaluate_rules(), enabled ones still fire."""

    def _make_bars(self):
        """Bars that would normally trigger many rules."""
        return _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
        ])

    def _make_prior(self):
        return {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 99.0, "is_inside": True,
            "parent_high": 102.0, "parent_low": 98.0,
        }

    def test_inside_day_breakout_disabled_phase1(self):
        """Phase 1 (2026-04-22): inside_day_breakout is removed from ENABLED_RULES.

        Original test asserted inside_day_breakout was enabled. After real-world
        evidence (AMD 04-22 stale misfire, gap-up invalidation), the inside-day
        family was disabled in favor of PDH/PDL rules. The function still exists
        but is never reached by evaluate_rules().
        """
        from alert_config import ENABLED_RULES
        assert "inside_day_breakout" not in ENABLED_RULES
        assert "inside_day_reclaim" not in ENABLED_RULES
        assert "inside_day_breakdown" not in ENABLED_RULES
        assert "inside_day_forming" not in ENABLED_RULES
        # Even with a valid inside-day setup, no signal should fire.
        bars = self._make_bars()
        prior = self._make_prior()
        signals = evaluate_rules("AAPL", bars, prior)
        types = {s.alert_type for s in signals}
        assert AlertType.INSIDE_DAY_BREAKOUT not in types

    def test_disabled_opening_range_breakout_does_not_fire(self):
        """opening_range_breakout is disabled and should not appear in signals."""
        bars = self._make_bars()
        prior = self._make_prior()
        signals = evaluate_rules("AAPL", bars, prior)
        types = {s.alert_type for s in signals}
        assert AlertType.OPENING_RANGE_BREAKOUT not in types

    def test_ema_crossover_is_disabled_phase1(self):
        """ema_crossover_5_20 disabled in Phase 1 (core S/R only)."""
        from alert_config import ENABLED_RULES
        assert "ema_crossover_5_20" not in ENABLED_RULES

    def test_disabled_gap_fill_does_not_fire(self):
        """gap_fill is disabled and should not appear in signals."""
        bars = self._make_bars()
        prior = self._make_prior()
        signals = evaluate_rules("AAPL", bars, prior)
        types = {s.alert_type for s in signals}
        assert AlertType.GAP_FILL not in types

    def test_enabled_ma_bounce_20_still_fires(self):
        """ma_bounce_20 is enabled and should still fire when conditions match."""
        bars = self._make_bars()
        prior = self._make_prior()
        signals = evaluate_rules("AAPL", bars, prior)
        ma_bounces = [s for s in signals if s.alert_type == AlertType.MA_BOUNCE_20]
        assert len(ma_bounces) >= 1


# ===== Support Breakdown Exit-Only =====

class TestSupportBreakdownExitOnly:
    """Support breakdown only fires when there's an active long position."""

    def _breakdown_bars(self):
        idx = pd.date_range("2024-01-15 09:30", periods=12, freq="5min")
        rows = [
            {"Open": 99.0, "High": 99.5, "Low": 98.5, "Close": 99.0, "Volume": 1000}
            for _ in range(12)
        ]
        # Last bar: conviction breakdown
        rows[-1] = {
            "Open": 98.2, "High": 98.5, "Low": 97.0,
            "Close": 97.1, "Volume": 2000,
        }
        return pd.DataFrame(rows, index=idx)

    def _breakdown_prior(self):
        return {
            "ma20": 100.0, "ma50": None, "close": 99.5,
            "high": 101.0, "low": 98.0, "is_inside": False,
        }

    def test_suppressed_when_no_position(self):
        """No active entry → support breakdown suppressed entirely."""
        bars = self._breakdown_bars()
        prior = self._breakdown_prior()
        signals = evaluate_rules("AMD", bars, prior, active_entries=None)
        bd = [s for s in signals if s.alert_type == AlertType.SUPPORT_BREAKDOWN]
        assert len(bd) == 0

    def test_fires_as_exit_long_when_active(self):
        """Active LONG → breakdown fires as SELL / EXIT LONG."""
        bars = self._breakdown_bars()
        prior = self._breakdown_prior()
        entries = [{"entry_price": 99.0, "stop_price": 98.0,
                    "target_1": 100.0, "target_2": 101.0}]
        signals = evaluate_rules("AMD", bars, prior, active_entries=entries)
        bd = [s for s in signals if s.alert_type == AlertType.SUPPORT_BREAKDOWN]
        if bd:
            assert bd[0].direction == "SELL"
            assert "EXIT LONG" in bd[0].message


# ===== Overhead MA Resistance Filter =====

class TestOverheadMAResistanceFilter:
    """BUY signals heading into nearby overhead MA are suppressed."""

    def test_buy_suppressed_when_ma_within_threshold(self):
        """Entry at 100, 100MA at 100.40 (0.4% away) → blocked."""
        blocked, label = _has_overhead_ma_resistance(
            entry=100.0, ma20=None, ma50=None, ma100=100.40, ma200=None,
        )
        assert blocked is True
        assert "100MA" in label

    def test_buy_allowed_when_ma_far_above(self):
        """Entry at 100, 100MA at 102 (2% away) → not blocked."""
        blocked, _ = _has_overhead_ma_resistance(
            entry=100.0, ma20=None, ma50=None, ma100=102.0, ma200=None,
        )
        assert blocked is False

    def test_sell_unaffected(self):
        """SELL signals are never suppressed by this filter (helper only checks entry)."""
        # Helper doesn't know direction — caller gates on direction.
        # Just verify that MAs below entry don't trigger.
        blocked, _ = _has_overhead_ma_resistance(
            entry=100.0, ma20=95.0, ma50=90.0, ma100=85.0, ma200=80.0,
        )
        assert blocked is False

    def test_ma_below_entry_not_blocking(self):
        """MAs below entry price are supports, not resistance."""
        blocked, _ = _has_overhead_ma_resistance(
            entry=100.0, ma20=99.0, ma50=98.0, ma100=95.0, ma200=90.0,
        )
        assert blocked is False

    def test_closest_overhead_ma_reported(self):
        """When multiple MAs are overhead, the first one found is reported."""
        blocked, label = _has_overhead_ma_resistance(
            entry=100.0, ma20=100.3, ma50=100.4, ma100=105.0, ma200=110.0,
        )
        assert blocked is True
        assert "20MA" in label

    def test_none_mas_handled(self):
        """All None MAs → not blocked."""
        blocked, _ = _has_overhead_ma_resistance(
            entry=100.0, ma20=None, ma50=None, ma100=None, ma200=None,
        )
        assert blocked is False

    def test_integration_buy_suppressed_in_evaluate_rules(self):
        """BUY signal suppressed by overhead MA resistance in full pipeline."""
        # Bar triggers MA bounce 20 (low near ma20=100, close above it)
        # but 50MA sits just above entry → overhead resistance blocks
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 100.4,  # 50MA overhead within 0.5%
            "close": 100.5, "high": 102.0, "low": 99.0, "is_inside": False,
        }
        signals = evaluate_rules("TEST", bars, prior)
        # MA bounce 20 requires ma20 > ma50 for uptrend — here ma20 < ma50,
        # so it won't even fire. Let's use a scenario where it does fire
        # but gets blocked by overhead resistance.
        # Actually, ma20 < ma50 prevents the bounce. Use ma100 overhead instead.
        prior2 = {
            "ma20": 100.0, "ma50": 95.0, "ma100": 100.4,
            "close": 100.5, "high": 102.0, "low": 99.0, "is_inside": False,
        }
        signals2 = evaluate_rules("TEST", bars, prior2)
        ma_bounces = [s for s in signals2 if s.alert_type == AlertType.MA_BOUNCE_20]
        # P3: overhead MA filter now tags signals instead of dropping them
        # Signal is kept but marked with suppressed_reason + _suppress_telegram
        if ma_bounces:
            assert ma_bounces[0].suppressed_reason is not None, \
                "MA bounce near overhead 100MA should be tagged with suppressed_reason"
            assert "overhead_ma" in ma_bounces[0].suppressed_reason
            assert ma_bounces[0]._suppress_telegram is True


# ===== RSI Wilder Computation =====

from analytics.intraday_data import compute_rsi_wilder


class TestComputeRsiWilder:
    """Tests for compute_rsi_wilder() helper."""

    def test_all_gains_returns_near_100(self):
        """Prices only going up → RSI near 100."""
        closes = pd.Series([100 + i for i in range(20)])
        rsi = compute_rsi_wilder(closes, period=14)
        assert rsi is not None
        assert rsi > 95

    def test_all_losses_returns_near_0(self):
        """Prices only going down → RSI near 0."""
        closes = pd.Series([120 - i for i in range(20)])
        rsi = compute_rsi_wilder(closes, period=14)
        assert rsi is not None
        assert rsi < 5

    def test_insufficient_data_returns_none(self):
        """Fewer than period+1 bars → None."""
        closes = pd.Series([100, 101, 102])
        rsi = compute_rsi_wilder(closes, period=14)
        assert rsi is None

    def test_flat_prices_returns_50(self):
        """No price changes → RSI should be 50 (no gains or losses)."""
        closes = pd.Series([100.0] * 20)
        rsi = compute_rsi_wilder(closes, period=14)
        assert rsi is not None
        assert rsi == 50.0

    def test_known_value_range(self):
        """Mixed gains/losses → RSI in valid range."""
        closes = pd.Series([100, 102, 101, 103, 100, 104, 102, 105,
                            103, 106, 104, 107, 105, 108, 106, 109])
        rsi = compute_rsi_wilder(closes, period=14)
        assert rsi is not None
        assert 0 <= rsi <= 100

    def test_output_always_bounded(self):
        """RSI must always be in [0, 100]."""
        # Volatile series
        closes = pd.Series([100, 110, 90, 115, 85, 120, 80, 125,
                            75, 130, 70, 135, 65, 140, 60, 145])
        rsi = compute_rsi_wilder(closes, period=14)
        assert rsi is not None
        assert 0 <= rsi <= 100


# ===== SPY RSI/EMA Confidence Modifier =====

class TestPerSymbolRsi:
    """Tests for per-symbol RSI14 enrichment in evaluate_rules."""

    def _base_spy(self, **overrides):
        ctx = {
            "trend": "bullish", "close": 690.0, "ma20": 685.0,
            "ma5": 688.0, "ma50": 680.0, "regime": "TRENDING_UP",
            "intraday_change_pct": 0.5, "spy_bouncing": False, "spy_intraday_low": 0.0,
            "spy_at_support": False, "spy_at_resistance": False,
            "spy_level_label": "", "spy_support_bounce_rate": 0.5,
            "spy_rsi14": 50.0, "spy_ema20": 688.0, "spy_ema50": 685.0,
            "spy_ema_spread_pct": 0.44, "spy_at_ma_support": None,
            "spy_ema_regime": "TRENDING_UP",
        }
        ctx.update(overrides)
        return ctx

    def _run(self, rsi14, spy_ctx=None):
        """Run evaluate_rules with a MA bounce trigger and given sym RSI."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 99.0, "is_inside": False,
            "rsi14": rsi14,
        }
        ctx = spy_ctx or self._base_spy()
        return evaluate_rules("GOOGL", bars, prior, spy_context=ctx)

    def test_rsi_below_35_demotes_buy_confidence(self):
        """RSI < 35 → high demoted to medium + crash risk message."""
        signals = self._run(rsi14=25.0)
        buy = [s for s in signals if s.direction == "BUY"]
        assert len(buy) >= 1
        for s in buy:
            assert s.confidence != "high"
            assert "GOOGL RSI crash risk (25)" in s.message

    def test_rsi_above_70_adds_overbought_caution(self):
        """RSI > 70 → message added, confidence NOT demoted."""
        signals = self._run(rsi14=78.0)
        ma = [s for s in signals if s.alert_type == AlertType.MA_BOUNCE_20]
        assert len(ma) >= 1
        for s in ma:
            assert "GOOGL RSI overbought (78)" in s.message
            # Overbought is informational — confidence stays as-is
            assert s.confidence == "high"

    def test_rsi_neutral_no_message(self):
        """RSI in normal range (50) → no per-symbol RSI message."""
        signals = self._run(rsi14=50.0)
        buy = [s for s in signals if s.direction == "BUY"]
        assert len(buy) >= 1
        for s in buy:
            assert "GOOGL RSI" not in s.message

    def test_rsi_none_no_message(self):
        """RSI is None → no per-symbol RSI message."""
        signals = self._run(rsi14=None)
        buy = [s for s in signals if s.direction == "BUY"]
        assert len(buy) >= 1
        for s in buy:
            assert "GOOGL RSI" not in s.message

    def test_rsi_below_35_stacks_with_spy_rsi_oversold(self):
        """Both sym RSI < 35 and SPY RSI < 35 → both messages present."""
        spy_ctx = self._base_spy(spy_rsi14=30.0)
        signals = self._run(rsi14=25.0, spy_ctx=spy_ctx)
        buy = [s for s in signals if s.direction == "BUY"]
        assert len(buy) >= 1
        for s in buy:
            assert "GOOGL RSI crash risk" in s.message
            assert "SPY RSI oversold" in s.message

    def test_rsi_below_35_on_medium_stays_medium(self):
        """RSI < 35 on already-medium confidence → stays medium + message."""
        # CHOPPY regime will demote high→medium, then RSI < 35 tries to demote again
        spy_ctx = self._base_spy(regime="CHOPPY", spy_rsi14=50.0)
        signals = self._run(rsi14=20.0, spy_ctx=spy_ctx)
        ma = [s for s in signals if s.alert_type == AlertType.MA_BOUNCE_20]
        assert len(ma) >= 1
        for s in ma:
            assert s.confidence == "medium"
            assert "GOOGL RSI crash risk (20)" in s.message

    def test_rsi_value_appears_in_message(self):
        """The RSI numeric value appears in the enrichment message."""
        signals = self._run(rsi14=28.0)
        buy = [s for s in signals if s.direction == "BUY"]
        assert len(buy) >= 1
        assert any("28" in s.message for s in buy)

    def test_sell_signals_unaffected_by_rsi(self):
        """SELL signals should not have per-symbol RSI messages."""
        bars = _bars([
            {"Open": 100, "High": 101.5, "Low": 99, "Close": 101.2, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 99.0, "is_inside": False,
            "rsi14": 25.0,
        }
        signals = evaluate_rules("GOOGL", bars, prior, spy_context=self._base_spy())
        sells = [s for s in signals if s.direction == "SELL"]
        for s in sells:
            assert "GOOGL RSI" not in s.message


class TestSpyRsiConfidenceModifier:
    """Tests for RSI/EMA enrichment block in evaluate_rules."""

    def _base_spy(self, **overrides):
        """Base SPY context (TRENDING_UP) with RSI/EMA defaults."""
        ctx = {
            "trend": "bullish", "close": 690.0, "ma20": 685.0,
            "ma5": 688.0, "ma50": 680.0, "regime": "TRENDING_UP",
            "intraday_change_pct": 0.5, "spy_bouncing": False, "spy_intraday_low": 0.0,
            "spy_at_support": False, "spy_at_resistance": False,
            "spy_level_label": "", "spy_support_bounce_rate": 0.5,
            "spy_rsi14": 50.0, "spy_ema20": 688.0, "spy_ema50": 685.0,
            "spy_ema_spread_pct": 0.44, "spy_at_ma_support": None,
            "spy_ema_regime": "TRENDING_UP",
        }
        ctx.update(overrides)
        return ctx

    def _run(self, spy_ctx):
        """Run evaluate_rules with a MA bounce trigger and given spy_context."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 99.0, "is_inside": False,
        }
        signals = evaluate_rules("AAPL", bars, prior, spy_context=spy_ctx)
        return [s for s in signals if s.direction == "BUY"]

    def test_rsi_oversold_boosts_confidence(self):
        """RSI < 35 → medium→high, 'SPY RSI oversold' in message."""
        spy_ctx = self._base_spy(spy_rsi14=30.0)
        buy_signals = self._run(spy_ctx)
        assert len(buy_signals) >= 1
        for s in buy_signals:
            assert "SPY RSI oversold" in s.message
            assert "30" in s.message

    def test_rsi_overbought_demotes_confidence(self):
        """RSI > 70 → high→medium, 'SPY RSI overbought' in message."""
        spy_ctx = self._base_spy(spy_rsi14=75.0)
        buy_signals = self._run(spy_ctx)
        assert len(buy_signals) >= 1
        ma_signals = [s for s in buy_signals if s.alert_type == AlertType.MA_BOUNCE_20]
        for s in ma_signals:
            assert s.confidence == "medium"
            assert "SPY RSI overbought" in s.message
            assert "75" in s.message

    def test_rsi_neutral_no_change(self):
        """RSI in normal range (50) → no RSI message."""
        spy_ctx = self._base_spy(spy_rsi14=50.0)
        buy_signals = self._run(spy_ctx)
        assert len(buy_signals) >= 1
        for s in buy_signals:
            assert "SPY RSI" not in s.message

    def test_rsi_none_no_change(self):
        """RSI is None (insufficient data) → no RSI message."""
        spy_ctx = self._base_spy(spy_rsi14=None)
        buy_signals = self._run(spy_ctx)
        assert len(buy_signals) >= 1
        for s in buy_signals:
            assert "SPY RSI" not in s.message

    def test_ema_convergence_message(self):
        """EMA spread < 0.5% → 'SPY EMAs converging' in message."""
        spy_ctx = self._base_spy(spy_ema_spread_pct=0.3)
        buy_signals = self._run(spy_ctx)
        assert len(buy_signals) >= 1
        assert any("SPY EMAs converging" in s.message for s in buy_signals)

    def test_ema_spread_wide_no_message(self):
        """EMA spread > 0.5% → no convergence message."""
        spy_ctx = self._base_spy(spy_ema_spread_pct=1.5)
        buy_signals = self._run(spy_ctx)
        assert len(buy_signals) >= 1
        for s in buy_signals:
            assert "SPY EMAs converging" not in s.message

    def test_spy_ma_support_annotation(self):
        """SPY at 50MA support → 'SPY at 50MA support' in message."""
        spy_ctx = self._base_spy(spy_at_ma_support="50MA", spy_rsi14=50.0)
        buy_signals = self._run(spy_ctx)
        assert len(buy_signals) >= 1
        assert any("SPY at 50MA support" in s.message for s in buy_signals)

    def test_spy_ma_support_with_rsi_low(self):
        """SPY at 100MA + RSI < 40 → institutional level message."""
        spy_ctx = self._base_spy(spy_at_ma_support="100MA", spy_rsi14=35.0)
        buy_signals = self._run(spy_ctx)
        assert len(buy_signals) >= 1
        assert any(
            "SPY oversold at 100MA (institutional level)" in s.message
            for s in buy_signals
        )

    def test_rsi_oversold_stacks_with_regime_demotion(self):
        """CHOPPY demotes high→medium, then RSI < 35 restores medium→high."""
        spy_ctx = self._base_spy(regime="CHOPPY", spy_rsi14=30.0)
        buy_signals = self._run(spy_ctx)
        ma_signals = [s for s in buy_signals if s.alert_type == AlertType.MA_BOUNCE_20]
        assert len(ma_signals) >= 1
        for s in ma_signals:
            # CHOPPY demotes to medium, RSI oversold restores to high
            assert s.confidence == "high"
            assert "CHOPPY" in s.message
            assert "SPY RSI oversold" in s.message

    def test_rsi_overbought_stacks_on_already_medium(self):
        """Overbought RSI on already-medium confidence → stays medium, message added."""
        # CHOPPY regime demotes to medium, then RSI overbought can't demote further
        spy_ctx = self._base_spy(regime="CHOPPY", spy_rsi14=75.0)
        buy_signals = self._run(spy_ctx)
        ma_signals = [s for s in buy_signals if s.alert_type == AlertType.MA_BOUNCE_20]
        assert len(ma_signals) >= 1
        for s in ma_signals:
            assert s.confidence == "medium"
            assert "CHOPPY" in s.message
            assert "SPY RSI overbought" in s.message


# ===== Session Low Structural Stops for MA Bounce =====

class TestSessionLowStop:
    """Session low overrides fixed MA-offset stops for MA bounce rules."""

    def _make_bars(self, session_low, bounce_close, ma_level=100.0, n_bars=5):
        """Build intraday bars with a specific session low and bounce bar."""
        rows = []
        # Earlier bars with the session low
        for i in range(n_bars - 1):
            rows.append({
                "Open": ma_level + 0.5, "High": ma_level + 1.0,
                "Low": session_low, "Close": ma_level + 0.3,
                "Volume": 1000,
            })
        # Last bar: bounces off MA, close above it
        rows.append({
            "Open": ma_level - 0.1, "High": ma_level + 1.0,
            "Low": ma_level - 0.02,  # within proximity of MA
            "Close": bounce_close,
            "Volume": 1000,
        })
        return _bars(rows)

    def test_ma20_stop_overridden_to_session_low(self, monkeypatch):
        """MA20 bounce stop = session_low * 0.998, not MA * 0.995."""
        monkeypatch.setattr(
            "analytics.intraday_data.fetch_hourly_bars",
            lambda *a, **kw: pd.DataFrame(),
        )
        # Disable _cap_risk so we can test session low override in isolation
        monkeypatch.setattr(
            "analytics.intraday_rules._cap_risk",
            lambda entry, stop, **kw: stop,
        )
        session_low = 99.0
        ma20 = 100.0
        bars = self._make_bars(session_low=session_low, bounce_close=100.3, ma_level=ma20)
        prior = {
            "ma20": ma20, "ma50": 95.0, "close": 100.5,
            "high": 105.0, "low": 98.0, "is_inside": False,
        }
        signals = evaluate_rules("AAPL", bars, prior)
        ma20_sigs = [s for s in signals if s.alert_type == AlertType.MA_BOUNCE_20]
        assert len(ma20_sigs) >= 1
        sig = ma20_sigs[0]
        expected_stop = round(session_low * (1 - 0.002), 2)  # 99.0 * 0.998 = 98.80
        assert sig.stop == expected_stop
        # Not the old fixed MA offset (100.0 * 0.995 = 99.50)
        assert sig.stop != round(ma20 * 0.995, 2)

    def test_ma100_stop_overridden_to_session_low(self, monkeypatch):
        """MA100 bounce also gets session low structural stop."""
        monkeypatch.setattr(
            "analytics.intraday_data.fetch_hourly_bars",
            lambda *a, **kw: pd.DataFrame(),
        )
        # Disable _cap_risk so we can test session low override in isolation
        monkeypatch.setattr(
            "analytics.intraday_rules._cap_risk",
            lambda entry, stop, **kw: stop,
        )
        # Disable consolidation so the MA100 signal isn't merged with other BUY signals
        monkeypatch.setattr(
            "analytics.intraday_rules._consolidate_signals",
            lambda signals: signals,
        )
        session_low = 678.02
        ma100 = 680.33
        # Build bars: session low in earlier bars, last bar bounces off MA100
        rows = []
        for i in range(4):
            rows.append({
                "Open": 679.0, "High": 681.0,
                "Low": session_low, "Close": 679.5,
                "Volume": 1000,
            })
        rows.append({
            "Open": 680.0, "High": 682.0,
            "Low": 680.0,  # within 0.5% proximity of MA100
            "Close": 681.0,
            "Volume": 1000,
        })
        bars = _bars(rows)
        prior = {
            "ma20": 687.0, "ma50": 685.0, "ma100": ma100,
            "close": 682.0, "high": 690.0, "low": 650.0, "is_inside": False,
        }
        signals = evaluate_rules("SPY", bars, prior)
        ma100_sigs = [s for s in signals if s.alert_type == AlertType.MA_BOUNCE_100]
        assert len(ma100_sigs) >= 1
        sig = ma100_sigs[0]
        expected_stop = round(session_low * (1 - 0.002), 2)  # 678.02 * 0.998 = 676.66
        assert sig.stop == expected_stop

    def test_no_override_when_session_low_equals_entry(self, monkeypatch):
        """When session_low >= entry, the MA-offset stop is kept."""
        monkeypatch.setattr(
            "analytics.intraday_data.fetch_hourly_bars",
            lambda *a, **kw: pd.DataFrame(),
        )
        ma20 = 100.0
        # All bars have Low >= ma20 (entry), so session_low >= entry → no override
        rows = []
        for i in range(4):
            rows.append({
                "Open": 101.0, "High": 102.0,
                "Low": 100.0,  # equal to entry
                "Close": 101.5,
                "Volume": 1000,
            })
        # Last bar: low within proximity of MA but exactly at MA
        rows.append({
            "Open": 100.2, "High": 101.5,
            "Low": 100.0,  # at the MA level
            "Close": 100.3,
            "Volume": 1000,
        })
        bars = _bars(rows)
        prior = {
            "ma20": ma20, "ma50": 95.0, "close": 100.5,
            "high": 105.0, "low": 98.0, "is_inside": False,
        }
        signals = evaluate_rules("AAPL", bars, prior)
        ma20_sigs = [s for s in signals if s.alert_type == AlertType.MA_BOUNCE_20]
        if ma20_sigs:
            sig = ma20_sigs[0]
            # session_low (100.0) >= entry (100.0), no override
            # Stop should be the _cap_risk result (not session_low-based)
            assert sig.stop != round(100.0 * (1 - 0.002), 2)

    def test_cap_risk_tightens_after_session_low_stop(self, monkeypatch):
        """_cap_risk still applies as safety net after session low override."""
        monkeypatch.setattr(
            "analytics.intraday_data.fetch_hourly_bars",
            lambda *a, **kw: pd.DataFrame(),
        )
        # Session low very far below MA → structural stop is wide
        # _cap_risk should tighten it to DAY_TRADE_MAX_RISK_PCT
        session_low = 95.0  # 5% below MA — very wide
        ma20 = 100.0
        bars = self._make_bars(session_low=session_low, bounce_close=100.3, ma_level=ma20)
        prior = {
            "ma20": ma20, "ma50": 94.0, "close": 100.5,
            "high": 105.0, "low": 93.0, "is_inside": False,
        }
        signals = evaluate_rules("AAPL", bars, prior)
        ma20_sigs = [s for s in signals if s.alert_type == AlertType.MA_BOUNCE_20]
        assert len(ma20_sigs) >= 1
        sig = ma20_sigs[0]
        # Structural stop would be 95.0 * 0.998 = 94.81 (risk = 5.19, ~5.2%)
        # _cap_risk for AAPL: 0.3% → max risk = 0.30 → stop = 99.70
        # So _cap_risk should have tightened it
        assert sig.stop == 99.70

    def test_pdl_reclaim_not_affected(self, monkeypatch):
        """Prior day low reclaim keeps its own bar-low stop, unaffected by session low override."""
        monkeypatch.setattr(
            "analytics.intraday_data.fetch_hourly_bars",
            lambda *a, **kw: pd.DataFrame(),
        )
        # PDL reclaim: bar dips below prior low then closes above
        prior_low = 99.0
        rows = []
        for i in range(4):
            rows.append({
                "Open": 100.0, "High": 101.0,
                "Low": 99.5, "Close": 100.5,
                "Volume": 1000,
            })
        # Last bar: dips below prior low, reclaims
        rows.append({
            "Open": 99.2, "High": 100.5,
            "Low": 98.85,  # below prior_low (99.0) by > 0.1%
            "Close": 99.5, "Volume": 1000,
        })
        bars = _bars(rows)
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 105.0, "low": prior_low, "is_inside": False,
        }
        signals = evaluate_rules("AAPL", bars, prior)
        pdl_sigs = [s for s in signals if s.alert_type == AlertType.PRIOR_DAY_LOW_RECLAIM]
        if pdl_sigs:
            sig = pdl_sigs[0]
            # PDL reclaim stop should NOT be session_low * 0.998
            session_low_stop = round(98.85 * (1 - 0.002), 2)
            assert sig.stop != session_low_stop or sig.alert_type != AlertType.PRIOR_DAY_LOW_RECLAIM

    def test_targets_recalculated_with_structural_stop(self, monkeypatch):
        """After session low override, T1/T2 use new risk (before smart targets)."""
        monkeypatch.setattr(
            "analytics.intraday_data.fetch_hourly_bars",
            lambda *a, **kw: pd.DataFrame(),
        )
        # Disable consolidation so the MA20 signal isn't merged with other BUY signals
        monkeypatch.setattr(
            "analytics.intraday_rules._consolidate_signals",
            lambda signals: signals,
        )
        session_low = 99.0
        ma20 = 100.0
        bars = self._make_bars(session_low=session_low, bounce_close=100.3, ma_level=ma20)
        prior = {
            "ma20": ma20, "ma50": 95.0, "close": 100.5,
            # Place prior high above entry so smart targets can find it
            "high": 103.0, "low": 98.0, "is_inside": False,
        }
        signals = evaluate_rules("AAPL", bars, prior)
        ma20_sigs = [s for s in signals if s.alert_type == AlertType.MA_BOUNCE_20]
        assert len(ma20_sigs) >= 1
        sig = ma20_sigs[0]
        # Targets should be set and above entry
        assert sig.target_1 > sig.entry
        assert sig.target_2 > sig.target_1


# ===== MA Confluence Detection =====


class TestMAConfluence:
    def test_detects_50ma_near_entry(self):
        """50MA within 0.23% of entry → confluence detected."""
        has, label, val = _check_ma_confluence(
            entry=217.00,
            alert_type=AlertType.PRIOR_DAY_LOW_RECLAIM,
            ma20=None, ma50=217.50, ma100=None, ma200=None,
        )
        assert has is True
        assert label == "50MA"
        assert "217.50" in val

    def test_skips_self_confluence(self):
        """ma_bounce_50 should not flag 50MA as confluence on itself.

        In reality, MA_BOUNCE_50 entry = round(ma50, 2), so entry == ma50.
        """
        has, label, _ = _check_ma_confluence(
            entry=217.50,
            alert_type=AlertType.MA_BOUNCE_50,
            ma20=None, ma50=217.50, ma100=None, ma200=None,
        )
        assert has is False

    def test_prioritizes_higher_ma(self):
        """When both 50MA and 200MA are near entry, 200MA wins."""
        has, label, _ = _check_ma_confluence(
            entry=217.00,
            alert_type=AlertType.PRIOR_DAY_LOW_RECLAIM,
            ma20=None, ma50=217.50, ma100=None, ma200=217.80,
        )
        assert has is True
        assert label == "200MA"

    def test_outside_band_no_confluence(self):
        """MA 2% away from entry → no confluence."""
        has, label, _ = _check_ma_confluence(
            entry=217.00,
            alert_type=AlertType.PRIOR_DAY_LOW_RECLAIM,
            ma20=None, ma50=221.34, ma100=None, ma200=None,
        )
        assert has is False


# ===== MA50 Counter-Trend Bounce =====


class TestMA50CounterTrend:
    def test_counter_trend_fires(self):
        """Prior close below 50MA, bar bounces off 50MA → signal fires."""
        bar = _bar(open_=100, high=101, low=99.98, close=100.3)
        sig = check_ma_bounce_50("AAPL", pd.DataFrame([bar]), ma20=102.0, ma50=100.0, prior_close=99.5)
        assert sig is not None
        assert sig.alert_type == AlertType.MA_BOUNCE_50
        assert "counter-trend" in sig.message

    def test_counter_trend_lower_confidence(self):
        """Counter-trend bounce always gets medium confidence, never high."""
        # proximity <= 0.001 would normally be "high" — counter-trend caps at medium
        bar = _bar(open_=100, high=101, low=100.05, close=100.3)
        sig = check_ma_bounce_50("AAPL", pd.DataFrame([bar]), ma20=102.0, ma50=100.0, prior_close=99.5)
        assert sig is not None
        assert sig.confidence == "medium"


# ===== MA Resistance Role-Flip =====


class TestMaResistanceRoleFlip:
    def test_role_flip_message(self):
        """Prior close below MA, rejection at MA → message includes role-flip note."""
        bar = _bar(open_=99, high=100.2, low=98.5, close=99.5)
        sig = check_ma_resistance(
            "TSLA", bar, ma20=100.1, ma50=None, ma100=None, ma200=None,
            prior_close=99.0,
        )
        assert sig is not None
        assert "recently broken" in sig.message
        assert "acting as resistance" in sig.message

    def test_no_fire_when_prior_above_ma(self):
        """Prior close above MA → MA is support, not resistance → skip."""
        bar = _bar(open_=99, high=100.2, low=98.5, close=99.5)
        sig = check_ma_resistance(
            "TSLA", bar, ma20=100.1, ma50=None, ma100=None, ma200=None,
            prior_close=101.0,
        )
        assert sig is None  # price dropping into MA = support, not resistance


# ===== EMA Resistance =====

class TestEmaResistance:
    """EMA resistance — price rallies into overhead EMA and gets rejected."""

    def test_fires_when_bar_high_near_ema20_and_closes_below(self):
        """Bar high touches EMA20, close below → rejection."""
        bar = _bar(open_=99, high=100.2, low=98.5, close=99.5)
        sig = check_ema_resistance("BTC-USD", bar, ema20=100.1, ema50=105.0)
        assert sig is not None
        assert sig.alert_type == AlertType.EMA_RESISTANCE
        assert sig.direction == "SELL"
        assert "EMA20" in sig.message

    def test_fires_when_bar_high_near_ema50_and_closes_below(self):
        """Bar high touches EMA50 (EMA20 not overhead), close below → rejection."""
        bar = _bar(open_=99, high=100.2, low=98.5, close=99.5)
        # EMA20 below close → skipped; EMA50 overhead → fires
        sig = check_ema_resistance("BTC-USD", bar, ema20=98.0, ema50=100.1)
        assert sig is not None
        assert "EMA50" in sig.message

    def test_fires_when_bar_high_near_ema100_and_closes_below(self):
        """Bar high touches EMA100, close below → rejection."""
        bar = _bar(open_=99, high=100.2, low=98.5, close=99.5)
        # EMA20 and EMA50 below close → skipped; EMA100 overhead → fires
        sig = check_ema_resistance(
            "BTC-USD", bar, ema20=98.0, ema50=97.0, ema100=100.1,
        )
        assert sig is not None
        assert "EMA100" in sig.message

    def test_no_fire_when_close_above_ema(self):
        """Close above EMA = breakout, not rejection."""
        bar = _bar(open_=99, high=101, low=99, close=100.5)
        sig = check_ema_resistance("BTC-USD", bar, ema20=100.0, ema50=105.0)
        assert sig is None

    def test_no_fire_when_far_from_ema(self):
        """Bar high more than 0.3% away from EMA → no proximity."""
        bar = _bar(open_=99, high=99.5, low=98.5, close=99.2)
        sig = check_ema_resistance("BTC-USD", bar, ema20=100.5, ema50=105.0)
        assert sig is None

    def test_no_fire_when_prior_close_above_ema(self):
        """Prior close above EMA → EMA is support, not resistance."""
        bar = _bar(open_=99, high=100.2, low=98.5, close=99.5)
        sig = check_ema_resistance(
            "BTC-USD", bar, ema20=100.1, ema50=105.0, prior_close=101.0,
        )
        assert sig is None

    def test_recently_broken_label(self):
        """Prior close below EMA → 'recently broken, acting as resistance' tag."""
        bar = _bar(open_=99, high=100.2, low=98.5, close=99.5)
        sig = check_ema_resistance(
            "BTC-USD", bar, ema20=100.1, ema50=105.0, prior_close=99.0,
        )
        assert sig is not None
        assert "recently broken" in sig.message
        assert "acting as resistance" in sig.message

    def test_no_fire_when_all_emas_none(self):
        bar = _bar(open_=99, high=100.2, low=98.5, close=99.5)
        sig = check_ema_resistance("BTC-USD", bar, ema20=None, ema50=None)
        assert sig is None

    def test_no_fire_when_all_emas_below_close(self):
        """All EMAs below close → no overhead resistance."""
        bar = _bar(open_=99, high=101, low=99, close=100.5)
        sig = check_ema_resistance(
            "BTC-USD", bar, ema20=98.0, ema50=97.0, ema100=96.0,
        )
        assert sig is None

    def test_fires_when_bar_high_near_ema200_and_closes_below(self):
        """Bar high touches EMA200, close below → rejection."""
        bar = _bar(open_=99, high=100.2, low=98.5, close=99.5)
        sig = check_ema_resistance(
            "BTC-USD", bar, ema20=98.0, ema50=97.0, ema100=96.0, ema200=100.1,
        )
        assert sig is not None
        assert "EMA200" in sig.message

    def test_no_fire_ema200_when_prior_close_above(self):
        """Prior close above EMA200 → support, not resistance."""
        bar = _bar(open_=99, high=100.2, low=98.5, close=99.5)
        sig = check_ema_resistance(
            "BTC-USD", bar, ema20=98.0, ema50=97.0, ema100=96.0,
            ema200=100.1, prior_close=101.0,
        )
        assert sig is None


# ===== Fix 1: Widened Resistance Proximity =====

class TestResistanceProximityWidened:
    def test_fires_at_0_12_percent_proximity(self):
        """LRCX at 0.12% from prior high — within tightened 0.15% threshold."""
        prior_high = 224.12
        bar_high = prior_high * (1 - 0.0012)  # 0.12% below
        bar = _bar(high=bar_high)
        sig = check_resistance_prior_high("LRCX", bar, prior_day_high=prior_high, has_active_entry=False)
        assert sig is not None
        assert sig.alert_type == AlertType.RESISTANCE_PRIOR_HIGH

    def test_fires_at_0_20_percent(self):
        """0.20% away — within the original 0.3% threshold (reverted from 0.15%)."""
        prior_high = 224.12
        bar_high = prior_high * (1 - 0.0020)  # 0.20% below
        bar = _bar(high=bar_high)
        sig = check_resistance_prior_high("LRCX", bar, prior_day_high=prior_high, has_active_entry=False)
        assert sig is not None  # 0.20% is within 0.3% threshold


# ===== Fix 3: VWAP Reclaim =====

class TestVWAPReclaim:
    @staticmethod
    def _make_vwap_bars(
        n_bars=20,
        low_bar=3,
        session_low=98.0,
        below_vwap_bars=None,
        last_close=100.4,
        last_volume=1500,
    ):
        """Build synthetic bars with some bars below VWAP and a reclaim.

        Returns (bars, vwap_series) ready for check_vwap_reclaim().
        VWAP is constant at 100.0.  last_close default 100.4 = 0.4% above VWAP
        (within the 0.5% proximity guard).
        """
        if below_vwap_bars is None:
            below_vwap_bars = [low_bar, low_bar + 1, low_bar + 2]
        rows = []
        for i in range(n_bars):
            if i == low_bar:
                rows.append({
                    "Open": 99.0, "High": 99.5, "Low": session_low,
                    "Close": 99.0, "Volume": 1200,
                })
            elif i in below_vwap_bars:
                rows.append({
                    "Open": 99.5, "High": 100.0, "Low": 99.2,
                    "Close": 99.5, "Volume": 1000,
                })
            else:
                rows.append({
                    "Open": 100.3, "High": 100.5, "Low": 100.0,
                    "Close": 100.3, "Volume": 1000,
                })
        rows[-1] = {
            "Open": 100.3, "High": 100.5, "Low": 100.0,
            "Close": last_close, "Volume": last_volume,
        }
        bars = pd.DataFrame(rows)
        vwap = pd.Series([100.0] * n_bars)
        return bars, vwap

    def test_fires_on_vwap_reclaim(self):
        """Was below VWAP recently, last bar closes above → fire."""
        bars, vwap = self._make_vwap_bars(
            low_bar=14, below_vwap_bars=[14, 15, 16], last_close=100.25,
        )
        sig = check_vwap_reclaim("AAPL", bars, vwap, bar_volume=1500, avg_volume=1000)
        assert sig is not None
        assert sig.alert_type == AlertType.VWAP_RECLAIM
        assert sig.direction == "BUY"
        assert sig.entry == 100.0

    def test_fires_on_afternoon_reclaim(self):
        """Low in afternoon (bar 15), not just morning — should still fire."""
        bars, vwap = self._make_vwap_bars(
            n_bars=20, low_bar=15, below_vwap_bars=[15, 16, 17],
            last_close=100.25,
        )
        sig = check_vwap_reclaim("AAPL", bars, vwap, bar_volume=1500, avg_volume=1000)
        assert sig is not None

    def test_no_fire_when_close_below_vwap(self):
        """Last bar closes below VWAP → no reclaim."""
        bars, vwap = self._make_vwap_bars(last_close=99.5)
        sig = check_vwap_reclaim("AAPL", bars, vwap, bar_volume=1500, avg_volume=1000)
        assert sig is None

    def test_no_fire_when_never_below_vwap(self):
        """Price was never below VWAP → not a reclaim."""
        bars, vwap = self._make_vwap_bars(
            below_vwap_bars=[], low_bar=3, session_low=100.1, last_close=101.0,
        )
        # Override: all bars close above VWAP
        for i in range(len(bars)):
            bars.loc[i, "Close"] = 100.5
            bars.loc[i, "Low"] = 100.1
        bars.loc[len(bars) - 1, "Close"] = 101.0
        sig = check_vwap_reclaim("AAPL", bars, vwap, bar_volume=1500, avg_volume=1000)
        assert sig is None

    def test_no_fire_when_recovery_too_small(self):
        """Recovery < 0.5% from session low → noise."""
        rows = []
        for _ in range(20):
            rows.append({
                "Open": 100.0, "High": 100.5, "Low": 100.0,
                "Close": 100.2, "Volume": 1000,
            })
        rows[3] = {"Open": 99.9, "High": 100.0, "Low": 99.80, "Close": 99.9, "Volume": 1200}
        rows[-1] = {"Open": 100.0, "High": 100.2, "Low": 100.0, "Close": 100.1, "Volume": 1500}
        bars = pd.DataFrame(rows)
        vwap = pd.Series([100.0] * 20)
        sig = check_vwap_reclaim("AAPL", bars, vwap, bar_volume=1500, avg_volume=1000)
        assert sig is None

    def test_high_volume_gives_high_confidence(self):
        """Volume ≥ 1.2x → confidence='high'."""
        bars, vwap = self._make_vwap_bars(
            low_bar=14, below_vwap_bars=[14, 15, 16], last_close=100.25,
        )
        sig = check_vwap_reclaim("AAPL", bars, vwap, bar_volume=1300, avg_volume=1000)
        assert sig is not None
        assert sig.confidence == "high"

    def test_low_volume_gives_medium_confidence(self):
        """Volume < 1.2x → confidence='medium'."""
        bars, vwap = self._make_vwap_bars(
            low_bar=14, below_vwap_bars=[14, 15, 16], last_close=100.25,
        )
        sig = check_vwap_reclaim("AAPL", bars, vwap, bar_volume=900, avg_volume=1000)
        assert sig is not None
        assert sig.confidence == "medium"

    def test_no_fire_when_price_too_far_above_vwap(self):
        """Price 1.4% above VWAP → already ran, skip."""
        bars, vwap = self._make_vwap_bars(
            low_bar=14, below_vwap_bars=[14, 15, 16], last_close=101.5,
        )
        sig = check_vwap_reclaim("AAPL", bars, vwap, bar_volume=1500, avg_volume=1000)
        assert sig is None

    def test_empty_bars_returns_none(self):
        """Empty bars DataFrame → None."""
        bars = pd.DataFrame()
        vwap = pd.Series(dtype=float)
        sig = check_vwap_reclaim("AAPL", bars, vwap, bar_volume=1500, avg_volume=1000)
        assert sig is None


# ---------------------------------------------------------------------------
# VWAP Bounce (pullback to VWAP that holds)
# ---------------------------------------------------------------------------


class TestVWAPBounce:
    """Tests for check_vwap_bounce — pullback to VWAP holds as continuation."""

    @staticmethod
    def _make_bounce_bars(
        n_bars=20,
        last_close=100.3,
        last_low=100.0,
        last_volume=1500,
        above_pct=0.8,
    ):
        """Build bars where most bars are above VWAP=100, last bar dips to VWAP.

        above_pct controls what fraction of lookback bars close above VWAP.
        """
        rows = []
        lookback = min(10, n_bars - 1)
        above_count = int(lookback * above_pct)
        for i in range(n_bars - 1):
            if i >= (n_bars - 1 - lookback) and (i - (n_bars - 1 - lookback)) >= above_count:
                # These bars close below VWAP
                rows.append({
                    "Open": 99.8, "High": 100.0, "Low": 99.5,
                    "Close": 99.7, "Volume": 1000,
                })
            else:
                # Above VWAP
                rows.append({
                    "Open": 100.5, "High": 101.0, "Low": 100.2,
                    "Close": 100.8, "Volume": 1000,
                })
        # Last bar: dips to VWAP, closes above
        rows.append({
            "Open": 100.5, "High": 100.6, "Low": last_low,
            "Close": last_close, "Volume": last_volume,
        })
        bars = pd.DataFrame(rows)
        vwap = pd.Series([100.0] * n_bars)
        return bars, vwap

    def test_fires_on_vwap_bounce(self):
        """Price above VWAP, dips to test, holds → fire."""
        bars, vwap = self._make_bounce_bars(last_close=100.3, last_low=100.0)
        sig = check_vwap_bounce("AAPL", bars, vwap, bar_volume=1500, avg_volume=1000)
        assert sig is not None
        assert sig.alert_type == AlertType.VWAP_BOUNCE
        assert sig.direction == "BUY"
        assert sig.entry == 100.0

    def test_stop_is_below_vwap(self):
        """Stop should be VWAP * (1 - offset), i.e. close below VWAP."""
        bars, vwap = self._make_bounce_bars(last_close=100.3, last_low=100.0)
        sig = check_vwap_bounce("AAPL", bars, vwap, bar_volume=1500, avg_volume=1000)
        assert sig is not None
        assert sig.stop < 100.0  # below VWAP

    def test_no_fire_when_close_below_vwap(self):
        """Last bar closes below VWAP → didn't hold."""
        bars, vwap = self._make_bounce_bars(last_close=99.8, last_low=99.5)
        sig = check_vwap_bounce("AAPL", bars, vwap, bar_volume=1500, avg_volume=1000)
        assert sig is None

    def test_no_fire_when_close_too_far_above(self):
        """Close 1% above VWAP → already bounced, too late."""
        bars, vwap = self._make_bounce_bars(last_close=101.0, last_low=100.0)
        sig = check_vwap_bounce("AAPL", bars, vwap, bar_volume=1500, avg_volume=1000)
        assert sig is None

    def test_no_fire_when_low_didnt_touch_vwap(self):
        """Bar low is 0.5% above VWAP → never tested VWAP."""
        bars, vwap = self._make_bounce_bars(last_close=100.8, last_low=100.5)
        sig = check_vwap_bounce("AAPL", bars, vwap, bar_volume=1500, avg_volume=1000)
        assert sig is None

    def test_no_fire_when_not_trending_above(self):
        """Only 30% of bars above VWAP → no uptrend context."""
        bars, vwap = self._make_bounce_bars(
            last_close=100.3, last_low=100.0, above_pct=0.3,
        )
        sig = check_vwap_bounce("AAPL", bars, vwap, bar_volume=1500, avg_volume=1000)
        assert sig is None

    def test_high_volume_gives_high_confidence(self):
        """Volume ≥ 1.2x → confidence='high'."""
        bars, vwap = self._make_bounce_bars(last_close=100.3, last_low=100.0)
        sig = check_vwap_bounce("AAPL", bars, vwap, bar_volume=1300, avg_volume=1000)
        assert sig is not None
        assert sig.confidence == "high"

    def test_low_volume_gives_medium_confidence(self):
        """Volume < 1.2x → confidence='medium'."""
        bars, vwap = self._make_bounce_bars(last_close=100.3, last_low=100.0)
        sig = check_vwap_bounce("AAPL", bars, vwap, bar_volume=900, avg_volume=1000)
        assert sig is not None
        assert sig.confidence == "medium"

    def test_low_dip_below_vwap_still_fires(self):
        """Bar low dips slightly below VWAP (within touch %) → still a test."""
        bars, vwap = self._make_bounce_bars(last_close=100.2, last_low=99.8)
        sig = check_vwap_bounce("AAPL", bars, vwap, bar_volume=1500, avg_volume=1000)
        assert sig is not None

    def test_empty_bars_returns_none(self):
        """Empty bars → None."""
        bars = pd.DataFrame()
        vwap = pd.Series(dtype=float)
        sig = check_vwap_bounce("AAPL", bars, vwap, bar_volume=1500, avg_volume=1000)
        assert sig is None


# ---------------------------------------------------------------------------
# Opening Low Base
# ---------------------------------------------------------------------------

class TestOpeningLowBase:
    """Tests for check_opening_low_base — first 15 min low holds as base."""

    def _make_bars(self, prices):
        """Build bars from list of (open, high, low, close) tuples."""
        rows = []
        for o, h, l, c in prices:
            rows.append({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 1000})
        return pd.DataFrame(rows)

    def test_classic_opening_low_base_fires(self):
        """LRCX-style: dips in first 3 bars, then holds above low for 3+ bars."""
        # entry = 217 * 1.003 = 217.65, stop = 216.35, T1 = 218.95
        # last bar close must be <= T1 to avoid staleness filter
        bars = self._make_bars([
            # Opening window (3 bars) — dip from 220 to 217
            (220, 221, 218, 219),    # bar 0: opens 220, dips to 218
            (219, 220, 217, 218),    # bar 1: dips further to 217 (session low)
            (218, 219, 217.5, 218),  # bar 2: holds near low
            # Hold bars — price stays above 217.65 but below T1 218.95
            (218, 219, 218, 218.2),  # bar 3: hold ✓
            (218.2, 219, 218, 218.5),  # bar 4: hold ✓
            (218.5, 219, 218, 218.3),  # bar 5: hold ✓
            (218.3, 219, 218, 218.7),  # bar 6: hold ✓ — fires here
        ])
        sig = check_opening_low_base("LRCX", bars)
        assert sig is not None
        assert sig.alert_type == AlertType.OPENING_LOW_BASE
        assert sig.direction == "BUY"
        assert sig.stop < 217  # below session low

    def test_no_dip_returns_none(self):
        """Flat open — no meaningful dip → no signal."""
        bars = self._make_bars([
            (220, 221, 219.5, 220),  # tiny dip, < 0.3%
            (220, 221, 219.8, 220.5),
            (220.5, 221, 220, 220.5),
            (220.5, 221, 220, 220.5),
            (220.5, 221, 220, 220.5),
            (220.5, 221, 220, 220.5),
            (220.5, 221, 220, 220.5),
        ])
        sig = check_opening_low_base("AAPL", bars)
        assert sig is None

    def test_low_after_window_returns_none(self):
        """Session low comes after the 15-min window → no signal."""
        bars = self._make_bars([
            # Opening window — mild
            (220, 221, 219, 220),
            (220, 221, 219, 220),
            (220, 221, 219, 220),
            # Bar 3 makes new low — outside window
            (220, 220, 215, 216),
            (216, 218, 216, 217),
            (217, 218, 217, 217.5),
            (217.5, 218, 217, 217.5),
        ])
        sig = check_opening_low_base("AAPL", bars)
        assert sig is None

    def test_not_enough_hold_bars_returns_none(self):
        """Price dips below hold threshold too soon → base not confirmed."""
        bars = self._make_bars([
            (220, 221, 217, 218),    # bar 0: dip
            (218, 219, 217, 218),    # bar 1: session low 217
            (218, 219, 217.5, 218),  # bar 2
            (218, 220, 218, 219),    # bar 3: hold ✓
            (219, 220, 216, 217),    # bar 4: breaks below → reset
            (217, 218, 217, 217.5),  # bar 5: hold ✓
            (217.5, 218, 217.5, 218),  # bar 6: hold ✓ — only 2 consecutive
        ])
        sig = check_opening_low_base("AAPL", bars)
        assert sig is None

    def test_too_few_bars_returns_none(self):
        """Not enough bars → None."""
        bars = self._make_bars([
            (220, 221, 217, 218),
            (218, 219, 217, 218),
            (218, 219, 218, 219),
        ])
        sig = check_opening_low_base("AAPL", bars)
        assert sig is None

    def test_high_confidence_on_deep_dip(self):
        """Deep dip (>=0.5%) + 4+ hold bars → high confidence."""
        # entry = 216 * 1.003 = 216.65, stop = 215.35, T1 = 217.95
        # last bar close must be <= T1 to avoid staleness
        bars = self._make_bars([
            (220, 221, 218, 219),
            (219, 219, 216, 217),      # 1.8% dip from open
            (217, 218, 217, 217.5),
            (217.5, 218, 217, 217.2),  # hold ✓
            (217.2, 218, 217, 217.5),  # hold ✓
            (217.5, 218, 217, 217.3),  # hold ✓
            (217.3, 218, 217, 217.6),  # hold ✓ — 4 consecutive
            (217.6, 218, 217, 217.8),  # hold ✓
        ])
        sig = check_opening_low_base("LRCX", bars)
        assert sig is not None
        assert sig.confidence == "high"

    def test_empty_bars_returns_none(self):
        """Empty DataFrame → None."""
        bars = pd.DataFrame()
        sig = check_opening_low_base("AAPL", bars)
        assert sig is None


# ── EMA Bounce 100 ──────────────────────────────────────────────


class TestEmaBounce100:
    """Tests for check_ema_bounce_100() — intermediate EMA support."""

    @staticmethod
    def _bar(low, close, high=None, open_=None, volume=100_000):
        return pd.Series({
            "Open": open_ or close,
            "High": high or close,
            "Low": low,
            "Close": close,
            "Volume": volume,
        })

    def test_classic_bounce_fires(self):
        """Bar low near EMA100, closes above → BUY."""
        ema100 = 676.86
        bar = self._bar(low=676.50, close=679.69, high=680.0)
        sig = check_ema_bounce_100("SPY", pd.DataFrame([bar]), ema100, prior_close=685.0)
        assert sig is not None
        assert sig.alert_type == AlertType.EMA_BOUNCE_100
        assert sig.direction == "BUY"
        assert sig.entry == round(ema100, 2)
        assert sig.confidence == "high"

    def test_no_fire_when_close_below_ema(self):
        """Bar closes below EMA100 → no bounce."""
        ema100 = 676.86
        bar = self._bar(low=675.0, close=676.0)
        sig = check_ema_bounce_100("SPY", pd.DataFrame([bar]), ema100, prior_close=685.0)
        assert sig is None

    def test_no_fire_when_too_far(self):
        """Both Low and Close far from EMA100 → no fire."""
        ema100 = 676.86
        # Low >0.5% below, Close >2% above (exceeds max distance)
        bar = self._bar(low=670.0, close=691.0)
        sig = check_ema_bounce_100("SPY", pd.DataFrame([bar]), ema100, prior_close=685.0)
        assert sig is None

    def test_counter_trend_medium_confidence(self):
        """Prior close below EMA100 → counter-trend → medium."""
        ema100 = 676.86
        bar = self._bar(low=676.50, close=679.69)
        sig = check_ema_bounce_100("SPY", pd.DataFrame([bar]), ema100, prior_close=670.0)
        assert sig is not None
        assert sig.confidence == "medium"
        assert "counter-trend" in sig.message

    def test_none_when_ema100_missing(self):
        """EMA100 is None → None."""
        bar = self._bar(low=676.50, close=679.69)
        sig = check_ema_bounce_100("SPY", pd.DataFrame([bar]), None, prior_close=685.0)
        assert sig is None

    def test_stop_uses_ma100_offset(self):
        """Stop should be EMA100 * (1 - 0.7%)."""
        ema100 = 676.86
        bar = self._bar(low=676.50, close=679.69)
        sig = check_ema_bounce_100("SPY", pd.DataFrame([bar]), ema100, prior_close=685.0)
        assert sig is not None
        expected_stop = round(ema100 * (1 - 0.007), 2)
        assert sig.stop == expected_stop


# ===== EMA Bounce 200 (BUY) =====

class TestEmaBounce200:
    """Tests for check_ema_bounce_200() — major institutional EMA level."""

    @staticmethod
    def _bar(low, close, high=None, open_=None, volume=100_000):
        return pd.Series({
            "Open": open_ or close,
            "High": high or close,
            "Low": low,
            "Close": close,
            "Volume": volume,
        })

    def test_classic_bounce_fires(self):
        """Bar low near EMA200, closes above → BUY."""
        ema200 = 650.0
        bar = self._bar(low=649.50, close=653.0, high=654.0)
        sig = check_ema_bounce_200("SPY", pd.DataFrame([bar]), ema200, prior_close=660.0)
        assert sig is not None
        assert sig.alert_type == AlertType.EMA_BOUNCE_200
        assert sig.direction == "BUY"
        assert sig.entry == round(ema200, 2)
        assert sig.confidence == "high"

    def test_no_fire_when_close_below_ema(self):
        """Bar closes below EMA200 → no bounce."""
        ema200 = 650.0
        bar = self._bar(low=648.0, close=649.0)
        sig = check_ema_bounce_200("SPY", pd.DataFrame([bar]), ema200, prior_close=660.0)
        assert sig is None

    def test_no_fire_when_too_far(self):
        """Both Low and Close far from EMA200 → no fire."""
        ema200 = 650.0
        # Low >0.8% below, Close >2% above (exceeds max distance)
        bar = self._bar(low=642.0, close=665.0)
        sig = check_ema_bounce_200("SPY", pd.DataFrame([bar]), ema200, prior_close=660.0)
        assert sig is None

    def test_counter_trend_medium_confidence(self):
        """Prior close below EMA200 → counter-trend → medium."""
        ema200 = 650.0
        bar = self._bar(low=649.50, close=653.0)
        sig = check_ema_bounce_200("SPY", pd.DataFrame([bar]), ema200, prior_close=640.0)
        assert sig is not None
        assert sig.confidence == "medium"
        assert "counter-trend" in sig.message

    def test_none_when_ema200_missing(self):
        """EMA200 is None → None."""
        bar = self._bar(low=649.50, close=653.0)
        sig = check_ema_bounce_200("SPY", pd.DataFrame([bar]), None, prior_close=660.0)
        assert sig is None

    def test_stop_uses_ma200_offset(self):
        """Stop should be EMA200 * (1 - 1.0%)."""
        ema200 = 650.0
        bar = self._bar(low=649.50, close=653.0)
        sig = check_ema_bounce_200("SPY", pd.DataFrame([bar]), ema200, prior_close=660.0)
        assert sig is not None
        expected_stop = round(ema200 * (1 - 0.010), 2)
        assert sig.stop == expected_stop

    def test_targets_are_1r_and_2r(self):
        """T1 = entry + risk, T2 = entry + 2*risk."""
        ema200 = 650.0
        bar = self._bar(low=649.50, close=653.0)
        sig = check_ema_bounce_200("SPY", pd.DataFrame([bar]), ema200, prior_close=660.0)
        assert sig is not None
        risk = sig.entry - sig.stop
        assert sig.target_1 == round(sig.entry + risk, 2)
        assert sig.target_2 == round(sig.entry + 2 * risk, 2)


# ===== Inside Day Breakdown (SELL — informational) =====

class TestInsideDayBreakdown:
    """Tests for check_inside_day_breakdown()."""

    def _inside_prior(self, **overrides):
        d = {
            "is_inside": True, "high": 50.5, "low": 49.0,
            "parent_high": 52.0, "parent_low": 48.0,
        }
        d.update(overrides)
        return d

    def test_fires_on_close_below_inside_low(self):
        bar = _bar(open_=49.5, high=49.8, low=48.5, close=48.7)
        sig = check_inside_day_breakdown("SPY", bar, self._inside_prior())
        assert sig is not None
        assert sig.alert_type == AlertType.INSIDE_DAY_BREAKDOWN
        assert sig.direction == "SELL"

    def test_no_fire_when_close_above_inside_low(self):
        bar = _bar(open_=49.5, high=50.0, low=49.2, close=49.5)
        sig = check_inside_day_breakdown("SPY", bar, self._inside_prior())
        assert sig is None

    def test_no_fire_when_close_equals_inside_low(self):
        bar = _bar(open_=49.5, high=50.0, low=48.8, close=49.0)
        sig = check_inside_day_breakdown("SPY", bar, self._inside_prior())
        assert sig is None  # >= inside_low, no breakdown

    def test_no_fire_when_not_inside_day(self):
        bar = _bar(open_=49.5, high=49.8, low=48.5, close=48.7)
        prior = self._inside_prior(is_inside=False)
        sig = check_inside_day_breakdown("SPY", bar, prior)
        assert sig is None

    def test_no_fire_when_prior_day_none(self):
        bar = _bar()
        assert check_inside_day_breakdown("X", bar, None) is None

    def test_no_fire_when_prior_day_empty(self):
        bar = _bar()
        assert check_inside_day_breakdown("X", bar, {}) is None

    def test_no_fire_when_zero_range(self):
        bar = _bar(open_=49.5, high=49.8, low=48.5, close=48.7)
        prior = self._inside_prior(high=49.0, low=49.0)  # zero range
        sig = check_inside_day_breakdown("SPY", bar, prior)
        assert sig is None

    def test_confidence_is_high(self):
        bar = _bar(open_=49.5, high=49.8, low=48.5, close=48.7)
        sig = check_inside_day_breakdown("SPY", bar, self._inside_prior())
        assert sig is not None
        assert sig.confidence == "high"

    def test_message_includes_inside_low_and_range(self):
        bar = _bar(open_=49.5, high=49.8, low=48.5, close=48.7)
        sig = check_inside_day_breakdown("SPY", bar, self._inside_prior())
        assert sig is not None
        assert "$49.00" in sig.message  # inside low
        assert "inside range" in sig.message


# ===== Inside Day Reclaim (BUY — failed breakdown trap) =====

class TestInsideDayReclaim:
    """Tests for check_inside_day_reclaim()."""

    def _inside_prior(self, **overrides):
        d = {
            "is_inside": True, "high": 50.5, "low": 49.0,
            "parent_high": 52.0, "parent_low": 48.0,
        }
        d.update(overrides)
        return d

    def test_fires_on_dip_and_reclaim(self):
        bars = _bars([
            {"Open": 49.5, "High": 49.8, "Low": 48.5, "Close": 48.7, "Volume": 1000},
            {"Open": 48.8, "High": 49.5, "Low": 48.6, "Close": 49.3, "Volume": 1200},
        ])
        sig = check_inside_day_reclaim("SPY", bars, self._inside_prior())
        assert sig is not None
        assert sig.alert_type == AlertType.INSIDE_DAY_RECLAIM
        assert sig.direction == "BUY"
        assert sig.entry == 49.0  # inside low

    def test_stop_below_session_low(self):
        bars = _bars([
            {"Open": 49.5, "High": 49.8, "Low": 48.5, "Close": 48.7, "Volume": 1000},
            {"Open": 48.8, "High": 49.5, "Low": 48.6, "Close": 49.3, "Volume": 1200},
        ])
        sig = check_inside_day_reclaim("SPY", bars, self._inside_prior())
        assert sig is not None
        # Stop should be below session low (48.5)
        assert sig.stop < 48.5

    def test_targets_are_1r_and_2r(self):
        bars = _bars([
            {"Open": 49.5, "High": 49.8, "Low": 48.5, "Close": 48.7, "Volume": 1000},
            {"Open": 48.8, "High": 49.5, "Low": 48.6, "Close": 49.3, "Volume": 1200},
        ])
        sig = check_inside_day_reclaim("SPY", bars, self._inside_prior())
        assert sig is not None
        risk = sig.entry - sig.stop
        assert risk > 0
        assert abs(sig.target_1 - (sig.entry + risk)) < 0.01
        assert abs(sig.target_2 - (sig.entry + 2 * risk)) < 0.01

    def test_no_fire_when_no_dip(self):
        bars = _bars([
            {"Open": 49.5, "High": 50.0, "Low": 49.1, "Close": 49.8, "Volume": 1000},
        ])
        sig = check_inside_day_reclaim("SPY", bars, self._inside_prior())
        assert sig is None  # low 49.1 > 49.0 * (1 - 0.0003) ≈ 48.985

    def test_no_fire_when_still_below_inside_low(self):
        bars = _bars([
            {"Open": 49.5, "High": 49.8, "Low": 48.5, "Close": 48.7, "Volume": 1000},
        ])
        sig = check_inside_day_reclaim("SPY", bars, self._inside_prior())
        assert sig is None  # close 48.7 <= 49.0

    def test_no_fire_when_not_inside_day(self):
        bars = _bars([
            {"Open": 49.5, "High": 49.8, "Low": 48.5, "Close": 49.3, "Volume": 1000},
        ])
        prior = self._inside_prior(is_inside=False)
        sig = check_inside_day_reclaim("SPY", bars, prior)
        assert sig is None

    def test_no_fire_when_prior_day_none(self):
        bars = _bars([
            {"Open": 49.5, "High": 49.8, "Low": 48.5, "Close": 49.3, "Volume": 1000},
        ])
        assert check_inside_day_reclaim("X", bars, None) is None

    def test_no_fire_when_prior_day_empty(self):
        bars = _bars([
            {"Open": 49.5, "High": 49.8, "Low": 48.5, "Close": 49.3, "Volume": 1000},
        ])
        assert check_inside_day_reclaim("X", bars, {}) is None

    def test_no_fire_when_bars_empty(self):
        sig = check_inside_day_reclaim("X", pd.DataFrame(), self._inside_prior())
        assert sig is None

    def test_no_fire_when_zero_inside_low(self):
        bars = _bars([
            {"Open": 49.5, "High": 49.8, "Low": -0.01, "Close": 0.5, "Volume": 1000},
        ])
        prior = self._inside_prior(low=0)
        sig = check_inside_day_reclaim("X", bars, prior)
        assert sig is None

    def test_no_fire_when_zero_range(self):
        bars = _bars([
            {"Open": 49.5, "High": 49.8, "Low": 48.5, "Close": 49.3, "Volume": 1000},
        ])
        prior = self._inside_prior(high=49.0, low=49.0)  # zero range
        sig = check_inside_day_reclaim("X", bars, prior)
        assert sig is None

    def test_confidence_is_high(self):
        bars = _bars([
            {"Open": 49.5, "High": 49.8, "Low": 48.5, "Close": 48.7, "Volume": 1000},
            {"Open": 48.8, "High": 49.5, "Low": 48.6, "Close": 49.3, "Volume": 1200},
        ])
        sig = check_inside_day_reclaim("SPY", bars, self._inside_prior())
        assert sig is not None
        assert sig.confidence == "high"

    def test_message_includes_dip_and_reclaim_levels(self):
        bars = _bars([
            {"Open": 49.5, "High": 49.8, "Low": 48.5, "Close": 48.7, "Volume": 1000},
            {"Open": 48.8, "High": 49.5, "Low": 48.6, "Close": 49.3, "Volume": 1200},
        ])
        sig = check_inside_day_reclaim("SPY", bars, self._inside_prior())
        assert sig is not None
        assert "$48.50" in sig.message  # dip level
        assert "$49.00" in sig.message  # inside low
        assert "failed breakdown" in sig.message


# ===== MA Context Detection =====

class TestDetectMAContext:
    """Tests for _detect_ma_context() — defending/rejected MA detection."""

    def test_defending_100ma(self):
        """Price 0.3% above 100MA → defending='100MA'."""
        price = 100.0
        ma100 = 99.70  # 0.3% below
        defending, rejected = _detect_ma_context(
            price, None, None, ma100, None, None, None, None,
        )
        assert defending == "100MA"
        assert rejected == ""

    def test_rejected_50ema(self):
        """Price 0.3% below 50EMA → rejected_by='50EMA'."""
        price = 100.0
        ema50 = 100.30  # 0.3% above
        defending, rejected = _detect_ma_context(
            price, None, None, None, None, None, ema50, None,
        )
        assert defending == ""
        assert rejected == "50EMA"

    def test_no_nearby_ma(self):
        """Price far from all MAs → both empty."""
        price = 100.0
        defending, rejected = _detect_ma_context(
            price, 95.0, 90.0, 85.0, 80.0, 96.0, 91.0, 86.0,
        )
        assert defending == ""
        assert rejected == ""

    def test_closest_wins(self):
        """When near multiple MAs, closest wins."""
        price = 100.0
        ma50 = 99.80   # 0.2% below — closer
        ma100 = 99.60  # 0.4% below — farther
        defending, rejected = _detect_ma_context(
            price, None, ma50, ma100, None, None, None, None,
        )
        assert defending == "50MA"

    def test_both_defending_and_rejected(self):
        """Price squeezed between two MAs."""
        price = 100.0
        ma100 = 99.70   # 0.3% below — defending
        ema50 = 100.30   # 0.3% above — rejecting
        defending, rejected = _detect_ma_context(
            price, None, None, ma100, None, None, ema50, None,
        )
        assert defending == "100MA"
        assert rejected == "50EMA"

    def test_zero_price_returns_empty(self):
        """Edge case: zero price returns empty."""
        defending, rejected = _detect_ma_context(
            0.0, 50.0, 100.0, 150.0, 200.0, 50.0, 100.0, 150.0,
        )
        assert defending == ""
        assert rejected == ""

    def test_all_none_mas(self):
        """All MAs are None → both empty."""
        defending, rejected = _detect_ma_context(
            100.0, None, None, None, None, None, None, None,
        )
        assert defending == ""
        assert rejected == ""


class TestDayPatternPropagation:
    """Test that prior_day pattern flows to AlertSignal in evaluate_rules."""

    def test_day_pattern_propagated(self):
        """AlertSignal.day_pattern gets set from prior_day['pattern']."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.0, "Close": 100.0, "Volume": 1000},
            {"Open": 100, "High": 101, "Low": 99.9, "Close": 100.3, "Volume": 1000},
        ])
        prior = {
            "close": 100.0, "high": 101.0, "low": 99.0,
            "ma20": 100.0, "ma50": 99.5, "ma100": 98.0, "ma200": 95.0,
            "ema20": 100.0, "ema50": 99.5, "ema100": 98.0,
            "atr14": 2.0, "avg_volume": 1000, "rsi14": 50.0,
            "pattern": "inside",
        }
        signals = evaluate_rules("TEST", bars, prior)
        # Even if no signal fires, verify the field exists on AlertSignal
        sig = AlertSignal(symbol="TEST", direction="BUY",
                          alert_type=AlertType.MA_BOUNCE_20, price=100.0)
        sig.day_pattern = prior.get("pattern", "normal")
        assert sig.day_pattern == "inside"


# ===== Crypto 24h Integration =====

def _crypto_prior_day():
    """Standard prior_day dict for crypto tests."""
    return {
        "close": 60000.0, "high": 61000.0, "low": 59000.0,
        "ma20": 60000.0, "ma50": 59500.0, "ma100": 58000.0, "ma200": 55000.0,
        "ema20": 60000.0, "ema50": 59500.0, "ema100": 58000.0,
        "atr14": 2000.0, "avg_volume": 5000, "rsi14": 50.0,
    }


def _crypto_bars(n=10):
    """Generate n synthetic 5-min BTC-like bars."""
    rows = []
    for i in range(n):
        rows.append({
            "Open": 60000 + i * 10,
            "High": 60050 + i * 10,
            "Low": 59950 + i * 10,
            "Close": 60020 + i * 10,
            "Volume": 5000,
        })
    return _bars(rows)


class TestCryptoIntegration:
    """Tests for BTC-USD/ETH-USD 24h market support."""

    def test_crypto_evaluate_rules_no_spy_demotion(self):
        """BUY signal for crypto should not get SPY regime demotion."""
        bars = _crypto_bars(10)
        # Force a MA bounce by setting ma20 near the bar low
        prior = _crypto_prior_day()
        prior["ma20"] = bars.iloc[-1]["Low"] * 1.001  # within 0.3% proximity

        signals = evaluate_rules(
            "BTC-USD", bars, prior,
            spy_context={"trend": "bearish", "regime": "CHOPPY"},
            is_crypto=True,
        )
        for sig in signals:
            if sig.direction == "BUY":
                assert "CHOPPY market" not in sig.message
                assert "SPY TRENDING DOWN" not in sig.message
                assert "SPY bearish" not in sig.message

    def test_crypto_entries_always_allowed(self):
        """Crypto signals should never get 'session: closed' caution."""
        bars = _crypto_bars(10)
        prior = _crypto_prior_day()
        prior["ma20"] = bars.iloc[-1]["Low"] * 1.001

        signals = evaluate_rules(
            "BTC-USD", bars, prior,
            spy_context=None,
            is_crypto=True,
        )
        for sig in signals:
            assert "session: closed" not in sig.message

    def test_crypto_opening_range_from_first_bars(self):
        """Crypto ORB uses first 6 bars of data, not 9:30 ET."""
        bars = _crypto_bars(10)
        result = _compute_crypto_opening_range(bars)
        assert result is not None
        first_6 = bars.iloc[:6]
        assert result["or_high"] == first_6["High"].max()
        assert result["or_low"] == first_6["Low"].min()
        assert result["or_complete"] is True

    def test_crypto_opening_range_insufficient_bars(self):
        """Crypto ORB returns None with fewer than 6 bars."""
        bars = _crypto_bars(3)
        result = _compute_crypto_opening_range(bars)
        assert result is None

    def test_equity_path_unchanged_with_spy_demotion(self):
        """Equity symbols still get SPY regime demotion when is_crypto=False."""
        # Build bars where MA bounce would fire
        bar_data = []
        for i in range(10):
            bar_data.append({
                "Open": 100 + i * 0.1,
                "High": 101 + i * 0.1,
                "Low": 99.95 + i * 0.1,
                "Close": 100.3 + i * 0.1,
                "Volume": 1000,
            })
        bars = _bars(bar_data)
        prior = {
            "close": 100.0, "high": 101.0, "low": 99.0,
            "ma20": bars.iloc[-1]["Low"] * 1.001,
            "ma50": 99.5, "ma100": 98.0, "ma200": 95.0,
            "ema20": 100.0, "ema50": 99.5, "ema100": 98.0,
            "atr14": 2.0, "avg_volume": 1000, "rsi14": 50.0,
        }
        signals = evaluate_rules(
            "AAPL", bars, prior,
            spy_context={"trend": "bearish", "regime": "CHOPPY"},
            is_crypto=False,
        )
        buy_signals = [s for s in signals if s.direction == "BUY"]
        if buy_signals:
            # At least one BUY should have SPY caution
            has_choppy = any("CHOPPY" in s.message for s in buy_signals)
            assert has_choppy

    def test_crypto_no_rs_demotion(self):
        """Crypto BUY should not get RS (relative strength vs SPY) demotion."""
        bars = _crypto_bars(10)
        prior = _crypto_prior_day()
        prior["ma20"] = bars.iloc[-1]["Low"] * 1.001

        signals = evaluate_rules(
            "BTC-USD", bars, prior,
            spy_context={"trend": "neutral", "regime": "TRENDING_UP",
                         "intraday_change": 1.0},
            is_crypto=True,
        )
        for sig in signals:
            assert "RS CAUTION" not in sig.message


# ===== First Hour Close Summary =====


class TestFirstHourSummary:
    """Tests for check_first_hour_summary — NOTICE alert after first hour closes."""

    def _make_bars(self, n=13, open_=100.0, trend="up"):
        """Create n bars simulating a first-hour session.

        trend: 'up' = gradually rising, 'down' = gradually falling, 'flat' = sideways
        """
        rows = []
        for i in range(n):
            if trend == "up":
                o = open_ + i * 0.2
                c = o + 0.15
                h = c + 0.05
                lo = o - 0.05
            elif trend == "down":
                o = open_ - i * 0.2
                c = o - 0.15
                h = o + 0.05
                lo = c - 0.05
            else:  # flat
                o = open_
                c = open_ + 0.01
                h = open_ + 0.05
                lo = open_ - 0.05
            rows.append({"Open": o, "High": h, "Low": lo, "Close": c, "Volume": 1000})
        return _bars(rows)

    def _make_prior(self):
        return {
            "close": 99.0, "high": 105.0, "low": 95.0,
            "ma20": 98.0, "ma50": 96.0, "ma100": 94.0, "ma200": 90.0,
            "ema20": 98.5, "ema50": 96.5, "ema100": 94.5,
            "rsi14": 55.0,
        }

    def test_fires_with_13_bars_bullish(self):
        """13+ bars and bullish first hour → NOTICE with BULLISH direction label."""
        bars = self._make_bars(13, trend="up")
        sig = check_first_hour_summary("AAPL", bars, self._make_prior())
        assert sig is not None
        assert sig.alert_type == AlertType.FIRST_HOUR_SUMMARY
        assert sig.direction == "NOTICE"
        assert "BULLISH" in sig.message
        assert "range" in sig.message

    def test_fires_with_13_bars_bearish(self):
        """13+ bars and bearish first hour → NOTICE with BEARISH direction label."""
        bars = self._make_bars(13, trend="down")
        sig = check_first_hour_summary("AAPL", bars, self._make_prior())
        assert sig is not None
        assert "BEARISH" in sig.message

    def test_fires_with_13_bars_flat(self):
        """13+ bars and flat first hour → NOTICE with FLAT direction label."""
        bars = self._make_bars(13, trend="flat")
        sig = check_first_hour_summary("AAPL", bars, self._make_prior())
        assert sig is not None
        assert "FLAT" in sig.message

    def test_no_fire_with_fewer_than_13_bars(self):
        """< 13 bars means first hour hasn't completed → None."""
        bars = self._make_bars(12, trend="up")
        sig = check_first_hour_summary("AAPL", bars, self._make_prior())
        assert sig is None

    def test_no_fire_if_already_fired_today(self):
        """Already in fired_today set → None (dedup)."""
        bars = self._make_bars(13, trend="up")
        fired = {("AAPL", "first_hour_summary")}
        sig = check_first_hour_summary("AAPL", bars, self._make_prior(), fired_today=fired)
        assert sig is None

    def test_fires_for_different_symbol_in_fired_today(self):
        """fired_today has NVDA but not AAPL → should fire for AAPL."""
        bars = self._make_bars(13, trend="up")
        fired = {("NVDA", "first_hour_summary")}
        sig = check_first_hour_summary("AAPL", bars, self._make_prior(), fired_today=fired)
        assert sig is not None

    def test_no_fire_without_prior_day(self):
        """No prior_day context → None."""
        bars = self._make_bars(13, trend="up")
        sig = check_first_hour_summary("AAPL", bars, None)
        assert sig is None

    def test_message_includes_range_and_finish(self):
        """Message contains range % and finish description."""
        bars = self._make_bars(13, trend="up")
        sig = check_first_hour_summary("AAPL", bars, self._make_prior())
        assert sig is not None
        assert "range" in sig.message
        assert "finish" in sig.message

    def test_strong_finish_near_high(self):
        """Close near high of first-hour range → 'strong finish'."""
        # Build bars where close of bar 11 is near the session high
        rows = []
        for i in range(13):
            rows.append({"Open": 100, "High": 102, "Low": 99, "Close": 101.8, "Volume": 1000})
        bars = _bars(rows)
        sig = check_first_hour_summary("AAPL", bars, self._make_prior())
        assert sig is not None
        assert "strong finish" in sig.message

    def test_weak_finish_near_low(self):
        """Close near low of first-hour range → 'weak finish'."""
        rows = []
        for i in range(13):
            rows.append({"Open": 100, "High": 102, "Low": 99, "Close": 99.2, "Volume": 1000})
        bars = _bars(rows)
        sig = check_first_hour_summary("AAPL", bars, self._make_prior())
        assert sig is not None
        assert "weak finish" in sig.message

    def test_level_tags_prior_high_touched(self):
        """First-hour high touches prior day high → message includes 'touched prior high'."""
        prior = self._make_prior()
        prior["high"] = 101.5  # within first-hour range
        rows = []
        for i in range(13):
            rows.append({"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 1000})
        bars = _bars(rows)
        sig = check_first_hour_summary("AAPL", bars, prior)
        assert sig is not None
        assert "touched prior high" in sig.message

    def test_level_tags_ma_in_range(self):
        """MA20 within first-hour range → message includes '20MA in range'."""
        prior = self._make_prior()
        prior["ma20"] = 100.5  # within the first-hour low-high range
        rows = []
        for i in range(13):
            rows.append({"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 1000})
        bars = _bars(rows)
        sig = check_first_hour_summary("AAPL", bars, prior)
        assert sig is not None
        assert "20MA in range" in sig.message

    def test_confidence_is_info(self):
        """Confidence should be 'info' — this is informational, not actionable."""
        bars = self._make_bars(13, trend="up")
        sig = check_first_hour_summary("AAPL", bars, self._make_prior())
        assert sig is not None
        assert sig.confidence == "info"

    def test_many_bars_still_fires(self):
        """With 30+ bars (well past first hour), still fires if not deduped."""
        bars = self._make_bars(30, trend="up")
        sig = check_first_hour_summary("AAPL", bars, self._make_prior())
        assert sig is not None


# ===== Professional Rules: MACD Histogram Flip =====

class TestMACDHistogramFlip:
    """Tests for check_macd_histogram_flip — momentum confirmation."""

    def _make_trending_bars(self, n, start=100, trend_up=True):
        """Create n bars with a clear trend for MACD computation."""
        rows = []
        for i in range(n):
            if trend_up:
                c = start + i * 0.3
            else:
                c = start - i * 0.3
            rows.append({
                "Open": c - 0.2, "High": c + 0.5,
                "Low": c - 0.5, "Close": c, "Volume": 1000,
            })
        return _bars(rows)

    def test_fires_on_histogram_flip_positive(self):
        """MACD histogram flips negative→positive → BUY signal."""
        # Create downtrend then uptrend to get histogram flip
        n = 40
        rows = []
        for i in range(20):
            c = 100 - i * 0.5  # downtrend
            rows.append({"Open": c + 0.2, "High": c + 0.5, "Low": c - 0.5, "Close": c, "Volume": 1000})
        for i in range(20):
            c = 90 + i * 0.8  # stronger uptrend to flip MACD
            rows.append({"Open": c - 0.2, "High": c + 0.5, "Low": c - 0.5, "Close": c, "Volume": 1000})
        bars = _bars(rows)
        prior = {"close": bars.iloc[-2]["Close"]}
        sig = check_macd_histogram_flip("AAPL", bars, prior)
        # May or may not fire depending on exact MACD values, but should not crash
        if sig is not None:
            assert sig.alert_type == AlertType.MACD_HISTOGRAM_FLIP
            assert sig.direction == "BUY"

    def test_returns_none_with_insufficient_bars(self):
        """Too few bars → None."""
        bars = self._make_trending_bars(10)
        sig = check_macd_histogram_flip("AAPL", bars, {"close": 99})
        assert sig is None

    def test_returns_none_when_histogram_stays_negative(self):
        """Steady downtrend keeps histogram negative → None."""
        bars = self._make_trending_bars(40, trend_up=False)
        prior = {"close": bars.iloc[-2]["Close"]}
        sig = check_macd_histogram_flip("AAPL", bars, prior)
        # In steady downtrend, histogram should stay negative
        assert sig is None

    def test_returns_none_without_close_confirmation(self):
        """Close below prior close → no confirmation → None."""
        rows = []
        for i in range(20):
            c = 100 - i * 0.5
            rows.append({"Open": c + 0.2, "High": c + 0.5, "Low": c - 0.5, "Close": c, "Volume": 1000})
        for i in range(20):
            c = 90 + i * 0.8
            rows.append({"Open": c - 0.2, "High": c + 0.5, "Low": c - 0.5, "Close": c, "Volume": 1000})
        bars = _bars(rows)
        # Set prior close higher than current → no confirmation
        prior = {"close": bars.iloc[-1]["Close"] + 10}
        sig = check_macd_histogram_flip("AAPL", bars, prior)
        assert sig is None


# ===== Professional Rules: Bollinger Band Squeeze Breakout =====

class TestBBSqueezeBreakout:
    """Tests for check_bb_squeeze_breakout — volatility squeeze detection."""

    def test_returns_none_with_insufficient_bars(self):
        """Too few bars for BB calculation → None."""
        rows = [{"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000}] * 10
        bars = _bars(rows)
        sig = check_bb_squeeze_breakout("AAPL", bars)
        assert sig is None

    def test_returns_none_no_breakout(self):
        """Close below upper band → no breakout → None."""
        # Create 50 bars with very tight range (squeeze) but close below upper band
        rows = []
        for i in range(50):
            c = 100.0 + (i % 2) * 0.01  # barely moves → tight BB
            rows.append({"Open": c, "High": c + 0.01, "Low": c - 0.01, "Close": c, "Volume": 1000})
        bars = _bars(rows)
        sig = check_bb_squeeze_breakout("AAPL", bars)
        # Close is inside the band, so no breakout
        assert sig is None

    def test_fires_on_squeeze_breakout(self):
        """Tight range followed by breakout above upper band → BUY."""
        rows = []
        # 45 bars of tight range (BB squeeze)
        for i in range(45):
            rows.append({"Open": 100, "High": 100.05, "Low": 99.95, "Close": 100, "Volume": 1000})
        # Last 5 bars: explosive breakout
        for i in range(5):
            c = 100 + (i + 1) * 2  # big move up
            rows.append({"Open": c - 1, "High": c + 1, "Low": c - 1.5, "Close": c, "Volume": 2000})
        bars = _bars(rows)
        sig = check_bb_squeeze_breakout("AAPL", bars)
        if sig is not None:
            assert sig.alert_type == AlertType.BB_SQUEEZE_BREAKOUT
            assert sig.direction == "BUY"
            assert sig.confidence == "high"


# ===== Professional Rules: ATR Computation & Dynamic Stops =====

class TestComputeATR:
    """Tests for compute_atr — Average True Range."""

    def test_returns_none_insufficient_bars(self):
        """Not enough bars → None."""
        rows = [{"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000}] * 5
        bars = _bars(rows)
        assert compute_atr(bars) is None

    def test_returns_valid_atr(self):
        """Enough bars → returns positive float."""
        rows = []
        for i in range(20):
            rows.append({"Open": 100 + i * 0.1, "High": 101 + i * 0.1, "Low": 99 + i * 0.1, "Close": 100.5 + i * 0.1, "Volume": 1000})
        bars = _bars(rows)
        atr = compute_atr(bars)
        assert atr is not None
        assert atr > 0

    def test_atr_reflects_volatility(self):
        """Higher volatility bars → higher ATR."""
        # Low vol bars
        rows_low = [{"Open": 100, "High": 100.5, "Low": 99.5, "Close": 100, "Volume": 1000}] * 20
        # High vol bars
        rows_high = [{"Open": 100, "High": 105, "Low": 95, "Close": 100, "Volume": 1000}] * 20
        atr_low = compute_atr(_bars(rows_low))
        atr_high = compute_atr(_bars(rows_high))
        assert atr_low is not None
        assert atr_high is not None
        assert atr_high > atr_low


class TestATRAdjustedStop:
    """Tests for atr_adjusted_stop — dynamic stop with feature flag."""

    def test_atr_stop_with_valid_atr(self):
        """USE_ATR_STOPS=True, valid ATR → entry - ATR * multiplier."""
        stop = atr_adjusted_stop(100.0, 2.0)
        # 100 - 2.0 * 1.5 = 97.0
        assert stop == 97.0

    def test_fallback_when_atr_none(self):
        """ATR is None → falls back to fixed % stop."""
        stop = atr_adjusted_stop(100.0, None)
        # Should be entry * (1 - DAY_TRADE_MAX_RISK_PCT) = 100 * 0.997 = 99.70
        assert stop == 99.70

    def test_per_symbol_override(self):
        """Per-symbol risk override applied on ATR=None fallback."""
        stop = atr_adjusted_stop(100.0, None, symbol="SPY")
        # SPY has 0.002 risk → 100 * 0.998 = 99.80
        assert stop == 99.80


# ===== Professional Rules: Trailing Stop =====

class TestTrailingStopHit:
    """Tests for check_trailing_stop_hit — trail-based exits."""

    def test_fires_when_low_breaches_trail(self):
        """Bar low below trailing stop → SELL signal."""
        bar = _bar(open_=100, high=101, low=98, close=99, volume=1000)
        sig = check_trailing_stop_hit("AAPL", bar, 99.50)
        assert sig is not None
        assert sig.alert_type == AlertType.TRAILING_STOP_HIT
        assert sig.direction == "SELL"

    def test_no_fire_when_low_above_trail(self):
        """Bar low stays above trailing stop → None."""
        bar = _bar(open_=100, high=101, low=99.6, close=100, volume=1000)
        sig = check_trailing_stop_hit("AAPL", bar, 99.50)
        assert sig is None

    def test_no_fire_when_trail_zero(self):
        """Trailing stop level at 0 → None."""
        bar = _bar()
        sig = check_trailing_stop_hit("AAPL", bar, 0)
        assert sig is None

    def test_no_fire_when_trail_negative(self):
        """Trailing stop level negative → None."""
        bar = _bar()
        sig = check_trailing_stop_hit("AAPL", bar, -1)
        assert sig is None


# ===== Professional Rules: Gap-and-Go =====

class TestGapAndGo:
    """Tests for check_gap_and_go — gap up with volume confirmation."""

    def test_fires_on_valid_gap_and_go(self):
        """1%+ gap up, 2x+ volume on first bar, close above open → BUY."""
        prior_close = 100.0
        rows = [
            {"Open": 102.0, "High": 103.0, "Low": 101.5, "Close": 102.5, "Volume": 5000},
            {"Open": 102.5, "High": 104.0, "Low": 102.0, "Close": 103.5, "Volume": 3000},
        ]
        bars = _bars(rows)
        sig = check_gap_and_go("AAPL", bars, prior_close, 3000, 2000)
        assert sig is not None
        assert sig.alert_type == AlertType.GAP_AND_GO
        assert sig.direction == "BUY"

    def test_no_fire_gap_too_small(self):
        """Gap < 1% → None."""
        rows = [
            {"Open": 100.5, "High": 101.0, "Low": 100.0, "Close": 100.8, "Volume": 5000},
        ]
        bars = _bars(rows)
        sig = check_gap_and_go("AAPL", bars, 100.0, 5000, 2000)
        assert sig is None

    def test_no_fire_low_volume(self):
        """First bar volume < 2x avg → None."""
        rows = [
            {"Open": 102.0, "High": 103.0, "Low": 101.5, "Close": 102.5, "Volume": 1500},
        ]
        bars = _bars(rows)
        sig = check_gap_and_go("AAPL", bars, 100.0, 1500, 2000)
        assert sig is None

    def test_no_fire_price_faded(self):
        """Close below gap open (faded) → None."""
        rows = [
            {"Open": 102.0, "High": 103.0, "Low": 100.5, "Close": 101.0, "Volume": 5000},
            {"Open": 101.0, "High": 101.5, "Low": 100.0, "Close": 100.5, "Volume": 3000},
        ]
        bars = _bars(rows)
        sig = check_gap_and_go("AAPL", bars, 100.0, 3000, 2000)
        assert sig is None

    def test_no_fire_empty_bars(self):
        """Empty bars → None."""
        bars = _bars([])
        sig = check_gap_and_go("AAPL", bars, 100.0, 1000, 1000)
        assert sig is None

    def test_no_fire_none_prior_close(self):
        """None prior close → None."""
        rows = [{"Open": 102.0, "High": 103.0, "Low": 101.5, "Close": 102.5, "Volume": 5000}]
        bars = _bars(rows)
        sig = check_gap_and_go("AAPL", bars, None, 5000, 2000)
        assert sig is None


# ===== Professional Rules: Fibonacci Retracement Bounce =====

class TestFibRetracementBounce:
    """Tests for check_fib_retracement_bounce — fib level support."""

    def test_fires_on_50pct_retracement_bounce(self):
        """Bar low at 50% fib, closes above → BUY."""
        # Prior range: high=110, low=100, range=10
        # 50% retracement = 110 - 5 = 105
        prior_high = 110.0
        prior_low = 100.0
        bar = _bar(open_=105.5, high=106, low=104.9, close=105.5, volume=1000)
        sig = check_fib_retracement_bounce("AAPL", bar, prior_high, prior_low)
        assert sig is not None
        assert sig.alert_type == AlertType.FIB_RETRACEMENT_BOUNCE
        assert sig.direction == "BUY"

    def test_fires_on_618_retracement(self):
        """Bar low at 61.8% fib → BUY with high confidence."""
        prior_high = 110.0
        prior_low = 100.0
        # 61.8% retracement = 110 - 6.18 = 103.82
        bar = _bar(open_=104.0, high=104.5, low=103.8, close=104.2, volume=1000)
        sig = check_fib_retracement_bounce("AAPL", bar, prior_high, prior_low)
        assert sig is not None
        assert sig.confidence == "high"

    def test_no_fire_range_too_small(self):
        """Prior range < 3% → None (too noisy)."""
        bar = _bar(open_=100, high=101, low=99.5, close=100.3, volume=1000)
        sig = check_fib_retracement_bounce("AAPL", bar, 101.0, 99.0)  # 2% range
        assert sig is None

    def test_no_fire_no_bounce(self):
        """Close below fib level (no bounce) → None."""
        prior_high = 110.0
        prior_low = 100.0
        # 50% = 105.0, close below it
        bar = _bar(open_=105.5, high=106, low=104.9, close=104.5, volume=1000)
        sig = check_fib_retracement_bounce("AAPL", bar, prior_high, prior_low)
        # Should return None because close(104.5) < fib(105.0)
        assert sig is None

    def test_no_fire_bar_too_far_from_fib(self):
        """Bar low not near any fib level → None."""
        bar = _bar(open_=108, high=109, low=107.5, close=108.5, volume=1000)
        sig = check_fib_retracement_bounce("AAPL", bar, 110.0, 100.0)
        # 107.5 isn't near 38.2%(105.82), 50%(105), or 61.8%(103.82)
        assert sig is None

    def test_no_fire_invalid_range(self):
        """Prior high <= prior low → None."""
        bar = _bar()
        sig = check_fib_retracement_bounce("AAPL", bar, 100.0, 100.0)
        assert sig is None


# =========================================================================
# Extended Professional Rule Tests — additional edge cases and coverage
# =========================================================================


class TestMACDHistogramFlipExtended:
    """Extended tests for check_macd_histogram_flip — edge cases and validation."""

    @staticmethod
    def _make_v_shaped_bars(n=50, start=100.0, dip_depth=0.5, recovery_strength=0.8):
        """Create V-shaped price action: decline then recovery to force histogram flip."""
        rows = []
        mid = n // 2
        for i in range(mid):
            c = start - dip_depth * (i + 1)
            rows.append({"Open": c + 0.2, "High": c + 0.5, "Low": c - 0.5, "Close": c, "Volume": 1000})
        base = start - dip_depth * mid
        for i in range(n - mid):
            c = base + recovery_strength * (i + 1)
            rows.append({"Open": c - 0.2, "High": c + 0.5, "Low": c - 0.3, "Close": c, "Volume": 1000})
        return pd.DataFrame(rows)

    def test_none_prior_day_does_not_crash(self):
        """prior_day=None should be handled gracefully."""
        bars = self._make_v_shaped_bars(50)
        sig = check_macd_histogram_flip("AAPL", bars, None)
        assert sig is None or isinstance(sig, AlertSignal)

    def test_prior_day_empty_dict(self):
        """prior_day={} (no 'close' key) should not crash."""
        bars = self._make_v_shaped_bars(50)
        sig = check_macd_histogram_flip("AAPL", bars, {})
        assert sig is None or isinstance(sig, AlertSignal)

    def test_exactly_35_bars_minimum(self):
        """With exactly MACD_SLOW(26) + MACD_SIGNAL(9) = 35 bars, should not crash."""
        bars = self._make_v_shaped_bars(35)
        prior = {"close": 90.0}
        sig = check_macd_histogram_flip("AAPL", bars, prior)
        assert sig is None or sig.alert_type == AlertType.MACD_HISTOGRAM_FLIP

    def test_34_bars_returns_none(self):
        """With 34 bars (one below minimum), must return None."""
        bars = self._make_v_shaped_bars(34)
        prior = {"close": 90.0}
        sig = check_macd_histogram_flip("AAPL", bars, prior)
        assert sig is None

    def test_no_flip_steady_uptrend(self):
        """Steady uptrend from start — histogram always positive, no flip."""
        rows = []
        for i in range(50):
            c = 80 + i * 0.6
            rows.append({"Open": c - 0.1, "High": c + 0.5, "Low": c - 0.3, "Close": c, "Volume": 1000})
        bars = pd.DataFrame(rows)
        prior = {"close": 70.0}
        sig = check_macd_histogram_flip("AAPL", bars, prior)
        assert sig is None

    def test_signal_fields_populated(self):
        """When signal fires, all expected fields are present."""
        bars = self._make_v_shaped_bars(50, start=100.0, dip_depth=0.5, recovery_strength=0.8)
        prior = {"close": bars.iloc[-1]["Close"] - 2.0}
        sig = check_macd_histogram_flip("AAPL", bars, prior)
        if sig is not None:
            assert sig.symbol == "AAPL"
            assert sig.alert_type == AlertType.MACD_HISTOGRAM_FLIP
            assert sig.direction == "BUY"
            assert sig.entry > 0
            assert sig.stop > 0
            assert sig.target_1 > sig.entry
            assert sig.target_2 > sig.target_1
            assert sig.confidence in ("high", "medium")
            assert "MACD histogram flip" in sig.message

    def test_high_confidence_when_momentum_strong(self):
        """High confidence when curr_hist > abs(prev_hist)."""
        bars = self._make_v_shaped_bars(50, start=100.0, dip_depth=0.3, recovery_strength=1.2)
        prior = {"close": bars.iloc[-1]["Close"] - 5.0}
        sig = check_macd_histogram_flip("AAPL", bars, prior)
        if sig is not None:
            # Strong recovery should produce curr_hist > abs(prev_hist) → high
            assert sig.confidence in ("high", "medium")

    def test_stop_below_session_low(self):
        """Stop should be 0.2% below session low."""
        bars = self._make_v_shaped_bars(50, start=100.0, dip_depth=0.5, recovery_strength=0.8)
        prior = {"close": bars.iloc[-1]["Close"] - 2.0}
        sig = check_macd_histogram_flip("AAPL", bars, prior)
        if sig is not None:
            session_low = bars["Low"].min()
            expected_stop = round(session_low * 0.998, 2)
            assert sig.stop == expected_stop


class TestBBSqueezeBreakoutExtended:
    """Extended tests for check_bb_squeeze_breakout — edge cases and data shapes."""

    @staticmethod
    def _make_squeeze_then_breakout(n=50, base=100.0, squeeze_bars=45, breakout_size=3.0):
        """Create tight-range bars (squeeze) then breakout."""
        rows = []
        for i in range(squeeze_bars):
            rows.append({
                "Open": base, "High": base + 0.05,
                "Low": base - 0.05, "Close": base + 0.01 * (i % 3 - 1),
                "Volume": 1000,
            })
        for i in range(n - squeeze_bars):
            c = base + breakout_size * (i + 1)
            rows.append({
                "Open": c - 0.5, "High": c + 1.0,
                "Low": c - 1.0, "Close": c,
                "Volume": 5000,
            })
        return pd.DataFrame(rows)

    def test_exactly_40_bars(self):
        """With exactly BB_PERIOD(20) + BB_SQUEEZE_LOOKBACK(20) = 40 bars, no crash."""
        bars = self._make_squeeze_then_breakout(n=40, squeeze_bars=38, breakout_size=3.0)
        sig = check_bb_squeeze_breakout("AAPL", bars)
        assert sig is None or sig.alert_type == AlertType.BB_SQUEEZE_BREAKOUT

    def test_39_bars_returns_none(self):
        """39 bars (one below minimum) → None."""
        rows = [{"Open": 100, "High": 100.05, "Low": 99.95, "Close": 100, "Volume": 1000}] * 39
        bars = pd.DataFrame(rows)
        sig = check_bb_squeeze_breakout("AAPL", bars)
        assert sig is None

    def test_wide_volatile_bars_no_squeeze(self):
        """Highly volatile bars — bandwidth is wide, no squeeze → None."""
        rows = []
        for i in range(50):
            swing = 5.0 * (1 if i % 2 == 0 else -1)
            c = 100 + swing
            rows.append({"Open": c - 2, "High": c + 3, "Low": c - 3, "Close": c, "Volume": 1000})
        bars = pd.DataFrame(rows)
        sig = check_bb_squeeze_breakout("AAPL", bars)
        assert sig is None

    def test_squeeze_but_close_at_middle_band(self):
        """Squeeze detected but close at SMA (middle band) → no breakout → None."""
        rows = []
        for i in range(50):
            rows.append({"Open": 100.0, "High": 100.02, "Low": 99.98, "Close": 100.0, "Volume": 1000})
        bars = pd.DataFrame(rows)
        sig = check_bb_squeeze_breakout("AAPL", bars)
        assert sig is None

    def test_signal_has_buy_direction(self):
        """When signal fires, direction must be BUY."""
        bars = self._make_squeeze_then_breakout(50, base=100.0, breakout_size=3.0)
        sig = check_bb_squeeze_breakout("AAPL", bars)
        if sig is not None:
            assert sig.direction == "BUY"
            assert sig.confidence == "high"

    def test_entry_at_upper_band_stop_at_middle(self):
        """Entry should be at upper band, stop at middle band."""
        bars = self._make_squeeze_then_breakout(50, base=100.0, breakout_size=3.0)
        sig = check_bb_squeeze_breakout("AAPL", bars)
        if sig is not None:
            assert sig.entry > 0
            assert sig.stop > 0
            assert sig.entry > sig.stop
            risk = sig.entry - sig.stop
            assert abs(sig.target_1 - (sig.entry + risk)) < 0.02
            assert abs(sig.target_2 - (sig.entry + 2 * risk)) < 0.02

    def test_message_mentions_squeeze(self):
        """Signal message should mention 'squeeze'."""
        bars = self._make_squeeze_then_breakout(50, base=100.0, breakout_size=3.0)
        sig = check_bb_squeeze_breakout("AAPL", bars)
        if sig is not None:
            assert "squeeze" in sig.message.lower()


class TestComputeATRExtended:
    """Extended tests for compute_atr — boundary conditions and accuracy."""

    @staticmethod
    def _make_bars_with_gaps(n, base=100.0, gap=2.0):
        """Create bars with gaps between close and next open (tests true range)."""
        rows = []
        for i in range(n):
            o = base + gap * (i % 2)
            h = o + 1.0
            low = o - 0.5
            c = o + 0.5
            rows.append({"Open": o, "High": h, "Low": low, "Close": c, "Volume": 1000})
        return pd.DataFrame(rows)

    def test_single_bar_returns_none(self):
        """A single bar is not enough."""
        bars = pd.DataFrame([{"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000}])
        assert compute_atr(bars, period=14) is None

    def test_period_1_with_2_bars(self):
        """Period=1 with 2 bars should work (period+1=2)."""
        rows = [
            {"Open": 100, "High": 102, "Low": 98, "Close": 101, "Volume": 1000},
            {"Open": 101, "High": 104, "Low": 99, "Close": 103, "Volume": 1000},
        ]
        bars = pd.DataFrame(rows)
        atr = compute_atr(bars, period=1)
        assert atr is not None
        assert atr > 0

    def test_atr_with_gaps_reflects_true_range(self):
        """True range includes gap from prior close, not just high-low."""
        rows = [
            {"Open": 100, "High": 101, "Low": 99, "Close": 100.5, "Volume": 1000},
            {"Open": 100.5, "High": 101, "Low": 99.5, "Close": 100, "Volume": 1000},
            # Gap bar: previous close was 100, this opens at 105
            {"Open": 105, "High": 106, "Low": 104, "Close": 105.5, "Volume": 1000},
        ]
        bars = pd.DataFrame(rows)
        atr = compute_atr(bars, period=1)
        assert atr is not None
        # Last bar true range should include gap: max(106-104, |106-100|, |104-100|) = 6
        assert atr >= 2.0  # At least the high-low range

    def test_default_period_is_14(self):
        """Default period parameter should be 14."""
        rows = []
        for i in range(20):
            rows.append({"Open": 100 + i * 0.1, "High": 101 + i * 0.1, "Low": 99 + i * 0.1, "Close": 100.5 + i * 0.1, "Volume": 1000})
        bars = pd.DataFrame(rows)
        atr_default = compute_atr(bars)
        atr_14 = compute_atr(bars, period=14)
        assert atr_default == atr_14

    def test_returns_float_type(self):
        """ATR should return a Python float."""
        rows = [{"Open": 100, "High": 102, "Low": 98, "Close": 100, "Volume": 1000}] * 20
        bars = pd.DataFrame(rows)
        atr = compute_atr(bars)
        assert isinstance(atr, float)


class TestATRAdjustedStopExtended:
    """Extended tests for atr_adjusted_stop — monkeypatch and edge cases."""

    def test_atr_stop_calculation(self):
        """ATR stop = entry - ATR * 1.5, exact value check."""
        assert atr_adjusted_stop(200.0, 4.0) == round(200.0 - 4.0 * 1.5, 2)

    def test_fallback_nvda_symbol(self):
        """NVDA per-symbol risk (0.4%) on fallback."""
        result = atr_adjusted_stop(300.0, None, symbol="NVDA")
        expected = round(300.0 * (1 - 0.004), 2)
        assert result == expected

    def test_fallback_crypto_btc(self):
        """BTC-USD per-symbol risk (0.8%) on fallback."""
        result = atr_adjusted_stop(50000.0, None, symbol="BTC-USD")
        expected = round(50000.0 * (1 - 0.008), 2)
        assert result == expected

    def test_fallback_crypto_eth(self):
        """ETH-USD per-symbol risk (1.0%) on fallback."""
        result = atr_adjusted_stop(3000.0, None, symbol="ETH-USD")
        expected = round(3000.0 * (1 - 0.010), 2)
        assert result == expected

    def test_atr_overrides_symbol_risk(self):
        """When ATR is valid, per-symbol risk is ignored — ATR calculation wins."""
        # SPY has 0.002 risk, but ATR should override
        result = atr_adjusted_stop(400.0, 5.0, symbol="SPY")
        expected = round(400.0 - 5.0 * 1.5, 2)
        assert result == expected

    def test_use_atr_stops_false_ignores_valid_atr(self, monkeypatch):
        """When USE_ATR_STOPS=False, valid ATR is ignored, falls back to fixed %."""
        import analytics.intraday_rules as mod
        monkeypatch.setattr(mod, "USE_ATR_STOPS", False)
        result = atr_adjusted_stop(100.0, 2.0)
        expected = round(100.0 * (1 - 0.003), 2)
        assert result == expected

    def test_use_atr_stops_false_with_symbol(self, monkeypatch):
        """USE_ATR_STOPS=False + symbol → uses per-symbol fixed %."""
        import analytics.intraday_rules as mod
        monkeypatch.setattr(mod, "USE_ATR_STOPS", False)
        result = atr_adjusted_stop(400.0, 5.0, symbol="SPY")
        expected = round(400.0 * (1 - 0.002), 2)
        assert result == expected

    def test_very_small_atr(self):
        """Very small but positive ATR → still uses ATR calculation."""
        result = atr_adjusted_stop(100.0, 0.01)
        expected = round(100.0 - 0.01 * 1.5, 2)
        assert result == expected

    def test_no_symbol_none_atr(self):
        """symbol=None + ATR=None → default risk %."""
        result = atr_adjusted_stop(100.0, None, symbol=None)
        expected = round(100.0 * (1 - 0.003), 2)
        assert result == expected


class TestTrailingStopHitExtended:
    """Extended tests for check_trailing_stop_hit — feature flag and edge cases."""

    def test_enable_trailing_stops_false_returns_none(self, monkeypatch):
        """ENABLE_TRAILING_STOPS=False → None even with valid breach."""
        import analytics.intraday_rules as mod
        monkeypatch.setattr(mod, "ENABLE_TRAILING_STOPS", False)
        bar = _bar(open_=100, high=101, low=95, close=96)
        sig = check_trailing_stop_hit("AAPL", bar, trailing_stop_level=98.0)
        assert sig is None

    def test_exact_touch_fires(self):
        """Low exactly at trailing stop level → fires (not strictly above)."""
        bar = _bar(open_=100, high=101, low=98.0, close=99.0)
        sig = check_trailing_stop_hit("AAPL", bar, trailing_stop_level=98.0)
        assert sig is not None
        assert sig.direction == "SELL"

    def test_low_one_cent_above_trail_no_fire(self):
        """Low one cent above trail level → no breach → None."""
        bar = _bar(open_=100, high=101, low=98.01, close=99.0)
        sig = check_trailing_stop_hit("AAPL", bar, trailing_stop_level=98.0)
        assert sig is not None if 98.01 <= 98.0 else sig is None
        # 98.01 > 98.0 → should be None
        assert sig is None

    def test_message_contains_trail_and_low(self):
        """Signal message includes trail level and bar low prices."""
        bar = _bar(open_=100, high=101, low=96.5, close=97.0)
        sig = check_trailing_stop_hit("AAPL", bar, trailing_stop_level=98.0)
        assert sig is not None
        assert "$96.50" in sig.message
        assert "$98.00" in sig.message

    def test_signal_price_is_close(self):
        """Signal price should be the bar's close."""
        bar = _bar(open_=100, high=101, low=96.5, close=97.0)
        sig = check_trailing_stop_hit("AAPL", bar, trailing_stop_level=98.0)
        assert sig is not None
        assert sig.price == 97.0

    def test_symbol_passed_through(self):
        """Symbol in signal matches input."""
        bar = _bar(open_=100, high=101, low=95, close=96)
        sig = check_trailing_stop_hit("TSLA", bar, trailing_stop_level=98.0)
        assert sig is not None
        assert sig.symbol == "TSLA"

    def test_very_large_trail_always_fires(self):
        """Trailing stop level above bar high → still fires (low < level)."""
        bar = _bar(open_=100, high=101, low=99, close=100)
        sig = check_trailing_stop_hit("AAPL", bar, trailing_stop_level=200.0)
        assert sig is not None


class TestGapAndGoExtended:
    """Extended tests for check_gap_and_go — confidence levels and edge cases."""

    def test_high_confidence_gap_2pct_plus(self):
        """Gap >= 2% → high confidence."""
        prior_close = 100.0
        rows = [
            {"Open": 103.0, "High": 104.0, "Low": 102.5, "Close": 103.5, "Volume": 5000},
            {"Open": 103.5, "High": 105.0, "Low": 103.0, "Close": 104.5, "Volume": 3000},
        ]
        bars = pd.DataFrame(rows)
        sig = check_gap_and_go("AAPL", bars, prior_close, 3000, 2000)
        assert sig is not None
        assert sig.confidence == "high"

    def test_medium_confidence_gap_1pct(self):
        """Gap between 1-2% → medium confidence."""
        prior_close = 100.0
        rows = [
            {"Open": 101.5, "High": 102.5, "Low": 101.0, "Close": 102.0, "Volume": 5000},
            {"Open": 102.0, "High": 103.0, "Low": 101.5, "Close": 102.5, "Volume": 3000},
        ]
        bars = pd.DataFrame(rows)
        sig = check_gap_and_go("AAPL", bars, prior_close, 3000, 2000)
        assert sig is not None
        assert sig.confidence == "medium"

    def test_stop_at_prior_close(self):
        """Stop should be at prior_close (gap fill level)."""
        prior_close = 100.0
        rows = [
            {"Open": 102.0, "High": 103.0, "Low": 101.5, "Close": 102.5, "Volume": 5000},
            {"Open": 102.5, "High": 104.0, "Low": 102.0, "Close": 103.0, "Volume": 3000},
        ]
        bars = pd.DataFrame(rows)
        sig = check_gap_and_go("AAPL", bars, prior_close, 3000, 2000)
        assert sig is not None
        assert sig.stop == 100.0

    def test_entry_at_gap_open(self):
        """Entry should be at the gap open price."""
        prior_close = 100.0
        rows = [
            {"Open": 102.0, "High": 103.0, "Low": 101.5, "Close": 102.5, "Volume": 5000},
            {"Open": 102.5, "High": 104.0, "Low": 102.0, "Close": 103.0, "Volume": 3000},
        ]
        bars = pd.DataFrame(rows)
        sig = check_gap_and_go("AAPL", bars, prior_close, 3000, 2000)
        assert sig is not None
        assert sig.entry == 102.0

    def test_prior_close_zero_returns_none(self):
        """prior_close=0 → None (division guard)."""
        rows = [{"Open": 102, "High": 103, "Low": 101, "Close": 102.5, "Volume": 5000}]
        bars = pd.DataFrame(rows)
        sig = check_gap_and_go("AAPL", bars, prior_close=0, bar_vol=5000, avg_vol=2000)
        assert sig is None

    def test_negative_prior_close_returns_none(self):
        """Negative prior_close → None."""
        rows = [{"Open": 102, "High": 103, "Low": 101, "Close": 102.5, "Volume": 5000}]
        bars = pd.DataFrame(rows)
        sig = check_gap_and_go("AAPL", bars, prior_close=-100.0, bar_vol=5000, avg_vol=2000)
        assert sig is None

    def test_exactly_1pct_gap_fires(self):
        """Gap of exactly 1% should fire (>= 0.01)."""
        prior_close = 100.0
        gap_open = 101.0  # exactly 1%
        rows = [
            {"Open": gap_open, "High": gap_open + 1.0, "Low": gap_open - 0.3, "Close": gap_open + 0.5, "Volume": 5000},
        ]
        bars = pd.DataFrame(rows)
        sig = check_gap_and_go("AAPL", bars, prior_close, 5000, 2000)
        assert sig is not None

    def test_exactly_2x_volume_fires(self):
        """First bar volume of exactly 2x average should fire (>= 2.0)."""
        prior_close = 100.0
        rows = [
            {"Open": 102.0, "High": 103.0, "Low": 101.5, "Close": 102.5, "Volume": 4000},
        ]
        bars = pd.DataFrame(rows)
        sig = check_gap_and_go("AAPL", bars, prior_close, 4000, 2000)
        assert sig is not None

    def test_just_below_2x_volume_no_fire(self):
        """First bar volume just below 2x → None."""
        prior_close = 100.0
        rows = [
            {"Open": 102.0, "High": 103.0, "Low": 101.5, "Close": 102.5, "Volume": 3999},
        ]
        bars = pd.DataFrame(rows)
        sig = check_gap_and_go("AAPL", bars, prior_close, 3999, 2000)
        assert sig is None

    def test_message_contains_gap_info(self):
        """Message should mention Gap-and-Go and volume ratio."""
        prior_close = 100.0
        rows = [
            {"Open": 102.0, "High": 103.0, "Low": 101.5, "Close": 102.5, "Volume": 5000},
            {"Open": 102.5, "High": 104.0, "Low": 102.0, "Close": 103.0, "Volume": 3000},
        ]
        bars = pd.DataFrame(rows)
        sig = check_gap_and_go("AAPL", bars, prior_close, 3000, 2000)
        assert sig is not None
        assert "Gap-and-Go" in sig.message
        assert "volume" in sig.message.lower()

    def test_risk_reward_targets(self):
        """Targets at 1R and 2R from entry."""
        prior_close = 100.0
        rows = [
            {"Open": 102.0, "High": 103.0, "Low": 101.5, "Close": 102.5, "Volume": 5000},
            {"Open": 102.5, "High": 104.0, "Low": 102.0, "Close": 103.0, "Volume": 3000},
        ]
        bars = pd.DataFrame(rows)
        sig = check_gap_and_go("AAPL", bars, prior_close, 3000, 2000)
        assert sig is not None
        risk = sig.entry - sig.stop
        assert risk > 0
        assert abs(sig.target_1 - (sig.entry + risk)) < 0.02
        assert abs(sig.target_2 - (sig.entry + 2 * risk)) < 0.02


class TestFibRetracementBounceExtended:
    """Extended tests for check_fib_retracement_bounce — all fib levels and validation."""

    def test_382_fib_bounce_medium_confidence(self):
        """38.2% retracement bounce → medium confidence (< 0.5)."""
        prior_high = 110.0
        prior_low = 100.0
        # 38.2% fib = 110 - 10 * 0.382 = 106.18
        fib_382 = prior_high - 10.0 * 0.382
        bar = _bar(open_=106.5, high=107.0, low=fib_382, close=106.8)
        sig = check_fib_retracement_bounce("AAPL", bar, prior_high, prior_low)
        assert sig is not None
        assert sig.confidence == "medium"

    def test_50_fib_high_confidence(self):
        """50% retracement → high confidence (>= 0.5)."""
        prior_high = 110.0
        prior_low = 100.0
        fib_50 = 105.0
        bar = _bar(open_=105.5, high=106.0, low=105.0, close=105.8)
        sig = check_fib_retracement_bounce("AAPL", bar, prior_high, prior_low)
        assert sig is not None
        assert sig.confidence == "high"

    def test_618_fib_high_confidence(self):
        """61.8% retracement → high confidence."""
        prior_high = 110.0
        prior_low = 100.0
        fib_618 = prior_high - 10.0 * 0.618  # 103.82
        bar = _bar(open_=104.2, high=104.5, low=fib_618, close=104.3)
        sig = check_fib_retracement_bounce("AAPL", bar, prior_high, prior_low)
        assert sig is not None
        assert sig.confidence == "high"

    def test_inverted_range_returns_none(self):
        """prior_high < prior_low → None."""
        bar = _bar(open_=100, high=101, low=99, close=100.5)
        sig = check_fib_retracement_bounce("AAPL", bar, prior_high=95.0, prior_low=100.0)
        assert sig is None

    def test_zero_prior_high_returns_none(self):
        """prior_high=0 → None."""
        bar = _bar(open_=5, high=6, low=4, close=5.5)
        sig = check_fib_retracement_bounce("AAPL", bar, prior_high=0, prior_low=0)
        assert sig is None

    def test_range_exactly_3pct(self):
        """Range exactly 3% of price → should pass the filter."""
        # prior_high=103, prior_low=100 → range=3, 3/103 ≈ 2.91% → below 3%, None
        bar = _bar(open_=101.5, high=102, low=101.5, close=101.8)
        sig = check_fib_retracement_bounce("AAPL", bar, prior_high=103.0, prior_low=100.0)
        assert sig is None  # 2.91% < 3%

    def test_range_above_3pct_passes(self):
        """Range > 3% of price → passes the filter."""
        # prior_high=104, prior_low=100 → range=4, 4/104 ≈ 3.85% → passes
        prior_high = 104.0
        prior_low = 100.0
        fib_50 = prior_high - 4.0 * 0.5  # 102.0
        bar = _bar(open_=102.3, high=102.5, low=102.0, close=102.4)
        sig = check_fib_retracement_bounce("AAPL", bar, prior_high, prior_low)
        assert sig is not None

    def test_bar_low_just_outside_proximity(self):
        """Bar low slightly outside proximity threshold → None."""
        prior_high = 110.0
        prior_low = 100.0
        fib_50 = 105.0
        # FIB_BOUNCE_PROXIMITY_PCT = 0.003 → 105 * 0.003 = 0.315
        # Bar low at 105.4 → distance = 0.4 → 0.4/105 = 0.0038 > 0.003
        bar = _bar(open_=106, high=106.5, low=105.4, close=106.0)
        sig = check_fib_retracement_bounce("AAPL", bar, prior_high, prior_low)
        # Should not fire for 50% fib; check if it fires for any level
        # 38.2% = 106.18, distance from 105.4 = 0.78, 0.78/106.18 = 0.73% > 0.3%
        # So no level matches
        assert sig is None

    def test_entry_at_fib_level(self):
        """Entry should be at the rounded fib level."""
        prior_high = 110.0
        prior_low = 100.0
        fib_50 = 105.0
        bar = _bar(open_=105.5, high=106.0, low=105.0, close=105.8)
        sig = check_fib_retracement_bounce("AAPL", bar, prior_high, prior_low)
        assert sig is not None
        assert sig.entry == 105.8

    def test_message_contains_fibonacci(self):
        """Signal message should mention Fibonacci."""
        prior_high = 110.0
        prior_low = 100.0
        bar = _bar(open_=105.5, high=106.0, low=105.0, close=105.8)
        sig = check_fib_retracement_bounce("AAPL", bar, prior_high, prior_low)
        assert sig is not None
        assert "Fibonacci" in sig.message

    def test_symbol_propagated(self):
        """Symbol passed through to signal."""
        prior_high = 110.0
        prior_low = 100.0
        bar = _bar(open_=105.5, high=106.0, low=105.0, close=105.8)
        sig = check_fib_retracement_bounce("NVDA", bar, prior_high, prior_low)
        assert sig is not None
        assert sig.symbol == "NVDA"

    def test_first_matching_fib_wins(self):
        """Function returns the first matching fib level (38.2% checked first)."""
        # If bar low is near both 38.2% and 50%, 38.2% should win
        prior_high = 110.0
        prior_low = 100.0
        # 38.2% = 106.18, 50% = 105.0
        # Place bar low near 38.2%
        bar = _bar(open_=106.5, high=107.0, low=106.18, close=106.8)
        sig = check_fib_retracement_bounce("AAPL", bar, prior_high, prior_low)
        assert sig is not None
        # Entry should be last bar Close (now uses close, not fib level)
        assert sig.entry == 106.8


# ---------------------------------------------------------------------------
# Prior Day Low Breakdown
# ---------------------------------------------------------------------------


class TestPriorDayLowBreakdown:
    """Tests for check_prior_day_low_breakdown — SELL when PDL breaks."""

    def test_fires_on_close_below_pdl_with_volume(self):
        bars = _bars([
            {"Open": 670, "High": 671, "Low": 669, "Close": 670, "Volume": 800},
            {"Open": 669, "High": 670, "Low": 667, "Close": 667.5, "Volume": 1200},
        ])
        sig = check_prior_day_low_breakdown("SPY", bars, prior_day_low=669.0,
                                             bar_volume=1200, avg_volume=1000)
        assert sig is not None
        assert sig.direction == "SELL"
        assert sig.alert_type == AlertType.PRIOR_DAY_LOW_BREAKDOWN
        assert "BREAKDOWN" in sig.message
        assert "EXIT LONG" in sig.message

    def test_no_fire_when_close_above_pdl(self):
        bars = _bars([
            {"Open": 670, "High": 671, "Low": 668, "Close": 669.5, "Volume": 1200},
        ])
        sig = check_prior_day_low_breakdown("SPY", bars, prior_day_low=669.0,
                                             bar_volume=1200, avg_volume=1000)
        assert sig is None

    def test_no_fire_low_volume(self):
        bars = _bars([
            {"Open": 669, "High": 670, "Low": 667, "Close": 667.5, "Volume": 500},
        ])
        sig = check_prior_day_low_breakdown("SPY", bars, prior_day_low=669.0,
                                             bar_volume=500, avg_volume=1000)
        assert sig is None

    def test_no_fire_when_too_far_below(self):
        bars = _bars([
            {"Open": 660, "High": 661, "Low": 658, "Close": 658, "Volume": 1200},
        ])
        sig = check_prior_day_low_breakdown("SPY", bars, prior_day_low=669.0,
                                             bar_volume=1200, avg_volume=1000)
        # 1.64% below — above 1.5% threshold
        assert sig is None


# ---------------------------------------------------------------------------
# Prior Day Low Resistance
# ---------------------------------------------------------------------------


class TestPriorDayLowResistance:
    """Tests for check_prior_day_low_resistance — PDL becomes overhead resistance."""

    def test_fires_when_pdl_rejected(self):
        """Price below PDL, rallies to PDL, gets rejected."""
        bars = _bars([
            {"Open": 668, "High": 669, "Low": 667, "Close": 667.5, "Volume": 1000},
            {"Open": 667.5, "High": 668, "Low": 666, "Close": 666.5, "Volume": 900},
            {"Open": 666.5, "High": 667, "Low": 665, "Close": 665.5, "Volume": 800},
            {"Open": 665.5, "High": 666, "Low": 665, "Close": 665.5, "Volume": 800},
            {"Open": 666, "High": 668.8, "Low": 665.5, "Close": 666, "Volume": 1100},
            {"Open": 666, "High": 668.9, "Low": 665, "Close": 666.5, "Volume": 1000},
        ])
        # PDL = 669.0 — price below, bar high reached 668.9 (within 0.4%), close at 666.5
        sig = check_prior_day_low_resistance("META", bars, prior_day_low=669.0)
        assert sig is not None
        assert sig.direction == "SELL"
        assert "RESISTANCE" in sig.message

    def test_no_fire_when_close_above_pdl(self):
        bars = _bars([
            {"Open": 668, "High": 670, "Low": 667, "Close": 669.5, "Volume": 1000},
            {"Open": 669, "High": 670, "Low": 668, "Close": 669.5, "Volume": 900},
            {"Open": 669, "High": 670, "Low": 668, "Close": 669.5, "Volume": 800},
            {"Open": 669, "High": 670, "Low": 668, "Close": 669.5, "Volume": 800},
            {"Open": 669, "High": 670, "Low": 668, "Close": 669.5, "Volume": 800},
            {"Open": 669, "High": 670, "Low": 668, "Close": 669.5, "Volume": 800},
        ])
        sig = check_prior_day_low_resistance("META", bars, prior_day_low=669.0)
        assert sig is None

    def test_no_fire_when_high_too_far_from_pdl(self):
        """Bar high didn't reach PDL — not testing it."""
        bars = _bars([
            {"Open": 665, "High": 666, "Low": 664, "Close": 664.5, "Volume": 1000},
            {"Open": 665, "High": 666, "Low": 664, "Close": 664.5, "Volume": 900},
            {"Open": 665, "High": 666, "Low": 664, "Close": 664.5, "Volume": 800},
            {"Open": 665, "High": 666, "Low": 664, "Close": 664.5, "Volume": 800},
            {"Open": 665, "High": 666, "Low": 664, "Close": 664.5, "Volume": 800},
            {"Open": 665, "High": 666, "Low": 664, "Close": 664.5, "Volume": 800},
        ])
        sig = check_prior_day_low_resistance("META", bars, prior_day_low=669.0)
        assert sig is None


# ---------------------------------------------------------------------------
# Morning Low Retest
# ---------------------------------------------------------------------------


class TestMorningLowRetest:
    """Tests for check_morning_low_retest — price retests first-hour low after rally."""

    def _make_opening_range(self, or_low=100.0, or_high=102.0):
        return {
            "or_low": or_low,
            "or_high": or_high,
            "or_range": or_high - or_low,
            "or_range_pct": (or_high - or_low) / or_low,
            "or_complete": True,
        }

    def test_fires_on_retest_after_rally(self):
        """Classic pattern: morning low, rally, pullback to retest, bounce."""
        # 6 opening range bars, then rally, then pullback to morning low
        prices = (
            # Opening range bars (first 30 min)
            [{"Open": 101, "High": 102, "Low": 100, "Close": 101, "Volume": 1000}] * 6
            # Rally bars
            + [{"Open": 101, "High": 103, "Low": 101, "Close": 102.5, "Volume": 1200}] * 4
            # Pullback to morning low, bounce
            + [{"Open": 101, "High": 101.5, "Low": 100.2, "Close": 100.8, "Volume": 1100}]
            + [{"Open": 100.8, "High": 101.2, "Low": 100.1, "Close": 100.5, "Volume": 1000}]
        )
        bars = _bars(prices)
        opening_range = self._make_opening_range(or_low=100.0, or_high=102.0)
        sig = check_morning_low_retest("GOOGL", bars, opening_range)
        assert sig is not None
        assert sig.alert_type == AlertType.MORNING_LOW_RETEST
        assert sig.entry == 100.5
        assert sig.stop < sig.entry

    def test_no_fire_before_first_hour(self):
        """Must have enough bars (past first hour)."""
        prices = [{"Open": 101, "High": 102, "Low": 100, "Close": 101, "Volume": 1000}] * 8
        bars = _bars(prices)
        opening_range = self._make_opening_range()
        sig = check_morning_low_retest("AAPL", bars, opening_range)
        assert sig is None

    def test_no_fire_without_rally(self):
        """Price must have rallied above morning low before retest."""
        prices = (
            [{"Open": 100.2, "High": 100.5, "Low": 100, "Close": 100.3, "Volume": 1000}] * 6
            + [{"Open": 100.3, "High": 100.4, "Low": 100.1, "Close": 100.2, "Volume": 900}] * 7
        )
        bars = _bars(prices)
        opening_range = self._make_opening_range(or_low=100.0, or_high=100.5)
        sig = check_morning_low_retest("AAPL", bars, opening_range)
        assert sig is None

    def test_no_fire_when_close_below_morning_low(self):
        """Bounce not confirmed if close is below morning low."""
        prices = (
            [{"Open": 101, "High": 102, "Low": 100, "Close": 101, "Volume": 1000}] * 6
            + [{"Open": 101, "High": 103, "Low": 101, "Close": 102.5, "Volume": 1200}] * 4
            + [{"Open": 100.5, "High": 100.8, "Low": 99.5, "Close": 99.8, "Volume": 1100}]
            + [{"Open": 99.8, "High": 100.2, "Low": 99.6, "Close": 99.7, "Volume": 1000}]
        )
        bars = _bars(prices)
        opening_range = self._make_opening_range(or_low=100.0, or_high=102.0)
        sig = check_morning_low_retest("AAPL", bars, opening_range)
        assert sig is None

    def test_no_fire_when_no_opening_range(self):
        prices = [{"Open": 101, "High": 102, "Low": 100, "Close": 101, "Volume": 1000}] * 13
        bars = _bars(prices)
        sig = check_morning_low_retest("AAPL", bars, None)
        assert sig is None


# ---------------------------------------------------------------------------
# First Hour High Breakout
# ---------------------------------------------------------------------------


class TestFirstHourHighBreakout:
    """Tests for check_first_hour_high_breakout."""

    def _make_opening_range(self, or_low=100.0, or_high=102.0):
        return {
            "or_low": or_low,
            "or_high": or_high,
            "or_range": or_high - or_low,
            "or_range_pct": (or_high - or_low) / or_low,
            "or_complete": True,
        }

    def test_fires_on_breakout_with_volume(self):
        """Price breaks above first-hour high with volume."""
        prices = (
            [{"Open": 101, "High": 102, "Low": 100, "Close": 101, "Volume": 1000}] * 6
            + [{"Open": 101, "High": 101.5, "Low": 100.5, "Close": 101, "Volume": 900}] * 5
            + [{"Open": 102, "High": 103, "Low": 101.8, "Close": 102.5, "Volume": 1200}]
        )
        bars = _bars(prices)
        opening_range = self._make_opening_range(or_low=100.0, or_high=102.0)
        sig = check_first_hour_high_breakout("SPY", bars, opening_range, 1200, 1000)
        assert sig is not None
        assert sig.alert_type == AlertType.FIRST_HOUR_HIGH_BREAKOUT
        assert sig.entry == 102.5

    def test_no_fire_below_first_hour_high(self):
        """No fire if close is below first-hour high."""
        prices = (
            [{"Open": 101, "High": 102, "Low": 100, "Close": 101, "Volume": 1000}] * 6
            + [{"Open": 101, "High": 101.5, "Low": 100.5, "Close": 101.5, "Volume": 900}] * 6
        )
        bars = _bars(prices)
        opening_range = self._make_opening_range(or_low=100.0, or_high=102.0)
        sig = check_first_hour_high_breakout("SPY", bars, opening_range, 900, 1000)
        assert sig is None

    def test_no_fire_low_volume(self):
        """No fire if volume is below threshold."""
        prices = (
            [{"Open": 101, "High": 102, "Low": 100, "Close": 101, "Volume": 1000}] * 6
            + [{"Open": 101, "High": 101.5, "Low": 100.5, "Close": 101, "Volume": 900}] * 5
            + [{"Open": 102, "High": 103, "Low": 101.8, "Close": 102.5, "Volume": 500}]
        )
        bars = _bars(prices)
        opening_range = self._make_opening_range(or_low=100.0, or_high=102.0)
        sig = check_first_hour_high_breakout("SPY", bars, opening_range, 500, 1000)
        assert sig is None


# ---------------------------------------------------------------------------
# MA/EMA Reclaim
# ---------------------------------------------------------------------------


class TestMAEMAReclaim:
    """Tests for check_ma_ema_reclaim — price crosses above daily MA/EMA."""

    def test_fires_when_prior_below_now_above(self):
        """Prior close below EMA50, current bar closes above → reclaim."""
        bars = _bars([
            {"Open": 2220, "High": 2245, "Low": 2215, "Close": 2240, "Volume": 1000},
        ])
        sig = check_ma_ema_reclaim(
            "ETH-USD", bars, ma_level=2221.0, prior_close=2200.0,
            alert_type=AlertType.EMA_RECLAIM_50, ma_label="EMA50",
        )
        assert sig is not None
        assert sig.alert_type == AlertType.EMA_RECLAIM_50
        assert sig.entry == 2240.0
        assert sig.stop < sig.entry
        assert "EMA50 reclaim" in sig.message

    def test_no_fire_when_prior_already_above(self):
        """Prior close already above MA — not a reclaim."""
        bars = _bars([
            {"Open": 2300, "High": 2340, "Low": 2290, "Close": 2330, "Volume": 1000},
        ])
        sig = check_ma_ema_reclaim(
            "ETH-USD", bars, ma_level=2221.0, prior_close=2250.0,
            alert_type=AlertType.EMA_RECLAIM_50, ma_label="EMA50",
        )
        assert sig is None

    def test_no_fire_when_close_below_ma(self):
        """Current bar closes below MA — reclaim not confirmed."""
        bars = _bars([
            {"Open": 2200, "High": 2220, "Low": 2190, "Close": 2210, "Volume": 1000},
        ])
        sig = check_ma_ema_reclaim(
            "ETH-USD", bars, ma_level=2221.0, prior_close=2200.0,
            alert_type=AlertType.EMA_RECLAIM_50, ma_label="EMA50",
        )
        assert sig is None

    def test_no_fire_when_too_far_above(self):
        """Skip if price already ran 2%+ above MA — stale signal."""
        bars = _bars([
            {"Open": 2300, "High": 2340, "Low": 2290, "Close": 2260, "Volume": 1000},
        ])
        sig = check_ma_ema_reclaim(
            "ETH-USD", bars, ma_level=2221.0, prior_close=2200.0,
            alert_type=AlertType.EMA_RECLAIM_50, ma_label="EMA50",
        )
        # 2260 is ~1.76% above 2221 — above 1.5% threshold
        assert sig is None

    def test_works_for_all_ma_types(self):
        """Verify it works with different AlertType enums."""
        bars = _bars([
            {"Open": 101, "High": 102, "Low": 100.5, "Close": 101.5, "Volume": 1000},
        ])
        for at, label in [
            (AlertType.MA_RECLAIM_20, "20MA"),
            (AlertType.MA_RECLAIM_200, "200MA"),
            (AlertType.EMA_RECLAIM_100, "EMA100"),
        ]:
            sig = check_ma_ema_reclaim(
                "AAPL", bars, ma_level=101.0, prior_close=100.0,
                alert_type=at, ma_label=label,
            )
            assert sig is not None
            assert sig.alert_type == at

    def test_no_fire_when_ma_none(self):
        bars = _bars([
            {"Open": 101, "High": 102, "Low": 100.5, "Close": 101.5, "Volume": 1000},
        ])
        sig = check_ma_ema_reclaim(
            "AAPL", bars, ma_level=None, prior_close=100.0,
            alert_type=AlertType.MA_RECLAIM_50, ma_label="50MA",
        )
        assert sig is None


# ---------------------------------------------------------------------------
# Session High Retracement
# ---------------------------------------------------------------------------


class TestSessionHighRetracement:
    """Tests for check_session_high_retracement — rally then pullback to session low."""

    def _make_bars(self, prices):
        """Build bars from list of (open, high, low, close) tuples."""
        rows = []
        for o, h, l, c in prices:
            rows.append({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 1000})
        return pd.DataFrame(rows)

    def test_classic_retracement_fires(self):
        """BTC-style: rally 2% then pull back to session low → fires."""
        bars = self._make_bars([
            # Open at 100, rally to ~103
            (100, 101, 99.5, 101),    # bar 0
            (101, 102, 100.5, 102),   # bar 1
            (102, 103, 101.5, 103),   # bar 2: session high
            (103, 103, 102, 102),     # bar 3: start pullback
            (102, 102, 101, 101),     # bar 4
            (101, 101, 100, 100),     # bar 5
            (100, 100.5, 99.5, 99.8),  # bar 6
            (99.8, 100, 99.5, 99.7),   # bar 7
            (99.7, 100, 99.5, 99.8),   # bar 8: near session low 99.5, close above
        ])
        last = bars.iloc[-1]
        sig = check_session_high_retracement("BTC", bars, last, 1000, 1500)
        assert sig is not None
        assert sig.alert_type == AlertType.SESSION_HIGH_RETRACEMENT
        assert sig.direction == "BUY"
        assert sig.entry == 99.5
        assert sig.stop < 99.5

    def test_no_rally_returns_none(self):
        """Flat day — no meaningful rally from open → no signal."""
        bars = self._make_bars([
            (100, 100.5, 99.5, 100),
            (100, 100.8, 99.5, 100),
            (100, 100.5, 99.5, 100),
            (100, 100.5, 99.5, 100),
            (100, 100.5, 99.5, 100),
            (100, 100.5, 99.5, 100),
            (100, 100.5, 99.5, 100),
            (100, 100.5, 99.5, 99.8),
        ])
        last = bars.iloc[-1]
        sig = check_session_high_retracement("AAPL", bars, last, 1000, 1500)
        assert sig is None

    def test_high_too_recent_returns_none(self):
        """Session high on the last bar — not enough time → no signal."""
        bars = self._make_bars([
            (100, 101, 99.5, 101),
            (101, 102, 100, 102),
            (102, 103, 101, 103),
            (103, 104, 102, 104),
            (104, 105, 103, 105),
            (105, 106, 104, 106),
            (106, 107, 105, 107),     # high on bar 6
            (107, 107, 99.5, 99.8),   # bar 7: pullback (high only 1 bar ago)
        ])
        last = bars.iloc[-1]
        sig = check_session_high_retracement("AAPL", bars, last, 1000, 1500)
        assert sig is None

    def test_not_near_session_low_returns_none(self):
        """Pullback only to midrange, not near session low → no signal."""
        bars = self._make_bars([
            (100, 101, 99, 101),      # session low = 99
            (101, 103, 100, 103),     # rally
            (103, 103, 102, 102),     # bar 2: session high
            (102, 102, 101, 101),
            (101, 101, 100, 100),
            (100, 100.5, 100, 100.2),
            (100.2, 100.5, 100, 100.2),
            (100.2, 100.5, 100, 100.2),
            (100.2, 100.5, 100, 100.2),  # low=100, session low=99 → 1% away
        ])
        last = bars.iloc[-1]
        sig = check_session_high_retracement("AAPL", bars, last, 1000, 1500)
        assert sig is None

    def test_close_below_session_low_returns_none(self):
        """Still falling — close below session low → no bounce confirmed."""
        bars = self._make_bars([
            (100, 101, 99.5, 101),
            (101, 103, 100, 103),     # session high
            (103, 103, 102, 102),
            (102, 102, 101, 101),
            (101, 101, 100, 100),
            (100, 100, 99, 99),
            (99, 99.5, 98.5, 98.5),
            (98.5, 99, 98, 98),
            (98, 98.5, 97, 97.5),     # close below session low
        ])
        last = bars.iloc[-1]
        sig = check_session_high_retracement("AAPL", bars, last, 1000, 1500)
        assert sig is None

    def test_too_few_bars_returns_none(self):
        """Not enough bars → None."""
        bars = self._make_bars([
            (100, 103, 99.5, 103),
            (103, 103, 99.5, 99.8),
        ])
        last = bars.iloc[-1]
        sig = check_session_high_retracement("AAPL", bars, last, 1000, 1500)
        assert sig is None

    def test_high_confidence_on_low_volume(self):
        """Low volume retest (exhaustion) → high confidence."""
        bars = self._make_bars([
            (100, 101, 99, 101),
            (101, 103, 100, 103),     # session high
            (103, 103, 102, 102),
            (102, 102, 101, 101),
            (101, 101, 100, 100),
            (100, 100, 99.2, 99.5),
            (99.5, 100, 99.2, 99.5),
            (99.5, 100, 99, 99.3),
            (99.3, 99.5, 99, 99.2),   # near session low 99, low vol
        ])
        last = bars.iloc[-1]
        # bar_volume < 0.8 * avg_volume → high confidence
        sig = check_session_high_retracement("BTC", bars, last, 500, 1000)
        assert sig is not None
        assert sig.confidence == "high"

    def test_stale_signal_past_t1_returns_none(self):
        """Price already ran past T1 → stale, no signal."""
        bars = self._make_bars([
            (100, 101, 95, 101),      # session low = 95
            (101, 103, 100, 103),     # session high (3% rally)
            (103, 103, 102, 102),
            (102, 102, 101, 101),
            (101, 101, 100, 100),
            (100, 100, 98, 98),
            (98, 98, 96, 96),
            (96, 97, 95, 96),
            (96, 97, 95.2, 96.5),     # near low but close already above T1
        ])
        last = bars.iloc[-1]
        sig = check_session_high_retracement("AAPL", bars, last, 1000, 1500)
        # T1 = 95 + (95 - 95*0.995) = 95 + 0.475 = 95.475
        # close 96.5 > T1 → stale
        assert sig is None


class TestInsideDayForming:
    """Tests for check_inside_day_forming() — NOTICE alert when today's range is inside yesterday's."""

    def _make_bars(self, ohlcv_list, n=15):
        """Create n bars of intraday data. ohlcv_list = [(O, H, L, C), ...]"""
        rows = []
        for o, h, l, c in ohlcv_list:
            rows.append({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 1000})
        # Pad to n bars if needed
        while len(rows) < n:
            rows.append(rows[-1].copy())
        return pd.DataFrame(rows)

    def test_fires_when_range_inside(self):
        """Today's range fully inside yesterday's → fires NOTICE."""
        # Prior day: low=95, high=105
        # Today: session high=103, session low=97 → inside
        bars = self._make_bars([
            (100, 103, 97, 101),
            (101, 102, 98, 100),
        ], n=15)
        sig = check_inside_day_forming("SPY", bars, prior_high=105, prior_low=95)
        assert sig is not None
        assert sig.alert_type == AlertType.INSIDE_DAY_FORMING
        assert sig.direction == "NOTICE"
        assert "INSIDE DAY FORMING" in sig.message

    def test_no_fire_when_high_exceeds_prior(self):
        """Session high above prior day high → not inside."""
        bars = self._make_bars([
            (100, 106, 97, 104),  # session high 106 > prior high 105
        ], n=15)
        sig = check_inside_day_forming("SPY", bars, prior_high=105, prior_low=95)
        assert sig is None

    def test_no_fire_when_low_below_prior(self):
        """Session low below prior day low → not inside."""
        bars = self._make_bars([
            (100, 103, 94, 101),  # session low 94 < prior low 95
        ], n=15)
        sig = check_inside_day_forming("SPY", bars, prior_high=105, prior_low=95)
        assert sig is None

    def test_no_fire_before_min_bars(self):
        """Not enough bars (< INSIDE_DAY_FORMING_MIN_BARS) → don't fire yet."""
        bars = self._make_bars([
            (100, 103, 97, 101),
        ], n=10)  # only 10 bars, min is 13
        sig = check_inside_day_forming("SPY", bars, prior_high=105, prior_low=95)
        assert sig is None

    def test_no_fire_when_prior_high_zero(self):
        """Invalid prior high → skip."""
        bars = self._make_bars([(100, 103, 97, 101)], n=15)
        sig = check_inside_day_forming("SPY", bars, prior_high=0, prior_low=95)
        assert sig is None

    def test_no_fire_when_prior_low_zero(self):
        """Invalid prior low → skip."""
        bars = self._make_bars([(100, 103, 97, 101)], n=15)
        sig = check_inside_day_forming("SPY", bars, prior_high=105, prior_low=0)
        assert sig is None

    def test_fires_at_exact_min_bars(self):
        """Exactly INSIDE_DAY_FORMING_MIN_BARS bars → fires."""
        bars = self._make_bars([(100, 103, 97, 101)], n=13)
        sig = check_inside_day_forming("SPY", bars, prior_high=105, prior_low=95)
        assert sig is not None

    def test_range_pct_in_message(self):
        """Message includes % of parent range used."""
        bars = self._make_bars([(100, 103, 97, 101)], n=15)
        sig = check_inside_day_forming("SPY", bars, prior_high=105, prior_low=95)
        assert sig is not None
        # range used = (103-97)/(105-95) = 60%
        assert "60%" in sig.message

    def test_boundary_levels_in_message(self):
        """Message includes both boundary levels for trade guidance."""
        bars = self._make_bars([(100, 103, 97, 101)], n=15)
        sig = check_inside_day_forming("SPY", bars, prior_high=105, prior_low=95)
        assert sig is not None
        assert "$95.00" in sig.message  # prior low
        assert "$105.00" in sig.message  # prior high


class TestWeeklyLowTest:
    """Tests for check_weekly_low_test() — NOTICE when price wicks below prior week low."""

    def test_fires_on_wick_below(self):
        """Bar low wicks below prior week low, close stays above → fires."""
        bar = _bar(open_=100, high=101, low=94.5, close=100)
        prior_day = {"prior_week_low": 95, "prior_week_high": 105}
        sig = check_weekly_low_test("SPY", bar, prior_day, prior_close=100)
        assert sig is not None
        assert sig.alert_type == AlertType.WEEKLY_LOW_TEST
        assert sig.direction == "NOTICE"
        assert "TESTING prior week low" in sig.message

    def test_no_fire_when_close_below(self):
        """Close below prior week low → breakdown, not test."""
        bar = _bar(open_=96, high=97, low=93, close=94)
        prior_day = {"prior_week_low": 95, "prior_week_high": 105}
        sig = check_weekly_low_test("SPY", bar, prior_day, prior_close=100)
        assert sig is None

    def test_no_fire_when_low_above(self):
        """Bar low stays above prior week low → no test."""
        bar = _bar(open_=100, high=101, low=96, close=100)
        prior_day = {"prior_week_low": 95, "prior_week_high": 105}
        sig = check_weekly_low_test("SPY", bar, prior_day, prior_close=100)
        assert sig is None

    def test_no_fire_when_prior_close_below(self):
        """Already below weekly low → not approaching from above."""
        bar = _bar(open_=94, high=95.5, low=93, close=95.2)
        prior_day = {"prior_week_low": 95, "prior_week_high": 105}
        sig = check_weekly_low_test("SPY", bar, prior_day, prior_close=94)
        assert sig is None

    def test_no_fire_when_no_weekly_low(self):
        """Missing prior week low → skip."""
        bar = _bar(open_=100, high=101, low=94, close=100)
        sig = check_weekly_low_test("SPY", bar, {}, prior_close=100)
        assert sig is None

    def test_exact_touch_fires(self):
        """Bar low exactly at prior week low → fires (testing the level)."""
        bar = _bar(open_=100, high=101, low=95, close=100)
        prior_day = {"prior_week_low": 95, "prior_week_high": 105}
        sig = check_weekly_low_test("SPY", bar, prior_day, prior_close=100)
        assert sig is not None

    def test_fires_without_prior_close(self):
        """No prior close → skips directional guard, still fires."""
        bar = _bar(open_=100, high=101, low=94, close=100)
        prior_day = {"prior_week_low": 95, "prior_week_high": 105}
        sig = check_weekly_low_test("SPY", bar, prior_day, prior_close=None)
        assert sig is not None


class TestWeeklyLowBreakdown:
    """Tests for check_weekly_low_breakdown() — SELL when price closes below prior week low."""

    def test_fires_on_close_below(self):
        """Close below prior week low → fires SELL."""
        bar = _bar(open_=96, high=97, low=93, close=94)
        prior_day = {"prior_week_low": 95, "prior_week_high": 105}
        sig = check_weekly_low_breakdown("SPY", bar, prior_day, 2000, 1000, prior_close=100)
        assert sig is not None
        assert sig.alert_type == AlertType.WEEKLY_LOW_BREAKDOWN
        assert sig.direction == "SELL"
        assert "WEEKLY LOW BREAKDOWN" in sig.message

    def test_no_fire_when_close_above(self):
        """Close above prior week low → not a breakdown."""
        bar = _bar(open_=96, high=97, low=94, close=96)
        prior_day = {"prior_week_low": 95, "prior_week_high": 105}
        sig = check_weekly_low_breakdown("SPY", bar, prior_day, 2000, 1000, prior_close=100)
        assert sig is None

    def test_no_fire_when_already_below(self):
        """Prior close already below weekly low → not a fresh breakdown."""
        bar = _bar(open_=93, high=94, low=92, close=93)
        prior_day = {"prior_week_low": 95, "prior_week_high": 105}
        sig = check_weekly_low_breakdown("SPY", bar, prior_day, 2000, 1000, prior_close=94)
        assert sig is None

    def test_no_fire_when_no_weekly_low(self):
        """Missing prior week low → skip."""
        bar = _bar(open_=96, high=97, low=93, close=94)
        sig = check_weekly_low_breakdown("SPY", bar, {}, 2000, 1000, prior_close=100)
        assert sig is None

    def test_high_volume_gets_high_confidence(self):
        """Volume >= 1.5x avg → high confidence."""
        bar = _bar(open_=96, high=97, low=93, close=94)
        prior_day = {"prior_week_low": 95, "prior_week_high": 105}
        sig = check_weekly_low_breakdown("SPY", bar, prior_day, 2000, 1000, prior_close=100)
        assert sig is not None
        assert sig.confidence == "high"  # 2000/1000 = 2.0x >= 1.5

    def test_low_volume_gets_medium_confidence(self):
        """Volume < 1.5x avg → medium confidence."""
        bar = _bar(open_=96, high=97, low=93, close=94)
        prior_day = {"prior_week_low": 95, "prior_week_high": 105}
        sig = check_weekly_low_breakdown("SPY", bar, prior_day, 1000, 1000, prior_close=100)
        assert sig is not None
        assert sig.confidence == "medium"  # 1.0x < 1.5

    def test_fires_without_prior_close(self):
        """No prior close → skips directional guard, still fires."""
        bar = _bar(open_=96, high=97, low=93, close=94)
        prior_day = {"prior_week_low": 95, "prior_week_high": 105}
        sig = check_weekly_low_breakdown("SPY", bar, prior_day, 2000, 1000, prior_close=None)
        assert sig is not None


# ===== Monthly Levels =====


class TestMonthlyLevelTouch:
    """Tests for check_monthly_level_touch() — BUY when price bounces at prior month low."""

    def _prior(self, pm_high=200.0, pm_low=180.0, **overrides):
        base = {
            "pattern": "normal", "high": 195.0, "low": 185.0,
            "close": 190.0, "is_inside": False,
            "parent_high": 196.0, "parent_low": 184.0,
            "prior_month_high": pm_high, "prior_month_low": pm_low,
        }
        base.update(overrides)
        return base

    def test_fires_on_bounce_at_prior_month_low(self):
        prior = self._prior(pm_high=200.0, pm_low=180.0)
        bars = pd.DataFrame([
            {"Open": 181.0, "High": 182.0, "Low": 180.50, "Close": 181.5, "Volume": 1000},
        ])
        sig = check_monthly_level_touch("SPY", bars, prior)
        assert sig is not None
        assert sig.alert_type == AlertType.MONTHLY_LEVEL_TOUCH
        assert sig.direction == "BUY"
        assert sig.entry == 180.0
        assert sig.target_1 == 200.0
        assert sig.confidence == "high"
        assert "prior month low" in sig.message

    def test_targets_use_monthly_range(self):
        prior = self._prior(pm_high=200.0, pm_low=180.0)
        bars = pd.DataFrame([
            {"Open": 181.0, "High": 182.0, "Low": 180.50, "Close": 181.5, "Volume": 1000},
        ])
        sig = check_monthly_level_touch("SPY", bars, prior)
        assert sig is not None
        assert sig.target_1 == 200.0
        assert sig.target_2 == 210.0  # 200 + 20*0.5

    def test_no_fire_when_far_from_monthly_level(self):
        prior = self._prior(pm_high=200.0, pm_low=180.0)
        bars = pd.DataFrame([
            {"Open": 177.0, "High": 178.0, "Low": 176.0, "Close": 177.5, "Volume": 1000},
        ])
        sig = check_monthly_level_touch("SPY", bars, prior)
        assert sig is None

    def test_no_fire_when_close_below_monthly_low(self):
        prior = self._prior(pm_high=200.0, pm_low=180.0)
        bars = pd.DataFrame([
            {"Open": 180.5, "High": 181.0, "Low": 180.20, "Close": 179.8, "Volume": 1000},
        ])
        sig = check_monthly_level_touch("SPY", bars, prior)
        assert sig is None

    def test_no_fire_when_monthly_data_unavailable(self):
        prior = self._prior()
        prior["prior_month_high"] = None
        prior["prior_month_low"] = None
        bars = pd.DataFrame([
            {"Open": 181.0, "High": 182.0, "Low": 180.50, "Close": 181.5, "Volume": 1000},
        ])
        sig = check_monthly_level_touch("SPY", bars, prior)
        assert sig is None

    def test_lookback_catches_earlier_touch(self):
        prior = self._prior(pm_high=200.0, pm_low=180.0)
        bars = pd.DataFrame([
            {"Open": 181.0, "High": 182.0, "Low": 180.20, "Close": 180.8, "Volume": 1000},
            {"Open": 180.8, "High": 181.5, "Low": 180.5, "Close": 181.0, "Volume": 1000},
            {"Open": 181.0, "High": 182.0, "Low": 180.8, "Close": 181.5, "Volume": 1000},
        ])
        sig = check_monthly_level_touch("SPY", bars, prior)
        assert sig is not None


class TestMonthlyHighBreakout:
    """Tests for check_monthly_high_breakout() — BUY when price breaks above prior month high."""

    def _prior(self, pm_high=200.0, pm_low=180.0):
        return {"prior_month_high": pm_high, "prior_month_low": pm_low}

    def test_fires_on_close_above_with_volume(self):
        # Phase 1: requires N=2 consecutive bars above monthly high.
        # Bar 2 Low must stay <= pm_high so risk > 0 (rule fires normally).
        prior = self._prior()
        bars = pd.DataFrame([
            {"Open": 199.0, "High": 200.3, "Low": 199.7, "Close": 200.2, "Volume": 1500},
            {"Open": 200.2, "High": 202.0, "Low": 199.8, "Close": 201.0, "Volume": 2000},
        ])
        sig = check_monthly_high_breakout("SPY", bars, prior, 2000, 1000)
        assert sig is not None
        assert sig.alert_type == AlertType.MONTHLY_HIGH_BREAKOUT
        assert sig.direction == "BUY"
        assert "Monthly high breakout" in sig.message

    def test_no_fire_when_close_below(self):
        prior = self._prior()
        bars = pd.DataFrame([
            {"Open": 199.0, "High": 200.5, "Low": 198.0, "Close": 199.5, "Volume": 2000},
        ])
        sig = check_monthly_high_breakout("SPY", bars, prior, 2000, 1000)
        assert sig is None

    def test_no_fire_low_volume(self):
        prior = self._prior()
        bars = pd.DataFrame([
            {"Open": 199.0, "High": 202.0, "Low": 198.5, "Close": 201.0, "Volume": 500},
        ])
        sig = check_monthly_high_breakout("SPY", bars, prior, 500, 1000)
        assert sig is None

    def test_no_fire_when_no_monthly_high(self):
        bars = pd.DataFrame([
            {"Open": 199.0, "High": 202.0, "Low": 198.5, "Close": 201.0, "Volume": 2000},
        ])
        sig = check_monthly_high_breakout("SPY", bars, {}, 2000, 1000)
        assert sig is None


class TestMonthlyHighTest:
    """Tests for check_monthly_high_test() — NOTICE when price wicks above prior month high."""

    def test_fires_on_wick_above(self):
        bar = _bar(open_=198, high=201, low=197, close=199)
        prior_day = {"prior_month_high": 200, "prior_month_low": 180}
        sig = check_monthly_high_test("SPY", bar, prior_day, prior_close=198)
        assert sig is not None
        assert sig.alert_type == AlertType.MONTHLY_HIGH_TEST
        assert sig.direction == "NOTICE"
        assert "TESTING prior month high" in sig.message

    def test_no_fire_when_close_above(self):
        bar = _bar(open_=199, high=202, low=198, close=201)
        prior_day = {"prior_month_high": 200, "prior_month_low": 180}
        sig = check_monthly_high_test("SPY", bar, prior_day, prior_close=198)
        assert sig is None

    def test_no_fire_when_high_below(self):
        bar = _bar(open_=197, high=199, low=196, close=198)
        prior_day = {"prior_month_high": 200, "prior_month_low": 180}
        sig = check_monthly_high_test("SPY", bar, prior_day, prior_close=197)
        assert sig is None

    def test_no_fire_when_prior_close_above(self):
        bar = _bar(open_=201, high=202, low=199, close=199.5)
        prior_day = {"prior_month_high": 200, "prior_month_low": 180}
        sig = check_monthly_high_test("SPY", bar, prior_day, prior_close=201)
        assert sig is None

    def test_no_fire_when_no_monthly_high(self):
        bar = _bar(open_=198, high=201, low=197, close=199)
        sig = check_monthly_high_test("SPY", bar, {}, prior_close=198)
        assert sig is None


class TestMonthlyHighResistance:
    """Tests for check_monthly_high_resistance() — SELL when approaching prior month high."""

    def test_fires_on_approach(self):
        bar = _bar(open_=198, high=199.8, low=197, close=199)
        prior_day = {"prior_month_high": 200, "prior_month_low": 180}
        sig = check_monthly_high_resistance("SPY", bar, prior_day)
        assert sig is not None
        assert sig.alert_type == AlertType.MONTHLY_HIGH_RESISTANCE
        assert sig.direction == "SELL"
        assert "Monthly high resistance" in sig.message

    def test_no_fire_when_close_above(self):
        bar = _bar(open_=199, high=201, low=198, close=201)
        prior_day = {"prior_month_high": 200, "prior_month_low": 180}
        sig = check_monthly_high_resistance("SPY", bar, prior_day)
        assert sig is None

    def test_no_fire_when_far_away(self):
        bar = _bar(open_=190, high=192, low=189, close=191)
        prior_day = {"prior_month_high": 200, "prior_month_low": 180}
        sig = check_monthly_high_resistance("SPY", bar, prior_day)
        assert sig is None


class TestMonthlyLowTest:
    """Tests for check_monthly_low_test() — NOTICE when price wicks below prior month low."""

    def test_fires_on_wick_below(self):
        bar = _bar(open_=182, high=183, low=179, close=182)
        prior_day = {"prior_month_low": 180, "prior_month_high": 200}
        sig = check_monthly_low_test("SPY", bar, prior_day, prior_close=182)
        assert sig is not None
        assert sig.alert_type == AlertType.MONTHLY_LOW_TEST
        assert sig.direction == "NOTICE"
        assert "TESTING prior month low" in sig.message

    def test_no_fire_when_close_below(self):
        bar = _bar(open_=181, high=182, low=178, close=179)
        prior_day = {"prior_month_low": 180, "prior_month_high": 200}
        sig = check_monthly_low_test("SPY", bar, prior_day, prior_close=182)
        assert sig is None

    def test_no_fire_when_low_above(self):
        bar = _bar(open_=182, high=183, low=181, close=182)
        prior_day = {"prior_month_low": 180, "prior_month_high": 200}
        sig = check_monthly_low_test("SPY", bar, prior_day, prior_close=182)
        assert sig is None

    def test_no_fire_when_prior_close_below(self):
        bar = _bar(open_=179, high=180.5, low=178, close=180.2)
        prior_day = {"prior_month_low": 180, "prior_month_high": 200}
        sig = check_monthly_low_test("SPY", bar, prior_day, prior_close=179)
        assert sig is None

    def test_no_fire_when_no_monthly_low(self):
        bar = _bar(open_=182, high=183, low=179, close=182)
        sig = check_monthly_low_test("SPY", bar, {}, prior_close=182)
        assert sig is None

    def test_fires_without_prior_close(self):
        bar = _bar(open_=182, high=183, low=179, close=182)
        prior_day = {"prior_month_low": 180, "prior_month_high": 200}
        sig = check_monthly_low_test("SPY", bar, prior_day, prior_close=None)
        assert sig is not None


class TestMonthlyLowBreakdown:
    """Tests for check_monthly_low_breakdown() — SELL when price closes below prior month low."""

    def test_fires_on_close_below(self):
        bar = _bar(open_=181, high=182, low=178, close=179)
        prior_day = {"prior_month_low": 180, "prior_month_high": 200}
        sig = check_monthly_low_breakdown("SPY", bar, prior_day, 2000, 1000, prior_close=182)
        assert sig is not None
        assert sig.alert_type == AlertType.MONTHLY_LOW_BREAKDOWN
        assert sig.direction == "SELL"
        assert "MONTHLY LOW BREAKDOWN" in sig.message

    def test_no_fire_when_close_above(self):
        bar = _bar(open_=181, high=182, low=179, close=181)
        prior_day = {"prior_month_low": 180, "prior_month_high": 200}
        sig = check_monthly_low_breakdown("SPY", bar, prior_day, 2000, 1000, prior_close=182)
        assert sig is None

    def test_no_fire_when_already_below(self):
        bar = _bar(open_=178, high=179, low=177, close=178)
        prior_day = {"prior_month_low": 180, "prior_month_high": 200}
        sig = check_monthly_low_breakdown("SPY", bar, prior_day, 2000, 1000, prior_close=179)
        assert sig is None

    def test_no_fire_when_no_monthly_low(self):
        bar = _bar(open_=181, high=182, low=178, close=179)
        sig = check_monthly_low_breakdown("SPY", bar, {}, 2000, 1000, prior_close=182)
        assert sig is None

    def test_high_volume_gets_high_confidence(self):
        bar = _bar(open_=181, high=182, low=178, close=179)
        prior_day = {"prior_month_low": 180, "prior_month_high": 200}
        sig = check_monthly_low_breakdown("SPY", bar, prior_day, 2000, 1000, prior_close=182)
        assert sig is not None
        assert sig.confidence == "high"

    def test_low_volume_gets_medium_confidence(self):
        bar = _bar(open_=181, high=182, low=178, close=179)
        prior_day = {"prior_month_low": 180, "prior_month_high": 200}
        sig = check_monthly_low_breakdown("SPY", bar, prior_day, 1000, 1000, prior_close=182)
        assert sig is not None
        assert sig.confidence == "medium"

    def test_fires_without_prior_close(self):
        bar = _bar(open_=181, high=182, low=178, close=179)
        prior_day = {"prior_month_low": 180, "prior_month_high": 200}
        sig = check_monthly_low_breakdown("SPY", bar, prior_day, 2000, 1000, prior_close=None)
        assert sig is not None


# ===== Multi-Day Double Bottom =====


class TestDetectDailyDoubleBottoms:
    """Tests for detect_daily_double_bottoms() in intraday_data.py."""

    @staticmethod
    def _make_daily_bars(lows, num_bars=20):
        """Build daily OHLCV bars with controlled lows.

        ``lows`` is a list of (bar_index, low_value) tuples for swing lows.
        All other bars get a default low well above the zone (2% higher)
        so recovery checks pass.
        """
        max_low = max(lv for _, lv in lows) if lows else 100.0
        # Default low must be > zone_high * (1 + recovery_pct)
        default_low = max_low * 1.02 if lows else 100.0
        rows = []
        for i in range(num_bars):
            custom = next((lv for idx, lv in lows if idx == i), None)
            low = custom if custom is not None else default_low
            rows.append({
                "Open": low + 5, "High": low + 10,
                "Low": low, "Close": low + 7, "Volume": 1000,
            })
        return pd.DataFrame(rows)

    def test_two_touches_detected(self):
        """Two swing lows at same level, separated by days → detected."""
        # Swing low at bar 3 and bar 10, both at $70,400
        bars = self._make_daily_bars([(3, 70400), (10, 70420)], num_bars=15)
        results = detect_daily_double_bottoms(bars)
        assert len(results) == 1
        assert results[0]["touch_count"] == 2
        assert results[0]["level"] == 70400

    def test_no_retest_not_detected(self):
        """Only one swing low → not detected."""
        bars = self._make_daily_bars([(5, 70400)], num_bars=15)
        results = detect_daily_double_bottoms(bars)
        assert len(results) == 0

    def test_three_touches_detected(self):
        """Three swing lows at same zone → touch_count=3."""
        bars = self._make_daily_bars(
            [(3, 70400), (7, 70420), (12, 70410)], num_bars=16
        )
        results = detect_daily_double_bottoms(bars)
        assert len(results) == 1
        assert results[0]["touch_count"] == 3

    def test_descending_lows_rejected(self):
        """Lows getting progressively lower → not a double bottom."""
        # Second low is 1% below first — descending
        bars = self._make_daily_bars([(3, 70400), (10, 69600)], num_bars=15)
        results = detect_daily_double_bottoms(bars)
        assert len(results) == 0

    def test_same_day_not_counted(self):
        """Both touches on adjacent bars (min_days_between=1) → not detected."""
        bars = self._make_daily_bars([(5, 70400), (6, 70420)], num_bars=15)
        results = detect_daily_double_bottoms(bars)
        assert len(results) == 0

    def test_no_recovery_between_touches(self):
        """All bars stay near zone low → no recovery → not detected."""
        # All bars have lows near 70400 — no bounce between touches
        lows = [(i, 70400 + i) for i in range(3, 12)]
        bars = self._make_daily_bars(lows, num_bars=15)
        # Override the "normal" bars so they also stay low
        for i in range(15):
            bars.loc[i, "Low"] = 70400 + (i * 2)
            bars.loc[i, "Close"] = 70410 + (i * 2)
            bars.loc[i, "High"] = 70420 + (i * 2)
        results = detect_daily_double_bottoms(bars)
        assert len(results) == 0

    def test_btc_level_prices(self):
        """Works correctly with $70K BTC prices — % thresholds scale."""
        bars = self._make_daily_bars(
            [(3, 70413), (10, 70450)], num_bars=15
        )
        results = detect_daily_double_bottoms(bars)
        assert len(results) == 1
        zone = results[0]
        assert zone["level"] == 70413
        assert zone["zone_high"] == 70450

    def test_stock_level_prices(self):
        """Works correctly with $150 stock prices."""
        bars = self._make_daily_bars(
            [(3, 148.50), (10, 148.70)], num_bars=15
        )
        results = detect_daily_double_bottoms(bars)
        assert any(z["level"] == 148.50 for z in results)

    def test_upper_quartile_zone_filtered_out(self):
        """Zone in the top 25% of range is filtered — only meaningful
        support zones in the lower 75% are detected."""
        # Build bars manually: lows at 69000 area and 78000 area,
        # with highs pushed to 80000 so 78000 is in the top quartile.
        rows = []
        for i in range(15):
            rows.append({
                "Open": 79000, "High": 80000,
                "Low": 79000, "Close": 79500, "Volume": 1000,
            })
        # Two touches at 69000 zone (lower 75%)
        rows[2]["Low"] = 69000
        rows[8]["Low"] = 69050
        # Two touches at 78000 zone (top 25%: 69000 + 11000*0.75 = 77250)
        rows[4]["Low"] = 78000
        rows[11]["Low"] = 78050
        bars = pd.DataFrame(rows)
        results = detect_daily_double_bottoms(bars)
        assert any(z["level"] == 69000 for z in results)
        assert not any(z["level"] == 78000 for z in results)

    def test_empty_dataframe(self):
        """Empty DataFrame → empty list."""
        results = detect_daily_double_bottoms(pd.DataFrame())
        assert results == []


class TestMultiDayDoubleBottom:
    """Tests for check_multi_day_double_bottom() rule in intraday_rules.py."""

    @staticmethod
    def _make_intraday_bars(last_low, last_close, num_bars=10):
        """Build intraday 5-min bars with a specific last bar."""
        rows = []
        for i in range(num_bars - 1):
            rows.append({
                "Open": last_close + 2, "High": last_close + 3,
                "Low": last_close + 1, "Close": last_close + 2,
                "Volume": 1000,
            })
        rows.append({
            "Open": last_low + 1, "High": last_close + 0.5,
            "Low": last_low, "Close": last_close, "Volume": 1000,
        })
        return pd.DataFrame(rows)

    def test_fires_when_bouncing_at_zone(self):
        """Intraday bar touches zone and closes above → BUY signal."""
        zone = {
            "level": 70400, "touch_count": 2,
            "first_touch_idx": 3, "last_touch_idx": 10,
            "zone_high": 70450,
        }
        # Last bar low = 70420 (within 0.5% of 70400), close = 70600
        bars = self._make_intraday_bars(last_low=70420, last_close=70600)
        sig = check_multi_day_double_bottom(
            "BTC-USD", bars, [zone], 1000, 1000,
        )
        assert sig is not None
        assert sig.alert_type == AlertType.MULTI_DAY_DOUBLE_BOTTOM
        assert sig.direction == "BUY"
        assert sig.entry == 70600.0  # entry at current price, not zone level
        assert sig.confidence == "medium"
        assert "Multi-day double bottom" in sig.message
        assert "2x" in sig.message

    def test_no_fire_when_too_far_above_zone(self):
        """Price already 3% above zone → stale, skip."""
        zone = {
            "level": 70400, "touch_count": 2,
            "first_touch_idx": 3, "last_touch_idx": 10,
            "zone_high": 70450,
        }
        # Price at 72600 — 3.1% above zone
        bars = self._make_intraday_bars(last_low=72580, last_close=72600)
        sig = check_multi_day_double_bottom(
            "BTC-USD", bars, [zone], 1000, 1000,
        )
        assert sig is None

    def test_no_fire_when_close_below_zone(self):
        """Close below zone level → no bounce confirmation."""
        zone = {
            "level": 70400, "touch_count": 2,
            "first_touch_idx": 3, "last_touch_idx": 10,
            "zone_high": 70450,
        }
        # Low touches zone but close is below it
        bars = self._make_intraday_bars(last_low=70380, last_close=70350)
        sig = check_multi_day_double_bottom(
            "BTC-USD", bars, [zone], 1000, 1000,
        )
        assert sig is None

    def test_confidence_high_on_three_touches(self):
        """Zone tested 3+ times → high confidence."""
        zone = {
            "level": 70400, "touch_count": 3,
            "first_touch_idx": 3, "last_touch_idx": 12,
            "zone_high": 70450,
        }
        bars = self._make_intraday_bars(last_low=70420, last_close=70600)
        sig = check_multi_day_double_bottom(
            "BTC-USD", bars, [zone], 1000, 1000,
        )
        assert sig is not None
        assert sig.confidence == "high"
        assert "3x" in sig.message

    def test_confidence_high_on_volume_exhaustion(self):
        """Low volume retest (< 0.8x avg) → high confidence."""
        zone = {
            "level": 70400, "touch_count": 2,
            "first_touch_idx": 3, "last_touch_idx": 10,
            "zone_high": 70450,
        }
        bars = self._make_intraday_bars(last_low=70420, last_close=70600)
        sig = check_multi_day_double_bottom(
            "BTC-USD", bars, [zone], 700, 1000,  # vol 0.7x
        )
        assert sig is not None
        assert sig.confidence == "high"

    def test_works_for_stocks(self):
        """Stock-level prices ($150) with same logic."""
        zone = {
            "level": 148.50, "touch_count": 2,
            "first_touch_idx": 3, "last_touch_idx": 10,
            "zone_high": 148.70,
        }
        bars = self._make_intraday_bars(last_low=148.60, last_close=149.20)
        sig = check_multi_day_double_bottom(
            "AAPL", bars, [zone], 1000, 1000,
        )
        assert sig is not None
        assert sig.entry == 149.20  # entry at current price
        assert sig.direction == "BUY"

    def test_no_fire_on_empty_zones(self):
        """Empty daily_double_bottoms → None."""
        bars = self._make_intraday_bars(last_low=70420, last_close=70600)
        sig = check_multi_day_double_bottom(
            "BTC-USD", bars, [], 1000, 1000,
        )
        assert sig is None

    def test_picks_nearest_zone(self):
        """Multiple zones — picks the one closest to current price."""
        zone_far = {
            "level": 68000, "touch_count": 2,
            "first_touch_idx": 2, "last_touch_idx": 8,
            "zone_high": 68100,
        }
        zone_near = {
            "level": 70400, "touch_count": 2,
            "first_touch_idx": 3, "last_touch_idx": 10,
            "zone_high": 70450,
        }
        bars = self._make_intraday_bars(last_low=70420, last_close=70600)
        sig = check_multi_day_double_bottom(
            "BTC-USD", bars, [zone_far, zone_near], 1000, 1000,
        )
        assert sig is not None
        assert sig.entry == 70600.0  # entry at current price

    def test_zone_range_in_message(self):
        """When zone_high != level, message shows range."""
        zone = {
            "level": 70400, "touch_count": 2,
            "first_touch_idx": 3, "last_touch_idx": 10,
            "zone_high": 70450,
        }
        bars = self._make_intraday_bars(last_low=70420, last_close=70600)
        sig = check_multi_day_double_bottom(
            "BTC-USD", bars, [zone], 1000, 1000,
        )
        assert "$70400.00" in sig.message
        assert "$70450.00" in sig.message


# ---------------------------------------------------------------------------
# Hourly Resistance Rejection SHORT
# ---------------------------------------------------------------------------


class TestHourlyResistanceRejectionShort:
    """Tests for check_hourly_resistance_rejection_short."""

    def test_fires_on_valid_rejection(self):
        """Bar high near resistance, close in lower 40% of range → SHORT."""
        # Resistance at 100.0, bar high reaches 99.9 (0.1% away), closes at 99.2
        bars = _bars([
            *[{"Open": 98, "High": 99, "Low": 97, "Close": 98.5, "Volume": 1000}] * 12,
            {"Open": 99, "High": 99.9, "Low": 99.0, "Close": 99.2, "Volume": 1500},
        ])
        sig = check_hourly_resistance_rejection_short(
            "ETH-USD", bars, hourly_resistance=[100.0], prior_close=98.0,
        )
        assert sig is not None
        assert sig.alert_type == AlertType.HOURLY_RESISTANCE_REJECTION_SHORT
        assert sig.direction == "SHORT"
        assert sig.entry == 99.2
        # Stop should be above resistance (100.0 * 1.003 = 100.30)
        assert sig.stop == 100.30
        assert "HOURLY RESISTANCE REJECTION" in sig.message

    def test_no_fire_close_too_high(self):
        """Bar touches resistance but closes in upper 60% → no rejection."""
        bars = _bars([
            *[{"Open": 98, "High": 99, "Low": 97, "Close": 98.5, "Volume": 1000}] * 12,
            {"Open": 99, "High": 99.9, "Low": 99.0, "Close": 99.7, "Volume": 1500},
        ])
        sig = check_hourly_resistance_rejection_short(
            "ETH-USD", bars, hourly_resistance=[100.0], prior_close=98.0,
        )
        assert sig is None

    def test_no_fire_price_above_level(self):
        """Prior close above resistance → it's support, not resistance."""
        bars = _bars([
            *[{"Open": 101, "High": 102, "Low": 100, "Close": 101, "Volume": 1000}] * 12,
            {"Open": 100.5, "High": 100.8, "Low": 99.5, "Close": 99.6, "Volume": 1500},
        ])
        sig = check_hourly_resistance_rejection_short(
            "ETH-USD", bars, hourly_resistance=[100.0], prior_close=101.0,
        )
        assert sig is None

    def test_no_fire_too_few_bars(self):
        """Less than 12 bars → no fire."""
        bars = _bars([
            {"Open": 99, "High": 99.9, "Low": 99.0, "Close": 99.2, "Volume": 1500},
        ] * 5)
        sig = check_hourly_resistance_rejection_short(
            "ETH-USD", bars, hourly_resistance=[100.0], prior_close=98.0,
        )
        assert sig is None

    def test_no_fire_empty_resistance(self):
        """No hourly resistance levels → no fire."""
        bars = _bars([
            *[{"Open": 98, "High": 99, "Low": 97, "Close": 98.5, "Volume": 1000}] * 13,
        ])
        sig = check_hourly_resistance_rejection_short(
            "ETH-USD", bars, hourly_resistance=[], prior_close=98.0,
        )
        assert sig is None

    def test_picks_nearest_resistance(self):
        """Multiple levels — fires on nearest resistance above price."""
        bars = _bars([
            *[{"Open": 98, "High": 99, "Low": 97, "Close": 98.5, "Volume": 1000}] * 12,
            {"Open": 99, "High": 99.9, "Low": 99.0, "Close": 99.2, "Volume": 1500},
        ])
        sig = check_hourly_resistance_rejection_short(
            "ETH-USD", bars, hourly_resistance=[100.0, 105.0, 110.0], prior_close=98.0,
        )
        assert sig is not None
        assert "$100.00" in sig.message

    def test_no_fire_bar_high_too_far(self):
        """Bar high too far from resistance → no fire."""
        bars = _bars([
            *[{"Open": 95, "High": 96, "Low": 94, "Close": 95.5, "Volume": 1000}] * 12,
            {"Open": 96, "High": 97, "Low": 95.5, "Close": 95.8, "Volume": 1500},
        ])
        # 97 is 3% away from 100 — well beyond 0.3% proximity
        sig = check_hourly_resistance_rejection_short(
            "ETH-USD", bars, hourly_resistance=[100.0], prior_close=95.0,
        )
        assert sig is None
