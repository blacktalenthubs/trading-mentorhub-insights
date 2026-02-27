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
    """Fetch SPY trend data for market context (cached 5 min).

    Returns dict with trend, close, ma20, and intraday_change_pct.
    """
    try:
        spy = yf.Ticker("SPY")
        hist = spy.history(period="1mo")
        if hist.empty or len(hist) < 20:
            return {"trend": "neutral", "close": 0.0, "ma20": 0.0, "intraday_change_pct": 0.0}
        ma20 = hist["Close"].rolling(20).mean().iloc[-1]
        close = hist["Close"].iloc[-1]
        trend = "bullish" if close > ma20 else "bearish"

        # Compute SPY intraday % change from today's bars
        intraday_change_pct = 0.0
        try:
            spy_intra = spy.history(period="1d", interval="5m")
            if not spy_intra.empty and len(spy_intra) >= 2:
                spy_open = spy_intra["Open"].iloc[0]
                spy_current = spy_intra["Close"].iloc[-1]
                if spy_open > 0:
                    intraday_change_pct = (spy_current - spy_open) / spy_open * 100
        except Exception:
            pass

        return {
            "trend": trend,
            "close": round(close, 2),
            "ma20": round(ma20, 2),
            "intraday_change_pct": round(intraday_change_pct, 2),
        }
    except Exception:
        return {"trend": "neutral", "close": 0.0, "ma20": 0.0, "intraday_change_pct": 0.0}


def compute_vwap(bars: pd.DataFrame) -> pd.Series:
    """Compute VWAP from intraday OHLCV bars."""
    if bars.empty or "Volume" not in bars.columns:
        return pd.Series(dtype=float)
    typical = (bars["High"] + bars["Low"] + bars["Close"]) / 3
    cum_vol = bars["Volume"].cumsum()
    cum_tp_vol = (typical * bars["Volume"]).cumsum()
    return cum_tp_vol / cum_vol


def detect_intraday_supports(bars_5m: pd.DataFrame, min_bounce_pct: float = 0.002) -> list[float]:
    """Find intraday support levels from hourly lows that held.

    Resamples 5-min bars to 1-hour, identifies hourly lows where
    the next hour's low stayed above and price bounced.
    """
    if bars_5m.empty or len(bars_5m) < 12:  # need at least 1 hour of data
        return []

    hourly = bars_5m.resample("1h").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }).dropna()

    supports = []
    for i in range(len(hourly) - 1):
        hour_low = hourly["Low"].iloc[i]
        next_low = hourly["Low"].iloc[i + 1]
        next_close = hourly["Close"].iloc[i + 1]
        # Low held: next hour didn't break it, and price bounced
        bounce = (next_close - hour_low) / hour_low if hour_low > 0 else 0
        if next_low >= hour_low * 0.999 and bounce >= min_bounce_pct:
            supports.append(round(hour_low, 2))

    return supports


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


def compute_opening_range(bars_5m: pd.DataFrame) -> dict | None:
    """Compute the opening range from the first 30 minutes of 5-min bars.

    Takes first 6 bars (6 * 5min = 30 minutes: 9:30-10:00).
    Returns dict with or_high, or_low, or_range, or_range_pct, or_complete.
    Returns None if fewer than 6 bars.
    """
    if bars_5m.empty or len(bars_5m) < 6:
        return None

    or_bars = bars_5m.iloc[:6]
    or_high = or_bars["High"].max()
    or_low = or_bars["Low"].min()
    or_range = or_high - or_low
    or_range_pct = or_range / or_low if or_low > 0 else 0.0

    return {
        "or_high": or_high,
        "or_low": or_low,
        "or_range": or_range,
        "or_range_pct": or_range_pct,
        "or_complete": len(bars_5m) >= 6,
    }


def check_mtf_alignment(bars_5m: pd.DataFrame) -> dict:
    """Check multi-timeframe alignment by resampling 5-min to 15-min.

    Computes EMA5 and EMA20 on 15-min closes. A single day gives ~26
    fifteen-minute bars — enough for EMA20.

    Returns dict with mtf_aligned, ema5_15m, ema20_15m, mtf_trend.
    """
    result = {"mtf_aligned": False, "ema5_15m": 0.0, "ema20_15m": 0.0, "mtf_trend": "neutral"}

    if bars_5m.empty or len(bars_5m) < 15:  # need at least 5 fifteen-min bars
        return result

    bars_15m = bars_5m.resample("15min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }).dropna()

    if len(bars_15m) < 5:
        return result

    ema5 = bars_15m["Close"].ewm(span=5, adjust=False).mean()
    ema20 = bars_15m["Close"].ewm(span=20, adjust=False).mean()

    ema5_val = ema5.iloc[-1]
    ema20_val = ema20.iloc[-1]
    aligned = ema5_val > ema20_val

    return {
        "mtf_aligned": bool(aligned),
        "ema5_15m": round(ema5_val, 2),
        "ema20_15m": round(ema20_val, 2),
        "mtf_trend": "bullish" if aligned else "bearish",
    }


def track_gap_fill(bars_5m: pd.DataFrame, today_open: float, prior_close: float) -> dict:
    """Track gap fill progress throughout the day.

    Returns dict with gap_size, gap_pct, gap_direction, fill_pct, is_filled.
    """
    result = {
        "gap_size": 0.0, "gap_pct": 0.0, "gap_direction": "flat",
        "fill_pct": 0.0, "is_filled": False,
    }

    if prior_close <= 0 or bars_5m.empty:
        return result

    gap_size = today_open - prior_close
    gap_pct = gap_size / prior_close * 100

    if abs(gap_pct) < 0.3:
        result["gap_direction"] = "flat"
        return result

    result["gap_size"] = gap_size
    result["gap_pct"] = round(gap_pct, 2)

    if gap_size > 0:
        # Gap up: fills when any bar low <= prior_close
        result["gap_direction"] = "gap_up"
        min_low = bars_5m["Low"].min()
        if min_low <= prior_close:
            result["is_filled"] = True
            result["fill_pct"] = 100.0
        else:
            filled = today_open - min_low
            result["fill_pct"] = round(filled / gap_size * 100, 1) if gap_size > 0 else 0.0
    else:
        # Gap down: fills when any bar high >= prior_close
        result["gap_direction"] = "gap_down"
        max_high = bars_5m["High"].max()
        if max_high >= prior_close:
            result["is_filled"] = True
            result["fill_pct"] = 100.0
        else:
            filled = max_high - today_open
            result["fill_pct"] = round(filled / abs(gap_size) * 100, 1) if gap_size != 0 else 0.0

    return result


def fetch_historical_intraday(
    symbol: str, target_date: str, interval: str = "5m",
) -> pd.DataFrame:
    """Fetch historical intraday bars for a specific date.

    Uses yfinance with explicit start/end dates. yfinance keeps ~59 days
    of intraday data.

    Args:
        symbol: Ticker symbol.
        target_date: ISO date string (e.g., "2025-05-01").
        interval: Bar interval (default "5m").

    Returns DataFrame with OHLCV columns, or empty DataFrame on failure.
    """
    try:
        start = pd.Timestamp(target_date)
        end = start + pd.Timedelta(days=1)
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start, end=end, interval=interval)
        if hist.empty:
            return pd.DataFrame()
        hist.index = hist.index.tz_localize(None)
        return hist[["Open", "High", "Low", "Close", "Volume"]].copy()
    except Exception:
        return pd.DataFrame()
