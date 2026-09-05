"""Tests for the scanner-scope rules: PWH/PMH breakout-retest + RSI 30-35 turn."""

import pandas as pd

from analytics.intraday_rules import (
    AlertType,
    check_level_breakout_retest,
    check_rsi_oversold_turn,
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
