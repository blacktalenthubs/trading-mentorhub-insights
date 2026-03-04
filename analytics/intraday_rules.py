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

import logging
from dataclasses import dataclass
from enum import Enum

import pandas as pd

logger = logging.getLogger("intraday_rules")

from alert_config import (
    BREAKDOWN_CONVICTION_PCT,
    BREAKDOWN_VOLUME_RATIO,
    BUY_ZONE_PROXIMITY_PCT,
    CONFLUENCE_BAND_PCT,
    CONSOLIDATION_MAX_BOOST,
    CONSOLIDATION_SCORE_BOOST,
    DAY_TRADE_MAX_RISK_PCT,
    EMA_MIN_BARS,
    ENABLED_RULES,
    HOURLY_RESISTANCE_APPROACH_PCT,
    LOW_VOLUME_SKIP_RATIO,
    MA_BOUNCE_PROXIMITY_PCT,
    MA_BOUNCE_SESSION_STOP_PCT,
    MA_STOP_OFFSET_PCT,
    MA100_BOUNCE_PROXIMITY_PCT,
    MA100_STOP_OFFSET_PCT,
    MA200_BOUNCE_PROXIMITY_PCT,
    MA200_STOP_OFFSET_PCT,
    MIN_TARGET_DISTANCE_PCT,
    ORB_BREAKDOWN_VOLUME_RATIO,
    ORB_MIN_RANGE_PCT,
    ORB_VOLUME_RATIO,
    OVERHEAD_MA_RESISTANCE_PCT,
    PDL_DIP_MIN_PCT,
    PER_SYMBOL_RISK,
    PLANNED_LEVEL_PROXIMITY_PCT,
    RESISTANCE_PROXIMITY_PCT,
    WEEKLY_LEVEL_PROXIMITY_PCT,
    WEEKLY_LEVEL_STOP_OFFSET_PCT,
    RS_UNDERPERFORM_FACTOR,
    SPY_EMA_CONVERGENCE_PCT,
    SPY_RSI_OVERBOUGHT,
    SPY_RSI_OVERSOLD,
    SPY_STRONG_BOUNCE_RATE,
    SYM_RSI_OVERBOUGHT,
    SYM_RSI_OVERSOLD,
    SESSION_LOW_BREAK_PROXIMITY_PCT,
    SESSION_LOW_MAX_RETEST_VOL_RATIO,
    SESSION_LOW_MIN_AGE_BARS,
    SESSION_LOW_MIN_RECOVERY_BARS,
    SESSION_LOW_PROXIMITY_PCT,
    SESSION_LOW_RECOVERY_PCT,
    SESSION_LOW_STOP_OFFSET_PCT,
    SUPPORT_BOUNCE_PROXIMITY_PCT,
)
from analytics.market_hours import get_session_phase, allow_new_entries


class AlertType(str, Enum):
    MA_BOUNCE_20 = "ma_bounce_20"
    MA_BOUNCE_50 = "ma_bounce_50"
    MA_BOUNCE_100 = "ma_bounce_100"
    MA_BOUNCE_200 = "ma_bounce_200"
    PRIOR_DAY_LOW_RECLAIM = "prior_day_low_reclaim"
    INSIDE_DAY_BREAKOUT = "inside_day_breakout"
    RESISTANCE_PRIOR_HIGH = "resistance_prior_high"
    TARGET_1_HIT = "target_1_hit"
    TARGET_2_HIT = "target_2_hit"
    STOP_LOSS_HIT = "stop_loss_hit"
    SUPPORT_BREAKDOWN = "support_breakdown"
    EMA_CROSSOVER_5_20 = "ema_crossover_5_20"
    AUTO_STOP_OUT = "auto_stop_out"
    OPENING_RANGE_BREAKOUT = "opening_range_breakout"
    OPENING_RANGE_BREAKDOWN = "opening_range_breakdown"
    INTRADAY_SUPPORT_BOUNCE = "intraday_support_bounce"
    SESSION_LOW_DOUBLE_BOTTOM = "session_low_double_bottom"
    GAP_FILL = "gap_fill"
    PLANNED_LEVEL_TOUCH = "planned_level_touch"
    WEEKLY_LEVEL_TOUCH = "weekly_level_touch"
    HOURLY_RESISTANCE_APPROACH = "hourly_resistance_approach"
    MA_RESISTANCE = "ma_resistance"
    OUTSIDE_DAY_BREAKOUT = "outside_day_breakout"
    RESISTANCE_PRIOR_LOW = "resistance_prior_low"
    BUY_ZONE_APPROACH = "buy_zone_approach"


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
    rs_ratio: float = 0.0
    mtf_aligned: bool = False
    confluence: bool = False
    confluence_ma: str = ""
    narrative: str = ""


def _volume_label(bar_volume: float, avg_volume: float) -> str:
    """Classify volume of the signal bar relative to average."""
    ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0
    if ratio >= 1.5:
        return "high volume"
    elif ratio <= 0.5:
        return "low volume (caution)"
    return "normal volume"


def _cap_risk(
    entry: float,
    stop: float,
    max_risk_pct: float = DAY_TRADE_MAX_RISK_PCT,
    symbol: str | None = None,
) -> float:
    """Tighten stop if risk exceeds max_risk_pct of entry.

    If symbol is provided and found in PER_SYMBOL_RISK, uses that rate
    instead of the default. Backward compatible without symbol arg.
    """
    if entry <= 0 or stop <= 0:
        return stop
    rate = PER_SYMBOL_RISK.get(symbol, max_risk_pct) if symbol else max_risk_pct
    max_risk = entry * rate
    if entry - stop > max_risk:
        return round(entry - max_risk, 2)
    return stop


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

    entry = round(ma20, 2)
    stop = round(ma20 * (1 - MA_STOP_OFFSET_PCT), 2)
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MA_BOUNCE_20,
        direction="BUY",
        price=bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high" if proximity <= 0.001 else "medium",
        message=(
            f"MA bounce 20MA — price pulled back to ${ma20:.2f} "
            f"and closed above at ${bar['Close']:.2f}"
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
    - Counter-trend bounces (prior_close <= ma50) allowed with reduced confidence
    """
    if ma50 is None or ma50 <= 0:
        return None
    counter_trend = prior_close is not None and prior_close <= ma50

    proximity = abs(bar["Low"] - ma50) / ma50
    if proximity > MA_BOUNCE_PROXIMITY_PCT:
        return None
    if bar["Close"] <= ma50:
        return None

    entry = round(ma50, 2)
    stop = round(ma50 * (1 - MA_STOP_OFFSET_PCT), 2)
    risk = entry - stop
    if risk <= 0:
        return None

    if counter_trend:
        confidence = "medium"
    else:
        confidence = "high" if proximity <= 0.001 else "medium"

    msg = (
        f"MA bounce 50MA — price pulled back to ${ma50:.2f} "
        f"and closed above at ${bar['Close']:.2f}"
    )
    if counter_trend:
        msg += " (counter-trend)"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MA_BOUNCE_50,
        direction="BUY",
        price=bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence=confidence,
        message=msg,
    )


# ---------------------------------------------------------------------------
# BUY Rule 3: MA Bounce 100MA
# ---------------------------------------------------------------------------

def check_ma_bounce_100(
    symbol: str,
    bar: pd.Series,
    ma100: float | None,
    prior_close: float | None,
) -> AlertSignal | None:
    """Price pulls back to 100MA and bounces — intermediate institutional level.

    Conditions:
    - ma100 is available
    - Bar low within MA100_BOUNCE_PROXIMITY_PCT of 100MA (0.5%)
    - Bar closes above 100MA
    """
    if ma100 is None or ma100 <= 0:
        return None

    proximity = abs(bar["Low"] - ma100) / ma100
    if proximity > MA100_BOUNCE_PROXIMITY_PCT:
        return None
    if bar["Close"] <= ma100:
        return None

    entry = round(ma100, 2)
    stop = round(ma100 * (1 - MA100_STOP_OFFSET_PCT), 2)
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MA_BOUNCE_100,
        direction="BUY",
        price=bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high",
        message=(
            f"MA bounce 100MA — price pulled back to ${ma100:.2f} "
            f"and closed above at ${bar['Close']:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# BUY Rule 4: MA Bounce 200MA
# ---------------------------------------------------------------------------

def check_ma_bounce_200(
    symbol: str,
    bar: pd.Series,
    ma200: float | None,
    prior_close: float | None,
) -> AlertSignal | None:
    """Price pulls back to 200MA and bounces — major institutional level.

    Conditions:
    - ma200 is available
    - Bar low within MA200_BOUNCE_PROXIMITY_PCT of 200MA (0.8%)
    - Bar closes above 200MA
    """
    if ma200 is None or ma200 <= 0:
        return None

    proximity = abs(bar["Low"] - ma200) / ma200
    if proximity > MA200_BOUNCE_PROXIMITY_PCT:
        return None
    if bar["Close"] <= ma200:
        return None

    entry = round(ma200, 2)
    stop = round(ma200 * (1 - MA200_STOP_OFFSET_PCT), 2)
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MA_BOUNCE_200,
        direction="BUY",
        price=bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high",
        message=(
            f"MA bounce 200MA — price pulled back to ${ma200:.2f} "
            f"and closed above at ${bar['Close']:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# BUY Rule 5: Prior Day Low Reclaim
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
    stop = last_bar["Low"]  # bar that confirmed reclaim, not widest intraday low
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
# BUY Rule: Outside Day Follow-Through Breakout
# ---------------------------------------------------------------------------


def check_outside_day_breakout(
    symbol: str,
    bar: pd.Series,
    prior_day: dict,
) -> AlertSignal | None:
    """Price breaks above bullish outside day high — continuation signal.

    Conditions:
    - Prior day was a bullish outside day (closed in upper portion of range)
    - Current bar closes above prior day high
    """
    if not prior_day or prior_day.get("pattern") != "outside":
        return None

    if prior_day.get("direction") != "bullish":
        return None

    prior_high = prior_day["high"]
    prior_low = prior_day["low"]
    day_range = prior_high - prior_low

    if day_range <= 0:
        return None

    if bar["Close"] <= prior_high:
        return None

    entry = prior_high
    midpoint = (prior_high + prior_low) / 2
    stop = midpoint
    risk = entry - stop

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.OUTSIDE_DAY_BREAKOUT,
        direction="BUY",
        price=bar["Close"],
        entry=round(entry, 2),
        stop=round(stop, 2),
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high",
        message=(
            f"Outside day breakout — broke above ${prior_high:.2f} "
            f"(stop at midpoint ${midpoint:.2f})"
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
    """Price hits prior day high — take profits or warn about resistance.

    Conditions:
    - Price within RESISTANCE_PROXIMITY_PCT of prior day high
    - With active entry: SELL signal (take profits)
    - Without active entry: INFO warning (resistance ahead)
    """
    if prior_day_high <= 0:
        return None

    proximity = abs(bar["High"] - prior_day_high) / prior_day_high
    if proximity > RESISTANCE_PROXIMITY_PCT:
        return None

    if has_active_entry:
        return AlertSignal(
            symbol=symbol,
            alert_type=AlertType.RESISTANCE_PRIOR_HIGH,
            direction="SELL",
            price=bar["High"],
            message=f"Resistance at prior high ${prior_day_high:.2f} — consider taking profits",
        )

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.RESISTANCE_PRIOR_HIGH,
        direction="SELL",
        price=bar["High"],
        confidence="medium",
        message=f"At prior day high ${prior_day_high:.2f} — resistance zone, watch for rejection",
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
# Rule 9: Support Breakdown (SHORT)
# ---------------------------------------------------------------------------


def check_support_breakdown(
    symbol: str,
    bar: pd.Series,
    prior_day_low: float,
    nearest_support: float,
    bar_volume: float,
    avg_volume: float,
) -> AlertSignal | None:
    """Support broken with high volume and conviction close — short signal.

    Conditions:
    - Close below the lower of prior_day_low and nearest_support
    - Volume >= BREAKDOWN_VOLUME_RATIO * average
    - Close in the lower BREAKDOWN_CONVICTION_PCT of the bar range
    """
    support = min(prior_day_low, nearest_support) if nearest_support > 0 else prior_day_low
    if support <= 0:
        return None
    if bar["Close"] >= support:
        return None  # not broken

    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0
    if vol_ratio < BREAKDOWN_VOLUME_RATIO:
        return None  # not enough volume

    bar_range = bar["High"] - bar["Low"]
    if bar_range <= 0:
        return None
    close_position = (bar["Close"] - bar["Low"]) / bar_range
    if close_position > BREAKDOWN_CONVICTION_PCT:
        return None  # not conviction close

    entry = bar["Close"]
    risk = support - entry  # positive since support > entry
    stop = support  # stop above broken support
    target_1 = entry - risk  # 1R below
    target_2 = entry - 2 * risk  # 2R below

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SUPPORT_BREAKDOWN,
        direction="SHORT",
        price=entry,
        entry=round(entry, 2),
        stop=round(stop, 2),
        target_1=round(target_1, 2),
        target_2=round(target_2, 2),
        confidence="high" if vol_ratio >= 2.0 else "medium",
        message=(
            f"Support breakdown at ${support:.2f} — volume {vol_ratio:.1f}x avg, "
            f"conviction close at ${entry:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# Rule 10: EMA Crossover 5/20 (BUY)
# ---------------------------------------------------------------------------


def check_ema_crossover_5_20(
    symbol: str,
    bars: pd.DataFrame,
    is_mega_cap: bool,
) -> AlertSignal | None:
    """Daily 5-bar EMA crosses above 20-bar EMA on a mega-cap stock — bullish entry.

    Uses **daily** bars for the crossover detection (not intraday).
    Entry/stop are derived from intraday bars for trade management.

    Conditions:
    - Symbol is in MEGA_CAP set
    - Previous daily bar: EMA5 <= EMA20; current daily bar: EMA5 > EMA20
    - Minimum separation: EMA5 must exceed EMA20 by >= 0.05% (anti-flicker)
    - Confirmation: crossover daily bar must close green (Close > Open)
    """
    if not is_mega_cap:
        return None

    # Fetch daily bars for crossover detection
    import yfinance as yf

    try:
        daily = yf.Ticker(symbol).history(period="3mo")
    except Exception:
        return None
    if daily.empty or len(daily) < EMA_MIN_BARS:
        return None

    ema5 = daily["Close"].ewm(span=5, adjust=False).mean()
    ema20 = daily["Close"].ewm(span=20, adjust=False).mean()

    if len(ema5) < 2:
        return None
    prev_cross = ema5.iloc[-2] <= ema20.iloc[-2]
    curr_cross = ema5.iloc[-1] > ema20.iloc[-1]
    if not (prev_cross and curr_cross):
        return None  # no crossover on daily

    # Anti-flicker: EMA5 must lead EMA20 by >= 0.05% to filter noise
    ema5_val = ema5.iloc[-1]
    ema20_val = ema20.iloc[-1]
    separation_pct = (ema5_val - ema20_val) / ema20_val if ema20_val > 0 else 0
    if separation_pct < 0.0005:
        return None  # too tight — likely flicker

    last_daily = daily.iloc[-1]

    # Confirmation: crossover daily bar must be green (bullish)
    if last_daily["Close"] <= last_daily["Open"]:
        return None  # red candle on crossover = not confirmed

    # Use intraday bars for entry/stop (trade management)
    if bars.empty:
        return None
    last_bar = bars.iloc[-1]
    entry = last_bar["Close"]
    recent_low = bars["Low"].iloc[-3:].min()  # recent intraday swing low as stop
    stop = recent_low
    risk = entry - stop
    if risk <= 0:
        return None

    target_1 = entry + risk  # 1R
    target_2 = entry + 2 * risk  # 2R

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.EMA_CROSSOVER_5_20,
        direction="BUY",
        price=entry,
        entry=round(entry, 2),
        stop=round(stop, 2),
        target_1=round(target_1, 2),
        target_2=round(target_2, 2),
        confidence="high",
        message=(
            f"5/20 EMA bullish crossover (daily) — EMA5 ${ema5_val:.2f} "
            f"crossed above EMA20 ${ema20_val:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# Rule 11: Auto Stop-Out (SELL)
# ---------------------------------------------------------------------------


def check_auto_stop_out(
    symbol: str,
    bar: pd.Series,
    auto_stop_entry: dict,
) -> AlertSignal | None:
    """Prior BUY entry's stop level breached — exit immediately.

    Conditions:
    - auto_stop_entry has valid entry_price and stop_price
    - Bar low <= stop_price
    """
    entry_price = auto_stop_entry.get("entry_price", 0)
    stop_price = auto_stop_entry.get("stop_price", 0)
    alert_type_str = auto_stop_entry.get("alert_type", "")
    if entry_price <= 0 or stop_price <= 0:
        return None
    if bar["Low"] > stop_price:
        return None  # stop not hit

    loss = entry_price - stop_price
    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.AUTO_STOP_OUT,
        direction="SELL",
        price=stop_price,
        entry=entry_price,
        stop=stop_price,
        confidence="high",
        message=(
            f"STOP OUT — {alert_type_str} entry at ${entry_price:.2f} failed, "
            f"stop ${stop_price:.2f} hit (-${loss:.2f}/share). Exit immediately."
        ),
    )


# ---------------------------------------------------------------------------
# Rule 12: Opening Range Breakout (BUY)
# ---------------------------------------------------------------------------


def check_opening_range_breakout(
    symbol: str,
    bar: pd.Series,
    opening_range: dict | None,
    bar_volume: float,
    avg_volume: float,
) -> AlertSignal | None:
    """Price breaks above the 30-min opening range with volume confirmation.

    Conditions:
    - Opening range is complete (>= 6 bars of 5-min data)
    - OR range >= ORB_MIN_RANGE_PCT of price
    - Bar close > OR high
    - Volume >= ORB_VOLUME_RATIO * average
    """
    if opening_range is None or not opening_range.get("or_complete"):
        return None

    or_high = opening_range["or_high"]
    or_low = opening_range["or_low"]
    or_range = opening_range["or_range"]
    or_range_pct = opening_range["or_range_pct"]

    if or_range_pct < ORB_MIN_RANGE_PCT:
        return None  # range too small

    if bar["Close"] <= or_high:
        return None  # hasn't broken out

    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0
    if vol_ratio < ORB_VOLUME_RATIO:
        return None  # insufficient volume

    entry = or_high
    stop = or_low
    target_1 = or_high + or_range
    target_2 = or_high + 2 * or_range

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.OPENING_RANGE_BREAKOUT,
        direction="BUY",
        price=bar["Close"],
        entry=round(entry, 2),
        stop=round(stop, 2),
        target_1=round(target_1, 2),
        target_2=round(target_2, 2),
        confidence="high" if vol_ratio >= 1.5 else "medium",
        message=(
            f"Opening range breakout — broke above OR high ${or_high:.2f} "
            f"(range ${or_range:.2f}, vol {vol_ratio:.1f}x)"
        ),
    )


# ---------------------------------------------------------------------------
# Rule 12b: Opening Range Breakdown (SELL — informational)
# ---------------------------------------------------------------------------


def check_orb_breakdown(
    symbol: str,
    bar: pd.Series,
    opening_range: dict | None,
    bar_volume: float,
    avg_volume: float,
) -> AlertSignal | None:
    """Price breaks below the 30-min opening range with volume confirmation.

    Conditions:
    - Opening range is complete (>= 6 bars of 5-min data)
    - OR range >= ORB_MIN_RANGE_PCT of price
    - Bar close < OR low
    - Volume >= ORB_BREAKDOWN_VOLUME_RATIO * average

    Informational SELL only — no short positions.
    """
    if opening_range is None or not opening_range.get("or_complete"):
        return None

    or_high = opening_range["or_high"]
    or_low = opening_range["or_low"]
    or_range = opening_range["or_range"]
    or_range_pct = opening_range["or_range_pct"]

    if or_range_pct < ORB_MIN_RANGE_PCT:
        return None  # range too small

    if bar["Close"] >= or_low:
        return None  # hasn't broken down

    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0
    if vol_ratio < ORB_BREAKDOWN_VOLUME_RATIO:
        return None  # insufficient volume

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.OPENING_RANGE_BREAKDOWN,
        direction="SELL",
        price=bar["Close"],
        confidence="high" if vol_ratio >= 1.5 else "medium",
        message=(
            f"ORB BREAKDOWN — closed ${bar['Close']:.2f} below OR low "
            f"${or_low:.2f} on {vol_ratio:.1f}x volume"
        ),
    )


# ---------------------------------------------------------------------------
# Rule 13: Intraday Support Bounce (BUY)
# ---------------------------------------------------------------------------


def check_intraday_support_bounce(
    symbol: str,
    bar: pd.Series,
    intraday_supports: list[dict],
    bar_volume: float,
    avg_volume: float,
) -> AlertSignal | None:
    """Price bounces off a held intraday support level — bullish entry.

    Conditions:
    - At least one intraday support exists
    - Bar low is within SUPPORT_BOUNCE_PROXIMITY_PCT of a support level
    - Bar close > support (bounce confirmed)
    - Volume >= LOW_VOLUME_SKIP_RATIO (not noise)

    Accepts list[dict] with keys: level, touch_count, hold_hours, strength.
    """
    if not intraday_supports:
        return None

    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0
    if vol_ratio < LOW_VOLUME_SKIP_RATIO:
        return None

    # Find closest support at or below bar low within proximity threshold
    best = None
    for sup in sorted(intraday_supports, key=lambda s: s["level"], reverse=True):
        lvl = sup["level"]
        if lvl > bar["Low"]:
            continue
        proximity = (bar["Low"] - lvl) / lvl if lvl > 0 else float("inf")
        if proximity <= SUPPORT_BOUNCE_PROXIMITY_PCT:
            best = sup
            break

    if best is None:
        return None

    best_support = best["level"]
    touch_count = best.get("touch_count", 1)
    strength = best.get("strength", "weak")

    if bar["Close"] <= best_support:
        return None  # didn't bounce above

    entry = best_support
    stop = bar["Low"] if bar["Low"] < best_support else best_support * (1 - 0.005)
    risk = entry - stop
    if risk <= 0:
        return None

    confidence = "high" if strength == "strong" else "medium"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.INTRADAY_SUPPORT_BOUNCE,
        direction="BUY",
        price=bar["Close"],
        entry=round(entry, 2),
        stop=round(stop, 2),
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence=confidence,
        message=(
            f"Intraday support bounce at ${best_support:.2f} "
            f"(tested {touch_count}x, {strength})"
        ),
    )


# ---------------------------------------------------------------------------
# Rule 15: Session Low Double-Bottom (BUY)
# ---------------------------------------------------------------------------


def check_session_low_retest(
    symbol: str,
    bars: pd.DataFrame,
    last_bar: pd.Series,
    bar_volume: float,
    avg_volume: float,
) -> AlertSignal | None:
    """Session low tested twice (double bottom) with recovery between — bullish entry.

    Conditions:
    1. Minimum bars: MIN_AGE + MIN_RECOVERY + 1
    2. Session low = bars["Low"].min()
    3. Volume cap: vol_ratio < SESSION_LOW_MAX_RETEST_VOL_RATIO (exhaustion, not panic)
    4. Last bar low within SESSION_LOW_PROXIMITY_PCT of session low (not below it)
    5. Last bar closes above session low (bounce confirmed)
    6. First touch: earliest bar (excl. last) with low within proximity of session low
    7. First touch >= SESSION_LOW_MIN_AGE_BARS bars ago
    8. Recovery: >= SESSION_LOW_MIN_RECOVERY_BARS consecutive bars with low > session_low * (1 + RECOVERY_PCT)
    """
    min_bars = SESSION_LOW_MIN_AGE_BARS + SESSION_LOW_MIN_RECOVERY_BARS + 1
    if len(bars) < min_bars:
        return None

    session_low = bars["Low"].min()
    if session_low <= 0:
        return None

    # Volume cap — retest must be exhaustion, not panic selling
    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0
    if vol_ratio >= SESSION_LOW_MAX_RETEST_VOL_RATIO:
        return None

    # Last bar low must be near session low but not below it
    proximity = (last_bar["Low"] - session_low) / session_low
    if proximity < 0 or proximity > SESSION_LOW_PROXIMITY_PCT:
        return None

    # Last bar must close above session low (bounce confirmed)
    if last_bar["Close"] <= session_low:
        return None

    # Find first touch: earliest bar (excluding last) with low within proximity
    first_touch_idx = None
    for i in range(len(bars) - 1):
        bar_low = bars["Low"].iloc[i]
        touch_proximity = abs(bar_low - session_low) / session_low
        if touch_proximity <= SESSION_LOW_PROXIMITY_PCT:
            first_touch_idx = i
            break

    if first_touch_idx is None:
        return None

    # First touch must be old enough
    bars_ago = len(bars) - 1 - first_touch_idx
    if bars_ago < SESSION_LOW_MIN_AGE_BARS:
        return None

    # Recovery between first touch and retest:
    # consecutive bars where low > session_low * (1 + RECOVERY_PCT)
    recovery_threshold = session_low * (1 + SESSION_LOW_RECOVERY_PCT)
    max_consecutive = 0
    consecutive = 0
    for i in range(first_touch_idx + 1, len(bars) - 1):
        if bars["Low"].iloc[i] > recovery_threshold:
            consecutive += 1
            max_consecutive = max(max_consecutive, consecutive)
        else:
            consecutive = 0

    if max_consecutive < SESSION_LOW_MIN_RECOVERY_BARS:
        return None

    # Entry/Stop/Targets
    entry = session_low
    stop = min(last_bar["Low"], session_low * (1 - SESSION_LOW_STOP_OFFSET_PCT))
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SESSION_LOW_DOUBLE_BOTTOM,
        direction="BUY",
        price=last_bar["Close"],
        entry=round(entry, 2),
        stop=round(stop, 2),
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="medium",
        message=(
            f"Session low double-bottom — ${session_low:.2f} tested twice, "
            f"recovery confirmed, bounce at ${last_bar['Close']:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# Rule 14: Gap Fill (INFO)
# ---------------------------------------------------------------------------


def check_gap_fill(
    symbol: str,
    bar: pd.Series,
    gap_info: dict,
) -> AlertSignal | None:
    """Gap fully fills — informational signal.

    Fires when gap_info shows is_filled=True. Direction: SELL for gap_up fill
    (bearish cue), BUY for gap_down fill (bullish cue). No entry/stop/target.
    """
    if not gap_info or not gap_info.get("is_filled"):
        return None
    if gap_info.get("gap_direction") == "flat":
        return None

    direction = "SELL" if gap_info["gap_direction"] == "gap_up" else "BUY"
    gap_pct = gap_info.get("gap_pct", 0)

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.GAP_FILL,
        direction=direction,
        price=bar["Close"],
        confidence="medium",
        message=(
            f"Gap fill complete — {gap_info['gap_direction'].replace('_', ' ')} "
            f"({gap_pct:+.1f}%) fully filled"
        ),
    )


# ---------------------------------------------------------------------------
# Rule 16: Planned Level Touch (BUY)
# ---------------------------------------------------------------------------


def _compute_planned_levels(prior_day: dict) -> dict | None:
    """Replicate Scanner get_levels() using prior_day dict (no extra API call).

    Returns dict with entry, stop, target_1, target_2, pattern or None for inside days.
    """
    pattern = prior_day.get("pattern", "normal")
    if pattern == "inside":
        return None  # already handled by check_inside_day_breakout

    high = prior_day.get("high", 0)
    low = prior_day.get("low", 0)
    day_range = high - low

    if day_range <= 0 or high <= 0 or low <= 0:
        return None

    if pattern == "outside":
        midpoint = (high + low) / 2
        return {
            "pattern": "outside",
            "entry": midpoint,
            "stop": low,
            "target_1": high,
            "target_2": high + (high - midpoint),
        }

    # Normal day
    return {
        "pattern": "normal",
        "entry": low,
        "stop": low - day_range * 0.25,
        "target_1": high,
        "target_2": high + day_range * 0.5,
    }


def check_planned_level_touch(
    symbol: str,
    bar: pd.Series,
    prior_day: dict,
) -> AlertSignal | None:
    """Price touches the Scanner's planned entry level and bounces — bullish entry.

    Conditions:
    1. Pattern is normal or outside (not inside)
    2. Bar low within PLANNED_LEVEL_PROXIMITY_PCT of planned entry
    3. Bar close > planned entry (bounce confirmed)
    4. Risk > 0
    """
    levels = _compute_planned_levels(prior_day)
    if levels is None:
        return None

    entry = levels["entry"]
    if entry <= 0:
        return None

    proximity = abs(bar["Low"] - entry) / entry
    if proximity > PLANNED_LEVEL_PROXIMITY_PCT:
        return None

    if bar["Close"] <= entry:
        return None  # no bounce

    stop = levels["stop"]
    stop = _cap_risk(entry, stop, symbol=symbol)
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.PLANNED_LEVEL_TOUCH,
        direction="NOTICE",
        price=bar["Close"],
        entry=round(entry, 2),
        stop=round(stop, 2),
        target_1=round(levels["target_1"], 2),
        target_2=round(levels["target_2"], 2),
        confidence="high",
        message=(
            f"Planned level touch ({levels['pattern']}) — "
            f"price at ${entry:.2f}, T1=${levels['target_1']:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# Rule 17: Weekly Level Touch (BUY)
# ---------------------------------------------------------------------------


def check_weekly_level_touch(
    symbol: str,
    bar: pd.Series,
    prior_day: dict,
) -> AlertSignal | None:
    """Price touches prior week low and bounces — bullish entry at institutional level.

    Conditions:
    1. prior_week_high and prior_week_low available and > 0
    2. Weekly range > 0
    3. Bar low within WEEKLY_LEVEL_PROXIMITY_PCT of prior_week_low
    4. Bar close > prior_week_low (bounce confirmed)
    5. Risk > 0 (after _cap_risk)
    """
    pw_high = prior_day.get("prior_week_high")
    pw_low = prior_day.get("prior_week_low")
    if pw_high is None or pw_low is None:
        return None
    if pw_high <= 0 or pw_low <= 0:
        return None

    weekly_range = pw_high - pw_low
    if weekly_range <= 0:
        return None

    proximity = abs(bar["Low"] - pw_low) / pw_low
    if proximity > WEEKLY_LEVEL_PROXIMITY_PCT:
        return None

    if bar["Close"] <= pw_low:
        return None  # no bounce

    entry = pw_low
    stop = pw_low * (1 - WEEKLY_LEVEL_STOP_OFFSET_PCT)
    stop = _cap_risk(entry, stop, symbol=symbol)
    risk = entry - stop
    if risk <= 0:
        return None

    target_1 = pw_high
    target_2 = pw_high + weekly_range * 0.5

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.WEEKLY_LEVEL_TOUCH,
        direction="NOTICE",
        price=bar["Close"],
        entry=round(entry, 2),
        stop=round(stop, 2),
        target_1=round(target_1, 2),
        target_2=round(target_2, 2),
        confidence="high",
        message=(
            f"Weekly level touch — price at prior week low ${pw_low:.2f}, "
            f"T1=${pw_high:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# Rule 22: Buy Zone Approach (BUY)
# ---------------------------------------------------------------------------


def check_buy_zone_approach(
    symbol: str,
    bar: pd.Series,
    prior_day: dict,
) -> AlertSignal | None:
    """Price approaches nearest support (Scanner's BUY ZONE concept) — bullish entry.

    Mirrors _find_nearest_support() from signal_engine.py to unify the Scanner's
    AT SUPPORT classification with an intraday alert.

    Conditions:
    1. At least one support candidate (prior_low, ma20, ma50) exists
    2. Nearest support at or below bar close is identified
    3. Bar low within BUY_ZONE_PROXIMITY_PCT of that support
    4. Bar close >= support (bounce/hold confirmed)
    5. Risk > 0 after _cap_risk
    """
    prior_low = prior_day.get("low", 0)
    ma20 = prior_day.get("ma20")
    ma50 = prior_day.get("ma50")
    high = prior_day.get("high", 0)

    # Build support candidates (same as signal_engine._find_nearest_support)
    candidates: list[tuple[float, str]] = []
    if prior_low > 0:
        candidates.append((prior_low, "Prior Day Low"))
    if ma20 is not None and ma20 > 0:
        candidates.append((ma20, "20 MA"))
    if ma50 is not None and ma50 > 0:
        candidates.append((ma50, "50 MA"))

    if not candidates:
        return None

    close = bar["Close"]

    # Find nearest support at or below current close
    below = [(lvl, label) for lvl, label in candidates if lvl <= close]
    if not below:
        return None  # price broke all supports — no buy zone

    below.sort(key=lambda x: close - x[0])
    support, support_label = below[0]

    if support <= 0:
        return None

    # Check bar low is within proximity of support
    proximity = abs(bar["Low"] - support) / support
    if proximity > BUY_ZONE_PROXIMITY_PCT:
        return None

    # Bounce/hold confirmed: close at or above support
    if close < support:
        return None

    # Compute entry/stop/targets using prior day range
    day_range = high - prior_low
    if day_range <= 0:
        return None

    entry = support
    stop = support - day_range * 0.25
    stop = _cap_risk(entry, stop, symbol=symbol)
    risk = entry - stop
    if risk <= 0:
        return None

    target_1 = high if high > entry else entry + day_range * 0.5
    target_2 = high + day_range * 0.5 if high > entry else entry + day_range

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.BUY_ZONE_APPROACH,
        direction="BUY",
        price=bar["Close"],
        entry=round(entry, 2),
        stop=round(stop, 2),
        target_1=round(target_1, 2),
        target_2=round(target_2, 2),
        confidence="high",
        message=(
            f"BUY ZONE — approaching {support_label} ${support:.2f}, "
            f"T1=${target_1:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# Rule 18: Hourly Resistance Approach (SELL)
# ---------------------------------------------------------------------------


def check_hourly_resistance_approach(
    symbol: str,
    bar: pd.Series,
    hourly_resistance: list[float],
    has_active_entry: bool,
) -> AlertSignal | None:
    """Active trade approaching hourly swing high resistance — tighten or take profits.

    Conditions:
    - has_active_entry is True
    - At least one hourly resistance level exists above current price
    - Bar high within HOURLY_RESISTANCE_APPROACH_PCT of an hourly resistance level
    """
    if not has_active_entry or not hourly_resistance:
        return None

    # Find nearest hourly resistance at or above bar high
    for level in sorted(hourly_resistance):
        if level < bar["High"]:
            continue
        proximity = (level - bar["High"]) / level if level > 0 else float("inf")
        if proximity <= HOURLY_RESISTANCE_APPROACH_PCT:
            return AlertSignal(
                symbol=symbol,
                alert_type=AlertType.HOURLY_RESISTANCE_APPROACH,
                direction="SELL",
                price=bar["High"],
                message=(
                    f"APPROACHING HOURLY RESISTANCE at ${level:.2f}"
                    f" — tighten stop or take profits"
                ),
            )
        break  # only check nearest level above

    return None


# ---------------------------------------------------------------------------
# SELL Rule 19: MA Resistance (overhead rejection)
# ---------------------------------------------------------------------------


def check_ma_resistance(
    symbol: str,
    bar: pd.Series,
    ma20: float | None,
    ma50: float | None,
    ma100: float | None,
    ma200: float | None,
    prior_close: float | None = None,
) -> AlertSignal | None:
    """Price rallies into overhead MA and gets rejected — bearish warning.

    Iterates MAs in order (20→50→100→200) and fires for the **lowest
    rejecting MA** only (first match = most relevant overhead resistance).

    Conditions per MA:
    - MA is available, positive, and above bar close (overhead)
    - Bar high within MA_BOUNCE_PROXIMITY_PCT of the MA
    - Bar close below the MA (rejection confirmed, not a breakout)
    """
    for ma_val, ma_label in [
        (ma20, "20"), (ma50, "50"), (ma100, "100"), (ma200, "200"),
    ]:
        if ma_val is None or ma_val <= 0 or ma_val <= bar["Close"]:
            continue  # skip: missing, zero, or below close (not overhead)
        proximity = abs(bar["High"] - ma_val) / ma_val
        if proximity > MA_BOUNCE_PROXIMITY_PCT:
            continue  # bar didn't reach this MA
        if bar["Close"] >= ma_val:
            continue  # closed above = bounce, not rejection
        msg = (
            f"MA{ma_label} RESISTANCE — rejected at ${ma_val:.2f}, "
            f"closed below at ${bar['Close']:.2f}"
        )
        # Role-flip: prior close was below this MA → recently broken, acting as ceiling
        if prior_close is not None and prior_close < ma_val:
            msg += " — recently broken, acting as resistance"
        return AlertSignal(
            symbol=symbol,
            alert_type=AlertType.MA_RESISTANCE,
            direction="SELL",
            price=bar["High"],
            message=msg,
        )
    return None


# ---------------------------------------------------------------------------
# SELL Rule 20: Prior Day Low as Resistance (overhead rejection)
# ---------------------------------------------------------------------------


def check_resistance_prior_low(
    symbol: str,
    bar: pd.Series,
    prior_day_low: float,
) -> AlertSignal | None:
    """Price rallies up to prior day low from below and gets rejected.

    Conditions:
    - prior_day_low > 0
    - Bar high within RESISTANCE_PROXIMITY_PCT of prior day low
    - Bar close below prior day low (rejection confirmed)
    """
    if prior_day_low <= 0:
        return None
    proximity = abs(bar["High"] - prior_day_low) / prior_day_low
    if proximity > RESISTANCE_PROXIMITY_PCT:
        return None
    if bar["Close"] >= prior_day_low:
        return None  # reclaimed = not rejection
    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.RESISTANCE_PRIOR_LOW,
        direction="SELL",
        price=bar["High"],
        message=(
            f"Prior day low resistance at ${prior_day_low:.2f} — "
            f"rejected, watch for continuation lower"
        ),
    )


# ---------------------------------------------------------------------------
# Smart Resistance-Based Targets
# ---------------------------------------------------------------------------


def _find_resistance_targets(
    entry: float,
    stop: float,
    prior_day: dict,
    current_vwap: float | None,
    hourly_resistance: list[float] | None = None,
) -> tuple[float, float, str, str] | None:
    """Find T1/T2 from actual chart resistance levels above entry.

    Collects resistance levels (prior high, MAs, weekly high, VWAP,
    hourly resistance), filters to levels above entry with minimum 1R
    distance, and returns the nearest two as smart targets.

    Returns (t1, t2, t1_label, t2_label) or None if no levels found.
    """
    if entry <= 0 or stop <= 0 or entry <= stop:
        return None

    # Collect candidate resistance levels with labels
    candidates: list[tuple[float, str]] = []
    level_map = {
        "prior high": prior_day.get("high"),
        "MA20": prior_day.get("ma20"),
        "MA50": prior_day.get("ma50"),
        "MA100": prior_day.get("ma100"),
        "MA200": prior_day.get("ma200"),
        "prior week high": prior_day.get("prior_week_high"),
    }
    for label, level in level_map.items():
        if level and level > entry:
            candidates.append((level, label))

    if current_vwap and current_vwap > entry:
        candidates.append((current_vwap, "VWAP"))

    if hourly_resistance:
        for level in hourly_resistance:
            if level > entry:
                candidates.append((level, "hourly resistance"))

    if not candidates:
        return None

    # Sort ascending (nearest resistance first)
    candidates.sort(key=lambda x: x[0])

    # Minimum target = entry + 1R (never worse than 1:1 R/R)
    risk = entry - stop
    min_target = entry + risk

    # T1 = first level >= min_target
    t1 = None
    t1_label = ""
    for level, label in candidates:
        if level >= min_target:
            t1 = level
            t1_label = label
            break

    if t1 is None:
        return None

    # T2 = next level above T1, or T1 + R if only one level
    t2 = None
    t2_label = ""
    for level, label in candidates:
        if level > t1:
            t2 = level
            t2_label = label
            break

    if t2 is None:
        t2 = round(t1 + risk, 2)
        t2_label = f"{t1_label}+1R"

    return (round(t1, 2), round(t2, 2), t1_label, t2_label)


# ---------------------------------------------------------------------------
# Volume Exhaustion Detection
# ---------------------------------------------------------------------------


def _detect_volume_exhaustion(
    bars: pd.DataFrame,
    avg_vol: float,
) -> tuple[str | None, str]:
    """Detect seller or buyer exhaustion from recent volume patterns.

    Seller exhaustion (bullish): declining volume on pullback — sellers drying up.
    Buyer exhaustion (bearish): volume spike with reversal — climax top.

    Returns (exhaustion_type, message) or (None, "").
    """
    from alert_config import (
        BUYER_EXHAUSTION_SPIKE_RATIO,
        SELLER_EXHAUSTION_MIN_BARS,
        SELLER_EXHAUSTION_VOL_RATIO,
    )

    if len(bars) < 4 or avg_vol <= 0:
        return (None, "")

    # --- Seller exhaustion: declining volume on pullback ---
    recent = bars.iloc[-4:]
    volumes = recent["Volume"].tolist()
    closes = recent["Close"].tolist()

    # Check for 3+ consecutive declining volume bars
    declining_count = 0
    for i in range(1, len(volumes)):
        if volumes[i] < volumes[i - 1]:
            declining_count += 1
        else:
            declining_count = 0

    # Price falling or flat (last close <= first close of window)
    price_falling = closes[-1] <= closes[0]

    if (declining_count >= SELLER_EXHAUSTION_MIN_BARS
            and price_falling
            and volumes[-1] < SELLER_EXHAUSTION_VOL_RATIO * avg_vol):
        return ("seller_exhaustion", "seller exhaustion — declining volume on pullback")

    # --- Buyer exhaustion: volume spike + reversal ---
    recent_3 = bars.iloc[-3:]
    for i in range(len(recent_3)):
        bar = recent_3.iloc[i]
        vol_ratio = bar["Volume"] / avg_vol
        if vol_ratio < BUYER_EXHAUSTION_SPIKE_RATIO:
            continue
        # Spike bar was bullish (close > open)
        if bar["Close"] <= bar["Open"]:
            continue
        # Check if this bar or next bar reversed (bearish candle)
        if i + 1 < len(recent_3):
            next_bar = recent_3.iloc[i + 1]
            if next_bar["Close"] < next_bar["Open"]:
                return ("buyer_exhaustion", "volume climax — potential reversal")
        # Spike is last bar — check if it itself reversed (wick rejection)
        # Upper wick > body = reversal signal
        if i == len(recent_3) - 1:
            body = bar["Close"] - bar["Open"]
            upper_wick = bar["High"] - bar["Close"]
            if body > 0 and upper_wick > body:
                return ("buyer_exhaustion", "volume climax — potential reversal")

    return (None, "")


# ---------------------------------------------------------------------------
# Noise filter
# ---------------------------------------------------------------------------


def _should_skip_noise(signal: AlertSignal, vol_ratio: float) -> bool:
    """Skip BUY signals on very low volume — likely noise."""
    if signal.direction != "BUY":
        return False
    return vol_ratio < LOW_VOLUME_SKIP_RATIO


def _has_overhead_ma_resistance(
    entry: float,
    ma20: float | None,
    ma50: float | None,
    ma100: float | None,
    ma200: float | None,
) -> tuple[bool, str]:
    """Check if any MA sits overhead within OVERHEAD_MA_RESISTANCE_PCT of entry.

    Returns (blocked, label) where label describes the blocking MA.
    Only flags MAs that are *above* entry — a BUY heading into resistance.
    """
    for label, ma in [("20MA", ma20), ("50MA", ma50), ("100MA", ma100), ("200MA", ma200)]:
        if ma is None or ma <= 0:
            continue
        if ma <= entry:
            continue  # MA is below entry — not overhead resistance
        gap_pct = (ma - entry) / entry
        if gap_pct <= OVERHEAD_MA_RESISTANCE_PCT:
            return True, f"{label} ${ma:.2f}"
    return False, ""


def _check_ma_confluence(
    entry: float,
    alert_type: AlertType,
    ma20: float | None,
    ma50: float | None,
    ma100: float | None,
    ma200: float | None,
) -> tuple[bool, str, str]:
    """Check if any MA aligns with a horizontal support entry.

    Returns (has_confluence, ma_label, ma_value_str).
    Prioritises higher MAs (200 > 100 > 50 > 20) — more institutional weight.
    Skips any MA whose rounded value equals the entry — that MA IS the signal's
    own support level (covers MA_BOUNCE, BUY_ZONE with MA candidate, etc.).
    """
    entry_r = round(entry, 2)
    for label, ma in [
        ("200MA", ma200), ("100MA", ma100), ("50MA", ma50), ("20MA", ma20),
    ]:
        if ma is None or ma <= 0:
            continue
        if round(ma, 2) == entry_r:
            continue  # MA value IS the entry — self-referencing
        if abs(ma - entry) / entry <= CONFLUENCE_BAND_PCT:
            return True, label, f"${ma:.2f}"
    return False, "", ""


# ---------------------------------------------------------------------------
# Score enrichment for intraday alerts
# ---------------------------------------------------------------------------


def _score_alert(
    sig: AlertSignal,
    ma20: float | None,
    ma50: float | None,
    close: float,
    vol_ratio: float,
) -> int:
    """Lightweight score (0-100) for an intraday AlertSignal."""
    score = 0
    # MA position (25): above both = 25, one = 15, none = 0
    above_20 = ma20 is not None and close > ma20
    above_50 = ma50 is not None and close > ma50
    score += 25 if (above_20 and above_50) else (15 if (above_20 or above_50) else 0)
    # Volume (25): high = 25, normal = 15, low = 5
    score += 25 if vol_ratio >= 1.2 else (15 if vol_ratio >= 0.8 else 5)
    # Confidence (25): high = 25, medium = 15
    score += 25 if sig.confidence == "high" else 15
    # Direction alignment (25): BUY above VWAP or SHORT below = 25
    vwap_aligned = (
        (sig.direction == "BUY" and sig.vwap_position == "above VWAP")
        or (sig.direction == "SHORT" and sig.vwap_position == "below VWAP")
    )
    score += 25 if vwap_aligned else 10
    return score


# ---------------------------------------------------------------------------
# Signal Consolidation
# ---------------------------------------------------------------------------


def _consolidate_signals(signals: list[AlertSignal]) -> list[AlertSignal]:
    """Merge multiple BUY signals for the same symbol.

    Keeps the highest-scored signal as primary, boosts its score
    by CONSOLIDATION_SCORE_BOOST per additional confirming signal
    (capped at CONSOLIDATION_MAX_BOOST). Appends confirming signal
    types to the message.

    SELL signals pass through unchanged.
    """
    from collections import defaultdict

    groups: dict[tuple[str, str], list[AlertSignal]] = defaultdict(list)
    for sig in signals:
        groups[(sig.symbol, sig.direction)].append(sig)

    result: list[AlertSignal] = []
    for (symbol, direction), group in groups.items():
        if direction != "BUY" or len(group) <= 1:
            result.extend(group)
            continue

        # Sort by score descending, pick highest as primary
        group.sort(key=lambda s: s.score, reverse=True)
        primary = group[0]
        others = group[1:]

        # Boost score
        boost = min(len(others) * CONSOLIDATION_SCORE_BOOST, CONSOLIDATION_MAX_BOOST)
        primary.score = min(100, primary.score + boost)

        # Recalculate score_label
        primary.score_label = (
            "A+" if primary.score >= 90
            else "A" if primary.score >= 75
            else "B" if primary.score >= 50
            else "C"
        )

        # Append confirming signal types to message
        types = [s.alert_type.value.replace("_", " ").title() for s in others]
        primary.message += f" [+{len(others)} confirming: {', '.join(types)}]"

        result.append(primary)

    return result


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def evaluate_rules(
    symbol: str,
    intraday_bars: pd.DataFrame,
    prior_day: dict | None,
    active_entries: list[dict] | None = None,
    spy_context: dict | None = None,
    auto_stop_entries: dict | None = None,
    is_cooled_down: bool = False,
    fired_today: set[tuple[str, str]] | None = None,
) -> list[AlertSignal]:
    """Evaluate all rules for a symbol and return fired signals.

    Context filters applied:
    - SPY trend: skip BUY rules if SPY is bearish
    - Session timing: skip BUY rules during opening range and last 30 min
    - Volume/VWAP/Gap: enrich signal messages after rules fire
    - Cooldown: skip BUY rules when is_cooled_down is True
    - Dedup: skip signals already in fired_today set

    Args:
        symbol: Ticker symbol.
        intraday_bars: Today's 5-min bars (DataFrame with OHLCV).
        prior_day: Dict from fetch_prior_day() with prior day context.
        active_entries: List of dicts with entry_price, stop_price, target_1, target_2
                        from active_entries table.
        spy_context: Dict from get_spy_context() with SPY trend info.
        auto_stop_entries: Dict with entry for auto stop-out tracking.
        is_cooled_down: If True, suppress all BUY signals (post stop-out cooldown).
        fired_today: Set of (symbol, alert_type) tuples already fired this session.

    Returns:
        List of AlertSignal objects for rules that fired.
    """
    if intraday_bars.empty or prior_day is None:
        return []

    signals: list[AlertSignal] = []
    last_bar = intraday_bars.iloc[-1]
    ma20 = prior_day.get("ma20")
    ma50 = prior_day.get("ma50")
    ma100 = prior_day.get("ma100")
    ma200 = prior_day.get("ma200")
    prior_close = prior_day.get("close")
    prior_high = prior_day.get("high", 0)
    prior_low = prior_day.get("low", 0)
    sym_rsi14 = prior_day.get("rsi14")

    # --- Context filters ---
    spy = spy_context or {}
    spy_trend = spy.get("trend", "neutral")
    phase = get_session_phase()
    entries_allowed = allow_new_entries()

    # Compute VWAP for context enrichment
    from analytics.intraday_data import (
        compute_vwap, classify_gap,
        compute_opening_range, check_mtf_alignment, track_gap_fill,
    )
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

    # Compute opening range for ORB rule
    opening_range = compute_opening_range(intraday_bars)

    # Compute MTF alignment
    mtf = check_mtf_alignment(intraday_bars)

    # Track gap fill
    gap_fill_info = track_gap_fill(intraday_bars, today_open, prior_close)

    # Compute symbol intraday % change for RS filter
    sym_intraday_change = 0.0
    if not intraday_bars.empty and len(intraday_bars) >= 2:
        sym_open = intraday_bars["Open"].iloc[0]
        sym_current = last_bar["Close"]
        if sym_open > 0:
            sym_intraday_change = (sym_current - sym_open) / sym_open * 100

    # Session low for structural MA bounce stops
    session_low = intraday_bars["Low"].min() if not intraday_bars.empty else 0

    # Detect intraday supports (used by both bounce BUY rule and breakdown SHORT)
    from analytics.intraday_data import detect_intraday_supports
    intraday_supports = detect_intraday_supports(intraday_bars)

    # Detect hourly resistance from multi-day 1h bars
    from analytics.intraday_data import fetch_hourly_bars, detect_hourly_resistance
    hourly_resistance: list[float] = []
    try:
        bars_1h = fetch_hourly_bars(symbol)
        if not bars_1h.empty:
            hourly_resistance = detect_hourly_resistance(bars_1h)
    except Exception:
        pass

    # --- BUY rules ---
    spy_regime = spy.get("regime", "CHOPPY")
    caution_notes = []
    if spy_trend == "bearish":
        caution_notes.append("SPY bearish (below 20MA)")
    if spy_regime == "CHOPPY":
        caution_notes.append(f"SPY regime: {spy_regime}")
    if spy_regime == "TRENDING_DOWN":
        caution_notes.append("SPY TRENDING DOWN — reduced confidence")
    if not entries_allowed:
        caution_notes.append(f"session: {phase}")
    caution_suffix = f" | CAUTION: {', '.join(caution_notes)}" if caution_notes else ""

    if not is_cooled_down:
        sig = check_ma_bounce_20(symbol, last_bar, ma20, ma50)
        if sig:
            sig.message += f" ({phase})"
            if vwap_pos:
                sig.message += f" — price {vwap_pos}"
                if vwap_pos == "below VWAP":
                    sig.message += " (use caution)"
                else:
                    sig.message += " (bullish confirmation)"
            sig.message += caution_suffix
            signals.append(sig)

        sig = check_ma_bounce_50(symbol, last_bar, ma20, ma50, prior_close)
        if sig:
            sig.message += f" ({phase})"
            if vwap_pos:
                sig.message += f" — price {vwap_pos}"
            sig.message += caution_suffix
            signals.append(sig)

        sig = check_ma_bounce_100(symbol, last_bar, ma100, prior_close)
        if sig:
            sig.message += f" ({phase})"
            if vwap_pos:
                sig.message += f" — price {vwap_pos}"
            sig.message += caution_suffix
            signals.append(sig)

        sig = check_ma_bounce_200(symbol, last_bar, ma200, prior_close)
        if sig:
            sig.message += f" ({phase})"
            if vwap_pos:
                sig.message += f" — price {vwap_pos}"
            sig.message += caution_suffix
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
            sig.message += caution_suffix
            signals.append(sig)

        if AlertType.INSIDE_DAY_BREAKOUT.value in ENABLED_RULES:
            sig = check_inside_day_breakout(symbol, last_bar, prior_day)
            if sig:
                sig.message += f" ({phase})"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        if AlertType.OUTSIDE_DAY_BREAKOUT.value in ENABLED_RULES:
            sig = check_outside_day_breakout(symbol, last_bar, prior_day)
            if sig:
                sig.message += f" ({phase})"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        # --- Opening Range Breakout ---
        if AlertType.OPENING_RANGE_BREAKOUT.value in ENABLED_RULES:
            sig = check_opening_range_breakout(
                symbol, last_bar, opening_range, bar_vol, avg_vol,
            )
            if sig:
                sig.message += f" ({phase})"
                sig.message += caution_suffix
                signals.append(sig)

        # --- Intraday Support Bounce ---
        if AlertType.INTRADAY_SUPPORT_BOUNCE.value in ENABLED_RULES:
            sig = check_intraday_support_bounce(
                symbol, last_bar, intraday_supports, bar_vol, avg_vol,
            )
            if sig:
                sig.message += f" ({phase})"
                # SPY bounce correlation — boost confidence
                if spy.get("spy_bouncing"):
                    sig.confidence = "high"
                    spy_low = spy.get("spy_intraday_low", 0)
                    sig.message += (
                        f" | SPY also bouncing from session low ${spy_low:.2f}"
                    )
                sig.message += caution_suffix
                signals.append(sig)

        # --- Session Low Double-Bottom ---
        sig = check_session_low_retest(
            symbol, intraday_bars, last_bar, bar_vol, avg_vol,
        )
        if sig:
            sig.message += f" ({phase})"
            if spy.get("spy_bouncing"):
                sig.confidence = "high"
                spy_low = spy.get("spy_intraday_low", 0)
                sig.message += f" | SPY double-bottom at ${spy_low:.2f}"
            sig.message += caution_suffix
            signals.append(sig)

        # --- Planned Level Touch ---
        sig = check_planned_level_touch(symbol, last_bar, prior_day)
        if sig:
            sig.message += f" ({phase})"
            if vwap_pos:
                sig.message += f" — price {vwap_pos}"
            sig.message += caution_suffix
            signals.append(sig)

        # --- Buy Zone Approach ---
        if AlertType.BUY_ZONE_APPROACH.value in ENABLED_RULES:
            sig = check_buy_zone_approach(symbol, last_bar, prior_day)
            if sig:
                sig.message += f" ({phase})"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        # --- Weekly Level Touch ---
        sig = check_weekly_level_touch(symbol, last_bar, prior_day)
        if sig:
            sig.message += f" ({phase})"
            if vwap_pos:
                sig.message += f" — price {vwap_pos}"
            sig.message += caution_suffix
            signals.append(sig)

    # --- Gap Fill (INFO — fires regardless of cooldown) ---
    if AlertType.GAP_FILL.value in ENABLED_RULES:
        sig = check_gap_fill(symbol, last_bar, gap_fill_info)
        if sig:
            sig.message += f" ({phase})"
            signals.append(sig)

    # --- SELL rules (always fire regardless of SPY/session) ---

    entries = active_entries or []
    has_active = len(entries) > 0

    sig = check_resistance_prior_high(symbol, last_bar, prior_high, has_active)
    if sig:
        signals.append(sig)

    sig = check_hourly_resistance_approach(symbol, last_bar, hourly_resistance, has_active)
    if sig:
        signals.append(sig)

    sig = check_ma_resistance(symbol, last_bar, ma20, ma50, ma100, ma200, prior_close)
    if sig:
        signals.append(sig)

    sig = check_resistance_prior_low(symbol, last_bar, prior_low)
    if sig:
        signals.append(sig)

    # --- Opening Range Breakdown (SELL — informational) ---
    if AlertType.OPENING_RANGE_BREAKDOWN.value in ENABLED_RULES:
        sig = check_orb_breakdown(symbol, last_bar, opening_range, bar_vol, avg_vol)
        if sig:
            sig.message += f" ({phase})"
            signals.append(sig)

    # Build a synthetic bar spanning all intraday highs/lows so target/stop
    # detection doesn't miss hits between poll intervals.
    session_bar = pd.Series({
        "High": intraday_bars["High"].max(),
        "Low": intraday_bars["Low"].min(),
        "Close": last_bar["Close"],
        "Open": last_bar["Open"],
        "Volume": last_bar["Volume"],
    })

    for entry in entries:
        ep = entry.get("entry_price") or 0
        t1 = entry.get("target_1") or 0
        t2 = entry.get("target_2") or 0
        sp = entry.get("stop_price") or 0

        sig = check_target_1_hit(symbol, session_bar, ep, t1)
        if sig:
            signals.append(sig)

        sig = check_target_2_hit(symbol, session_bar, ep, t2)
        if sig:
            signals.append(sig)

        sig = check_stop_loss_hit(symbol, session_bar, ep, sp)
        if sig:
            signals.append(sig)

    # --- Auto Stop-Out (SELL — tracked BUY entries) ---
    if auto_stop_entries:
        sig = check_auto_stop_out(symbol, last_bar, auto_stop_entries)
        if sig:
            signals.append(sig)

    # --- Support Breakdown (SHORT) ---
    from analytics.signal_engine import _find_nearest_support

    nearest_support, _ = _find_nearest_support(last_bar["Close"], prior_low, ma20, ma50)

    # Include intraday hourly supports — use closest below current price
    for sup in sorted(intraday_supports, key=lambda s: s["level"], reverse=True):
        lvl = sup["level"]
        if lvl < last_bar["Close"]:
            # Tighten nearest_support if intraday level is closer
            if nearest_support <= 0 or lvl > nearest_support:
                nearest_support = lvl
            break

    sig = check_support_breakdown(
        symbol, last_bar, prior_low, nearest_support, bar_vol, avg_vol,
    )
    if sig:
        sig.message += f" ({phase})"
        if intraday_supports:
            fmt_supports = [f"${s['level']:.2f}" for s in intraday_supports]
            sig.message += f" | intraday supports: {fmt_supports}"
        # Tag breakdown at session low — most significant intraday event
        # Use pre-breakdown session low (exclude last bar which is the breakdown bar)
        if len(intraday_bars) > 1:
            pre_breakdown_low = intraday_bars["Low"].iloc[:-1].min()
        else:
            pre_breakdown_low = 0
        broken_support = min(prior_low, nearest_support) if nearest_support > 0 else prior_low
        if pre_breakdown_low > 0 and broken_support > 0:
            sl_proximity = abs(broken_support - pre_breakdown_low) / pre_breakdown_low
            if sl_proximity <= SESSION_LOW_BREAK_PROXIMITY_PCT:
                sig.confidence = "high"
                sig.message += " | SESSION LOW BREAK — market dynamics shift"
        # Exit-only: suppress when no active position, convert to EXIT LONG when active
        if has_active:
            sig.direction = "SELL"
            sig.confidence = "high"
            sig.message = (
                f"EXIT LONG — support breakdown at ${broken_support:.2f}, "
                f"volume {bar_vol / avg_vol:.1f}x avg ({phase}). "
                f"Close long position immediately."
            )
            signals.append(sig)
        else:
            logger.debug(
                "%s: support breakdown suppressed (no active position)", symbol,
            )

    # --- EMA Crossover 5/20 (BUY — mega-cap only) ---
    if not is_cooled_down and AlertType.EMA_CROSSOVER_5_20.value in ENABLED_RULES:
        from config import MEGA_CAP

        is_mega = symbol.upper() in MEGA_CAP
        sig = check_ema_crossover_5_20(symbol, intraday_bars, is_mega)
        if sig:
            sig.message += f" ({phase})"
            sig.message += caution_suffix
            signals.append(sig)

    # --- Breakdown day suppression: remove BUY signals when SHORT fires ---
    has_breakdown = any(s.alert_type == AlertType.SUPPORT_BREAKDOWN for s in signals)
    if has_breakdown:
        dropped = [s for s in signals if s.direction == "BUY"]
        for s in dropped:
            logger.debug("%s: breakdown day filter dropped BUY %s", symbol, s.alert_type.value)
        signals = [s for s in signals if s.direction != "BUY"]

    # --- Dedup: remove signals already fired today ---
    if fired_today:
        pre_dedup = signals[:]
        signals = [
            s for s in signals
            if (symbol, s.alert_type.value) not in fired_today
        ]
        for s in pre_dedup:
            if (symbol, s.alert_type.value) in fired_today:
                logger.debug("%s: dedup filter dropped %s (already fired today)", symbol, s.alert_type.value)

    # --- Noise filter: drop low-volume BUY signals ---
    vol_ratio = bar_vol / avg_vol if avg_vol > 0 else 1.0
    pre_noise = signals[:]
    signals = [s for s in signals if not _should_skip_noise(s, vol_ratio)]
    for s in pre_noise:
        if _should_skip_noise(s, vol_ratio):
            logger.debug(
                "%s: noise filter dropped %s (vol_ratio=%.2f < threshold)",
                symbol, s.alert_type.value, vol_ratio,
            )

    # --- Staleness filter: drop BUY signals where price already ran past entry + 1R ---
    current_price = last_bar["Close"]
    pre_stale = signals[:]
    signals = [
        s for s in signals
        if not (s.direction == "BUY" and s.entry and s.stop
                and current_price > s.entry + (s.entry - s.stop))
    ]
    for s in pre_stale:
        if (s.direction == "BUY" and s.entry and s.stop
                and current_price > s.entry + (s.entry - s.stop)):
            logger.debug(
                "%s: staleness filter dropped %s (price=%.2f > entry+1R=%.2f)",
                symbol, s.alert_type.value, current_price,
                s.entry + (s.entry - s.stop),
            )

    # --- Overhead MA resistance filter: suppress BUY heading into nearby MA above ---
    pre_overhead = signals[:]
    filtered_signals: list[AlertSignal] = []
    for s in signals:
        if s.direction == "BUY" and s.entry:
            blocked, ma_label = _has_overhead_ma_resistance(
                s.entry, ma20, ma50, ma100, ma200,
            )
            if blocked:
                logger.debug(
                    "%s: overhead MA filter dropped %s (entry=%.2f near %s)",
                    symbol, s.alert_type.value, s.entry, ma_label,
                )
                continue
        filtered_signals.append(s)
    signals = filtered_signals

    # --- Relative Strength filter ---
    spy_intraday_change = spy.get("intraday_change_pct", 0.0)

    # --- Enrich all signals with context ---
    _MA_BOUNCE_RULES = {
        AlertType.MA_BOUNCE_20, AlertType.MA_BOUNCE_50,
        AlertType.MA_BOUNCE_100, AlertType.MA_BOUNCE_200,
    }
    for sig in signals:
        # Structural stop: use session low for MA bounce rules
        if (sig.direction == "BUY" and sig.alert_type in _MA_BOUNCE_RULES
                and session_low > 0 and session_low < sig.entry):
            structural_stop = round(
                session_low * (1 - MA_BOUNCE_SESSION_STOP_PCT), 2,
            )
            sig.stop = structural_stop
            risk = sig.entry - sig.stop
            sig.target_1 = round(sig.entry + risk, 2)
            sig.target_2 = round(sig.entry + 2 * risk, 2)

        # Apply per-symbol risk cap to all BUY signals and recalculate targets
        if sig.direction == "BUY" and sig.entry and sig.stop:
            capped_stop = _cap_risk(sig.entry, sig.stop, symbol=symbol)
            if capped_stop != sig.stop:
                sig.stop = capped_stop
                risk = sig.entry - sig.stop
                sig.target_1 = round(sig.entry + risk, 2)
                sig.target_2 = round(sig.entry + 2 * risk, 2)

        # Smart resistance-based targets (override R-based defaults)
        _STRUCTURAL_TARGET_RULES = {
            AlertType.INSIDE_DAY_BREAKOUT,
            AlertType.PLANNED_LEVEL_TOUCH,
            AlertType.WEEKLY_LEVEL_TOUCH,
        }
        if (sig.direction == "BUY" and sig.entry and sig.stop
                and sig.alert_type not in _STRUCTURAL_TARGET_RULES):
            smart = _find_resistance_targets(
                sig.entry, sig.stop, prior_day, current_vwap,
                hourly_resistance=hourly_resistance,
            )
            if smart:
                sig.target_1, sig.target_2, t1_label, t2_label = smart
                sig.message += f" | T1: {t1_label} ${sig.target_1:.2f}, T2: {t2_label} ${sig.target_2:.2f}"

        # Minimum target distance: prevent tiny T1/T2 on chased entries
        if (sig.direction == "BUY" and sig.entry and sig.target_1 is not None):
            min_dist = sig.entry * MIN_TARGET_DISTANCE_PCT
            if sig.target_1 < sig.entry + min_dist:
                sig.target_1 = round(sig.entry + min_dist, 2)
            if (sig.target_2 is not None
                    and sig.target_2 - sig.target_1 < min_dist):
                sig.target_2 = round(sig.target_1 + min_dist, 2)

        # Guardrail: T1 must be above the current price for BUY signals.
        # When entry < current price (e.g. ORB entry = breakout level),
        # R-based or smart targets can land below the displayed price.
        if (sig.direction == "BUY" and sig.target_1 is not None
                and sig.entry and sig.stop
                and sig.target_1 <= current_price):
            risk = sig.entry - sig.stop
            if risk > 0:
                sig.target_1 = round(current_price + risk, 2)
                sig.target_2 = round(current_price + 2 * risk, 2)

        # MA confluence detection: flag when an MA aligns with a horizontal entry.
        # Runs before macro demotions so CHOPPY/SPY can still override the boost.
        if sig.direction == "BUY" and sig.entry:
            has_conf, conf_label, conf_val = _check_ma_confluence(
                sig.entry, sig.alert_type, ma20, ma50, ma100, ma200,
            )
            if has_conf:
                sig.confluence = True
                sig.confluence_ma = conf_label
                sig.message += f" | {conf_label} confluence at {conf_val}"
                if sig.confidence == "medium":
                    sig.confidence = "high"

        sig.spy_trend = spy_trend
        sig.session_phase = phase
        sig.volume_label = vol_label
        sig.vwap_position = vwap_pos
        sig.gap_info = gap_info
        if sig.direction == "BUY" and vol_label:
            sig.message += f" | {vol_label}"
        if gap_info and sig.direction == "BUY":
            sig.message += f" | {gap_info}"

        # Volume exhaustion detection
        exhaustion_type, exhaustion_msg = _detect_volume_exhaustion(intraday_bars, avg_vol)
        if sig.direction == "BUY" and exhaustion_type == "seller_exhaustion":
            if sig.confidence == "medium":
                sig.confidence = "high"
            sig.message += f" | {exhaustion_msg}"
        elif sig.direction == "BUY" and exhaustion_type == "buyer_exhaustion":
            sig.message += f" | CAUTION: {exhaustion_msg}"

        # RS filter: demote BUY confidence when severely underperforming SPY
        if sig.direction == "BUY" and spy_intraday_change != 0:
            rs_ratio = sym_intraday_change / spy_intraday_change if spy_intraday_change != 0 else 0.0
            sig.rs_ratio = round(rs_ratio, 2)
            # If both are negative and symbol is falling N times harder than SPY
            if (spy_intraday_change < 0 and sym_intraday_change < 0
                    and sym_intraday_change < spy_intraday_change * RS_UNDERPERFORM_FACTOR):
                if sig.confidence == "high":
                    sig.confidence = "medium"
                sig.message += (
                    f" | RS CAUTION: {symbol} {sym_intraday_change:+.1f}% vs "
                    f"SPY {spy_intraday_change:+.1f}% (underperforming {rs_ratio:.1f}x)"
                )

        # Regime demotion: reduce BUY confidence in CHOPPY markets
        if sig.direction == "BUY" and spy_regime == "CHOPPY":
            if sig.confidence == "high":
                sig.confidence = "medium"
            sig.message += " | CHOPPY market — reduced confidence"

        # SPY TRENDING_DOWN: strongest demotion — demote to medium, strong warning
        if sig.direction == "BUY" and spy_regime == "TRENDING_DOWN":
            if sig.confidence == "high":
                sig.confidence = "medium"
            sig.message += " | SPY TRENDING DOWN — use extreme caution"

        # SPY S/R level reaction: adjust BUY confidence based on SPY position
        if sig.direction == "BUY":
            spy_at_resistance = spy.get("spy_at_resistance", False)
            spy_at_support = spy.get("spy_at_support", False)
            spy_level_label = spy.get("spy_level_label", "")
            spy_bounce_rate = spy.get("spy_support_bounce_rate", 0.5)

            if spy_at_resistance:
                if sig.confidence == "high":
                    sig.confidence = "medium"
                sig.message += f" | SPY at resistance ({spy_level_label}) — reduced confidence"
            elif spy_at_support:
                if spy_bounce_rate >= SPY_STRONG_BOUNCE_RATE:
                    sig.message += (
                        f" | SPY at support ({spy_level_label},"
                        f" {spy_bounce_rate:.0%} hist. bounce rate)"
                    )
                else:
                    if sig.confidence == "high":
                        sig.confidence = "medium"
                    sig.message += (
                        f" | SPY weak support ({spy_level_label},"
                        f" {spy_bounce_rate:.0%} hist. bounce rate)"
                    )

        # RSI confidence adjustment (runs AFTER regime demotion — intentional)
        spy_rsi = spy.get("spy_rsi14")
        if sig.direction == "BUY" and spy_rsi is not None:
            if spy_rsi < SPY_RSI_OVERSOLD:
                if sig.confidence == "medium":
                    sig.confidence = "high"
                sig.message += f" | SPY RSI oversold ({spy_rsi:.0f})"
            elif spy_rsi > SPY_RSI_OVERBOUGHT:
                if sig.confidence == "high":
                    sig.confidence = "medium"
                sig.message += f" | SPY RSI overbought ({spy_rsi:.0f})"

        # Per-symbol RSI: crash risk below 30, overbought above 70
        if sig.direction == "BUY" and sym_rsi14 is not None:
            if sym_rsi14 < SYM_RSI_OVERSOLD:
                if sig.confidence == "high":
                    sig.confidence = "medium"
                sig.message += f" | {symbol} RSI crash risk ({sym_rsi14:.0f})"
            elif sym_rsi14 > SYM_RSI_OVERBOUGHT:
                sig.message += f" | {symbol} RSI overbought ({sym_rsi14:.0f})"

        # EMA spread observation (informational only, no confidence change)
        spy_ema_spread = spy.get("spy_ema_spread_pct", 0.0)
        if sig.direction == "BUY" and abs(spy_ema_spread) < SPY_EMA_CONVERGENCE_PCT * 100:
            sig.message += " | SPY EMAs converging — big move pending"

        # SPY MA-level annotation
        spy_ma_support = spy.get("spy_at_ma_support")
        if sig.direction == "BUY" and spy_ma_support:
            if spy_rsi is not None and spy_rsi < 40:
                sig.message += (
                    f" | SPY oversold at {spy_ma_support} (institutional level)"
                )
            else:
                sig.message += f" | SPY at {spy_ma_support} support"

        # MTF alignment enrichment
        sig.mtf_aligned = mtf["mtf_aligned"]
        if sig.direction == "BUY":
            if mtf["mtf_aligned"]:
                sig.message += " | 15m trend aligned"
            else:
                sig.message += " | 15m trend NOT aligned (caution)"

        sig.score = _score_alert(sig, ma20, ma50, last_bar["Close"], vol_ratio)

        # Confluence score boost
        if sig.confluence:
            sig.score = min(100, sig.score + 10)

        # MTF alignment score boost
        if sig.direction == "BUY" and mtf["mtf_aligned"]:
            sig.score = min(100, sig.score + 10)

        sig.score_label = (
            "A+" if sig.score >= 90
            else "A" if sig.score >= 75
            else "B" if sig.score >= 50
            else "C"
        )

    # --- Consolidate same-symbol BUY signals ---
    signals = _consolidate_signals(signals)

    return signals
