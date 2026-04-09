"""Multi-timeframe confluence scoring.

Checks daily, 4H, and intraday trend alignment for a given symbol.
Returns a score of 0-3 indicating how many timeframes agree on direction.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import yfinance as yf
import pandas as pd

logger = logging.getLogger("confluence")


def _trend_direction(df: pd.DataFrame, ema_fast: int = 20, ema_slow: int = 50) -> Optional[str]:
    """Determine trend direction from OHLCV dataframe.

    Returns "bullish", "bearish", or None if indeterminate.
    Uses:
      - Price vs EMA20 (short-term trend)
      - EMA20 vs EMA50 (medium-term trend)
      - Last 3 closes trending up/down
    """
    if df is None or len(df) < ema_slow + 5:
        return None

    close = df["Close"]
    ema_f = close.ewm(span=ema_fast, adjust=False).mean()
    ema_s = close.ewm(span=ema_slow, adjust=False).mean()

    last_close = float(close.iloc[-1])
    last_ema_f = float(ema_f.iloc[-1])
    last_ema_s = float(ema_s.iloc[-1])

    # Scoring: price > EMA20 (+1), EMA20 > EMA50 (+1), last 3 closes rising (+1)
    bullish_pts = 0
    if last_close > last_ema_f:
        bullish_pts += 1
    if last_ema_f > last_ema_s:
        bullish_pts += 1

    # Check last 3 closes trending
    recent = close.iloc[-3:].values
    if len(recent) == 3:
        if recent[2] > recent[1] > recent[0]:
            bullish_pts += 1
        elif recent[2] < recent[1] < recent[0]:
            bullish_pts -= 1

    if bullish_pts >= 2:
        return "bullish"
    elif bullish_pts <= 0:
        return "bearish"
    return None  # mixed / indeterminate


def compute_confluence(
    symbol: str,
    intraday_direction: str,
) -> Tuple[int, str]:
    """Compute multi-timeframe confluence for a symbol.

    Args:
        symbol: Ticker symbol (e.g., "SPY", "ETH-USD")
        intraday_direction: "BUY" or "SHORT" from the alert

    Returns:
        (score, label) where score is 0-3 and label describes alignment.
    """
    # Normalize intraday direction
    intraday_trend = "bullish" if intraday_direction in ("BUY", "LONG", "Bullish") else "bearish"

    score = 1  # intraday signal counts as 1
    timeframes_aligned = ["intraday"]

    try:
        # Fetch daily data (6 months for reliable EMAs)
        daily = yf.download(symbol, period="6mo", interval="1d", progress=False)
        if hasattr(daily.columns, "droplevel") and isinstance(daily.columns, pd.MultiIndex):
            daily.columns = daily.columns.droplevel(1)
        daily_trend = _trend_direction(daily)
        if daily_trend == intraday_trend:
            score += 1
            timeframes_aligned.append("daily")
    except Exception:
        logger.debug("Confluence: failed to fetch daily for %s", symbol)
        daily_trend = None

    try:
        # Fetch 4H data (use 60m interval, 1 month)
        h4 = yf.download(symbol, period="1mo", interval="60m", progress=False)
        if hasattr(h4.columns, "droplevel") and isinstance(h4.columns, pd.MultiIndex):
            h4.columns = h4.columns.droplevel(1)
        # Resample to 4H if we got hourly data
        if h4 is not None and len(h4) > 20:
            h4_trend = _trend_direction(h4, ema_fast=20, ema_slow=50)
        else:
            h4_trend = None
        if h4_trend == intraday_trend:
            score += 1
            timeframes_aligned.append("4H")
    except Exception:
        logger.debug("Confluence: failed to fetch 4H for %s", symbol)
        h4_trend = None

    # Build label
    if score == 3:
        label = "Strong Confluence"
    elif score == 2:
        label = "Moderate Confluence"
    else:
        label = "Weak"

    detail = " + ".join(timeframes_aligned)
    logger.debug(
        "Confluence %s: %d/3 (%s) — daily=%s, 4H=%s, intraday=%s",
        symbol, score, detail, daily_trend, h4_trend, intraday_trend,
    )

    return score, label


# Cache to avoid re-fetching within same poll cycle
_confluence_cache: dict[str, Tuple[Optional[str], Optional[str]]] = {}


def get_cached_trends(symbol: str) -> Tuple[Optional[str], Optional[str]]:
    """Get cached daily + 4H trends for a symbol (fetched once per poll cycle).

    Returns (daily_trend, h4_trend) — each "bullish", "bearish", or None.
    """
    if symbol in _confluence_cache:
        return _confluence_cache[symbol]

    daily_trend = None
    h4_trend = None

    try:
        daily = yf.download(symbol, period="6mo", interval="1d", progress=False)
        if hasattr(daily.columns, "droplevel") and isinstance(daily.columns, pd.MultiIndex):
            daily.columns = daily.columns.droplevel(1)
        daily_trend = _trend_direction(daily)
    except Exception:
        pass

    try:
        h4 = yf.download(symbol, period="1mo", interval="60m", progress=False)
        if hasattr(h4.columns, "droplevel") and isinstance(h4.columns, pd.MultiIndex):
            h4.columns = h4.columns.droplevel(1)
        if h4 is not None and len(h4) > 20:
            h4_trend = _trend_direction(h4)
    except Exception:
        pass

    _confluence_cache[symbol] = (daily_trend, h4_trend)
    return daily_trend, h4_trend


def clear_confluence_cache():
    """Clear at start of each poll cycle."""
    _confluence_cache.clear()


def quick_confluence(symbol: str, intraday_direction: str) -> Tuple[int, str]:
    """Fast confluence check using cached trends.

    Call clear_confluence_cache() at start of each poll cycle,
    then this function uses cached daily/4H data.
    """
    intraday_trend = "bullish" if intraday_direction in ("BUY", "LONG", "Bullish") else "bearish"
    daily_trend, h4_trend = get_cached_trends(symbol)

    score = 1  # intraday counts as 1
    if daily_trend == intraday_trend:
        score += 1
    if h4_trend == intraday_trend:
        score += 1

    if score == 3:
        label = "Strong Confluence"
    elif score == 2:
        label = "Moderate Confluence"
    else:
        label = "Weak"

    return score, label
