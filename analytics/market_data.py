"""Shared market data functions — OHLC fetch, day classification, key levels.

Extracted from pages/9_Pre_Market_Planner.py for reuse across pages.
"""

from __future__ import annotations

import logging
import os

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_PERIOD_DAYS = {
    "1d": 1, "5d": 5, "1mo": 30, "3mo": 92, "6mo": 183,
    "1y": 365, "2y": 730, "5y": 1825, "10y": 3650, "ytd": 365, "max": 3650,
}

_ALPACA_TF = {
    "1m": ("Minute", 1), "2m": ("Minute", 2), "5m": ("Minute", 5),
    "15m": ("Minute", 15), "30m": ("Minute", 30),
    "60m": ("Hour", 1), "1h": ("Hour", 1),
    "4h": ("Hour", 4), "1d": ("Day", 1), "1wk": ("Week", 1),
}


def _fetch_ohlc_alpaca(symbol: str, period: str, interval: str) -> pd.DataFrame:
    """Fetch OHLC from Alpaca stocks API. Returns empty on any failure."""
    if os.environ.get("ALPACA_DISABLED", "").lower() in ("1", "true", "yes"):
        return pd.DataFrame()
    key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not secret:
        return pd.DataFrame()
    tf_info = _ALPACA_TF.get(interval)
    if not tf_info:
        return pd.DataFrame()

    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        from datetime import datetime, timedelta

        unit_str, amount = tf_info
        unit = getattr(TimeFrameUnit, unit_str)
        tf = TimeFrame(amount, unit)

        days = _PERIOD_DAYS.get(period, 90)
        client = StockHistoricalDataClient(key, secret)
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf,
            start=datetime.now() - timedelta(days=days),
            feed="iex",
        )
        bars = client.get_stock_bars(req)
        df = bars.df
        if df.empty:
            return pd.DataFrame()

        df = df.reset_index(level="symbol", drop=True)
        if df.index.tz is not None:
            df.index = df.index.tz_convert(None)
        df = df.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        })
        return df[["Open", "High", "Low", "Close", "Volume"]].copy()
    except Exception as e:
        logger.info("Alpaca OHLC fetch failed for %s %s/%s: %s",
                    symbol, period, interval, str(e)[:80])
        return pd.DataFrame()


def fetch_ohlc(
    symbol: str, period: str = "3mo", interval: str = "1d",
) -> pd.DataFrame:
    """Fetch OHLC data — Alpaca primary, Coinbase crypto, yfinance fallback.

    Returns DataFrame with Open, High, Low, Close, Volume columns.
    Returns empty DataFrame on failure.
    """
    from config import is_crypto_alert_symbol

    # Crypto — Coinbase primary (reliable), yfinance fallback
    if is_crypto_alert_symbol(symbol):
        df = _fetch_ohlc_coinbase(symbol, period, interval)
        if not df.empty:
            return df
        # Fall through to yfinance

    # Equity — Alpaca primary (Yahoo rate-limits Railway IPs constantly)
    else:
        df = _fetch_ohlc_alpaca(symbol, period, interval)
        if not df.empty:
            return df
        # Fall through to yfinance

    # yfinance last resort
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)
        if hist.empty:
            return pd.DataFrame()
        if hist.index.tz is not None:
            hist.index = hist.index.tz_convert(None)
        return hist[["Open", "High", "Low", "Close", "Volume"]].copy()
    except Exception:
        return pd.DataFrame()


def _fetch_ohlc_coinbase(symbol: str, period: str, interval: str) -> pd.DataFrame:
    """Fetch OHLCV from Coinbase for crypto symbols."""
    import requests
    import logging
    from datetime import datetime, timedelta, timezone

    _gran_map = {
        "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
        "60m": 3600, "1h": 3600, "4h": 14400,
        "1d": 86400, "1wk": 604800,
    }
    _period_days = {
        "1d": 1, "5d": 5, "1mo": 30, "3mo": 90,
        "6mo": 180, "1y": 365, "2y": 730, "5y": 1825,
    }

    granularity = _gran_map.get(interval)
    days = _period_days.get(period, 90)
    if not granularity:
        return pd.DataFrame()

    try:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        # Coinbase max 300 candles per request — limit range if needed
        max_candles = 300
        min_start = end - timedelta(seconds=granularity * max_candles)
        if start < min_start:
            start = min_start

        url = f"https://api.exchange.coinbase.com/products/{symbol}/candles"
        resp = requests.get(url, params={
            "start": start.isoformat(), "end": end.isoformat(),
            "granularity": granularity,
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data, columns=["timestamp", "Low", "High", "Open", "Close", "Volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
        df = df.sort_values("timestamp").set_index("timestamp")
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        # Strip timezone for consistency with yfinance path
        if df.index.tz is not None:
            df.index = df.index.tz_convert(None)
        return df
    except Exception:
        logging.getLogger("market_data").warning(
            "Coinbase OHLC fetch failed for %s — falling back to yfinance", symbol,
        )
        return pd.DataFrame()


def classify_day(row, prev_row) -> tuple[str, str]:
    """Classify a candle relative to previous day.

    Returns (pattern, direction) where:
        pattern: "inside" | "outside" | "normal"
        direction: "bullish" | "bearish" | "neutral"
    """
    if prev_row is None:
        return "normal", "—"

    curr_h, curr_l = row["High"], row["Low"]
    prev_h, prev_l = prev_row["High"], prev_row["Low"]

    is_inside = curr_h <= prev_h and curr_l >= prev_l
    is_outside = curr_h > prev_h and curr_l < prev_l

    day_range = curr_h - curr_l
    if day_range > 0:
        close_position = (row["Close"] - curr_l) / day_range
    else:
        close_position = 0.5

    if close_position >= 0.6:
        direction = "bullish"
    elif close_position <= 0.4:
        direction = "bearish"
    else:
        direction = "neutral"

    if is_inside:
        return "inside", direction
    elif is_outside:
        return "outside", direction
    else:
        return "normal", direction


def get_levels(hist: pd.DataFrame, idx: int) -> dict:
    """Calculate key trading levels for the next session based on candle pattern."""
    row = hist.iloc[idx]
    prev_row = hist.iloc[idx - 1] if idx > 0 else None

    pattern, direction = classify_day(row, prev_row)

    levels = {
        "pattern": pattern,
        "direction": direction,
        "prior_high": row["High"],
        "prior_low": row["Low"],
        "prior_close": row["Close"],
        "prior_open": row["Open"],
        "prior_range": row["High"] - row["Low"],
        "prior_mid": (row["High"] + row["Low"]) / 2,
    }

    if prev_row is not None:
        levels["parent_high"] = prev_row["High"]
        levels["parent_low"] = prev_row["Low"]
        levels["parent_range"] = prev_row["High"] - prev_row["Low"]
        levels["parent_mid"] = (prev_row["High"] + prev_row["Low"]) / 2

    if pattern == "inside":
        parent_h = prev_row["High"] if prev_row is not None else row["High"]
        parent_l = prev_row["Low"] if prev_row is not None else row["Low"]
        inside_h = row["High"]
        inside_l = row["Low"]

        levels["entry_long"] = inside_h
        levels["stop_long"] = inside_l
        levels["target_1"] = inside_h + (inside_h - inside_l)
        levels["target_2"] = inside_h + (parent_h - parent_l)
        levels["risk_per_share"] = inside_h - inside_l
        levels["notes"] = (
            f"Inside day — range ${row['High'] - row['Low']:,.2f} inside "
            f"parent range ${parent_h - parent_l:,.2f}. "
            f"Tight stop at inside low. Wait for breakout above ${inside_h:,.2f}. "
            f"Good R:R setup for day trade."
        )
        if direction == "bullish":
            levels["bias"] = "Bullish — inside day closed strong, breakout up more likely"
        elif direction == "bearish":
            levels["bias"] = "Bearish lean — inside day closed weak, be cautious on long breakout"
        else:
            levels["bias"] = "Neutral — wait for the breakout direction"

    elif pattern == "outside":
        levels["entry_long"] = levels["prior_mid"]
        levels["stop_long"] = row["Low"]
        levels["target_1"] = row["High"]
        levels["target_2"] = row["High"] + (row["High"] - levels["prior_mid"])
        levels["risk_per_share"] = levels["prior_mid"] - row["Low"]
        levels["notes"] = (
            f"Outside day — range ${row['High'] - row['Low']:,.2f} engulfs prior day. "
            f"Wide range means wide stops. Consider half-size position. "
            f"Wait for pullback to midpoint ${levels['prior_mid']:,.2f} before entry."
        )
        if direction == "bullish":
            levels["bias"] = (
                "Closed bullish (upper range) — continuation likely. "
                "Buy pullback to midpoint, stop below midpoint."
            )
            levels["alt_stop"] = levels["prior_mid"] - (row["High"] - levels["prior_mid"]) * 0.5
            levels["alt_notes"] = (
                f"Tighter stop option: ${levels['alt_stop']:,.2f} "
                f"(below midpoint by half the upper range). Reduces risk but may get stopped on normal pullback."
            )
        elif direction == "bearish":
            levels["bias"] = (
                "Closed bearish (lower range) — reversal/continuation down likely. "
                "AVOID longs or wait for very strong support. Consider sitting out."
            )
        else:
            levels["bias"] = (
                "Closed neutral — no clear direction. Chop likely. "
                "Trade smaller or wait for next day's setup."
            )

    else:
        levels["entry_long"] = row["Low"]
        levels["stop_long"] = row["Low"] - (row["High"] - row["Low"]) * 0.25
        levels["target_1"] = row["High"]
        levels["target_2"] = row["High"] + (row["High"] - row["Low"]) * 0.5
        levels["risk_per_share"] = row["Low"] - levels["stop_long"]
        levels["notes"] = (
            f"Normal day — range ${row['High'] - row['Low']:,.2f}. "
            f"Trade prior day H/L as support/resistance."
        )
        if direction == "bullish":
            levels["bias"] = "Closed bullish — look for pullback to prior day low for long entry"
        elif direction == "bearish":
            levels["bias"] = "Closed bearish — prior day low may break, be defensive"
        else:
            levels["bias"] = "Neutral close — trade the range, buy low sell high"

    return levels
