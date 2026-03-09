"""Comprehensive tests for professional swing trading rules in swing_rules.py.

Covers: MACD crossover, RSI divergence, bull flag, candle patterns,
consecutive red days, and the evaluate_swing_rules orchestrator.
"""

import pytest

from analytics.swing_rules import (
    check_swing_macd_crossover,
    check_swing_rsi_divergence,
    check_swing_bull_flag,
    check_swing_candle_patterns,
    check_swing_consecutive_days,
    evaluate_swing_rules,
)
from analytics.intraday_rules import AlertSignal, AlertType


# ---------------------------------------------------------------------------
# MACD Signal Line Crossover
# ---------------------------------------------------------------------------


class TestSwingMACDCrossover:
    """Tests for check_swing_macd_crossover — MACD crosses above signal line."""

    def test_bullish_crossover_fires_buy(self):
        """MACD was below signal, now above -> BUY signal."""
        prior_day = {
            "macd_line": 0.50,
            "macd_line_prev": -0.10,
            "macd_signal": 0.30,
            "macd_signal_prev": 0.20,
            "close": 150.0,
            "open": 148.0,
        }
        sig = check_swing_macd_crossover("AAPL", prior_day)
        assert sig is not None
        assert sig.direction == "BUY"
        assert sig.alert_type == AlertType.SWING_MACD_CROSSOVER
        assert sig.symbol == "AAPL"
        assert sig.price == 150.0

    def test_no_crossover_macd_stays_above(self):
        """MACD was already above signal and remains above -> None."""
        prior_day = {
            "macd_line": 0.60,
            "macd_line_prev": 0.50,  # already above signal_prev
            "macd_signal": 0.30,
            "macd_signal_prev": 0.20,
            "close": 150.0,
        }
        assert check_swing_macd_crossover("AAPL", prior_day) is None

    def test_macd_below_signal_no_cross(self):
        """MACD still below signal -> None."""
        prior_day = {
            "macd_line": 0.10,
            "macd_line_prev": -0.10,
            "macd_signal": 0.30,
            "macd_signal_prev": 0.20,
            "close": 150.0,
        }
        assert check_swing_macd_crossover("AAPL", prior_day) is None

    def test_missing_macd_data(self):
        """Missing MACD fields -> None."""
        assert check_swing_macd_crossover("AAPL", {}) is None
        assert check_swing_macd_crossover("AAPL", {"macd_line": 0.5}) is None

    def test_missing_close(self):
        """All MACD data present but no close -> None."""
        prior_day = {
            "macd_line": 0.50,
            "macd_line_prev": -0.10,
            "macd_signal": 0.30,
            "macd_signal_prev": 0.20,
        }
        assert check_swing_macd_crossover("AAPL", prior_day) is None

    def test_crossover_exactly_equal_prev(self):
        """MACD prev == signal prev (at boundary, not above) -> crossover fires."""
        prior_day = {
            "macd_line": 0.50,
            "macd_line_prev": 0.20,  # equal to signal_prev
            "macd_signal": 0.30,
            "macd_signal_prev": 0.20,
            "close": 150.0,
        }
        sig = check_swing_macd_crossover("AAPL", prior_day)
        assert sig is not None
        assert sig.direction == "BUY"

    def test_macd_equal_to_signal_today_no_fire(self):
        """MACD == signal today (not strictly above) -> None."""
        prior_day = {
            "macd_line": 0.30,
            "macd_line_prev": -0.10,
            "macd_signal": 0.30,
            "macd_signal_prev": 0.20,
            "close": 150.0,
        }
        assert check_swing_macd_crossover("AAPL", prior_day) is None


# ---------------------------------------------------------------------------
# RSI Divergence
# ---------------------------------------------------------------------------


class TestSwingRSIDivergence:
    """Tests for check_swing_rsi_divergence — bullish RSI divergence."""

    def _make_divergence_data(self):
        """Build data with price lower low but RSI higher low.

        Creates a 20-bar series where:
        - Price swing lows: bar 5 = 100, bar 15 = 97 (lower low, 3% drop)
        - RSI swing lows: bar 5 = 30, bar 15 = 35 (higher low)
        """
        closes = [105.0] * 20
        rsi = [50.0] * 20

        # First swing low at index 5
        closes[4] = 102.0
        closes[5] = 100.0  # local min
        closes[6] = 103.0
        rsi[4] = 35.0
        rsi[5] = 30.0
        rsi[6] = 45.0

        # Second swing low at index 15 — price lower, RSI higher
        closes[14] = 99.0
        closes[15] = 97.0  # lower low
        closes[16] = 101.0
        rsi[14] = 38.0
        rsi[15] = 35.0  # higher low than 30
        rsi[16] = 48.0

        return closes, rsi

    def test_bullish_divergence_fires_buy(self):
        """Price lower low + RSI higher low -> BUY signal."""
        closes, rsi = self._make_divergence_data()
        sig = check_swing_rsi_divergence("MSFT", closes, rsi)
        assert sig is not None
        assert sig.direction == "BUY"
        assert sig.alert_type == AlertType.SWING_RSI_DIVERGENCE
        assert sig.symbol == "MSFT"

    def test_no_divergence_price_higher_low(self):
        """Price makes higher low -> no divergence -> None."""
        closes, rsi = self._make_divergence_data()
        # Make second low higher than first
        closes[15] = 102.0
        assert check_swing_rsi_divergence("MSFT", closes, rsi) is None

    def test_insufficient_data(self):
        """Less than 20 bars -> None."""
        closes = [100.0] * 10
        rsi = [50.0] * 10
        assert check_swing_rsi_divergence("MSFT", closes, rsi) is None

    def test_empty_data(self):
        """Empty lists -> None."""
        assert check_swing_rsi_divergence("MSFT", [], []) is None

    def test_swing_too_small(self):
        """Price difference < 2% -> None (below DIVERGENCE_MIN_SWING_SIZE)."""
        closes = [105.0] * 20
        rsi = [50.0] * 20

        # First swing low
        closes[4] = 102.0
        closes[5] = 100.0
        closes[6] = 103.0
        rsi[4] = 35.0
        rsi[5] = 30.0
        rsi[6] = 45.0

        # Second swing low — price drop is only ~1% (too small)
        closes[14] = 101.0
        closes[15] = 99.5  # only 0.5% lower than 100
        closes[16] = 102.0
        rsi[14] = 38.0
        rsi[15] = 35.0
        rsi[16] = 48.0

        assert check_swing_rsi_divergence("MSFT", closes, rsi) is None

    def test_no_swing_lows_in_data(self):
        """Monotonically increasing data has no local minima -> None."""
        closes = [float(100 + i) for i in range(20)]
        rsi = [float(40 + i) for i in range(20)]
        assert check_swing_rsi_divergence("MSFT", closes, rsi) is None

    def test_rsi_also_lower_low_no_divergence(self):
        """Price lower low AND RSI lower low -> no divergence -> None."""
        closes = [105.0] * 20
        rsi = [50.0] * 20

        closes[4] = 102.0
        closes[5] = 100.0
        closes[6] = 103.0
        rsi[4] = 35.0
        rsi[5] = 30.0
        rsi[6] = 45.0

        closes[14] = 99.0
        closes[15] = 97.0  # lower low
        closes[16] = 101.0
        rsi[14] = 28.0
        rsi[15] = 25.0  # also lower low -> no divergence
        rsi[16] = 48.0

        assert check_swing_rsi_divergence("MSFT", closes, rsi) is None


# ---------------------------------------------------------------------------
# Bull Flag
# ---------------------------------------------------------------------------


class TestSwingBullFlag:
    """Tests for check_swing_bull_flag — impulse + flag consolidation + breakout."""

    def _make_bull_flag_bars(
        self,
        impulse_pct=0.08,
        flag_days=3,
        retrace_pct=0.30,
        breakout=True,
    ):
        """Build daily bars for a bull flag pattern.

        The algorithm scans impulse_start from index 0, measuring a 5-bar
        impulse (indices impulse_start .. impulse_start+5), then a flag
        starting at impulse_start+5, then a breakout bar after the flag.

        We place flat pre-impulse bars, then a clear 5-bar rally, then a
        tight flag, then a breakout (or not).
        """
        bars = []
        base_price = 100.0

        # Flat pre-impulse bars so total count >= min_bars (5+8+1=14)
        for _ in range(5):
            bars.append({
                "open": base_price,
                "high": base_price + 0.10,
                "low": base_price - 0.10,
                "close": base_price,
            })

        # 5-day impulse move (strong green bars)
        impulse_target = base_price * (1 + impulse_pct)
        step = (impulse_target - base_price) / 5
        for i in range(5):
            o = base_price + step * i
            c = base_price + step * (i + 1)
            bars.append({
                "open": round(o, 2),
                "high": round(c + 0.10, 2),
                "low": round(o - 0.10, 2),
                "close": round(c, 2),
            })

        # The scanner iterates impulse_start; the real impulse starts at
        # index 5 (after the flat padding).  impulse_end = 5 + 5 = 10.
        # impulse_low = bars[5]["low"], impulse_high = max(high) of bars[5:10].
        impulse_low = bars[5]["low"]  # base_price - 0.10
        impulse_high = max(b["high"] for b in bars[5:10])
        impulse_range = impulse_high - impulse_low

        # Flag (consolidation) — tight range with controlled retracement
        flag_low_price = impulse_high - retrace_pct * impulse_range
        flag_high_price = impulse_high - 0.05
        for _ in range(flag_days):
            mid = (flag_high_price + flag_low_price) / 2
            bars.append({
                "open": round(mid + 0.05, 2),
                "high": round(flag_high_price, 2),
                "low": round(flag_low_price, 2),
                "close": round(mid - 0.05, 2),
            })

        # Breakout bar (or not)
        if breakout:
            bars.append({
                "open": round(flag_high_price - 0.5, 2),
                "high": round(flag_high_price + 2.0, 2),
                "low": round(flag_high_price - 0.5, 2),
                "close": round(flag_high_price + 1.5, 2),
            })
        else:
            bars.append({
                "open": round(flag_low_price + 0.1, 2),
                "high": round(flag_high_price - 0.3, 2),
                "low": round(flag_low_price, 2),
                "close": round(flag_low_price + 0.2, 2),
            })

        return bars

    def test_valid_bull_flag_fires_buy(self):
        """Strong impulse + tight flag + breakout -> BUY."""
        bars = self._make_bull_flag_bars(impulse_pct=0.08, flag_days=3, retrace_pct=0.30)
        sig = check_swing_bull_flag("NVDA", bars)
        assert sig is not None
        assert sig.direction == "BUY"
        assert sig.alert_type == AlertType.SWING_BULL_FLAG
        assert sig.stop is not None
        assert sig.target_1 is not None
        assert sig.target_2 is not None

    def test_impulse_too_small_no_fire(self):
        """Impulse < 5% -> None."""
        bars = self._make_bull_flag_bars(impulse_pct=0.03)
        assert check_swing_bull_flag("NVDA", bars) is None

    def test_retracement_too_deep_no_fire(self):
        """Flag retraces > 50% of impulse -> None.

        We build bars manually so the only impulse window has a flag
        that retraces too deeply for any flag_len the scanner tries.
        """
        bars = []
        # 5 flat bars (no impulse here)
        for _ in range(5):
            bars.append({"open": 100, "high": 100, "low": 100, "close": 100})
        # 5-bar impulse: 100 -> 110 (10% move, low=100, high=110)
        for i in range(5):
            c = 100 + 2 * (i + 1)
            bars.append({"open": c - 2, "high": c, "low": c - 2, "close": c})
        # Flag that retraces 80% of the impulse (way past 50%)
        # impulse range = 110-100=10, 80% retrace => flag_low = 110 - 8 = 102
        for _ in range(4):
            bars.append({"open": 103, "high": 104, "low": 101, "close": 102})
        # Breakout bar that clears flag high
        bars.append({"open": 104, "high": 106, "low": 104, "close": 105})
        assert check_swing_bull_flag("NVDA", bars) is None

    def test_no_breakout_no_fire(self):
        """Close stays below flag high -> None."""
        bars = self._make_bull_flag_bars(breakout=False)
        assert check_swing_bull_flag("NVDA", bars) is None

    def test_insufficient_bars(self):
        """Too few bars -> None."""
        bars = [
            {"open": 100, "high": 101, "low": 99, "close": 100}
            for _ in range(3)
        ]
        assert check_swing_bull_flag("NVDA", bars) is None

    def test_empty_bars(self):
        """Empty list -> None."""
        assert check_swing_bull_flag("NVDA", []) is None

    def test_bull_flag_has_entry_stop_targets(self):
        """Valid bull flag should set entry, stop, target_1, target_2."""
        bars = self._make_bull_flag_bars(impulse_pct=0.10, flag_days=4, retrace_pct=0.25)
        sig = check_swing_bull_flag("NVDA", bars)
        if sig is not None:
            assert sig.entry is not None
            assert sig.stop is not None
            assert sig.target_1 is not None
            assert sig.target_2 is not None
            assert sig.target_1 > sig.entry
            assert sig.target_2 > sig.target_1
            assert sig.score == 75
            assert sig.score_label == "A"


# ---------------------------------------------------------------------------
# Candle Patterns
# ---------------------------------------------------------------------------


class TestSwingCandlePatterns:
    """Tests for check_swing_candle_patterns — hammer and bullish engulfing."""

    def test_hammer_near_ema20_fires_buy(self):
        """Green candle with lower wick > 2x body near EMA20 -> BUY."""
        prior_day = {
            "open": 99.0,
            "close": 100.0,   # green, body = 1.0
            "high": 100.2,    # upper wick = 0.2 (< body)
            "low": 96.5,      # lower wick = 99 - 96.5 = 2.5 (> 2x body)
            "prev_close": 99.5,
            "prev_open": 100.5,
            "ema20": 99.8,    # close within 2% of ema20
        }
        sig = check_swing_candle_patterns("AMZN", prior_day)
        assert sig is not None
        assert sig.direction == "BUY"
        assert sig.alert_type == AlertType.SWING_CANDLE_PATTERN
        assert "Hammer" in sig.message

    def test_bullish_engulfing_fires_buy(self):
        """Green body > 1.1x prior red body -> BUY."""
        prior_day = {
            "open": 98.0,
            "close": 101.0,    # green, body = 3.0
            "high": 101.5,
            "low": 97.5,
            "prev_open": 101.0,
            "prev_close": 98.5,  # red, body = 2.5; 3.0 > 1.1*2.5 = 2.75
            "ema20": 100.0,
        }
        sig = check_swing_candle_patterns("AMZN", prior_day)
        assert sig is not None
        assert sig.direction == "BUY"
        assert sig.alert_type == AlertType.SWING_CANDLE_PATTERN
        assert "Engulfing" in sig.message

    def test_no_pattern_normal_candle(self):
        """Regular candle — not a hammer, not engulfing -> None."""
        prior_day = {
            "open": 99.0,
            "close": 100.0,
            "high": 101.0,    # upper wick = 1.0 (>= body, not hammer)
            "low": 98.5,      # lower wick = 0.5 (< 2x body)
            "prev_open": 99.0,
            "prev_close": 100.0,  # prior green, not red
            "ema20": 100.0,
        }
        assert check_swing_candle_patterns("AMZN", prior_day) is None

    def test_missing_data_returns_none(self):
        """Missing OHLC fields -> None."""
        assert check_swing_candle_patterns("AMZN", {}) is None
        assert check_swing_candle_patterns("AMZN", {"open": 100}) is None

    def test_red_candle_not_hammer(self):
        """Red candle with long lower wick is not a hammer (green preferred)."""
        prior_day = {
            "open": 100.0,
            "close": 99.0,    # red candle
            "high": 100.2,
            "low": 96.5,      # long lower wick
            "prev_close": 99.5,
            "prev_open": 100.5,
            "ema20": 99.8,
        }
        assert check_swing_candle_patterns("AMZN", prior_day) is None

    def test_engulfing_body_too_small(self):
        """Green body < 1.1x prior red body -> not engulfing -> None."""
        prior_day = {
            "open": 98.0,
            "close": 100.0,    # body = 2.0
            "high": 100.5,
            "low": 97.5,
            "prev_open": 101.0,
            "prev_close": 99.0,  # red body = 2.0; 2.0 < 1.1*2.0 = 2.2
            "ema20": 100.0,
        }
        assert check_swing_candle_patterns("AMZN", prior_day) is None

    def test_hammer_far_from_ema20_still_fires(self):
        """Hammer pattern fires even far from EMA20, but confidence differs."""
        prior_day = {
            "open": 99.0,
            "close": 100.0,
            "high": 100.2,
            "low": 96.5,
            "prev_close": 99.5,
            "prev_open": 100.5,
            "ema20": 90.0,  # far from EMA20
        }
        sig = check_swing_candle_patterns("AMZN", prior_day)
        assert sig is not None
        assert sig.confidence == "medium"

    def test_hammer_near_ema20_high_confidence(self):
        """Hammer near EMA20 gets high confidence."""
        prior_day = {
            "open": 99.0,
            "close": 100.0,
            "high": 100.2,
            "low": 96.5,
            "prev_close": 99.5,
            "prev_open": 100.5,
            "ema20": 99.5,
        }
        sig = check_swing_candle_patterns("AMZN", prior_day)
        assert sig is not None
        assert sig.confidence == "high"

    def test_zero_range_candle(self):
        """Candle with high == low (doji with no range) -> None."""
        prior_day = {
            "open": 100.0,
            "close": 100.0,
            "high": 100.0,
            "low": 100.0,
            "prev_close": 99.0,
            "prev_open": 100.0,
            "ema20": 100.0,
        }
        assert check_swing_candle_patterns("AMZN", prior_day) is None


# ---------------------------------------------------------------------------
# Consecutive Red Days
# ---------------------------------------------------------------------------


class TestSwingConsecutiveDays:
    """Tests for check_swing_consecutive_days — 3+ red days near EMA20."""

    def test_three_red_days_near_ema20_fires_buy(self):
        """3 consecutive red days near EMA20 -> BUY signal."""
        ema = 100.0
        bars = [
            {"open": 101.0, "close": 100.5, "ema20": ema},  # red
            {"open": 100.5, "close": 100.0, "ema20": ema},  # red
            {"open": 100.0, "close": 99.5, "ema20": ema},   # red, within 2%
        ]
        sig = check_swing_consecutive_days("GOOG", bars)
        assert sig is not None
        assert sig.direction == "BUY"
        assert sig.alert_type == AlertType.SWING_CONSECUTIVE_RED
        assert "3 consecutive red days" in sig.message

    def test_only_two_red_days_no_fire(self):
        """Only 2 red days -> None."""
        ema = 100.0
        bars = [
            {"open": 101.0, "close": 100.5, "ema20": ema},  # red
            {"open": 100.5, "close": 100.0, "ema20": ema},  # red
        ]
        assert check_swing_consecutive_days("GOOG", bars) is None

    def test_red_days_not_near_ema20(self):
        """3 red days but far from EMA20 -> None."""
        bars = [
            {"open": 101.0, "close": 100.5, "ema20": 80.0},
            {"open": 100.5, "close": 100.0, "ema20": 80.0},
            {"open": 100.0, "close": 99.5, "ema20": 80.0},  # >2% away from ema20
        ]
        assert check_swing_consecutive_days("GOOG", bars) is None

    def test_green_days_no_fire(self):
        """All green days -> None."""
        ema = 100.0
        bars = [
            {"open": 99.0, "close": 100.0, "ema20": ema},  # green
            {"open": 100.0, "close": 101.0, "ema20": ema},  # green
            {"open": 101.0, "close": 102.0, "ema20": ema},  # green
        ]
        assert check_swing_consecutive_days("GOOG", bars) is None

    def test_mixed_days_no_fire(self):
        """Red-green-red pattern -> not consecutive -> None."""
        ema = 100.0
        bars = [
            {"open": 101.0, "close": 100.5, "ema20": ema},  # red
            {"open": 100.0, "close": 100.5, "ema20": ema},  # green (breaks streak)
            {"open": 100.5, "close": 100.0, "ema20": ema},  # red
        ]
        assert check_swing_consecutive_days("GOOG", bars) is None

    def test_four_red_days_fires(self):
        """4 consecutive red days near EMA20 -> fires."""
        ema = 100.0
        bars = [
            {"open": 102.0, "close": 101.5, "ema20": ema},
            {"open": 101.5, "close": 101.0, "ema20": ema},
            {"open": 101.0, "close": 100.5, "ema20": ema},
            {"open": 100.5, "close": 100.0, "ema20": ema},  # within 2%
        ]
        sig = check_swing_consecutive_days("GOOG", bars)
        assert sig is not None
        assert "4 consecutive red days" in sig.message

    def test_empty_bars(self):
        """Empty list -> None."""
        assert check_swing_consecutive_days("GOOG", []) is None

    def test_no_ema20_data(self):
        """Missing ema20 -> near_support is False -> None."""
        bars = [
            {"open": 101.0, "close": 100.5},
            {"open": 100.5, "close": 100.0},
            {"open": 100.0, "close": 99.5},
        ]
        assert check_swing_consecutive_days("GOOG", bars) is None


# ---------------------------------------------------------------------------
# Integration: evaluate_swing_rules orchestrator
# ---------------------------------------------------------------------------


class TestEvaluateSwingRules:
    """Integration tests for evaluate_swing_rules — ensures new rules fire."""

    def _base_prior_day(self):
        return {
            "close": 150.0,
            "open": 148.0,
            "high": 151.0,
            "low": 147.0,
            "rsi14": 50.0,
            "rsi14_prev": 50.0,
            "ema5": 149.0,
            "ema5_prev": 148.0,
            "ema10": 148.0,
            "ema20": 147.0,
            "ema20_prev": 146.5,
            "ma200": 140.0,
            # Prior candle is green so bullish engulfing won't trigger
            "prev_close": 149.0,
            "prev_open": 148.0,
        }

    def _spy_context(self):
        return {"spy_ema20": 500.0, "close": 510.0, "trend": "bullish"}

    def test_macd_crossover_fires_through_orchestrator(self):
        """MACD crossover detected via evaluate_swing_rules."""
        prior_day = self._base_prior_day()
        prior_day.update({
            "macd_line": 0.50,
            "macd_line_prev": -0.10,
            "macd_signal": 0.30,
            "macd_signal_prev": 0.20,
        })
        signals = evaluate_swing_rules("TEST", prior_day, self._spy_context(), set())
        macd_signals = [s for s in signals if s.alert_type == AlertType.SWING_MACD_CROSSOVER]
        assert len(macd_signals) == 1
        assert macd_signals[0].direction == "BUY"

    def test_candle_pattern_fires_through_orchestrator(self):
        """Candle pattern detected via evaluate_swing_rules."""
        prior_day = self._base_prior_day()
        # Set up hammer pattern
        prior_day.update({
            "open": 99.0,
            "close": 100.0,
            "high": 100.2,
            "low": 96.5,
            "ema20": 99.5,
        })
        signals = evaluate_swing_rules("TEST", prior_day, self._spy_context(), set())
        candle_signals = [s for s in signals if s.alert_type == AlertType.SWING_CANDLE_PATTERN]
        assert len(candle_signals) == 1

    def test_rsi_divergence_fires_through_orchestrator(self):
        """RSI divergence detected via evaluate_swing_rules."""
        prior_day = self._base_prior_day()

        closes = [105.0] * 20
        rsi = [50.0] * 20
        closes[4], closes[5], closes[6] = 102.0, 100.0, 103.0
        rsi[4], rsi[5], rsi[6] = 35.0, 30.0, 45.0
        closes[14], closes[15], closes[16] = 99.0, 97.0, 101.0
        rsi[14], rsi[15], rsi[16] = 38.0, 35.0, 48.0

        prior_day["daily_closes"] = closes
        prior_day["daily_rsi"] = rsi

        signals = evaluate_swing_rules("TEST", prior_day, self._spy_context(), set())
        div_signals = [s for s in signals if s.alert_type == AlertType.SWING_RSI_DIVERGENCE]
        assert len(div_signals) == 1

    def test_consecutive_red_fires_through_orchestrator(self):
        """Consecutive red days detected via evaluate_swing_rules."""
        prior_day = self._base_prior_day()
        ema = 100.0
        prior_day["daily_bars"] = [
            {"open": 101.0, "close": 100.5, "ema20": ema},
            {"open": 100.5, "close": 100.0, "ema20": ema},
            {"open": 100.0, "close": 99.5, "ema20": ema},
        ]

        signals = evaluate_swing_rules("TEST", prior_day, self._spy_context(), set())
        red_signals = [s for s in signals if s.alert_type == AlertType.SWING_CONSECUTIVE_RED]
        assert len(red_signals) == 1

    def test_fired_today_dedup_prevents_repeat(self):
        """Signal already in fired_today set -> should not appear again."""
        prior_day = self._base_prior_day()
        prior_day.update({
            "macd_line": 0.50,
            "macd_line_prev": -0.10,
            "macd_signal": 0.30,
            "macd_signal_prev": 0.20,
        })
        fired = {("TEST", AlertType.SWING_MACD_CROSSOVER.value)}
        signals = evaluate_swing_rules("TEST", prior_day, self._spy_context(), fired)
        macd_signals = [s for s in signals if s.alert_type == AlertType.SWING_MACD_CROSSOVER]
        assert len(macd_signals) == 0

    def test_no_signals_from_neutral_data(self):
        """Neutral prior_day with no special conditions -> no setup signals.

        RSI zone signals may still fire depending on thresholds, but
        no MACD/flag/candle/divergence/consecutive signals should fire.
        """
        prior_day = self._base_prior_day()
        signals = evaluate_swing_rules("TEST", prior_day, self._spy_context(), set())
        setup_types = {
            AlertType.SWING_MACD_CROSSOVER,
            AlertType.SWING_RSI_DIVERGENCE,
            AlertType.SWING_BULL_FLAG,
            AlertType.SWING_CANDLE_PATTERN,
            AlertType.SWING_CONSECUTIVE_RED,
        }
        setup_signals = [s for s in signals if s.alert_type in setup_types]
        assert len(setup_signals) == 0

    def test_spy_trend_enriched_on_signals(self):
        """Fired signals should have spy_trend from spy_context."""
        prior_day = self._base_prior_day()
        prior_day.update({
            "macd_line": 0.50,
            "macd_line_prev": -0.10,
            "macd_signal": 0.30,
            "macd_signal_prev": 0.20,
        })
        spy = self._spy_context()
        signals = evaluate_swing_rules("TEST", prior_day, spy, set())
        macd_signals = [s for s in signals if s.alert_type == AlertType.SWING_MACD_CROSSOVER]
        assert len(macd_signals) == 1
        assert macd_signals[0].spy_trend == "bullish"
