"""Shared market data functions — OHLC fetch, day classification, key levels.

Extracted from pages/9_Pre_Market_Planner.py for reuse across pages.
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf


def fetch_ohlc(symbol: str, period: str = "3mo") -> pd.DataFrame:
    """Fetch OHLC data via yfinance.

    Returns DataFrame with Open, High, Low, Close, Volume columns.
    Returns empty DataFrame on failure.
    Note: No @st.cache_data here — caching is applied at the page level.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        if hist.empty:
            return pd.DataFrame()
        hist.index = hist.index.tz_localize(None)
        return hist[["Open", "High", "Low", "Close", "Volume"]].copy()
    except Exception:
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
