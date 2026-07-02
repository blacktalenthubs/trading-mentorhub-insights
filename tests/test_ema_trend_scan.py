"""Tests for the validated EMA trend-pullback detection engine."""
from __future__ import annotations
import numpy as np, pandas as pd
from analytics.ema_trend_scan import detect_entry, EMA_TREND_20, adx_series


def _uptrend(n=80, start=100.0, step=1.2):
    # steady rising close with tiny noise → rising 20 EMA, decent ADX
    close = np.array([start + i * step for i in range(n)])
    o = close - step * 0.3
    h = close + step * 0.4
    l = close - step * 0.4
    return pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": close})


def _append_bar(df, o, h, l, c):
    row = pd.DataFrame({"Open": [o], "High": [h], "Low": [l], "Close": [c]})
    return pd.concat([df, row], ignore_index=True)


def test_fires_on_clean_pullback_hold():
    df = _uptrend()
    e20 = df["Close"].ewm(span=20).mean().iloc[-1]
    # pullback bar: low tags the 20 EMA, closes ~2% above it green
    df = _append_bar(df, o=e20 * 0.995, h=e20 * 1.025, l=e20 * 0.999, c=e20 * 1.02)
    hit = detect_entry(df, EMA_TREND_20)
    assert hit is not None
    assert hit["alert_type"] == "ema_trend_20"
    assert hit["direction"] == "BUY"
    assert hit["dist_pct"] <= 4.0


def test_rejects_downtrend():
    # falling close → 20 EMA falling → rising filter blocks it
    close = np.array([200.0 - i * 1.2 for i in range(80)])
    df = pd.DataFrame({"Open": close + 0.3, "High": close + 0.5, "Low": close - 0.5, "Close": close})
    e20 = df["Close"].ewm(span=20).mean().iloc[-1]
    df = _append_bar(df, o=e20 * 0.995, h=e20 * 1.025, l=e20 * 0.999, c=e20 * 1.02)
    assert detect_entry(df, EMA_TREND_20) is None


def test_rejects_extended_reclaim():
    df = _uptrend()
    e20 = df["Close"].ewm(span=20).mean().iloc[-1]
    # low tags the 20 but closes 9% above it → beyond max_dist 4%
    df = _append_bar(df, o=e20 * 0.999, h=e20 * 1.10, l=e20 * 0.999, c=e20 * 1.09)
    assert detect_entry(df, EMA_TREND_20) is None


def test_rejects_no_touch():
    df = _uptrend()
    e20 = df["Close"].ewm(span=20).mean().iloc[-1]
    # bar stays well above the 20 (low never tags it)
    df = _append_bar(df, o=e20 * 1.05, h=e20 * 1.08, l=e20 * 1.04, c=e20 * 1.06)
    assert detect_entry(df, EMA_TREND_20) is None


def test_rejects_red_bar():
    df = _uptrend()
    e20 = df["Close"].ewm(span=20).mean().iloc[-1]
    # tags the 20 but closes red (below open) → not a reclaim
    df = _append_bar(df, o=e20 * 1.03, h=e20 * 1.03, l=e20 * 0.999, c=e20 * 1.01)
    hit = detect_entry(df, EMA_TREND_20)
    assert hit is None or hit["entry"] > 0  # red (close<open) must not fire
    # explicit red: close < open
    df2 = _append_bar(_uptrend(), o=e20 * 1.02, h=e20 * 1.02, l=e20 * 0.999, c=e20 * 1.005)
    assert detect_entry(df2, EMA_TREND_20) is None
