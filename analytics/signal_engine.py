"""Signal scoring engine — composite BUY/WAIT/AVOID recommendations.

Combines candle pattern, MA position, support proximity, and volume
into a 0-100 score for each symbol.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from analytics.market_data import classify_day, fetch_ohlc, get_levels
from config import SCORE_THRESHOLDS, STRATEGY_TAGS


@dataclass
class SignalResult:
    """Composite signal for a single symbol."""

    symbol: str
    score: int  # 0-100
    signal: str  # BUY / WAIT / AVOID
    signal_type: str  # ma_bounce, support_bounce, breakout, etc.
    pattern: str  # inside / outside / normal
    direction: str  # bullish / bearish / neutral
    entry: float
    stop: float
    target_1: float
    target_2: float
    risk_per_share: float
    rr_ratio: float  # R:R to target 1
    scores: dict = field(default_factory=dict)  # breakdown by factor
    last_close: float = 0.0
    ma20: float | None = None
    ma50: float | None = None
    avg_volume: float = 0.0
    last_volume: float = 0.0


def _score_to_signal(score: int) -> str:
    """Map numeric score to BUY/WAIT/AVOID."""
    if score >= SCORE_THRESHOLDS["BUY"]:
        return "BUY"
    if score >= SCORE_THRESHOLDS["WAIT"]:
        return "WAIT"
    return "AVOID"


# ---------------------------------------------------------------------------
# Factor 1: Candle Pattern (0-25)
# ---------------------------------------------------------------------------

_CANDLE_SCORES = {
    ("inside", "bullish"): 25,
    ("inside", "neutral"): 20,
    ("normal", "bullish"): 18,
    ("inside", "bearish"): 12,
    ("outside", "bullish"): 10,
    ("normal", "neutral"): 10,
    ("normal", "bearish"): 5,
    ("outside", "neutral"): 3,
    ("outside", "bearish"): 0,
}


def score_candle_pattern(pattern: str, direction: str) -> int:
    """Score based on candle pattern and direction (0-25)."""
    return _CANDLE_SCORES.get((pattern, direction), 10)


# ---------------------------------------------------------------------------
# Factor 2: MA Position (0-25)
# ---------------------------------------------------------------------------

def score_ma_position(
    close: float,
    ma20: float | None,
    ma50: float | None,
) -> int:
    """Score based on price position relative to 20 and 50 MAs (0-25)."""
    if ma20 is None or ma50 is None:
        return 12  # not enough data — neutral

    if close > ma20 > ma50:
        return 25  # bullish structure
    if close < ma20 and close > ma50 and ma20 > ma50:
        # Pulled back to 20MA area, still above 50MA
        pct_from_ma20 = abs(close - ma20) / ma20
        if pct_from_ma20 <= 0.01:
            return 22  # right at 20MA — bounce candidate
        return 18  # between MAs, weak pullback
    if close > ma50 and ma20 > ma50:
        # Above 50MA, 20MA above — weak structure
        return 15
    if close > ma50:
        return 8  # above 50MA but weak
    return 0  # below both MAs


# ---------------------------------------------------------------------------
# Factor 3: Support Proximity (0-25)
# ---------------------------------------------------------------------------

def score_support_proximity(
    close: float,
    high: float,
    low: float,
    ma20: float | None,
    ma50: float | None,
) -> int:
    """Score based on how close price is to support (0-25)."""
    day_range = high - low
    if day_range <= 0:
        return 10

    # Check if close is near an MA (within 0.5%)
    for ma in [ma20, ma50]:
        if ma is not None and ma > 0:
            pct_from_ma = abs(close - ma) / ma
            if pct_from_ma <= 0.005:
                return 25  # sitting right on MA support

    # Close position within day's range
    close_pct = (close - low) / day_range

    if close_pct <= 0.30:
        return 20  # lower 30% — near day's low (support)
    if close_pct <= 0.70:
        return 10  # mid-range
    return 5  # upper 30% — extended from support


# ---------------------------------------------------------------------------
# Factor 4: Volume (0-25)
# ---------------------------------------------------------------------------

def score_volume(
    last_volume: float,
    avg_volume: float,
    pattern: str,
    direction: str,
) -> int:
    """Score based on volume relative to average (0-25)."""
    if avg_volume <= 0:
        return 12  # no volume data — neutral

    vol_ratio = last_volume / avg_volume

    if direction in ("bullish",):
        if vol_ratio >= 1.5:
            return 25  # high vol + bullish
        if vol_ratio >= 1.2:
            return 20  # above avg + bullish
    if pattern == "inside" and vol_ratio < 0.8:
        return 18  # low vol + inside day = compression (good)
    if 0.8 <= vol_ratio <= 1.2:
        return 12  # near average
    if vol_ratio < 0.8 and pattern == "normal":
        return 8  # low vol + normal day
    if vol_ratio >= 1.2 and direction == "bearish":
        return 5  # high vol + bearish

    return 12  # default neutral


# ---------------------------------------------------------------------------
# Signal type detection
# ---------------------------------------------------------------------------

def _detect_signal_type(
    pattern: str,
    direction: str,
    close: float,
    ma20: float | None,
    ma50: float | None,
) -> str:
    """Map conditions to a strategy tag from STRATEGY_TAGS."""
    # MA bounce: price pulled back to an MA and is near it
    for ma in [ma20, ma50]:
        if ma is not None and ma > 0:
            if abs(close - ma) / ma <= 0.005:
                return "ma_bounce"

    if pattern == "inside":
        return "breakout"

    if direction == "bullish" and pattern == "normal":
        return "support_bounce"

    if pattern == "outside" and direction == "bullish":
        return "momentum"

    if ma20 is not None and ma50 is not None:
        if close < ma20 and close > ma50:
            return "pullback_buy"

    return "key_level"


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def analyze_symbol(hist: pd.DataFrame, symbol: str = "") -> SignalResult | None:
    """Run all scoring factors on a symbol's history and return a SignalResult.

    Returns None if not enough data.
    """
    if hist.empty or len(hist) < 2:
        return None

    # Compute MAs on full history
    hist = hist.copy()
    hist["MA20"] = hist["Close"].rolling(window=20).mean()
    hist["MA50"] = hist["Close"].rolling(window=50).mean()

    last_idx = len(hist) - 1
    row = hist.iloc[last_idx]
    prev_row = hist.iloc[last_idx - 1]

    pattern, direction = classify_day(row, prev_row)
    levels = get_levels(hist, last_idx)

    close = row["Close"]
    high = row["High"]
    low = row["Low"]
    ma20 = hist["MA20"].iloc[last_idx] if pd.notna(hist["MA20"].iloc[last_idx]) else None
    ma50 = hist["MA50"].iloc[last_idx] if pd.notna(hist["MA50"].iloc[last_idx]) else None

    # Volume
    last_vol = row["Volume"]
    avg_vol = hist["Volume"].rolling(window=20).mean().iloc[last_idx]
    if pd.isna(avg_vol):
        avg_vol = hist["Volume"].mean()

    # Score each factor
    s_candle = score_candle_pattern(pattern, direction)
    s_ma = score_ma_position(close, ma20, ma50)
    s_support = score_support_proximity(close, high, low, ma20, ma50)
    s_volume = score_volume(last_vol, avg_vol, pattern, direction)

    total = s_candle + s_ma + s_support + s_volume
    signal = _score_to_signal(total)
    signal_type = _detect_signal_type(pattern, direction, close, ma20, ma50)

    risk = levels["risk_per_share"]
    reward_1 = levels["target_1"] - levels["entry_long"]
    rr = reward_1 / risk if risk > 0 else 0

    return SignalResult(
        symbol=symbol,
        score=total,
        signal=signal,
        signal_type=signal_type,
        pattern=pattern,
        direction=direction,
        entry=levels["entry_long"],
        stop=levels["stop_long"],
        target_1=levels["target_1"],
        target_2=levels["target_2"],
        risk_per_share=risk,
        rr_ratio=rr,
        scores={
            "candle_pattern": s_candle,
            "ma_position": s_ma,
            "support_proximity": s_support,
            "volume": s_volume,
        },
        last_close=close,
        ma20=ma20,
        ma50=ma50,
        avg_volume=avg_vol,
        last_volume=last_vol,
    )


def scan_watchlist(
    symbols: list[str],
    period: str = "3mo",
) -> list[SignalResult]:
    """Fetch data and score each symbol. Returns results sorted by score desc.

    Symbols that fail to fetch are silently skipped.
    """
    results: list[SignalResult] = []
    for sym in symbols:
        sym = sym.upper().strip()
        if not sym:
            continue
        hist = fetch_ohlc(sym, period)
        if hist.empty:
            continue
        result = analyze_symbol(hist, sym)
        if result is not None:
            results.append(result)

    results.sort(key=lambda r: r.score, reverse=True)
    return results
