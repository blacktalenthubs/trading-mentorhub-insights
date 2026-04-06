"""Tests for new Spec 14 swing entry rules."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Load swing_rules directly to avoid app.py collision
_api_dir = Path(__file__).resolve().parents[1] / "api"
_root = Path(__file__).resolve().parents[1]

# Need alert_config and analytics on path
if str(_root) not in sys.path:
    sys.path.append(str(_root))


class TestSwingRsi30Bounce:
    """Test check_swing_rsi_30_bounce rule."""

    def _make_prior_day(self, rsi=31, rsi_prev=28, close=100, high=101, low=98, **kwargs):
        pd = {
            "rsi14": rsi, "rsi14_prev": rsi_prev,
            "close": close, "high": high, "low": low,
            "open": 99, "prev_close": 97,
            "ma200": 95, "ema200": 95,
            "ema50": 98, "ma50": 98,
            "ema20": 99, "ema20_prev": 98.5,
        }
        pd.update(kwargs)
        return pd

    def test_fires_on_rsi_cross_above_30(self):
        from analytics.swing_rules import check_swing_rsi_30_bounce
        pd = self._make_prior_day(rsi=31, rsi_prev=28, close=100, high=101, low=98)
        sig = check_swing_rsi_30_bounce("AAPL", pd)
        assert sig is not None
        assert sig.direction == "BUY"
        assert "RSI 30 bounce" in sig.message

    def test_no_fire_rsi_still_below_30(self):
        from analytics.swing_rules import check_swing_rsi_30_bounce
        pd = self._make_prior_day(rsi=28, rsi_prev=25)
        sig = check_swing_rsi_30_bounce("AAPL", pd)
        assert sig is None

    def test_no_fire_rsi_was_already_above_30(self):
        from analytics.swing_rules import check_swing_rsi_30_bounce
        pd = self._make_prior_day(rsi=35, rsi_prev=32)
        sig = check_swing_rsi_30_bounce("AAPL", pd)
        assert sig is None

    def test_no_fire_close_in_lower_half(self):
        from analytics.swing_rules import check_swing_rsi_30_bounce
        # close in lower half of range = no buying pressure
        pd = self._make_prior_day(rsi=31, rsi_prev=28, close=98.5, high=101, low=98)
        sig = check_swing_rsi_30_bounce("AAPL", pd)
        assert sig is None

    def test_score_boost_near_200ma(self):
        from analytics.swing_rules import check_swing_rsi_30_bounce
        pd = self._make_prior_day(rsi=31, rsi_prev=28, close=96, high=97, low=94, ma200=95)
        sig = check_swing_rsi_30_bounce("AAPL", pd)
        assert sig is not None
        assert sig.score >= 80  # base 60 + 20 for near 200MA


class TestSwing200maHold:
    """Test check_swing_200ma_hold rule."""

    def _make_prior_day(self, **kwargs):
        pd = {
            "close": 100, "low": 96, "high": 101, "open": 98,
            "prev_close": 101, "ma200": 96, "ema200": 96,
            "ema50": 105, "ema20": 108,
            "rsi14": 38,
        }
        pd.update(kwargs)
        return pd

    def test_fires_on_wick_to_200ma(self):
        from analytics.swing_rules import check_swing_200ma_hold
        pd = self._make_prior_day(close=100, low=96, ma200=96, prev_close=101)
        sig = check_swing_200ma_hold("AAPL", pd)
        assert sig is not None
        assert "200MA hold" in sig.message

    def test_no_fire_close_below_200ma(self):
        from analytics.swing_rules import check_swing_200ma_hold
        pd = self._make_prior_day(close=95, low=94, ma200=96)
        sig = check_swing_200ma_hold("AAPL", pd)
        assert sig is None

    def test_no_fire_prev_was_below_200ma(self):
        from analytics.swing_rules import check_swing_200ma_hold
        pd = self._make_prior_day(close=100, low=96, ma200=96, prev_close=95)
        sig = check_swing_200ma_hold("AAPL", pd)
        assert sig is None

    def test_no_fire_low_too_far_from_200ma(self):
        from analytics.swing_rules import check_swing_200ma_hold
        pd = self._make_prior_day(close=100, low=99, ma200=96)
        sig = check_swing_200ma_hold("AAPL", pd)
        assert sig is None


class TestSwing50maHold:
    """Test check_swing_50ma_hold rule."""

    def _make_prior_day(self, **kwargs):
        pd = {
            "close": 100, "low": 98, "high": 101, "open": 99,
            "ema50": 98, "ma50": 98, "ema20": 102,
            "rsi14": 42,
        }
        pd.update(kwargs)
        return pd

    def test_fires_on_wick_to_50ma(self):
        from analytics.swing_rules import check_swing_50ma_hold
        pd = self._make_prior_day()
        sig = check_swing_50ma_hold("AAPL", pd)
        assert sig is not None
        assert "50MA hold" in sig.message

    def test_no_fire_close_below_50ma(self):
        from analytics.swing_rules import check_swing_50ma_hold
        pd = self._make_prior_day(close=97)
        sig = check_swing_50ma_hold("AAPL", pd)
        assert sig is None

    def test_no_fire_downtrend(self):
        from analytics.swing_rules import check_swing_50ma_hold
        # ema20 below ema50 = downtrend
        pd = self._make_prior_day(ema20=96)
        sig = check_swing_50ma_hold("AAPL", pd)
        assert sig is None


class TestSwingWeeklySupport:
    """Test check_swing_weekly_support rule."""

    def _make_prior_day(self, **kwargs):
        pd = {
            "close": 100, "low": 96, "high": 101, "open": 98,
            "prior_week_low": 96, "prior_week_high": 110,
            "rsi14": 38, "ma200": 95,
        }
        pd.update(kwargs)
        return pd

    def test_fires_on_weekly_support_hold(self):
        from analytics.swing_rules import check_swing_weekly_support
        pd = self._make_prior_day()
        sig = check_swing_weekly_support("AAPL", pd)
        assert sig is not None
        assert "Weekly support" in sig.message

    def test_no_fire_close_below_weekly_low(self):
        from analytics.swing_rules import check_swing_weekly_support
        pd = self._make_prior_day(close=95)
        sig = check_swing_weekly_support("AAPL", pd)
        assert sig is None

    def test_no_fire_low_too_far(self):
        from analytics.swing_rules import check_swing_weekly_support
        pd = self._make_prior_day(low=100)  # low is 4% above PWL
        sig = check_swing_weekly_support("AAPL", pd)
        assert sig is None


class TestSwingNotifierFormat:
    """Test that swing alerts format correctly for Telegram."""

    def test_swing_buy_formats_with_swing_label(self):
        from analytics.intraday_rules import AlertSignal, AlertType
        from alerting.notifier import _format_sms_body
        sig = AlertSignal(
            symbol="AAPL",
            alert_type=AlertType.SWING_RSI_30_BOUNCE,
            direction="BUY",
            price=100.0,
            entry=100.0,
            stop=97.0,
            target_1=106.0,
            score=70,
            message="[SWING] RSI 30 bounce — RSI 29 → 31",
        )
        body = _format_sms_body(sig)
        assert body is not None
        assert "SWING LONG" in body
        assert "Entry $100.00" in body

    def test_swing_exit_formats_correctly(self):
        from analytics.intraday_rules import AlertSignal, AlertType
        from alerting.notifier import _format_sms_body
        sig = AlertSignal(
            symbol="AAPL",
            alert_type=AlertType.SWING_TARGET_HIT,
            direction="SELL",
            price=106.0,
            message="[SWING] Target hit — RSI 72",
        )
        body = _format_sms_body(sig)
        assert body is not None
        assert "SWING EXIT" in body

    def test_swing_rsi_notice_formats(self):
        from analytics.intraday_rules import AlertSignal, AlertType
        from alerting.notifier import _format_sms_body
        sig = AlertSignal(
            symbol="AAPL",
            alert_type=AlertType.SWING_RSI_OVERSOLD,
            direction="BUY",
            price=95.0,
            message="[SWING] RSI oversold — 32 → 28",
        )
        body = _format_sms_body(sig)
        assert body is not None
        assert "SWING NOTICE" in body
