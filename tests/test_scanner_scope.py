"""Tests for the scanner-scope rules: PWH/PMH breakout-retest + RSI 30-35 turn."""

import pandas as pd

from analytics.intraday_rules import (
    AlertType,
    check_level_breakout_retest,
    check_rsi_oversold_turn,
    check_swing_2h_reclaims,
)


def _bars(rows):
    return pd.DataFrame([{"Open": o, "High": h, "Low": l, "Close": c, "Volume": 1000}
                         for o, h, l, c in rows])


# ── PWH / PMH breakout-retest ────────────────────────────────────────────────
def test_breakout_retest_qualifies():
    lvl = 100.0
    bars = _bars([(98, 99, 97, 98),          # below the level
                  (98, 100.6, 98, 100.3),    # broke above (close > level)
                  (100.3, 100.5, 100.0, 100.2)])  # retested (low→level) & held above
    sig = check_level_breakout_retest("X", bars, lvl, "PWH", AlertType.PWH_BREAKOUT_RETEST)
    assert sig is not None
    assert sig.alert_type == AlertType.PWH_BREAKOUT_RETEST
    assert sig.direction == "BUY"
    assert "PWH" in sig.message


def test_breakout_retest_rejects_no_breakout():
    lvl = 100.0
    bars = _bars([(98, 99.5, 97, 99), (99, 99.8, 98.5, 99.2), (99.2, 99.9, 98.8, 99.5)])
    assert check_level_breakout_retest("X", bars, lvl, "PWH", AlertType.PWH_BREAKOUT_RETEST) is None


def test_breakout_retest_rejects_not_holding():
    lvl = 100.0
    bars = _bars([(98, 99, 97, 98), (98, 100.6, 98, 100.3), (100.3, 100.4, 99.0, 99.5)])
    assert check_level_breakout_retest("X", bars, lvl, "PMH", AlertType.PMH_BREAKOUT_RETEST) is None


# ── RSI 30-35 oversold turn ──────────────────────────────────────────────────
def test_rsi_turn_qualifies():
    bars = _bars([(50, 51, 49, 50), (50, 51, 49.5, 50.5)])
    sig = check_rsi_oversold_turn("X", bars, rsi14=32.0, rsi14_prev=28.0)
    assert sig is not None
    assert sig.alert_type == AlertType.RSI_30_35
    assert sig.direction == "BUY"


def test_rsi_turn_rejects_not_from_below_30():
    bars = _bars([(50, 51, 49, 50)])
    # prior RSI already above 30 → not a reclaim from oversold
    assert check_rsi_oversold_turn("X", bars, rsi14=33.0, rsi14_prev=32.0) is None


def test_rsi_turn_rejects_above_zone():
    bars = _bars([(50, 51, 49, 50)])
    assert check_rsi_oversold_turn("X", bars, rsi14=40.0, rsi14_prev=28.0) is None


def test_rsi_turn_rejects_still_oversold():
    bars = _bars([(50, 51, 49, 50)])
    assert check_rsi_oversold_turn("X", bars, rsi14=28.0, rsi14_prev=25.0) is None


def test_rsi_turn_bad_inputs():
    bars = _bars([(50, 51, 49, 50)])
    assert check_rsi_oversold_turn("X", bars, None, 28.0) is None
    assert check_rsi_oversold_turn("X", _bars([]), 32.0, 28.0) is None


# ── 2-hour swing reclaim ─────────────────────────────────────────────────────
def test_swing_2h_reclaim_qualifies_8wema():
    prior_day = {"wema8": 100.0, "wema21": 90.0, "w30": 80.0, "ma200": 70.0}
    # 2h candle: day opened above 100 (via today_open), wicked to 100, closed above
    bars = _bars([(101, 102, 99.9, 100.5), (100.5, 101, 100.2, 100.6)])
    sigs = check_swing_2h_reclaims("X", bars, prior_day, today_open=101.0)
    assert any(s.alert_type == AlertType.SWING_RECLAIM_8WEMA for s in sigs)
    # 21wema (90): never wicked to it (low 99.9 > 90) → no signal
    assert not any(s.alert_type == AlertType.SWING_RECLAIM_21WEMA for s in sigs)
    assert all("2h swing" in s.message for s in sigs)


def test_swing_2h_reclaim_bad_inputs():
    assert check_swing_2h_reclaims("X", _bars([]), {"wema8": 100.0}, 101.0) == []
    assert check_swing_2h_reclaims("X", _bars([(1, 1, 1, 1)]), None, 1.0) == []
