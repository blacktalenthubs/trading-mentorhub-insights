"""Intraday alert rules — 8 mechanical day-trade signals.

BUY rules (1-4): MA bounce 20/50, prior day low reclaim, inside day breakout.
SELL rules (5-8): Resistance at prior high, target 1/2 hit, stop loss hit.

Context filters (applied before/after rules):
- SPY trend: skip BUY if SPY below 20MA
- Session timing: no new BUY entries during opening range or last 30 min
- Volume confirmation: label signal bar volume
- VWAP position: note above/below VWAP
- Gap analysis: adjust confidence on gap days
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
from analytics.market_hours import get_session_phase, allow_new_entries


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
    spy_trend: str = ""
    session_phase: str = ""
    volume_label: str = ""
    vwap_position: str = ""
    gap_info: str = ""
    score: int = 0
    score_label: str = ""


def _volume_label(bar_volume: float, avg_volume: float) -> str:
    """Classify volume of the signal bar relative to average."""
    ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0
    if ratio >= 1.5:
        return "high volume"
    elif ratio <= 0.5:
        return "low volume (caution)"
    return "normal volume"


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
        message=(
            f"T1 hit at ${target_1:.2f} (1R from entry ${entry_price:.2f}) "
            f"— sell half, move stop to breakeven"
        ),
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
    spy_context: dict | None = None,
) -> list[AlertSignal]:
    """Evaluate all 8 rules for a symbol and return fired signals.

    Context filters applied:
    - SPY trend: skip BUY rules if SPY is bearish
    - Session timing: skip BUY rules during opening range and last 30 min
    - Volume/VWAP/Gap: enrich signal messages after rules fire

    Args:
        symbol: Ticker symbol.
        intraday_bars: Today's 5-min bars (DataFrame with OHLCV).
        prior_day: Dict from fetch_prior_day() with prior day context.
        active_entries: List of dicts with entry_price, stop_price, target_1, target_2
                        from active_entries table.
        spy_context: Dict from get_spy_context() with SPY trend info.

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

    # --- Context filters ---
    spy = spy_context or {}
    spy_trend = spy.get("trend", "neutral")
    phase = get_session_phase()
    entries_allowed = allow_new_entries()

    # Compute VWAP for context enrichment
    from analytics.intraday_data import compute_vwap, classify_gap
    vwap_series = compute_vwap(intraday_bars)
    current_vwap = vwap_series.iloc[-1] if not vwap_series.empty else None
    vwap_pos = ""
    if current_vwap and current_vwap > 0:
        vwap_pos = "above VWAP" if last_bar["Close"] > current_vwap else "below VWAP"

    # Compute gap context
    today_open = intraday_bars["Open"].iloc[0] if not intraday_bars.empty else 0
    prior_range = prior_day.get("parent_range", prior_high - prior_low)
    gap = classify_gap(today_open, prior_close, prior_range)
    gap_info = ""
    if gap["type"] != "flat":
        gap_info = f"{gap['type'].replace('_', ' ')} ({gap['gap_pct']:+.1f}%)"

    # Volume context
    avg_vol = intraday_bars["Volume"].mean() if not intraday_bars.empty else 0
    bar_vol = last_bar["Volume"]
    vol_label = _volume_label(bar_vol, avg_vol)

    # --- BUY rules (gated by SPY trend + session timing) ---
    skip_buys = spy_trend == "bearish" or not entries_allowed

    if not skip_buys:
        sig = check_ma_bounce_20(symbol, last_bar, ma20, ma50)
        if sig:
            sig.message += f" ({phase})"
            if vwap_pos:
                sig.message += f" — price {vwap_pos}"
                if vwap_pos == "below VWAP":
                    sig.message += " (use caution)"
                else:
                    sig.message += " (bullish confirmation)"
            signals.append(sig)

        sig = check_ma_bounce_50(symbol, last_bar, ma20, ma50, prior_close)
        if sig:
            sig.message += f" ({phase})"
            if vwap_pos:
                sig.message += f" — price {vwap_pos}"
            signals.append(sig)

        sig = check_prior_day_low_reclaim(symbol, intraday_bars, prior_low)
        if sig:
            sig.message += f" ({phase})"
            # Gap down days boost PDL reclaim confidence
            if gap["type"] == "gap_down":
                sig.confidence = "high"
                sig.message += " — gap fill opportunity"
            if vwap_pos:
                sig.message += f" — price {vwap_pos}"
            signals.append(sig)

        sig = check_inside_day_breakout(symbol, last_bar, prior_day)
        if sig:
            sig.message += f" ({phase})"
            # Gap up reduces MA bounce likelihood but inside day breakouts are different
            if vwap_pos:
                sig.message += f" — price {vwap_pos}"
            signals.append(sig)

    # --- SELL rules (always fire regardless of SPY/session) ---

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

    # --- Enrich all signals with context ---
    for sig in signals:
        sig.spy_trend = spy_trend
        sig.session_phase = phase
        sig.volume_label = vol_label
        sig.vwap_position = vwap_pos
        sig.gap_info = gap_info
        if sig.direction == "BUY" and vol_label:
            sig.message += f" | {vol_label}"
        if gap_info and sig.direction == "BUY":
            sig.message += f" | {gap_info}"

    return signals
