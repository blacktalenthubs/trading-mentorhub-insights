"""Intraday alert rules — 8 mechanical day-trade signals.

BUY rules (1-4): MA bounce 20/50, prior day low reclaim, inside day breakout.
SELL rules (5-8): Resistance at prior high, target 1/2 hit, stop loss hit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from alert_config import (
    MA_BOUNCE_PROXIMITY_PCT,
    MA_STOP_OFFSET_PCT,
    PDL_DIP_MIN_PCT,
    RESISTANCE_PROXIMITY_PCT,
)


class AlertType(str, Enum):
    MA_BOUNCE_20 = "ma_bounce_20"
    MA_BOUNCE_50 = "ma_bounce_50"
    PRIOR_DAY_LOW_RECLAIM = "prior_day_low_reclaim"
    INSIDE_DAY_BREAKOUT = "inside_day_breakout"
    RESISTANCE_PRIOR_HIGH = "resistance_prior_high"
    TARGET_1_HIT = "target_1_hit"
    TARGET_2_HIT = "target_2_hit"
    STOP_LOSS_HIT = "stop_loss_hit"


@dataclass
class AlertSignal:
    """A single alert signal fired by a rule."""

    symbol: str
    alert_type: AlertType
    direction: str  # BUY or SELL
    price: float
    entry: float | None = None
    stop: float | None = None
    target_1: float | None = None
    target_2: float | None = None
    confidence: str = ""
    message: str = ""


# ---------------------------------------------------------------------------
# BUY Rule 1: MA Bounce 20MA
# ---------------------------------------------------------------------------

def check_ma_bounce_20(
    symbol: str,
    bar: pd.Series,
    ma20: float | None,
    ma50: float | None,
) -> AlertSignal | None:
    """Price pulls back to 20MA and bounces — bullish in uptrend.

    Conditions:
    - ma20 and ma50 are available
    - Bar low within MA_BOUNCE_PROXIMITY_PCT of 20MA
    - Bar closes above 20MA
    - 20MA > 50MA (uptrend confirmation)
    """
    if ma20 is None or ma50 is None:
        return None
    if ma20 <= 0 or ma50 <= 0:
        return None
    if ma20 <= ma50:
        return None  # not in uptrend

    proximity = abs(bar["Low"] - ma20) / ma20
    if proximity > MA_BOUNCE_PROXIMITY_PCT:
        return None
    if bar["Close"] <= ma20:
        return None  # didn't bounce above

    entry = bar["Close"]
    stop = min(bar["Low"], ma20 * (1 - MA_STOP_OFFSET_PCT))
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MA_BOUNCE_20,
        direction="BUY",
        price=bar["Close"],
        entry=entry,
        stop=round(stop, 2),
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high" if proximity <= 0.001 else "medium",
        message=(
            f"MA bounce 20MA — price pulled back to ${ma20:.2f} "
            f"and closed above at ${entry:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# BUY Rule 2: MA Bounce 50MA
# ---------------------------------------------------------------------------

def check_ma_bounce_50(
    symbol: str,
    bar: pd.Series,
    ma20: float | None,
    ma50: float | None,
    prior_close: float | None,
) -> AlertSignal | None:
    """Price pulls back to 50MA and bounces — deeper pullback buy.

    Conditions:
    - ma50 is available
    - Bar low within MA_BOUNCE_PROXIMITY_PCT of 50MA
    - Bar closes above 50MA
    - Prior close was above 50MA (pullback, not breakdown)
    """
    if ma50 is None or ma50 <= 0:
        return None
    if prior_close is not None and prior_close <= ma50:
        return None  # was already below — this is breakdown, not pullback

    proximity = abs(bar["Low"] - ma50) / ma50
    if proximity > MA_BOUNCE_PROXIMITY_PCT:
        return None
    if bar["Close"] <= ma50:
        return None

    entry = bar["Close"]
    stop = min(bar["Low"], ma50 * (1 - MA_STOP_OFFSET_PCT))
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MA_BOUNCE_50,
        direction="BUY",
        price=bar["Close"],
        entry=entry,
        stop=round(stop, 2),
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high" if proximity <= 0.001 else "medium",
        message=(
            f"MA bounce 50MA — price pulled back to ${ma50:.2f} "
            f"and closed above at ${entry:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# BUY Rule 3: Prior Day Low Reclaim
# ---------------------------------------------------------------------------

def check_prior_day_low_reclaim(
    symbol: str,
    bars: pd.DataFrame,
    prior_day_low: float,
) -> AlertSignal | None:
    """Price dips below prior day low then reclaims above it.

    Conditions:
    - Some bar went below prior day low by >= PDL_DIP_MIN_PCT
    - Current (last) bar closes back above prior day low
    """
    if bars.empty or prior_day_low <= 0:
        return None

    # Check if any bar dipped below prior day low
    min_dip = prior_day_low * (1 - PDL_DIP_MIN_PCT)
    dipped = bars["Low"].min() <= min_dip

    if not dipped:
        return None

    last_bar = bars.iloc[-1]
    if last_bar["Close"] <= prior_day_low:
        return None  # hasn't reclaimed yet

    entry = prior_day_low
    intraday_low = bars["Low"].min()
    stop = intraday_low
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.PRIOR_DAY_LOW_RECLAIM,
        direction="BUY",
        price=last_bar["Close"],
        entry=round(entry, 2),
        stop=round(stop, 2),
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high",
        message=(
            f"Prior day low reclaim — dipped to ${intraday_low:.2f}, "
            f"reclaimed above ${prior_day_low:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# BUY Rule 4: Inside Day Breakout
# ---------------------------------------------------------------------------

def check_inside_day_breakout(
    symbol: str,
    bar: pd.Series,
    prior_day: dict,
) -> AlertSignal | None:
    """Price breaks above inside day high.

    Conditions:
    - Prior day was classified as inside day
    - Current bar closes above inside day high
    """
    if not prior_day or not prior_day.get("is_inside"):
        return None

    inside_high = prior_day["high"]
    inside_low = prior_day["low"]
    parent_high = prior_day["parent_high"]
    parent_low = prior_day["parent_low"]

    if bar["Close"] <= inside_high:
        return None

    entry = inside_high
    stop = inside_low
    inside_range = inside_high - inside_low
    parent_range = parent_high - parent_low

    if inside_range <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.INSIDE_DAY_BREAKOUT,
        direction="BUY",
        price=bar["Close"],
        entry=round(entry, 2),
        stop=round(stop, 2),
        target_1=round(inside_high + inside_range, 2),
        target_2=round(inside_high + parent_range, 2),
        confidence="high",
        message=(
            f"Inside day breakout — broke above ${inside_high:.2f} "
            f"(inside range ${inside_range:.2f})"
        ),
    )


# ---------------------------------------------------------------------------
# SELL Rule 5: Resistance at Prior High
# ---------------------------------------------------------------------------

def check_resistance_prior_high(
    symbol: str,
    bar: pd.Series,
    prior_day_high: float,
    has_active_entry: bool,
) -> AlertSignal | None:
    """Price hits prior day high — take profits.

    Conditions:
    - Price within RESISTANCE_PROXIMITY_PCT of prior day high
    - Active BUY entry exists for this symbol
    """
    if not has_active_entry:
        return None
    if prior_day_high <= 0:
        return None

    proximity = abs(bar["High"] - prior_day_high) / prior_day_high
    if proximity > RESISTANCE_PROXIMITY_PCT:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.RESISTANCE_PRIOR_HIGH,
        direction="SELL",
        price=bar["High"],
        message=f"Resistance at prior high ${prior_day_high:.2f} — consider taking profits",
    )


# ---------------------------------------------------------------------------
# SELL Rule 6: Target 1 Hit
# ---------------------------------------------------------------------------

def check_target_1_hit(
    symbol: str,
    bar: pd.Series,
    entry_price: float,
    target_1: float,
) -> AlertSignal | None:
    """Price reaches Target 1 (1R)."""
    if entry_price <= 0 or target_1 <= 0:
        return None
    if bar["High"] < target_1:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.TARGET_1_HIT,
        direction="SELL",
        price=target_1,
        message=f"Target 1 hit at ${target_1:.2f} (1R from entry ${entry_price:.2f})",
    )


# ---------------------------------------------------------------------------
# SELL Rule 7: Target 2 Hit
# ---------------------------------------------------------------------------

def check_target_2_hit(
    symbol: str,
    bar: pd.Series,
    entry_price: float,
    target_2: float,
) -> AlertSignal | None:
    """Price reaches Target 2 (2R)."""
    if entry_price <= 0 or target_2 <= 0:
        return None
    if bar["High"] < target_2:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.TARGET_2_HIT,
        direction="SELL",
        price=target_2,
        message=f"Target 2 hit at ${target_2:.2f} (2R from entry ${entry_price:.2f})",
    )


# ---------------------------------------------------------------------------
# SELL Rule 8: Stop Loss Hit
# ---------------------------------------------------------------------------

def check_stop_loss_hit(
    symbol: str,
    bar: pd.Series,
    entry_price: float,
    stop_price: float,
) -> AlertSignal | None:
    """Price hits stop loss level."""
    if entry_price <= 0 or stop_price <= 0:
        return None
    if bar["Low"] > stop_price:
        return None

    loss = entry_price - stop_price
    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.STOP_LOSS_HIT,
        direction="SELL",
        price=stop_price,
        message=(
            f"Stop loss hit at ${stop_price:.2f} "
            f"(-${loss:.2f}/share from entry ${entry_price:.2f})"
        ),
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def evaluate_rules(
    symbol: str,
    intraday_bars: pd.DataFrame,
    prior_day: dict | None,
    active_entries: list[dict] | None = None,
) -> list[AlertSignal]:
    """Evaluate all 8 rules for a symbol and return fired signals.

    Args:
        symbol: Ticker symbol.
        intraday_bars: Today's 5-min bars (DataFrame with OHLCV).
        prior_day: Dict from fetch_prior_day() with prior day context.
        active_entries: List of dicts with entry_price, stop_price, target_1, target_2
                        from active_entries table.

    Returns:
        List of AlertSignal objects for rules that fired.
    """
    if intraday_bars.empty or prior_day is None:
        return []

    signals: list[AlertSignal] = []
    last_bar = intraday_bars.iloc[-1]
    ma20 = prior_day.get("ma20")
    ma50 = prior_day.get("ma50")
    prior_close = prior_day.get("close")
    prior_high = prior_day.get("high", 0)
    prior_low = prior_day.get("low", 0)

    # --- BUY rules ---

    sig = check_ma_bounce_20(symbol, last_bar, ma20, ma50)
    if sig:
        signals.append(sig)

    sig = check_ma_bounce_50(symbol, last_bar, ma20, ma50, prior_close)
    if sig:
        signals.append(sig)

    sig = check_prior_day_low_reclaim(symbol, intraday_bars, prior_low)
    if sig:
        signals.append(sig)

    sig = check_inside_day_breakout(symbol, last_bar, prior_day)
    if sig:
        signals.append(sig)

    # --- SELL rules (require active entries) ---

    entries = active_entries or []
    has_active = len(entries) > 0

    sig = check_resistance_prior_high(symbol, last_bar, prior_high, has_active)
    if sig:
        signals.append(sig)

    for entry in entries:
        ep = entry.get("entry_price", 0)
        t1 = entry.get("target_1", 0)
        t2 = entry.get("target_2", 0)
        sp = entry.get("stop_price", 0)

        sig = check_target_1_hit(symbol, last_bar, ep, t1)
        if sig:
            signals.append(sig)

        sig = check_target_2_hit(symbol, last_bar, ep, t2)
        if sig:
            signals.append(sig)

        sig = check_stop_loss_hit(symbol, last_bar, ep, sp)
        if sig:
            signals.append(sig)

    return signals
