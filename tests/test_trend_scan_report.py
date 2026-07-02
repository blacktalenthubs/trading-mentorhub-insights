"""Tests for the read-only Trend Setups briefing classifier."""
from __future__ import annotations
import numpy as np, pandas as pd
from analytics.trend_scan_report import build_trend_report


def _uptrend(n=80, start=100.0, step=1.2):
    close = np.array([start + i * step for i in range(n)])
    return pd.DataFrame({"Open": close - 0.3, "High": close + 0.4, "Low": close - 0.4, "Close": close})


def test_ready_now_when_at_the_line():
    df = _uptrend()
    e20 = df["Close"].ewm(span=20).mean().iloc[-1]
    # last close sits right on the rising 20
    df.iloc[-1, df.columns.get_loc("Close")] = e20 * 1.01
    df.iloc[-1, df.columns.get_loc("Low")] = e20 * 0.999
    rep = build_trend_report(["X"], lambda s: df)
    assert rep["counts"]["ready"] == 1
    assert rep["ready_now"][0]["symbol"] == "X"


def test_extended_when_far_above_line():
    df = _uptrend()
    e20 = df["Close"].ewm(span=20).mean().iloc[-1]
    df.iloc[-1, df.columns.get_loc("Close")] = e20 * 1.10  # 10% above → extended
    df.iloc[-1, df.columns.get_loc("High")] = e20 * 1.11
    rep = build_trend_report(["X"], lambda s: df)
    assert rep["counts"]["extended"] == 1 and rep["counts"]["ready"] == 0


def test_rolling_off_when_below_line():
    close = np.array([200.0 - i * 1.2 for i in range(80)])  # downtrend → below 20
    df = pd.DataFrame({"Open": close + 0.3, "High": close + 0.5, "Low": close - 0.5, "Close": close})
    rep = build_trend_report(["X"], lambda s: df)
    assert rep["counts"]["rolling"] == 1


def test_skips_insufficient_history():
    df = pd.DataFrame({"Open": [1, 2], "High": [1, 2], "Low": [1, 2], "Close": [1, 2]})
    rep = build_trend_report(["X"], lambda s: df)
    assert rep["counts"] == {"ready": 0, "extended": 0, "rolling": 0}
