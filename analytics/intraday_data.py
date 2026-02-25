"""Intraday data fetching — 5-minute bars and prior-day context.

Uses yfinance for both intraday and daily data.
"""

from __future__ import annotations

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
    """Fetch prior day's OHLCV and moving averages.

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
