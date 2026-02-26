"""Intraday data fetching — 5-minute bars and prior-day context.

Uses yfinance for both intraday and daily data.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import yfinance as yf


def fetch_intraday(symbol: str, period: str = "1d", interval: str = "5m") -> pd.DataFrame:
    """Fetch intraday bars for a symbol.

    Returns DataFrame with Open, High, Low, Close, Volume columns.
    Index is timezone-naive datetime. Returns empty DataFrame on failure.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)
        if hist.empty:
            return pd.DataFrame()
        hist.index = hist.index.tz_localize(None)
        return hist[["Open", "High", "Low", "Close", "Volume"]].copy()
    except Exception:
        return pd.DataFrame()


def fetch_prior_day(symbol: str) -> dict | None:
    """Fetch the PRIOR COMPLETED trading day's data.

    During market hours the last bar from yfinance is today's partial data,
    so we use iloc[-2] (yesterday) and iloc[-3] (day before).
    After close the last bar is the completed day, so iloc[-1] and iloc[-2].

    Returns dict with keys: open, high, low, close, volume, ma20, ma50,
    pattern, direction, parent_high, parent_low.
    Returns None on failure.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="3mo")
        if hist.empty or len(hist) < 3:
            return None
        hist.index = hist.index.tz_localize(None)
        hist = hist[["Open", "High", "Low", "Close", "Volume"]].copy()

        # Compute MAs on full history
        hist["MA20"] = hist["Close"].rolling(window=20).mean()
        hist["MA50"] = hist["Close"].rolling(window=50).mean()

        # Date-aware selection: if last bar is today, it's partial
        today = pd.Timestamp.now().normalize()
        last_bar_date = hist.index[-1].normalize()

        if last_bar_date >= today:
            # Market is open — last bar is today's partial data
            if len(hist) < 4:
                return None
            last = hist.iloc[-2]  # yesterday (prior completed day)
            prev = hist.iloc[-3]  # day before yesterday
        else:
            # Market closed — last bar is the completed day
            last = hist.iloc[-1]
            prev = hist.iloc[-2]

        ma20 = last["MA20"] if pd.notna(last["MA20"]) else None
        ma50 = last["MA50"] if pd.notna(last["MA50"]) else None

        # Classify the prior day using market_data.classify_day
        from analytics.market_data import classify_day
        pattern, direction = classify_day(last, prev)

        # Check if prior day was an inside day
        is_inside = last["High"] <= prev["High"] and last["Low"] >= prev["Low"]

        return {
            "open": last["Open"],
            "high": last["High"],
            "low": last["Low"],
            "close": last["Close"],
            "volume": last["Volume"],
            "ma20": ma20,
            "ma50": ma50,
            "pattern": pattern,
            "direction": direction,
            "is_inside": is_inside,
            "parent_high": prev["High"],
            "parent_low": prev["Low"],
            "parent_range": prev["High"] - prev["Low"],
        }
    except Exception:
        return None


@st.cache_data(ttl=300)
def get_spy_context() -> dict:
    """Fetch SPY trend data for market context (cached 5 min)."""
    try:
        spy = yf.Ticker("SPY")
        hist = spy.history(period="1mo")
        if hist.empty or len(hist) < 20:
            return {"trend": "neutral", "close": 0.0, "ma20": 0.0}
        ma20 = hist["Close"].rolling(20).mean().iloc[-1]
        close = hist["Close"].iloc[-1]
        trend = "bullish" if close > ma20 else "bearish"
        return {"trend": trend, "close": round(close, 2), "ma20": round(ma20, 2)}
    except Exception:
        return {"trend": "neutral", "close": 0.0, "ma20": 0.0}


def compute_vwap(bars: pd.DataFrame) -> pd.Series:
    """Compute VWAP from intraday OHLCV bars."""
    if bars.empty or "Volume" not in bars.columns:
        return pd.Series(dtype=float)
    typical = (bars["High"] + bars["Low"] + bars["Close"]) / 3
    cum_vol = bars["Volume"].cumsum()
    cum_tp_vol = (typical * bars["Volume"]).cumsum()
    return cum_tp_vol / cum_vol


def classify_gap(today_open: float, prior_close: float, prior_range: float) -> dict:
    """Classify gap type and size."""
    if prior_close <= 0:
        return {"type": "flat", "gap_pct": 0.0}
    gap_pct = (today_open - prior_close) / prior_close * 100
    if abs(gap_pct) < 0.3:
        return {"type": "flat", "gap_pct": round(gap_pct, 2)}
    if gap_pct > 0:
        return {"type": "gap_up", "gap_pct": round(gap_pct, 2)}
    return {"type": "gap_down", "gap_pct": round(gap_pct, 2)}
