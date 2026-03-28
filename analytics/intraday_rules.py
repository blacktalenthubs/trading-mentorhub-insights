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
import math
from dataclasses import dataclass
from enum import Enum

import pandas as pd

logger = logging.getLogger("intraday_rules")

from alert_config import (
    BOUNCE_ALERT_TYPES,
    BREAKDOWN_CONVICTION_PCT,
    BREAKDOWN_VOLUME_RATIO,
    BUY_ZONE_PROXIMITY_PCT,
    CONFLUENCE_BAND_PCT,
    CONSOLIDATION_MAX_BOOST,
    CONSOLIDATION_SCORE_BOOST,
    DAILY_DB_INTRADAY_PROXIMITY_PCT,
    DAILY_DB_MAX_DISTANCE_CRYPTO_PCT,
    DAILY_DB_MAX_DISTANCE_PCT,
    DAILY_DB_STOP_OFFSET_PCT,
    DAY_TRADE_MAX_RISK_PCT,
    EMA_MIN_BARS,
    ENABLED_RULES,
    HOURLY_RESISTANCE_APPROACH_PCT,
    HOURLY_RES_REJECTION_CLOSE_PCT,
    HOURLY_RES_REJECTION_MIN_BARS,
    HOURLY_RES_REJECTION_PROXIMITY_PCT,
    HOURLY_RES_REJECTION_STOP_OFFSET_PCT,
    LOW_VOLUME_SKIP_RATIO,
    MA_BOUNCE_ALERT_TYPES,
    MA_BOUNCE_LOOKBACK_BARS,
    MA_BOUNCE_MAX_DISTANCE_PCT,
    MA_BOUNCE_PROXIMITY_PCT,
    MA_BOUNCE_SESSION_STOP_PCT,
    MA_STOP_OFFSET_PCT,
    MA100_BOUNCE_PROXIMITY_PCT,
    MA100_STOP_OFFSET_PCT,
    MA200_BOUNCE_PROXIMITY_PCT,
    MA200_STOP_OFFSET_PCT,
    MIN_STOP_DISTANCE_PCT,
    MIN_TARGET_DISTANCE_PCT,
    ORB_BREAKDOWN_VOLUME_RATIO,
    ORB_MIN_RANGE_PCT,
    ORB_VOLUME_RATIO,
    OVERHEAD_MA_RESISTANCE_PCT,
    PDH_BREAKOUT_VOLUME_RATIO,
    PDH_REJECTION_PROXIMITY_PCT,
    PDH_RETEST_HOLD_BARS,
    PDH_RETEST_MAX_DISTANCE_PCT,
    PDH_RETEST_PROXIMITY_PCT,
    PDH_RETEST_STOP_OFFSET_PCT,
    INSIDE_DAY_DIP_MIN_PCT,
    INSIDE_DAY_FORMING_MIN_BARS,
    INSIDE_DAY_SCORE_BOOST,
    PDL_BOUNCE_HOLD_BARS,
    PDL_BOUNCE_MAX_DISTANCE_CRYPTO_PCT,
    PDL_BOUNCE_MAX_DISTANCE_PCT,
    PDL_BOUNCE_PROXIMITY_PCT,
    PDL_BOUNCE_STOP_OFFSET_PCT,
    PDL_DIP_MIN_PCT,
    PDL_RECLAIM_MAX_DISTANCE_PCT,
    PDL_STOP_OFFSET_PCT,
    PER_SYMBOL_RISK,
    RESISTANCE_PROXIMITY_PCT,
    WEEKLY_LEVEL_PROXIMITY_PCT,
    WEEKLY_LEVEL_STOP_OFFSET_PCT,
    MONTHLY_LEVEL_PROXIMITY_PCT,
    MONTHLY_LEVEL_STOP_OFFSET_PCT,
    RS_UNDERPERFORM_FACTOR,
    SCORE_V2_RR_BONUS_POINTS,
    SCORE_V2_RR_BONUS_THRESHOLD,
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
    SUPPORT_BOUNCE_LOOKBACK_BARS,
    SUPPORT_BOUNCE_MAX_CLOSE_BELOW_PCT,
    SUPPORT_BOUNCE_MAX_DISTANCE_PCT,
    SUPPORT_BOUNCE_MIN_TOUCHES,
    SUPPORT_BOUNCE_PROXIMITY_PCT,
    VWAP_BOUNCE_ABOVE_PCT,
    VWAP_BOUNCE_MAX_DISTANCE_PCT,
    VWAP_BOUNCE_MIN_BARS,
    VWAP_BOUNCE_STOP_OFFSET_PCT,
    VWAP_BOUNCE_TOUCH_PCT,
    VWAP_RECLAIM_MAX_DISTANCE_PCT,
    VWAP_SYMBOLS,
    VWAP_RECLAIM_MIN_BARS_AFTER_LOW,
    VWAP_RECLAIM_MIN_RECOVERY_PCT,
    VWAP_RECLAIM_MORNING_BARS,
    VWAP_RECLAIM_STOP_OFFSET_PCT,
    VWAP_RECLAIM_VOLUME_RATIO,
    OPENING_LOW_BASE_WINDOW_BARS,
    OPENING_LOW_BASE_HOLD_BARS,
    OPENING_LOW_BASE_HOLD_PCT,
    OPENING_LOW_BASE_MIN_DIP_PCT,
    MORNING_LOW_RETEST_MIN_BARS,
    MORNING_LOW_RETEST_RALLY_PCT,
    MORNING_LOW_RETEST_PROXIMITY_PCT,
    MORNING_LOW_RETEST_STOP_OFFSET_PCT,
    FIRST_HOUR_HIGH_BREAKOUT_MIN_BARS,
    FIRST_HOUR_HIGH_BREAKOUT_VOLUME_RATIO,
    MA_RECLAIM_STOP_OFFSET_PCT,
    MA_RECLAIM_MAX_DISTANCE_PCT,
    PDL_BREAKDOWN_VOLUME_RATIO,
    PDL_BREAKDOWN_MAX_DISTANCE_PCT,
    PDL_RESISTANCE_PROXIMITY_PCT,
    PDL_RESISTANCE_REJECTION_PCT,
    MA_APPROACH_PROXIMITY_PCT,
    MA100_APPROACH_PROXIMITY_PCT,
    MA200_APPROACH_PROXIMITY_PCT,
    OPENING_LOW_BASE_STOP_OFFSET_PCT,
    RETRACEMENT_MIN_RALLY_PCT,
    RETRACEMENT_MIN_AGE_BARS,
    RETRACEMENT_PROXIMITY_PCT,
    RETRACEMENT_STOP_OFFSET_PCT,
    ATR_PERIOD,
    ATR_DAY_TRADE_MULTIPLIER,
    USE_ATR_STOPS,
    TRAILING_STOP_ATR_MULTIPLIER,
    ENABLE_TRAILING_STOPS,
    MACD_FAST,
    MACD_SLOW,
    MACD_SIGNAL,
    BB_PERIOD,
    BB_STD_DEV,
    BB_SQUEEZE_LOOKBACK,
    BB_SQUEEZE_PERCENTILE,
    FIB_LEVELS,
    FIB_BOUNCE_PROXIMITY_PCT,
    GAP_AND_GO_MIN_PCT,
    GAP_AND_GO_VOLUME_RATIO,
)
from analytics.market_hours import (
    allow_new_entries,
    get_session_phase,
    get_session_phase_for_symbol,
)


class AlertType(str, Enum):
    MA_BOUNCE_20 = "ma_bounce_20"
    MA_BOUNCE_50 = "ma_bounce_50"
    MA_BOUNCE_100 = "ma_bounce_100"
    MA_BOUNCE_200 = "ma_bounce_200"
    PRIOR_DAY_LOW_RECLAIM = "prior_day_low_reclaim"
    PRIOR_DAY_LOW_BOUNCE = "prior_day_low_bounce"
    PRIOR_DAY_HIGH_BREAKOUT = "prior_day_high_breakout"
    PDH_TEST = "pdh_test"
    PDH_RETEST_HOLD = "pdh_retest_hold"
    INSIDE_DAY_BREAKOUT = "inside_day_breakout"
    INSIDE_DAY_BREAKDOWN = "inside_day_breakdown"
    INSIDE_DAY_RECLAIM = "inside_day_reclaim"
    RESISTANCE_PRIOR_HIGH = "resistance_prior_high"
    PDH_REJECTION = "pdh_rejection"
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
    MULTI_DAY_DOUBLE_BOTTOM = "multi_day_double_bottom"
    GAP_FILL = "gap_fill"
    PLANNED_LEVEL_TOUCH = "planned_level_touch"
    WEEKLY_LEVEL_TOUCH = "weekly_level_touch"
    HOURLY_RESISTANCE_APPROACH = "hourly_resistance_approach"
    MA_RESISTANCE = "ma_resistance"
    OUTSIDE_DAY_BREAKOUT = "outside_day_breakout"
    RESISTANCE_PRIOR_LOW = "resistance_prior_low"
    VWAP_RECLAIM = "vwap_reclaim"
    VWAP_BOUNCE = "vwap_bounce"
    OPENING_LOW_BASE = "opening_low_base"
    WEEKLY_HIGH_BREAKOUT = "weekly_high_breakout"
    WEEKLY_HIGH_TEST = "weekly_high_test"
    WEEKLY_HIGH_RESISTANCE = "weekly_high_resistance"
    WEEKLY_LOW_TEST = "weekly_low_test"
    WEEKLY_LOW_BREAKDOWN = "weekly_low_breakdown"
    MONTHLY_LEVEL_TOUCH = "monthly_level_touch"
    MONTHLY_HIGH_BREAKOUT = "monthly_high_breakout"
    MONTHLY_HIGH_TEST = "monthly_high_test"
    MONTHLY_HIGH_RESISTANCE = "monthly_high_resistance"
    MONTHLY_LOW_TEST = "monthly_low_test"
    MONTHLY_LOW_BREAKDOWN = "monthly_low_breakdown"
    EMA_BOUNCE_20 = "ema_bounce_20"
    EMA_BOUNCE_50 = "ema_bounce_50"
    EMA_BOUNCE_100 = "ema_bounce_100"
    EMA_BOUNCE_200 = "ema_bounce_200"
    EMA_RESISTANCE = "ema_resistance"
    # Swing trade — RSI zones
    SWING_RSI_APPROACHING_OVERSOLD = "swing_rsi_approaching_oversold"
    SWING_RSI_OVERSOLD = "swing_rsi_oversold"
    SWING_RSI_APPROACHING_OVERBOUGHT = "swing_rsi_approaching_overbought"
    SWING_RSI_OVERBOUGHT = "swing_rsi_overbought"
    # Swing trade — setups
    SWING_EMA_CROSSOVER_5_20 = "swing_ema_crossover_5_20"
    SWING_200MA_RECLAIM = "swing_200ma_reclaim"
    SWING_PULLBACK_20EMA = "swing_pullback_20ema"
    # Swing trade — management
    SWING_TARGET_HIT = "swing_target_hit"
    SWING_STOPPED_OUT = "swing_stopped_out"
    # Informational — first hour summary
    FIRST_HOUR_SUMMARY = "first_hour_summary"
    # Professional rules — day trade
    MACD_HISTOGRAM_FLIP = "macd_histogram_flip"
    BB_SQUEEZE_BREAKOUT = "bb_squeeze_breakout"
    TRAILING_STOP_HIT = "trailing_stop_hit"
    SESSION_HIGH_RETRACEMENT = "session_high_retracement"
    GAP_AND_GO = "gap_and_go"
    FIB_RETRACEMENT_BOUNCE = "fib_retracement_bounce"
    # Professional rules — swing
    SWING_MACD_CROSSOVER = "swing_macd_crossover"
    SWING_RSI_DIVERGENCE = "swing_rsi_divergence"
    SWING_BULL_FLAG = "swing_bull_flag"
    SWING_CANDLE_PATTERN = "swing_candle_pattern"
    SWING_CONSECUTIVE_RED = "swing_consecutive_red"
    # MA/EMA approach notice (heads-up, not a BUY)
    MA_APPROACH = "ma_approach"
    # Prior day low breakdown / resistance
    PRIOR_DAY_LOW_BREAKDOWN = "prior_day_low_breakdown"
    PRIOR_DAY_LOW_RESISTANCE = "prior_day_low_resistance"
    # Consolidation notice
    HOURLY_CONSOLIDATION = "hourly_consolidation"
    # Per-symbol consolidation breakout
    CONSOL_BREAKOUT_LONG = "consol_breakout_long"
    CONSOL_BREAKOUT_SHORT = "consol_breakout_short"
    # Session low bounce at hourly support → VWAP
    SESSION_LOW_BOUNCE_VWAP = "session_low_bounce_vwap"
    # SPY Short entry
    SPY_SHORT_ENTRY = "spy_short_entry"
    # Morning range retests
    MORNING_LOW_RETEST = "morning_low_retest"
    SESSION_LOW_REVERSAL = "session_low_reversal"
    VWAP_LOSS = "vwap_loss"
    EMA_REJECTION_SHORT = "ema_rejection_short"
    EMA_LOSS_SHORT = "ema_loss_short"
    HOURLY_RESISTANCE_REJECTION_SHORT = "hourly_resistance_rejection_short"
    SESSION_LOW_BREAKDOWN = "session_low_breakdown"
    MORNING_LOW_BREAKDOWN = "morning_low_breakdown"
    PDH_FAILED_BREAKOUT = "pdh_failed_breakout"
    FIRST_HOUR_HIGH_BREAKOUT = "first_hour_high_breakout"
    # MA/EMA reclaim — price crosses above key daily MA/EMA
    MA_RECLAIM_20 = "ma_reclaim_20"
    MA_RECLAIM_50 = "ma_reclaim_50"
    MA_RECLAIM_100 = "ma_reclaim_100"
    MA_RECLAIM_200 = "ma_reclaim_200"
    EMA_RECLAIM_20 = "ema_reclaim_20"
    EMA_RECLAIM_50 = "ema_reclaim_50"
    EMA_RECLAIM_100 = "ema_reclaim_100"
    EMA_RECLAIM_200 = "ema_reclaim_200"
    # Informational — inside day forming (today's range within yesterday's)
    INSIDE_DAY_FORMING = "inside_day_forming"


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
    score_v2: int = 0
    score_v2_label: str = ""
    rs_ratio: float = 0.0
    mtf_aligned: bool = False
    confluence: bool = False
    confluence_ma: str = ""
    narrative: str = ""
    day_pattern: str = ""      # "inside", "outside", "normal" — prior day's candle pattern
    ma_defending: str = ""     # e.g. "100MA" — nearest MA below price acting as support
    ma_rejected_by: str = ""   # e.g. "50EMA" — nearest MA above price acting as resistance
    score_factors: dict | None = None  # Breakdown: {"ma": 25, "vol": 15, "conf": 25, ...}
    _suppress_telegram: bool = False   # If True, record to DB but skip Telegram notification


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

def _is_reversal_candle(bars: pd.DataFrame, idx: int) -> bool:
    """Check if bar at idx shows bullish reversal characteristics.

    Returns True if the bar is a hammer, has a long lower wick (>= 60% of
    range), or is a bullish engulfing pattern.  Used to quality-filter
    MA/EMA bounce signals — non-reversal touches get demoted rather than
    suppressed so the educational platform still surfaces them.
    """
    if idx < 1 or idx >= len(bars):
        return False
    bar = bars.iloc[idx]
    o, h, l, c = float(bar["Open"]), float(bar["High"]), float(bar["Low"]), float(bar["Close"])
    bar_range = h - l
    if bar_range <= 0:
        return False
    body = abs(c - o)
    lower_wick = min(o, c) - l

    # Hammer: lower wick >= 1.5x body, close in upper 40%
    if lower_wick >= 1.5 * body and (c - l) / bar_range >= 0.6:
        return True

    # Long lower wick: >= 60% of range
    if lower_wick / bar_range >= 0.6:
        return True

    # Bullish engulfing: closes green, range > prior range
    prev = bars.iloc[idx - 1]
    prev_range = float(prev["High"]) - float(prev["Low"])
    if c > o and bar_range > prev_range and c > float(prev["Open"]):
        return True

    return False


def _find_ma_bounce_touch(
    bars: pd.DataFrame,
    ma_level: float,
    proximity_pct: float,
) -> float | None:
    """Scan last MA_BOUNCE_LOOKBACK_BARS bars for a touch near *ma_level*.

    Checks both Low and Close proximity — a bar whose Close is near the MA
    is just as valid a "touch" as one whose Low wicked to the MA.

    Returns the best (closest) proximity found, or None if no bar touched.
    """
    lookback = bars.tail(MA_BOUNCE_LOOKBACK_BARS)
    best_proximity: float | None = None
    for _, row in lookback.iterrows():
        low_prox = abs(row["Low"] - ma_level) / ma_level
        close_prox = abs(row["Close"] - ma_level) / ma_level
        prox = min(low_prox, close_prox)
        if prox <= proximity_pct:
            if best_proximity is None or prox < best_proximity:
                best_proximity = prox
    return best_proximity


def check_ma_bounce_20(
    symbol: str,
    bars: pd.DataFrame,
    ma20: float | None,
    ma50: float | None,
) -> AlertSignal | None:
    """Price pulls back to 20MA and bounces — bullish in uptrend.

    Scans last MA_BOUNCE_LOOKBACK_BARS bars for a touch near 20MA.
    Last bar must close above 20MA (bounce confirmed).

    Conditions:
    - ma20 and ma50 are available
    - Some recent bar low within MA_BOUNCE_PROXIMITY_PCT of 20MA
    - Last bar closes above 20MA
    - Last bar not too far above 20MA (max distance guard)
    - 20MA > 50MA (uptrend confirmation)
    """
    if ma20 is None or ma50 is None:
        return None
    if ma20 <= 0 or ma50 <= 0:
        return None
    if ma20 <= ma50:
        return None  # not in uptrend
    if bars.empty:
        return None

    proximity = _find_ma_bounce_touch(bars, ma20, MA_BOUNCE_PROXIMITY_PCT)
    if proximity is None:
        return None

    last_bar = bars.iloc[-1]
    if last_bar["Close"] <= ma20:
        return None  # didn't bounce above

    # Max-distance guard: don't fire if price already ran too far above MA
    distance = (last_bar["Close"] - ma20) / ma20
    if distance > MA_BOUNCE_MAX_DISTANCE_PCT:
        return None

    entry = round(ma20, 2)
    stop = round(ma20 * (1 - MA_STOP_OFFSET_PCT), 2)
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MA_BOUNCE_20,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high" if proximity <= 0.001 else "medium",
        message=(
            f"MA bounce 20MA — price pulled back to ${ma20:.2f} "
            f"and closed above at ${last_bar['Close']:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# BUY Rule 2: MA Bounce 50MA
# ---------------------------------------------------------------------------

def check_ma_bounce_50(
    symbol: str,
    bars: pd.DataFrame,
    ma20: float | None,
    ma50: float | None,
    prior_close: float | None,
) -> AlertSignal | None:
    """Price pulls back to 50MA and bounces — deeper pullback buy.

    Scans last MA_BOUNCE_LOOKBACK_BARS bars for a touch near 50MA.
    """
    if ma50 is None or ma50 <= 0:
        return None
    if bars.empty:
        return None
    counter_trend = prior_close is not None and prior_close <= ma50

    proximity = _find_ma_bounce_touch(bars, ma50, MA_BOUNCE_PROXIMITY_PCT)
    if proximity is None:
        return None

    last_bar = bars.iloc[-1]
    if last_bar["Close"] <= ma50:
        return None

    distance = (last_bar["Close"] - ma50) / ma50
    if distance > MA_BOUNCE_MAX_DISTANCE_PCT:
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
        f"and closed above at ${last_bar['Close']:.2f}"
    )
    if counter_trend:
        msg += " (counter-trend)"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MA_BOUNCE_50,
        direction="BUY",
        price=last_bar["Close"],
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
    bars: pd.DataFrame,
    ma100: float | None,
    prior_close: float | None,
) -> AlertSignal | None:
    """Price pulls back to 100MA and bounces — intermediate institutional level.

    Scans last MA_BOUNCE_LOOKBACK_BARS bars for a touch near 100MA.
    """
    if ma100 is None or ma100 <= 0:
        return None
    if bars.empty:
        return None

    proximity = _find_ma_bounce_touch(bars, ma100, MA100_BOUNCE_PROXIMITY_PCT)
    if proximity is None:
        return None

    last_bar = bars.iloc[-1]
    if last_bar["Close"] <= ma100:
        return None

    distance = (last_bar["Close"] - ma100) / ma100
    if distance > MA_BOUNCE_MAX_DISTANCE_PCT:
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
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high",
        message=(
            f"MA bounce 100MA — price pulled back to ${ma100:.2f} "
            f"and closed above at ${last_bar['Close']:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# BUY Rule 4: MA Bounce 200MA
# ---------------------------------------------------------------------------

def check_ma_bounce_200(
    symbol: str,
    bars: pd.DataFrame,
    ma200: float | None,
    prior_close: float | None,
) -> AlertSignal | None:
    """Price pulls back to 200MA and bounces — major institutional level.

    Scans last MA_BOUNCE_LOOKBACK_BARS bars for a touch near 200MA.
    """
    if ma200 is None or ma200 <= 0:
        return None
    if bars.empty:
        return None

    proximity = _find_ma_bounce_touch(bars, ma200, MA200_BOUNCE_PROXIMITY_PCT)
    if proximity is None:
        return None

    last_bar = bars.iloc[-1]
    if last_bar["Close"] <= ma200:
        return None

    distance = (last_bar["Close"] - ma200) / ma200
    if distance > MA_BOUNCE_MAX_DISTANCE_PCT:
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
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high",
        message=(
            f"MA bounce 200MA — price pulled back to ${ma200:.2f} "
            f"and closed above at ${last_bar['Close']:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# NOTICE: MA/EMA Approach — heads-up when price nears a key MA/EMA
# ---------------------------------------------------------------------------


def check_ma_approach(
    symbol: str,
    bars: pd.DataFrame,
    ma_level: float | None,
    approach_pct: float,
    bounce_pct: float,
    ma_label: str,
) -> AlertSignal | None:
    """Price is approaching a key MA/EMA but hasn't touched yet.

    Fires a NOTICE when price is within approach_pct but outside bounce_pct.
    This gives a heads-up to watch the chart for an actual touch/bounce.
    """
    if ma_level is None or ma_level <= 0:
        return None
    if bars.empty:
        return None

    last_bar = bars.iloc[-1]
    bar_low = last_bar["Low"]
    bar_close = last_bar["Close"]

    # Must be above the MA (approaching from above)
    if bar_close <= ma_level:
        return None

    # Distance from bar low to MA
    distance = (bar_low - ma_level) / ma_level

    # Must be within approach zone but NOT within touch zone
    if distance > approach_pct:
        return None  # too far
    if distance <= bounce_pct:
        return None  # already touching — let bounce rule handle it

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MA_APPROACH,
        direction="NOTICE",
        price=bar_close,
        entry=round(ma_level, 2),
        stop=None,
        target_1=None,
        target_2=None,
        confidence="info",
        message=(
            f"APPROACHING {ma_label} at ${ma_level:.2f} — "
            f"low ${bar_low:.2f} ({distance:.1%} away). "
            f"Watch for touch and bounce entry."
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
    # NaN guard: yfinance can return NaN for prior day low
    if (bars.empty
            or prior_day_low is None
            or (isinstance(prior_day_low, float) and math.isnan(prior_day_low))
            or prior_day_low <= 0):
        logger.debug(
            "%s: PDL reclaim skip — bars_empty=%s, prior_day_low=%s",
            symbol, bars.empty, prior_day_low,
        )
        return None

    # Check if any bar dipped below prior day low
    min_dip = prior_day_low * (1 - PDL_DIP_MIN_PCT)
    bar_low_min = bars["Low"].min()
    dipped = bar_low_min <= min_dip

    if not dipped:
        logger.debug(
            "%s: PDL reclaim skip — no dip (low=%.2f, threshold=%.2f, pdl=%.2f)",
            symbol, bar_low_min, min_dip, prior_day_low,
        )
        return None

    last_bar = bars.iloc[-1]
    if last_bar["Close"] <= prior_day_low:
        logger.debug(
            "%s: PDL reclaim skip — not reclaimed (close=%.2f <= pdl=%.2f)",
            symbol, last_bar["Close"], prior_day_low,
        )
        return None  # hasn't reclaimed yet

    # Skip if price already ran too far above entry — signal is stale
    distance_pct = (last_bar["Close"] - prior_day_low) / prior_day_low
    if distance_pct > PDL_RECLAIM_MAX_DISTANCE_PCT:
        logger.debug(
            "%s: PDL reclaim skip — stale (dist=%.3f%% > max=%.3f%%)",
            symbol, distance_pct * 100, PDL_RECLAIM_MAX_DISTANCE_PCT * 100,
        )
        return None

    entry = prior_day_low
    intraday_low = bars["Low"].min()
    # Level-based stop: PDL is the thesis — if it breaks, trade is wrong.
    # Data-driven: 0.5% below PDL gives 78% survival for SPY, 3-5x R:R.
    stop = prior_day_low * (1 - PDL_STOP_OFFSET_PCT)
    risk = entry - stop
    if risk <= 0:
        return None

    logger.debug(
        "%s: PDL reclaim FIRED — entry=%.2f stop=%.2f price=%.2f pdl=%.2f",
        symbol, entry, stop, last_bar["Close"], prior_day_low,
    )
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
# BUY Rule 5b: Prior Day Low Bounce (hold above level)
# ---------------------------------------------------------------------------


def check_prior_day_low_bounce(
    symbol: str,
    bars: pd.DataFrame,
    prior_day_low: float,
) -> AlertSignal | None:
    """Price approaches prior day low and bounces/holds above it.

    Unlike prior_day_low_reclaim (which requires a dip below), this fires
    when price gets close to PDL but doesn't break it — a "level hold" signal.

    Conditions:
    - Some bar's low was within PDL_BOUNCE_PROXIMITY_PCT of prior day low
    - No bar broke below prior day low (if it did, PDL reclaim handles it)
    - Last N bars all closed above prior day low (hold confirmed)
    - Price hasn't already run too far above
    """
    if bars.empty or prior_day_low <= 0 or len(bars) < PDL_BOUNCE_HOLD_BARS + 1:
        return None

    # If any bar broke below PDL, this is a reclaim scenario — let PDL reclaim handle it
    if bars["Low"].min() < prior_day_low * (1 - PDL_DIP_MIN_PCT):
        return None

    # Check if any bar's low touched within proximity of PDL
    proximity_level = prior_day_low * (1 + PDL_BOUNCE_PROXIMITY_PCT)
    touched = (bars["Low"] <= proximity_level).any()
    if not touched:
        return None

    # Confirm hold: last N bars all closed above PDL
    recent = bars.iloc[-PDL_BOUNCE_HOLD_BARS:]
    if not (recent["Close"] > prior_day_low).all():
        return None

    last_bar = bars.iloc[-1]

    # Skip if price already ran too far (tighter limit for crypto)
    _is_crypto = symbol.endswith("-USD")
    _max_dist = PDL_BOUNCE_MAX_DISTANCE_CRYPTO_PCT if _is_crypto else PDL_BOUNCE_MAX_DISTANCE_PCT
    distance_pct = (last_bar["Close"] - prior_day_low) / prior_day_low
    if distance_pct > _max_dist:
        return None

    entry = last_bar["Close"]
    stop = prior_day_low * (1 - PDL_STOP_OFFSET_PCT)
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.PRIOR_DAY_LOW_BOUNCE,
        direction="BUY",
        price=last_bar["Close"],
        entry=round(entry, 2),
        stop=round(stop, 2),
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high",
        message=(
            f"Prior day low bounce — held above ${prior_day_low:.2f}, "
            f"low ${bars['Low'].min():.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# SELL Rule: Prior Day Low Breakdown
# ---------------------------------------------------------------------------


def check_prior_day_low_breakdown(
    symbol: str,
    bars: pd.DataFrame,
    prior_day_low: float,
    bar_volume: float,
    avg_volume: float,
) -> AlertSignal | None:
    """Price breaks below prior day low on volume — bearish exit signal.

    Conditions:
    - Last bar closes below prior day low
    - Volume confirmation (>= PDL_BREAKDOWN_VOLUME_RATIO)
    - Price hasn't already fallen too far (staleness guard)
    """
    if bars.empty or prior_day_low is None or prior_day_low <= 0:
        return None
    if isinstance(prior_day_low, float) and math.isnan(prior_day_low):
        return None

    last_bar = bars.iloc[-1]
    if last_bar["Close"] >= prior_day_low:
        return None  # hasn't broken down

    # Volume confirmation
    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0
    if vol_ratio < PDL_BREAKDOWN_VOLUME_RATIO:
        return None

    # Staleness guard — skip if price already far below
    distance_pct = (prior_day_low - last_bar["Close"]) / prior_day_low
    if distance_pct > PDL_BREAKDOWN_MAX_DISTANCE_PCT:
        return None

    confidence = "high" if vol_ratio >= 1.5 else "medium"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.PRIOR_DAY_LOW_BREAKDOWN,
        direction="SELL",
        price=last_bar["Close"],
        entry=round(prior_day_low, 2),
        stop=None,
        target_1=None,
        target_2=None,
        confidence=confidence,
        message=(
            f"Prior day low BREAKDOWN — closed below ${prior_day_low:.2f} "
            f"at ${last_bar['Close']:.2f} (vol {vol_ratio:.1f}x). EXIT LONG."
        ),
    )


# ---------------------------------------------------------------------------
# SELL Rule: Prior Day Low as Resistance (after breakdown)
# ---------------------------------------------------------------------------


def check_prior_day_low_resistance(
    symbol: str,
    bars: pd.DataFrame,
    prior_day_low: float,
) -> AlertSignal | None:
    """After PDL breaks, price rallies back to PDL and gets rejected.

    Conditions:
    - Price is currently below PDL (breakdown already happened)
    - Bar high reached within proximity of PDL (tested it)
    - Bar closes below PDL (rejection confirmed)
    - Must have been below PDL for some bars (not just a wick)
    """
    if bars.empty or prior_day_low is None or prior_day_low <= 0:
        return None
    if isinstance(prior_day_low, float) and math.isnan(prior_day_low):
        return None
    if len(bars) < 6:
        return None

    last_bar = bars.iloc[-1]

    # Must be trading below PDL
    if last_bar["Close"] >= prior_day_low:
        return None

    # Bar high must have reached near PDL (testing it as resistance)
    proximity = (prior_day_low - last_bar["High"]) / prior_day_low
    if proximity > PDL_RESISTANCE_PROXIMITY_PCT:
        return None  # didn't reach PDL

    # Close must be meaningfully below PDL (rejection confirmed)
    rejection = (prior_day_low - last_bar["Close"]) / prior_day_low
    if rejection < PDL_RESISTANCE_REJECTION_PCT:
        return None  # close too near PDL, not a clear rejection

    # Confirm price has been below PDL for multiple bars (not a one-bar wick)
    recent = bars.tail(4)
    bars_below = (recent["Close"] < prior_day_low).sum()
    if bars_below < 2:
        return None  # just crossed below, let breakdown handle it

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.PRIOR_DAY_LOW_RESISTANCE,
        direction="SELL",
        price=last_bar["Close"],
        entry=round(prior_day_low, 2),
        stop=None,
        target_1=None,
        target_2=None,
        confidence="high" if bars_below >= 3 else "medium",
        message=(
            f"Prior day low RESISTANCE — PDL ${prior_day_low:.2f} rejected, "
            f"high ${last_bar['High']:.2f} but closed ${last_bar['Close']:.2f}. "
            f"PDL now overhead resistance."
        ),
    )


# ---------------------------------------------------------------------------
# BUY Rule 3b: Prior Day High Breakout
# ---------------------------------------------------------------------------

def check_prior_day_high_breakout(
    symbol: str,
    bars: pd.DataFrame,
    prior_day_high: float,
    bar_volume: float,
    avg_volume: float,
) -> AlertSignal | None:
    """Price breaks above prior day high with volume confirmation.

    Conditions:
    - Last bar closes above prior_day_high
    - Any bar above PDH in lookback has volume >= PDH_BREAKOUT_VOLUME_RATIO * avg
    - Entry = prior_day_high, Stop = last bar low (capped by _cap_risk)
    - Targets = 1R, 2R
    """
    if bars.empty or prior_day_high <= 0:
        return None

    last_bar = bars.iloc[-1]
    if last_bar["Close"] <= prior_day_high:
        return None

    # Scan lookback bars above PDH for best volume (breakout bar may not be current)
    lookback = bars.tail(MA_BOUNCE_LOOKBACK_BARS)
    above = lookback[lookback["Close"] > prior_day_high]
    if above.empty:
        # Fallback: at least the last bar is above
        best_vol = bar_volume
    else:
        best_vol = above["Volume"].max()

    vol_ratio = best_vol / avg_volume if avg_volume > 0 else 1.0
    if vol_ratio < PDH_BREAKOUT_VOLUME_RATIO:
        return None

    entry = round(prior_day_high, 2)
    stop = round(last_bar["Low"], 2)
    stop = _cap_risk(entry, stop, symbol=symbol)
    risk = entry - stop
    if risk <= 0:
        # Gap-up above breakout level (common for crypto) — use lookback low
        lookback_low = round(bars.tail(MA_BOUNCE_LOOKBACK_BARS)["Low"].min(), 2)
        if lookback_low < entry:
            stop = lookback_low
        else:
            # Even lookback is above PDH — use 0.5% buffer below PDH
            stop = round(entry * 0.995, 2)
        stop = _cap_risk(entry, stop, symbol=symbol)
        risk = entry - stop
        if risk <= 0:
            return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.PRIOR_DAY_HIGH_BREAKOUT,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high" if vol_ratio >= 1.5 else "medium",
        message=(
            f"Prior day high breakout — closed above ${prior_day_high:.2f} "
            f"(vol {vol_ratio:.1f}x avg)"
        ),
    )


# ---------------------------------------------------------------------------
# NOTICE: Prior Day High Test (wick above PDH, no close)
# ---------------------------------------------------------------------------


def check_pdh_test(
    symbol: str,
    bar: pd.Series,
    prior_day_high: float,
    prior_close: float | None = None,
) -> AlertSignal | None:
    """Bar high wicks above prior day high but close stays below — testing resistance.

    This is a heads-up that price is attacking PDH.  If the next bar closes
    above PDH the full PRIOR_DAY_HIGH_BREAKOUT will fire.

    Conditions:
    - Bar high >= prior_day_high (touched or exceeded)
    - Bar close < prior_day_high (not yet broken)
    - Approaching from below: prior close < prior_day_high
    """
    if prior_day_high <= 0:
        return None

    # Must wick above (or touch) PDH
    if bar["High"] < prior_day_high:
        return None

    # Must NOT have closed above — otherwise the breakout rule handles it
    if bar["Close"] >= prior_day_high:
        return None

    # Directional guard: only relevant if approaching from below
    if prior_close is not None and prior_close >= prior_day_high:
        return None

    pct_above = (bar["High"] - prior_day_high) / prior_day_high * 100

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.PDH_TEST,
        direction="NOTICE",
        price=bar["High"],
        entry=round(prior_day_high, 2),
        confidence="medium",
        message=(
            f"TESTING prior day high ${prior_day_high:.2f} — "
            f"wicked {pct_above:.2f}% above, closed ${bar['Close']:.2f} below. "
            f"Watch for close above for breakout entry"
        ),
    )


# ---------------------------------------------------------------------------
# BUY Rule 3c: Prior Day High Retest & Hold
# ---------------------------------------------------------------------------

def check_pdh_retest_hold(
    symbol: str,
    bars: pd.DataFrame,
    prior_day_high: float,
) -> AlertSignal | None:
    """Price broke above prior day high, pulled back to retest PDH, and holds.

    Classic breakout-retest pattern: PDH flips from resistance to support.
    Catches the re-entry if you missed the initial breakout.

    Conditions:
    - At least one prior bar closed above PDH (breakout confirmed)
    - Some recent bar's low touched within PDH_RETEST_PROXIMITY_PCT of PDH
    - Last N bars all closed above PDH (hold confirmed)
    - Price hasn't run too far above PDH
    """
    if bars.empty or prior_day_high <= 0 or len(bars) < PDH_RETEST_HOLD_BARS + 2:
        return None

    # Step 1: confirm breakout happened — at least one bar closed above PDH
    breakout_mask = bars["Close"] > prior_day_high
    if not breakout_mask.any():
        return None

    # Step 2: after breakout, price pulled back near PDH
    # Look for a bar whose low dipped within proximity of PDH
    first_breakout_idx = breakout_mask.idxmax()
    breakout_pos = bars.index.get_loc(first_breakout_idx)
    post_breakout = bars.iloc[breakout_pos:]
    if len(post_breakout) < PDH_RETEST_HOLD_BARS + 1:
        return None

    proximity_level = prior_day_high * (1 + PDH_RETEST_PROXIMITY_PCT)
    touched = (post_breakout["Low"] <= proximity_level).any()
    if not touched:
        return None

    # Step 3: confirm hold — last N bars all closed above PDH
    recent = bars.iloc[-PDH_RETEST_HOLD_BARS:]
    if not (recent["Close"] > prior_day_high).all():
        return None

    last_bar = bars.iloc[-1]

    # Step 4: skip if price already ran too far above PDH
    distance_pct = (last_bar["Close"] - prior_day_high) / prior_day_high
    if distance_pct > PDH_RETEST_MAX_DISTANCE_PCT:
        return None

    entry = round(last_bar["Close"], 2)
    stop = round(prior_day_high * (1 - PDH_RETEST_STOP_OFFSET_PCT), 2)
    stop = _cap_risk(entry, stop, symbol=symbol)
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.PDH_RETEST_HOLD,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high",
        message=(
            f"PDH retest & hold — broke above ${prior_day_high:.2f}, "
            f"pulled back and holding"
        ),
    )


# ---------------------------------------------------------------------------
# BUY Rule 4: Inside Day Breakout
# ---------------------------------------------------------------------------

def check_inside_day_forming(
    symbol: str,
    intraday_bars: pd.DataFrame,
    prior_high: float,
    prior_low: float,
) -> AlertSignal | None:
    """Detect when today's range is forming inside yesterday's range.

    Fires once after the first hour (INSIDE_DAY_FORMING_MIN_BARS) if today's
    session high is below prior day high AND session low is above prior day low.
    This is a NOTICE alert — it tells the trader the day is range-bound and
    only the boundaries (PDL/PDH) are tradeable.
    """
    if prior_high <= 0 or prior_low <= 0:
        return None
    if len(intraday_bars) < INSIDE_DAY_FORMING_MIN_BARS:
        return None

    session_high = intraday_bars["High"].max()
    session_low = intraday_bars["Low"].min()

    if session_high >= prior_high:
        return None
    if session_low <= prior_low:
        return None

    range_used_pct = (session_high - session_low) / (prior_high - prior_low) * 100

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.INSIDE_DAY_FORMING,
        direction="NOTICE",
        price=intraday_bars.iloc[-1]["Close"],
        entry=None,
        confidence="medium",
        message=(
            f"INSIDE DAY FORMING — today's range ${session_low:.2f}-${session_high:.2f} "
            f"within yesterday's ${prior_low:.2f}-${prior_high:.2f} "
            f"({range_used_pct:.0f}% of parent range). "
            f"Trade the boundaries: buy near ${prior_low:.2f}, sell near ${prior_high:.2f}"
        ),
    )


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
# SELL Rule: Inside Day Breakdown (informational)
# ---------------------------------------------------------------------------


def check_inside_day_breakdown(
    symbol: str,
    bar: pd.Series,
    prior_day: dict,
) -> AlertSignal | None:
    """Price breaks below inside day low — warning only (no short entry).

    Conditions:
    - Prior day was classified as inside day
    - Current bar closes below inside day low
    """
    if not prior_day or not prior_day.get("is_inside"):
        return None

    inside_high = prior_day["high"]
    inside_low = prior_day["low"]
    inside_range = inside_high - inside_low

    if inside_range <= 0:
        return None

    if bar["Close"] >= inside_low:
        return None  # hasn't broken down

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.INSIDE_DAY_BREAKDOWN,
        direction="SELL",
        price=bar["Close"],
        confidence="high",
        message=(
            f"Inside day breakdown — broke below ${inside_low:.2f} "
            f"(inside range ${inside_range:.2f})"
        ),
    )


# ---------------------------------------------------------------------------
# BUY Rule: Inside Day Reclaim (failed breakdown trap)
# ---------------------------------------------------------------------------


def check_inside_day_reclaim(
    symbol: str,
    bars: pd.DataFrame,
    prior_day: dict,
) -> AlertSignal | None:
    """Price dips below inside day low then reclaims above it.

    Follows check_prior_day_low_reclaim() pattern:
    - Prior day was inside day
    - Some bar dipped below inside_low by >= INSIDE_DAY_DIP_MIN_PCT
    - Last bar closes back above inside_low
    - Entry = inside_low, Stop = session low − 0.2%, T1 = 1R, T2 = 2R
    """
    if not prior_day or not prior_day.get("is_inside"):
        return None

    inside_low = prior_day["low"]
    inside_high = prior_day["high"]

    if inside_low <= 0 or (inside_high - inside_low) <= 0:
        return None

    if bars.empty:
        return None

    # Check if any bar dipped below inside low
    min_dip = inside_low * (1 - INSIDE_DAY_DIP_MIN_PCT)
    dipped = bars["Low"].min() <= min_dip

    if not dipped:
        return None

    last_bar = bars.iloc[-1]
    if last_bar["Close"] <= inside_low:
        return None  # hasn't reclaimed yet

    entry = inside_low
    intraday_low = bars["Low"].min()
    stop = intraday_low - entry * MA_BOUNCE_SESSION_STOP_PCT
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.INSIDE_DAY_RECLAIM,
        direction="BUY",
        price=last_bar["Close"],
        entry=round(entry, 2),
        stop=round(stop, 2),
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high",
        message=(
            f"Inside day reclaim — dipped to ${intraday_low:.2f}, "
            f"reclaimed above ${inside_low:.2f} (failed breakdown trap)"
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
            direction="NOTICE",
            price=bar["High"],
            message=f"At prior day high ${prior_day_high:.2f} — consider taking profits",
        )

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.RESISTANCE_PRIOR_HIGH,
        direction="NOTICE",
        price=bar["High"],
        confidence="medium",
        message=f"At prior day high ${prior_day_high:.2f} — resistance zone, watch for rejection",
    )


# ---------------------------------------------------------------------------
# SELL Rule 5b: Prior Day High Rejection (confirmed)
# ---------------------------------------------------------------------------


def check_pdh_rejection(
    symbol: str,
    bar: pd.Series,
    prior_day_high: float,
    prior_close: float | None = None,
) -> AlertSignal | None:
    """Price rallies into prior day high and gets rejected — bearish warning.

    Conditions (mirrors check_ema_resistance pattern):
    - Bar high within PDH_REJECTION_PROXIMITY_PCT of prior day high (touched)
    - Bar close is BELOW prior day high (rejection confirmed)
    - Directional guard: prior close below PDH (approaching from below = resistance)
    """
    if prior_day_high <= 0:
        return None

    proximity = abs(bar["High"] - prior_day_high) / prior_day_high
    if proximity > PDH_REJECTION_PROXIMITY_PCT:
        return None

    # Must close below prior day high — confirmed rejection
    if bar["Close"] >= prior_day_high:
        return None

    # Directional guard: if prior close was ABOVE PDH, price is pulling back
    # into it — PDH is acting as support, not resistance.  Skip.
    if prior_close is not None and prior_close > prior_day_high:
        return None

    msg = f"PRIOR DAY HIGH REJECTION — rejected at ${prior_day_high:.2f}, closed ${bar['Close']:.2f}"
    if prior_close is not None and prior_close < prior_day_high:
        msg += " — approaching from below, acting as resistance"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.PDH_REJECTION,
        direction="SELL",
        price=bar["High"],
        message=msg,
    )


# ---------------------------------------------------------------------------
# SHORT Rule: PDH Failed Breakout
# ---------------------------------------------------------------------------


def check_pdh_failed_breakout(
    symbol: str,
    bars: pd.DataFrame,
    prior_day_high: float,
) -> AlertSignal | None:
    """Price broke above PDH earlier in the session, then failed back below.

    A failed breakout above a key level is one of the strongest short signals —
    it traps buyers above resistance and the reversal accelerates as stops trigger.

    Conditions:
    1. At some point in the session, price closed above PDH (breakout occurred)
    2. Current bar closes below PDH (failure confirmed)
    3. At least 3 bars between breakout and failure (not same-bar wick)
    4. Must be past first 30 min (need context)
    """
    if prior_day_high <= 0 or bars.empty or len(bars) < 8:
        return None

    last_bar = bars.iloc[-1]
    last_close = float(last_bar["Close"])

    # Current bar must close below PDH
    if last_close >= prior_day_high:
        return None

    # Find if there was a prior close above PDH (the breakout)
    closes_above = bars[bars["Close"] > prior_day_high]
    if closes_above.empty:
        return None

    # Breakout must have happened at least 3 bars ago (not a same-bar wick)
    last_breakout_idx = closes_above.index[-1]
    bars_since_breakout = len(bars.loc[last_breakout_idx:]) - 1
    if bars_since_breakout < 3:
        return None

    # Must have had at least 2 bars closing above PDH (confirmed breakout, not just a wick)
    if len(closes_above) < 2:
        return None

    breakout_high = bars.loc[last_breakout_idx:, "High"].max()

    entry = round(last_close, 2)
    stop = round(prior_day_high * 1.003, 2)  # stop above PDH
    stop = _cap_risk(stop, entry, symbol=symbol)
    risk = stop - entry
    if risk <= 0:
        return None

    target_1 = round(entry - risk, 2)
    target_2 = round(entry - 2 * risk, 2)

    confidence = "high" if bars_since_breakout >= 6 else "medium"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.PDH_FAILED_BREAKOUT,
        direction="SHORT",
        price=last_close,
        entry=entry,
        stop=stop,
        target_1=target_1,
        target_2=target_2,
        confidence=confidence,
        message=(
            f"PDH FAILED BREAKOUT — broke above ${prior_day_high:.2f}, "
            f"rallied to ${breakout_high:.2f}, now failed back below at "
            f"${last_close:.2f}. Trapped longs above resistance."
        ),
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
            f"T1 hit at ${target_1:.2f} (entry ${entry_price:.2f}) "
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
        message=f"Target 2 hit at ${target_2:.2f} (entry ${entry_price:.2f})",
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
# BUY Rule: Weekly High Breakout
# ---------------------------------------------------------------------------


def check_weekly_high_breakout(
    symbol: str,
    bars: pd.DataFrame,
    prior_day: dict,
    bar_volume: float,
    avg_volume: float,
) -> AlertSignal | None:
    """Price breaks above prior week high with volume — bullish breakout."""
    pw_high = prior_day.get("prior_week_high")
    pw_low = prior_day.get("prior_week_low")
    if not pw_high or pw_high <= 0:
        return None

    if bars.empty:
        return None
    last_bar = bars.iloc[-1]
    if last_bar["Close"] <= pw_high:
        return None

    # Scan lookback bars above weekly high for best volume
    lookback = bars.tail(MA_BOUNCE_LOOKBACK_BARS)
    above = lookback[lookback["Close"] > pw_high]
    if above.empty:
        best_vol = bar_volume
    else:
        best_vol = above["Volume"].max()

    vol_ratio = best_vol / avg_volume if avg_volume > 0 else 1.0
    if vol_ratio < PDH_BREAKOUT_VOLUME_RATIO:
        return None

    entry = round(pw_high, 2)
    stop = round(last_bar["Low"], 2)
    stop = _cap_risk(entry, stop, symbol=symbol)
    risk = entry - stop
    if risk <= 0:
        # Gap-up above breakout level (common for crypto) — use lookback low
        lookback_low = round(bars.tail(MA_BOUNCE_LOOKBACK_BARS)["Low"].min(), 2)
        if lookback_low < entry:
            stop = lookback_low
        else:
            stop = round(entry * 0.995, 2)
        stop = _cap_risk(entry, stop, symbol=symbol)
        risk = entry - stop
        if risk <= 0:
            return None

    weekly_range = pw_high - pw_low if pw_low and pw_low > 0 else risk * 2

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.WEEKLY_HIGH_BREAKOUT,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + weekly_range, 2),
        confidence="high" if vol_ratio >= 1.5 else "medium",
        message=f"Weekly high breakout — closed above ${pw_high:.2f} (vol {vol_ratio:.1f}x avg)",
    )


# ---------------------------------------------------------------------------
# NOTICE: Weekly High Test (wick above prior week high, no close)
# ---------------------------------------------------------------------------


def check_weekly_high_test(
    symbol: str,
    bar: pd.Series,
    prior_day: dict,
    prior_close: float | None = None,
) -> AlertSignal | None:
    """Bar high wicks above prior week high but close stays below — testing key resistance.

    Heads-up that price is attacking the weekly level.  If the next bar
    closes above, WEEKLY_HIGH_BREAKOUT fires.

    Conditions:
    - Bar high >= prior_week_high (touched or exceeded)
    - Bar close < prior_week_high (not yet broken)
    - Approaching from below: prior close < prior_week_high
    """
    pw_high = prior_day.get("prior_week_high")
    if not pw_high or pw_high <= 0:
        return None

    # Must wick above (or touch) weekly high
    if bar["High"] < pw_high:
        return None

    # Must NOT have closed above — breakout rule handles that
    if bar["Close"] >= pw_high:
        return None

    # Directional guard: only if approaching from below
    if prior_close is not None and prior_close >= pw_high:
        return None

    pct_above = (bar["High"] - pw_high) / pw_high * 100

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.WEEKLY_HIGH_TEST,
        direction="NOTICE",
        price=bar["High"],
        entry=round(pw_high, 2),
        confidence="medium",
        message=(
            f"TESTING prior week high ${pw_high:.2f} — "
            f"wicked {pct_above:.2f}% above, closed ${bar['Close']:.2f} below. "
            f"Watch for close above for weekly breakout"
        ),
    )


# ---------------------------------------------------------------------------
# SELL Rule: Weekly High Resistance
# ---------------------------------------------------------------------------


def check_weekly_high_resistance(
    symbol: str,
    bar: pd.Series,
    prior_day: dict,
) -> AlertSignal | None:
    """Price approaches prior week high from below — resistance warning."""
    pw_high = prior_day.get("prior_week_high")
    if not pw_high or pw_high <= 0:
        return None
    if bar["Close"] >= pw_high:
        return None  # above = breakout, not resistance

    proximity = abs(bar["High"] - pw_high) / pw_high
    if proximity > WEEKLY_LEVEL_PROXIMITY_PCT:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.WEEKLY_HIGH_RESISTANCE,
        direction="SELL",
        price=bar["High"],
        message=f"Weekly high resistance — rejected near ${pw_high:.2f}, closed ${bar['Close']:.2f}",
    )


# ---------------------------------------------------------------------------
# NOTICE: Weekly Low Test (wick below prior week low, close stays above)
# ---------------------------------------------------------------------------


def check_weekly_low_test(
    symbol: str,
    bar: pd.Series,
    prior_day: dict,
    prior_close: float | None = None,
) -> AlertSignal | None:
    """Bar low wicks below prior week low but close stays above — testing support.

    Heads-up that price is probing the weekly support level. If it holds,
    weekly_level_touch fires for the bounce entry. If it breaks,
    weekly_low_breakdown fires.

    Conditions:
    - Bar low <= prior_week_low (touched or pierced)
    - Bar close > prior_week_low (not broken)
    - Approaching from above: prior close > prior_week_low
    """
    pw_low = prior_day.get("prior_week_low")
    if not pw_low or pw_low <= 0:
        return None

    # Must wick below (or touch) weekly low
    if bar["Low"] > pw_low:
        return None

    # Must NOT have closed below — breakdown rule handles that
    if bar["Close"] <= pw_low:
        return None

    # Directional guard: only if approaching from above
    if prior_close is not None and prior_close <= pw_low:
        return None

    pct_below = (pw_low - bar["Low"]) / pw_low * 100

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.WEEKLY_LOW_TEST,
        direction="NOTICE",
        price=bar["Low"],
        entry=round(pw_low, 2),
        confidence="medium",
        message=(
            f"TESTING prior week low ${pw_low:.2f} — "
            f"wicked {pct_below:.2f}% below, closed ${bar['Close']:.2f} above. "
            f"Watch for hold (bounce entry) or close below (breakdown)"
        ),
    )


# ---------------------------------------------------------------------------
# SELL Rule: Weekly Low Breakdown (close below prior week low)
# ---------------------------------------------------------------------------


def check_weekly_low_breakdown(
    symbol: str,
    bar: pd.Series,
    prior_day: dict,
    bar_volume: float,
    avg_volume: float,
    prior_close: float | None = None,
) -> AlertSignal | None:
    """Price closes below prior week low — weekly support lost.

    Conditions:
    - Bar close < prior_week_low
    - Approaching from above: prior close > prior_week_low (not already below)
    """
    pw_low = prior_day.get("prior_week_low")
    pw_high = prior_day.get("prior_week_high")
    if not pw_low or pw_low <= 0:
        return None

    if bar["Close"] >= pw_low:
        return None

    # Only fire when breaking down from above
    if prior_close is not None and prior_close <= pw_low:
        return None

    pct_below = (pw_low - bar["Close"]) / pw_low * 100
    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0

    weekly_range = pw_high - pw_low if pw_high and pw_high > pw_low else 0
    range_info = f", weekly range was ${weekly_range:.2f}" if weekly_range > 0 else ""

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.WEEKLY_LOW_BREAKDOWN,
        direction="SELL",
        price=bar["Close"],
        entry=round(pw_low, 2),
        confidence="high" if vol_ratio >= 1.5 else "medium",
        message=(
            f"WEEKLY LOW BREAKDOWN — closed {pct_below:.2f}% below ${pw_low:.2f} "
            f"(vol {vol_ratio:.1f}x avg{range_info}). "
            f"Weekly support lost — watch for continuation lower"
        ),
    )


# ---------------------------------------------------------------------------
# BUY Rule: Monthly Level Touch (bounce at prior month low)
# ---------------------------------------------------------------------------


def check_monthly_level_touch(
    symbol: str,
    bars: pd.DataFrame,
    prior_day: dict,
) -> AlertSignal | None:
    """Price touches prior month low and bounces — bullish entry at major structural level.

    Mirrors check_weekly_level_touch() but uses monthly levels and wider proximity.
    """
    pm_high = prior_day.get("prior_month_high")
    pm_low = prior_day.get("prior_month_low")
    if pm_high is None or pm_low is None:
        return None
    if pm_high <= 0 or pm_low <= 0:
        return None
    if bars.empty:
        return None

    monthly_range = pm_high - pm_low
    if monthly_range <= 0:
        return None

    # Scan lookback window for a touch near prior month low
    lookback = bars.tail(MA_BOUNCE_LOOKBACK_BARS)
    touched = False
    for _, row in lookback.iterrows():
        prox = abs(row["Low"] - pm_low) / pm_low
        if prox <= MONTHLY_LEVEL_PROXIMITY_PCT:
            touched = True
            break

    if not touched:
        return None

    last_bar = bars.iloc[-1]
    if last_bar["Close"] <= pm_low:
        return None  # no bounce

    entry = pm_low
    stop = pm_low * (1 - MONTHLY_LEVEL_STOP_OFFSET_PCT)
    stop = _cap_risk(entry, stop, symbol=symbol)
    risk = entry - stop
    if risk <= 0:
        return None

    target_1 = pm_high
    target_2 = pm_high + monthly_range * 0.5

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MONTHLY_LEVEL_TOUCH,
        direction="BUY",
        price=last_bar["Close"],
        entry=round(entry, 2),
        stop=round(stop, 2),
        target_1=round(target_1, 2),
        target_2=round(target_2, 2),
        confidence="high",
        message=(
            f"Monthly level touch — price at prior month low ${pm_low:.2f}, "
            f"T1=${pm_high:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# BUY Rule: Monthly High Breakout (close above prior month high with volume)
# ---------------------------------------------------------------------------


def check_monthly_high_breakout(
    symbol: str,
    bars: pd.DataFrame,
    prior_day: dict,
    bar_volume: float,
    avg_volume: float,
) -> AlertSignal | None:
    """Price breaks above prior month high with volume — bullish breakout."""
    pm_high = prior_day.get("prior_month_high")
    pm_low = prior_day.get("prior_month_low")
    if not pm_high or pm_high <= 0:
        return None

    if bars.empty:
        return None
    last_bar = bars.iloc[-1]
    if last_bar["Close"] <= pm_high:
        return None

    # Scan lookback bars above monthly high for best volume
    lookback = bars.tail(MA_BOUNCE_LOOKBACK_BARS)
    above = lookback[lookback["Close"] > pm_high]
    if above.empty:
        best_vol = bar_volume
    else:
        best_vol = above["Volume"].max()

    vol_ratio = best_vol / avg_volume if avg_volume > 0 else 1.0
    if vol_ratio < PDH_BREAKOUT_VOLUME_RATIO:
        return None

    entry = round(pm_high, 2)
    stop = round(last_bar["Low"], 2)
    stop = _cap_risk(entry, stop, symbol=symbol)
    risk = entry - stop
    if risk <= 0:
        return None

    monthly_range = pm_high - pm_low if pm_low and pm_low > 0 else risk * 2

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MONTHLY_HIGH_BREAKOUT,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + monthly_range, 2),
        confidence="high" if vol_ratio >= 1.5 else "medium",
        message=f"Monthly high breakout — closed above ${pm_high:.2f} (vol {vol_ratio:.1f}x avg)",
    )


# ---------------------------------------------------------------------------
# NOTICE: Monthly High Test (wick above prior month high, no close)
# ---------------------------------------------------------------------------


def check_monthly_high_test(
    symbol: str,
    bar: pd.Series,
    prior_day: dict,
    prior_close: float | None = None,
) -> AlertSignal | None:
    """Bar high wicks above prior month high but close stays below — testing key resistance."""
    pm_high = prior_day.get("prior_month_high")
    if not pm_high or pm_high <= 0:
        return None

    if bar["High"] < pm_high:
        return None

    if bar["Close"] >= pm_high:
        return None

    if prior_close is not None and prior_close >= pm_high:
        return None

    pct_above = (bar["High"] - pm_high) / pm_high * 100

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MONTHLY_HIGH_TEST,
        direction="NOTICE",
        price=bar["High"],
        entry=round(pm_high, 2),
        confidence="medium",
        message=(
            f"TESTING prior month high ${pm_high:.2f} — "
            f"wicked {pct_above:.2f}% above, closed ${bar['Close']:.2f} below. "
            f"Watch for close above for monthly breakout"
        ),
    )


# ---------------------------------------------------------------------------
# SELL Rule: Monthly High Resistance
# ---------------------------------------------------------------------------


def check_monthly_high_resistance(
    symbol: str,
    bar: pd.Series,
    prior_day: dict,
) -> AlertSignal | None:
    """Price approaches prior month high from below — resistance warning."""
    pm_high = prior_day.get("prior_month_high")
    if not pm_high or pm_high <= 0:
        return None
    if bar["Close"] >= pm_high:
        return None  # above = breakout, not resistance

    proximity = abs(bar["High"] - pm_high) / pm_high
    if proximity > MONTHLY_LEVEL_PROXIMITY_PCT:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MONTHLY_HIGH_RESISTANCE,
        direction="SELL",
        price=bar["High"],
        message=f"Monthly high resistance — rejected near ${pm_high:.2f}, closed ${bar['Close']:.2f}",
    )


# ---------------------------------------------------------------------------
# NOTICE: Monthly Low Test (wick below prior month low, close stays above)
# ---------------------------------------------------------------------------


def check_monthly_low_test(
    symbol: str,
    bar: pd.Series,
    prior_day: dict,
    prior_close: float | None = None,
) -> AlertSignal | None:
    """Bar low wicks below prior month low but close stays above — testing support."""
    pm_low = prior_day.get("prior_month_low")
    if not pm_low or pm_low <= 0:
        return None

    if bar["Low"] > pm_low:
        return None

    if bar["Close"] <= pm_low:
        return None

    if prior_close is not None and prior_close <= pm_low:
        return None

    pct_below = (pm_low - bar["Low"]) / pm_low * 100

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MONTHLY_LOW_TEST,
        direction="NOTICE",
        price=bar["Low"],
        entry=round(pm_low, 2),
        confidence="medium",
        message=(
            f"TESTING prior month low ${pm_low:.2f} — "
            f"wicked {pct_below:.2f}% below, closed ${bar['Close']:.2f} above. "
            f"Watch for hold (bounce entry) or close below (breakdown)"
        ),
    )


# ---------------------------------------------------------------------------
# SELL Rule: Monthly Low Breakdown (close below prior month low)
# ---------------------------------------------------------------------------


def check_monthly_low_breakdown(
    symbol: str,
    bar: pd.Series,
    prior_day: dict,
    bar_volume: float,
    avg_volume: float,
    prior_close: float | None = None,
) -> AlertSignal | None:
    """Price closes below prior month low — monthly support lost."""
    pm_low = prior_day.get("prior_month_low")
    pm_high = prior_day.get("prior_month_high")
    if not pm_low or pm_low <= 0:
        return None

    if bar["Close"] >= pm_low:
        return None

    if prior_close is not None and prior_close <= pm_low:
        return None

    pct_below = (pm_low - bar["Close"]) / pm_low * 100
    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0

    monthly_range = pm_high - pm_low if pm_high and pm_high > pm_low else 0
    range_info = f", monthly range was ${monthly_range:.2f}" if monthly_range > 0 else ""

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MONTHLY_LOW_BREAKDOWN,
        direction="SELL",
        price=bar["Close"],
        entry=round(pm_low, 2),
        confidence="high" if vol_ratio >= 1.5 else "medium",
        message=(
            f"MONTHLY LOW BREAKDOWN — closed {pct_below:.2f}% below ${pm_low:.2f} "
            f"(vol {vol_ratio:.1f}x avg{range_info}). "
            f"Monthly support lost — watch for continuation lower"
        ),
    )


# ---------------------------------------------------------------------------
# BUY Rule: EMA Bounce 20
# ---------------------------------------------------------------------------


def check_ema_bounce_20(
    symbol: str,
    bars: pd.DataFrame,
    ema20: float | None,
    ema50: float | None,
) -> AlertSignal | None:
    """Price pulls back to EMA20 and bounces — bullish in uptrend.

    Scans last MA_BOUNCE_LOOKBACK_BARS bars for a touch near EMA20.
    """
    if ema20 is None or ema50 is None:
        return None
    if ema20 <= 0 or ema50 <= 0:
        return None
    if ema20 <= ema50:
        return None  # not in uptrend
    if bars.empty:
        return None

    proximity = _find_ma_bounce_touch(bars, ema20, MA_BOUNCE_PROXIMITY_PCT)
    if proximity is None:
        return None

    last_bar = bars.iloc[-1]
    if last_bar["Close"] <= ema20:
        return None  # didn't bounce above

    distance = (last_bar["Close"] - ema20) / ema20
    if distance > MA_BOUNCE_MAX_DISTANCE_PCT:
        return None

    entry = round(ema20, 2)
    stop = round(ema20 * (1 - MA_STOP_OFFSET_PCT), 2)
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.EMA_BOUNCE_20,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high" if proximity <= 0.001 else "medium",
        message=(
            f"EMA bounce 20 — price pulled back to ${ema20:.2f} "
            f"and closed above at ${last_bar['Close']:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# BUY Rule: EMA Bounce 50
# ---------------------------------------------------------------------------


def check_ema_bounce_50(
    symbol: str,
    bars: pd.DataFrame,
    ema50: float | None,
    ema20: float | None,
    prior_close: float | None,
) -> AlertSignal | None:
    """Price pulls back to EMA50 and bounces — deeper pullback buy.

    Scans last MA_BOUNCE_LOOKBACK_BARS bars for a touch near EMA50.
    """
    if ema50 is None or ema50 <= 0:
        return None
    if bars.empty:
        return None
    counter_trend = prior_close is not None and prior_close <= ema50

    proximity = _find_ma_bounce_touch(bars, ema50, MA_BOUNCE_PROXIMITY_PCT)
    if proximity is None:
        return None

    last_bar = bars.iloc[-1]
    if last_bar["Close"] <= ema50:
        return None

    distance = (last_bar["Close"] - ema50) / ema50
    if distance > MA_BOUNCE_MAX_DISTANCE_PCT:
        return None

    entry = round(ema50, 2)
    stop = round(ema50 * (1 - MA_STOP_OFFSET_PCT), 2)
    risk = entry - stop
    if risk <= 0:
        return None

    if counter_trend:
        confidence = "medium"
    else:
        confidence = "high" if proximity <= 0.001 else "medium"

    msg = (
        f"EMA bounce 50 — price pulled back to ${ema50:.2f} "
        f"and closed above at ${last_bar['Close']:.2f}"
    )
    if counter_trend:
        msg += " (counter-trend)"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.EMA_BOUNCE_50,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence=confidence,
        message=msg,
    )


# ---------------------------------------------------------------------------
# BUY Rule: EMA Bounce 100
# ---------------------------------------------------------------------------


def check_ema_bounce_100(
    symbol: str,
    bars: pd.DataFrame,
    ema100: float | None,
    prior_close: float | None,
) -> AlertSignal | None:
    """Price pulls back to EMA100 and bounces — intermediate institutional level.

    Scans last MA_BOUNCE_LOOKBACK_BARS bars for a touch near EMA100.
    Uses MA100 thresholds (wider proximity/stop for institutional level).
    """
    if ema100 is None or ema100 <= 0:
        return None
    if bars.empty:
        return None

    proximity = _find_ma_bounce_touch(bars, ema100, MA100_BOUNCE_PROXIMITY_PCT)
    if proximity is None:
        return None

    last_bar = bars.iloc[-1]
    if last_bar["Close"] <= ema100:
        return None  # didn't bounce above

    distance = (last_bar["Close"] - ema100) / ema100
    if distance > MA_BOUNCE_MAX_DISTANCE_PCT:
        return None

    counter_trend = prior_close is not None and prior_close <= ema100

    entry = round(ema100, 2)
    stop = round(ema100 * (1 - MA100_STOP_OFFSET_PCT), 2)
    risk = entry - stop
    if risk <= 0:
        return None

    if counter_trend:
        confidence = "medium"
    else:
        confidence = "high" if proximity <= 0.002 else "medium"

    msg = (
        f"EMA bounce 100 — price pulled back to ${ema100:.2f} "
        f"and closed above at ${last_bar['Close']:.2f}"
    )
    if counter_trend:
        msg += " (counter-trend)"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.EMA_BOUNCE_100,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence=confidence,
        message=msg,
    )


# ---------------------------------------------------------------------------
# BUY Rule: EMA Bounce 200
# ---------------------------------------------------------------------------


def check_ema_bounce_200(
    symbol: str,
    bars: pd.DataFrame,
    ema200: float | None,
    prior_close: float | None,
) -> AlertSignal | None:
    """Price pulls back to EMA200 and bounces — major institutional level.

    Scans last MA_BOUNCE_LOOKBACK_BARS bars for a touch near EMA200.
    Uses MA200 thresholds (widest proximity/stop for long-term level).
    """
    if ema200 is None or ema200 <= 0:
        return None
    if bars.empty:
        return None

    proximity = _find_ma_bounce_touch(bars, ema200, MA200_BOUNCE_PROXIMITY_PCT)
    if proximity is None:
        return None

    last_bar = bars.iloc[-1]
    if last_bar["Close"] <= ema200:
        return None  # didn't bounce above

    distance = (last_bar["Close"] - ema200) / ema200
    if distance > MA_BOUNCE_MAX_DISTANCE_PCT:
        return None

    counter_trend = prior_close is not None and prior_close <= ema200

    entry = round(ema200, 2)
    stop = round(ema200 * (1 - MA200_STOP_OFFSET_PCT), 2)
    risk = entry - stop
    if risk <= 0:
        return None

    if counter_trend:
        confidence = "medium"
    else:
        confidence = "high" if proximity <= 0.004 else "medium"

    msg = (
        f"EMA bounce 200 — price pulled back to ${ema200:.2f} "
        f"and closed above at ${last_bar['Close']:.2f}"
    )
    if counter_trend:
        msg += " (counter-trend)"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.EMA_BOUNCE_200,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence=confidence,
        message=msg,
    )


# ---------------------------------------------------------------------------
# SELL Rule: EMA Resistance
# ---------------------------------------------------------------------------


def check_ema_resistance(
    symbol: str,
    bar: pd.Series,
    ema20: float | None,
    ema50: float | None,
    prior_close: float | None = None,
    ema100: float | None = None,
    ema200: float | None = None,
) -> AlertSignal | None:
    """Price rallies into overhead EMA and gets rejected — bearish warning."""
    for ema_val, label in [(ema20, "20"), (ema50, "50"), (ema100, "100"), (ema200, "200")]:
        if ema_val is None or ema_val <= 0 or ema_val <= bar["Close"]:
            continue
        proximity = abs(bar["High"] - ema_val) / ema_val
        if proximity > MA_BOUNCE_PROXIMITY_PCT:
            continue
        if bar["Close"] >= ema_val:
            continue
        # Direction check: if prior close was ABOVE this EMA, price is falling
        # into it — the EMA is acting as SUPPORT, not resistance.  Skip.
        # (Mirrors check_ma_resistance directional guard.)
        if prior_close is not None and prior_close > ema_val:
            continue
        msg = f"EMA{label} RESISTANCE — rejected at ${ema_val:.2f}, closed ${bar['Close']:.2f}"
        if prior_close is not None and prior_close < ema_val:
            msg += " — recently broken, acting as resistance"
        return AlertSignal(
            symbol=symbol,
            alert_type=AlertType.EMA_RESISTANCE,
            direction="SELL",
            price=bar["High"],
            message=msg,
        )
    return None


# ---------------------------------------------------------------------------
# Rule 10: EMA Crossover 5/20 (BUY)
# ---------------------------------------------------------------------------


def check_ema_crossover_5_20(
    symbol: str,
    bars: pd.DataFrame,
) -> AlertSignal | None:
    """Daily 5-bar EMA crosses above 20-bar EMA — bullish entry.

    Uses **daily** bars for the crossover detection (not intraday).
    Entry/stop are derived from intraday bars for trade management.

    Conditions:
    - Previous daily bar: EMA5 <= EMA20; current daily bar: EMA5 > EMA20
    - Scans last 3 days for the crossover (wider detection window)
    - Minimum separation: EMA5 must exceed EMA20 by >= 0.05% (anti-flicker)
    - Confirmation: crossover daily bar must close green (Close > Open)
    """
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

    # Look back up to 3 days for a recent crossover
    found_crossover = False
    crossover_idx = None
    for i in range(1, min(4, len(ema5))):
        prev_idx = -(i + 1)
        curr_idx = -i
        if abs(prev_idx) > len(ema5) or abs(curr_idx) > len(ema5):
            break
        prev_cross = ema5.iloc[prev_idx] <= ema20.iloc[prev_idx]
        curr_cross = ema5.iloc[curr_idx] > ema20.iloc[curr_idx]
        if prev_cross and curr_cross:
            # Verify separation on the crossover day
            ema5_val = ema5.iloc[curr_idx]
            ema20_val = ema20.iloc[curr_idx]
            separation_pct = (ema5_val - ema20_val) / ema20_val if ema20_val > 0 else 0
            if separation_pct >= 0.0005:
                found_crossover = True
                crossover_idx = curr_idx
                break

    if not found_crossover:
        return None

    # Use latest EMA values for the message
    ema5_val = ema5.iloc[-1]
    ema20_val = ema20.iloc[-1]

    # EMA5 must still be above EMA20 today (crossover still valid)
    if ema5_val <= ema20_val:
        return None

    last_daily = daily.iloc[crossover_idx]

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
    bars: pd.DataFrame,
    intraday_supports: list[dict],
    bar_volume: float,
    avg_volume: float,
) -> AlertSignal | None:
    """Price bounces off a held intraday support level — bullish entry.

    Scans the last SUPPORT_BOUNCE_LOOKBACK_BARS bars (default 6 = 30 min) for
    a support touch rather than only checking the last bar.  This catches
    bounces that started 2-3 bars ago and are already 1% above support by
    the time the current bar closes.

    Guard: if price has already run more than SUPPORT_BOUNCE_MAX_DISTANCE_PCT
    above the support, the signal is stale and we skip it.

    Accepts ``bars`` as a DataFrame (last N 5-min bars) and
    ``intraday_supports`` as list[dict] with keys: level, touch_count,
    hold_hours, strength.
    """
    if bars.empty or not intraday_supports:
        return None

    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0
    if vol_ratio < LOW_VOLUME_SKIP_RATIO:
        return None

    lookback = bars.tail(SUPPORT_BOUNCE_LOOKBACK_BARS)
    last_bar = bars.iloc[-1]

    # Scan lookback window for the best support touch.
    # Fix: directional check — bar low must actually REACH the support level
    # (at or slightly above/below), not just be "near" it from far above.
    best = None
    touch_bar_low = None
    for sup in sorted(intraday_supports, key=lambda s: s["level"], reverse=True):
        lvl = sup["level"]
        # Fix 2: require minimum touch count — "tested 1x" is noise
        if sup.get("touch_count", 1) < SUPPORT_BOUNCE_MIN_TOUCHES:
            continue
        for _, row in lookback.iterrows():
            # Directional: low must be at or below level * (1 + proximity)
            # This prevents counting bars whose low is far above support
            if lvl > 0 and row["Low"] <= lvl * (1 + SUPPORT_BOUNCE_PROXIMITY_PCT):
                best = sup
                touch_bar_low = row["Low"]
                break
        if best is not None:
            break

    if best is None:
        return None

    best_support = best["level"]
    touch_count = best.get("touch_count", 1)
    strength = best.get("strength", "weak")

    # Last bar must close above support (bounce confirmed)
    if last_bar["Close"] <= best_support:
        return None

    # Max-distance guard: don't fire if price already ran too far above support
    distance = (last_bar["Close"] - best_support) / best_support if best_support > 0 else 0
    if distance > SUPPORT_BOUNCE_MAX_DISTANCE_PCT:
        return None

    # Fix 3: consolidation filter — if many bars closed below the level,
    # it's a chop zone (price oscillating through it), not real support.
    recent_bars = bars.tail(max(SUPPORT_BOUNCE_LOOKBACK_BARS * 3, 18))
    if len(recent_bars) > 0 and best_support > 0:
        closes_below = (recent_bars["Close"] < best_support).sum()
        if closes_below / len(recent_bars) > SUPPORT_BOUNCE_MAX_CLOSE_BELOW_PCT:
            return None

    entry = best_support
    stop = touch_bar_low if touch_bar_low < best_support else best_support * (1 - 0.005)
    risk = entry - stop
    if risk <= 0:
        return None

    confidence = "high" if strength == "strong" else "medium"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.INTRADAY_SUPPORT_BOUNCE,
        direction="BUY",
        price=last_bar["Close"],
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
# Rule: VWAP Reclaim (Morning Reversal BUY)
# ---------------------------------------------------------------------------


def check_vwap_reclaim(
    symbol: str,
    bars: pd.DataFrame,
    vwap_series: pd.Series,
    bar_volume: float,
    avg_volume: float,
) -> AlertSignal | None:
    """Price reclaims VWAP from below — bullish reversal signal.

    Pattern: price was trading below VWAP, last bar closes above it.

    Conditions:
    1. At least VWAP_RECLAIM_MIN_BARS_AFTER_LOW bars of data
    2. Some recent bar traded below VWAP (confirming price was under)
    3. Last bar closes above VWAP (reclaim confirmed)
    4. Recovery from session low >= VWAP_RECLAIM_MIN_RECOVERY_PCT
    """
    if bars.empty or vwap_series.empty:
        return None
    if len(bars) < VWAP_RECLAIM_MIN_BARS_AFTER_LOW + 1:
        return None

    last_bar = bars.iloc[-1]
    current_vwap = vwap_series.iloc[-1]
    if current_vwap <= 0:
        return None

    # Last bar must close above VWAP
    if last_bar["Close"] <= current_vwap:
        return None

    # Price must be close to VWAP — skip if already ran past
    distance_pct = (last_bar["Close"] - current_vwap) / current_vwap
    if distance_pct > VWAP_RECLAIM_MAX_DISTANCE_PCT:
        return None

    # Confirm price was recently below VWAP (lookback last 12 bars = 60 min)
    lookback = min(12, len(bars) - 1)
    recent = bars.iloc[-(lookback + 1):-1]  # exclude last bar
    recent_vwap = vwap_series.iloc[-(lookback + 1):-1]
    if recent.empty:
        return None
    was_below = (recent["Close"] < recent_vwap).any()
    if not was_below:
        return None  # wasn't below VWAP recently — not a reclaim

    session_low = bars["Low"].min()

    # Recovery must be meaningful
    recovery_pct = (last_bar["Close"] - session_low) / session_low if session_low > 0 else 0
    if recovery_pct < VWAP_RECLAIM_MIN_RECOVERY_PCT:
        return None

    entry = round(current_vwap, 2)
    stop = round(session_low * (1 - VWAP_RECLAIM_STOP_OFFSET_PCT), 2)
    risk = entry - stop
    if risk <= 0:
        return None

    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 0.0
    confidence = "high" if vol_ratio >= 1.2 else "medium"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.VWAP_RECLAIM,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence=confidence,
        message=(
            f"VWAP reclaim — morning low ${session_low:.2f}, "
            f"recovered {recovery_pct:.1%} through VWAP ${current_vwap:.2f} "
            f"(vol {vol_ratio:.1f}x)"
        ),
    )


# ---------------------------------------------------------------------------
# Rule: VWAP Bounce (BUY) — pullback to VWAP that holds
# ---------------------------------------------------------------------------


def check_vwap_bounce(
    symbol: str,
    bars: pd.DataFrame,
    vwap_series: pd.Series,
    bar_volume: float,
    avg_volume: float,
) -> AlertSignal | None:
    """Price trending above VWAP pulls back to test it and holds — continuation.

    Conditions:
    1. Enough bars for context (VWAP_BOUNCE_MIN_BARS)
    2. Majority of recent bars closed above VWAP (uptrend)
    3. Current bar's Low dips near VWAP (touch/test)
    4. Current bar closes above VWAP (the hold)
    5. Close not too far above VWAP (proximity guard)
    """
    if bars.empty or vwap_series.empty:
        return None
    if len(bars) < VWAP_BOUNCE_MIN_BARS:
        return None

    last_bar = bars.iloc[-1]
    current_vwap = vwap_series.iloc[-1]
    if current_vwap <= 0:
        return None

    # Last bar must close above VWAP
    if last_bar["Close"] <= current_vwap:
        return None

    # Close can't be too far above VWAP — must be near the bounce
    distance_pct = (last_bar["Close"] - current_vwap) / current_vwap
    if distance_pct > VWAP_BOUNCE_MAX_DISTANCE_PCT:
        return None

    # Bar's low must have touched/dipped near VWAP
    low_distance = (last_bar["Low"] - current_vwap) / current_vwap
    if abs(low_distance) > VWAP_BOUNCE_TOUCH_PCT:
        return None

    # Uptrend context: majority of lookback bars closed above VWAP
    lookback = min(10, len(bars) - 1)
    recent = bars.iloc[-(lookback + 1):-1]
    recent_vwap = vwap_series.iloc[-(lookback + 1):-1]
    above_count = (recent["Close"] > recent_vwap).sum()
    if above_count / len(recent) < VWAP_BOUNCE_ABOVE_PCT:
        return None

    entry = round(current_vwap, 2)
    stop = round(current_vwap * (1 - VWAP_BOUNCE_STOP_OFFSET_PCT), 2)
    risk = entry - stop
    if risk <= 0:
        return None

    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 0.0
    confidence = "high" if vol_ratio >= 1.2 else "medium"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.VWAP_BOUNCE,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence=confidence,
        message=(
            f"VWAP bounce — retraced to VWAP ${current_vwap:.2f} and held, "
            f"close ${last_bar['Close']:.2f} "
            f"(vol {vol_ratio:.1f}x)"
        ),
    )


# ---------------------------------------------------------------------------
# Rule 16: Opening Low Base (BUY)
# ---------------------------------------------------------------------------


def check_opening_low_base(
    symbol: str,
    bars: pd.DataFrame,
) -> AlertSignal | None:
    """Session low set in first 15 min, price bases and holds above it.

    Pattern: stock dips in first 3 bars (15 min), finds its floor, then
    holds above that low for at least 3 consecutive bars — confirming a base.

    Conditions:
    1. Session low is within the first OPENING_LOW_BASE_WINDOW_BARS bars
    2. Low is a meaningful dip from open (>= MIN_DIP_PCT)
    3. At least OPENING_LOW_BASE_HOLD_BARS consecutive bars after low
       with Low > session_low * (1 + HOLD_PCT) — base confirmed
    4. Last bar closes above the hold threshold (still basing, not breaking)
    """
    min_bars = OPENING_LOW_BASE_WINDOW_BARS + OPENING_LOW_BASE_HOLD_BARS + 1
    if len(bars) < min_bars:
        return None

    # Session low must be in the opening window
    window = bars.iloc[:OPENING_LOW_BASE_WINDOW_BARS]
    window_low = window["Low"].min()
    session_low = bars["Low"].min()

    if window_low > session_low:
        return None  # session low came after the opening window

    if window_low <= 0:
        return None

    # Low must be a meaningful dip from open
    open_price = bars["Open"].iloc[0]
    dip_pct = (open_price - window_low) / open_price if open_price > 0 else 0
    if dip_pct < OPENING_LOW_BASE_MIN_DIP_PCT:
        return None

    # Find index of the low bar in the window
    low_idx = window["Low"].idxmin()
    low_pos = bars.index.get_loc(low_idx)

    # Count consecutive hold bars after the low
    hold_threshold = window_low * (1 + OPENING_LOW_BASE_HOLD_PCT)
    consecutive_hold = 0
    for i in range(low_pos + 1, len(bars)):
        if bars["Low"].iloc[i] >= hold_threshold:
            consecutive_hold += 1
        else:
            consecutive_hold = 0  # reset on break

    if consecutive_hold < OPENING_LOW_BASE_HOLD_BARS:
        return None

    last_bar = bars.iloc[-1]
    if last_bar["Close"] <= hold_threshold:
        return None  # not holding

    # Entry = hold threshold (the base level), not current price
    entry = round(hold_threshold, 2)
    stop = round(window_low * (1 - OPENING_LOW_BASE_STOP_OFFSET_PCT), 2)
    risk = entry - stop
    if risk <= 0:
        return None

    # Skip if price already ran past T1 — signal is stale
    target_1 = round(entry + risk, 2)
    if last_bar["Close"] > target_1:
        return None

    confidence = "high" if dip_pct >= 0.005 and consecutive_hold >= 4 else "medium"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.OPENING_LOW_BASE,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=target_1,
        target_2=round(entry + 2 * risk, 2),
        confidence=confidence,
        message=(
            f"Opening low base — low ${window_low:.2f} set in first 15 min, "
            f"held {consecutive_hold} bars, dip {dip_pct:.1%} from open"
        ),
    )


# ---------------------------------------------------------------------------
# Bounce Quality Classifier — tags bounce signals with quality assessment
# ---------------------------------------------------------------------------


def classify_bounce_quality(
    bars: pd.DataFrame,
    vwap_series: pd.Series | None,
    bar_volume: float,
    avg_volume: float,
    bounce_level: float,
) -> dict:
    """Score bounce quality on 3 factors to differentiate liquidity grabs
    from weak relief rallies.

    Returns dict with:
      quality: "strong" | "moderate" | "weak"
      factors: list of strings describing what was found
      tag: formatted string to append to signal message

    Three checks (1 point each, max 3):
    1. Wick test: did price wick below the level and close above?
       (liquidity grab pattern — swept stops then reclaimed)
    2. Volume test: is bounce volume >= 1.2x average?
       (real buyers stepping in, not just short covering)
    3. VWAP test: is price above VWAP or reclaiming it?
       (buyers in control of the session)
    """
    score = 0
    factors: list[str] = []

    if bars.empty or bounce_level <= 0:
        return {"quality": "weak", "factors": [], "tag": ""}

    last_bar = bars.iloc[-1]

    # 1. Wick test: bar wicked below level but closed above
    # Check last 3 bars for wick pattern (the bounce might be 1-2 bars old)
    lookback = min(3, len(bars))
    wick_found = False
    for i in range(-lookback, 0):
        bar = bars.iloc[i]
        if bar["Low"] < bounce_level and bar["Close"] > bounce_level:
            wick_found = True
            break
    if wick_found:
        score += 1
        factors.append("wick reclaim")

    # 2. Volume test: bounce volume vs average
    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0
    if vol_ratio >= 1.2:
        score += 1
        factors.append(f"vol {vol_ratio:.1f}x")

    # 3. VWAP test: price above VWAP or within 0.1% (reclaiming)
    if vwap_series is not None and not vwap_series.empty:
        current_vwap = vwap_series.iloc[-1]
        if current_vwap > 0:
            vwap_dist = (last_bar["Close"] - current_vwap) / current_vwap
            if vwap_dist >= -0.001:  # above or within 0.1% of VWAP
                score += 1
                factors.append("above VWAP")

    # Classify
    if score >= 3:
        quality = "strong"
    elif score >= 2:
        quality = "moderate"
    else:
        quality = "weak"

    factors_str = " + ".join(factors) if factors else "no confirming factors"
    tag = f" | BOUNCE QUALITY: {quality.upper()} ({factors_str})"

    return {"quality": quality, "factors": factors, "tag": tag}


# ---------------------------------------------------------------------------
# Rule: Session Low at Hourly Support → Bounce to VWAP (BUY)
# ---------------------------------------------------------------------------


def check_session_low_reversal(
    symbol: str,
    bars: pd.DataFrame,
) -> AlertSignal | None:
    """Session low established with reversal candle + volume spike.

    Fires at the low itself, not after VWAP reclaim. The entry is near
    the low with tight risk.

    Conditions:
    1. Must have at least 6 bars (30 min into session)
    2. Current or prior bar made the session low
    3. The low bar shows a reversal candle (hammer or long lower wick)
    4. Volume on the low bar >= 1.5x session average (capitulation)
    5. Current bar closes above the low bar's close (confirmation)
    """
    if bars.empty or len(bars) < 6:
        return None

    session_low = bars["Low"].min()
    session_low_idx = bars["Low"].idxmin()
    last_bar = bars.iloc[-1]

    # Session low must be recent (last 5 bars = 25 min on 5-min bars)
    # If the low bar itself is a strong bullish close, it can self-confirm
    bars_since_low = len(bars.loc[session_low_idx:]) - 1
    if bars_since_low > 5:
        return None  # too old — missed the entry window

    low_bar = bars.loc[session_low_idx]
    low_o = float(low_bar["Open"])
    low_h = float(low_bar["High"])
    low_l = float(low_bar["Low"])
    low_c = float(low_bar["Close"])
    low_vol = float(low_bar["Volume"]) if pd.notna(low_bar["Volume"]) else 0
    low_range = low_h - low_l
    low_body = abs(low_c - low_o)

    if low_range <= 0:
        return None

    # Reversal candle check: hammer, long lower wick, OR strong bullish close
    lower_wick = min(low_o, low_c) - low_l
    is_hammer = lower_wick >= 1.5 * low_body and (low_c - low_l) / low_range >= 0.6
    is_long_wick = lower_wick / low_range >= 0.6
    # Strong bullish close: green candle where close is in upper 25% of range
    # and body fills > 60% of range (strong buying at the low)
    is_bullish_close = (
        low_c > low_o
        and low_body / low_range >= 0.6
        and (low_c - low_l) / low_range >= 0.75
    )

    if not is_hammer and not is_long_wick and not is_bullish_close:
        return None

    # Volume check: 1.2x for strong bullish close (needs less volume
    # confirmation), 1.5x for hammer/wick patterns
    avg_vol = bars["Volume"].mean()
    vol_ratio = low_vol / avg_vol if avg_vol > 0 else 0
    _vol_threshold = 1.2 if is_bullish_close else 1.5
    if vol_ratio < _vol_threshold:
        return None

    # Confirmation: current bar closes above the low bar's close
    # OR the low bar itself is a strong bullish close (self-confirming)
    if bars_since_low == 0 and is_bullish_close:
        pass  # low bar is self-confirming — strong green candle at the low
    elif bars_since_low == 0:
        return None  # current bar IS the low, need next bar to confirm
    elif float(last_bar["Close"]) <= low_c:
        return None  # next bar didn't confirm

    candle_type = "hammer" if is_hammer else "strong bullish close" if is_bullish_close else "long wick"
    entry = round(float(last_bar["Close"]), 2)
    stop = round(session_low * 0.997, 2)  # stop just below session low
    stop = _cap_risk(entry, stop, symbol=symbol)
    risk = entry - stop
    if risk <= 0:
        return None

    target_1 = round(entry + risk, 2)
    target_2 = round(entry + 2 * risk, 2)

    confidence = "high" if vol_ratio >= 2.0 and is_hammer else "medium"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SESSION_LOW_REVERSAL,
        direction="BUY",
        price=float(last_bar["Close"]),
        entry=entry,
        stop=stop,
        target_1=target_1,
        target_2=target_2,
        confidence=confidence,
        message=(
            f"SESSION LOW REVERSAL — low ${session_low:.2f} with "
            f"{candle_type} candle on {vol_ratio:.1f}x volume. "
            f"Buyers stepping in at the low."
        ),
    )


def check_vwap_loss(
    symbol: str,
    bars: pd.DataFrame,
    vwap_series: pd.Series,
) -> AlertSignal | None:
    """Price was above VWAP, now confirms close below — bearish shift.

    Conditions:
    1. At least 12 bars (60 min into session)
    2. At least 3 of the prior 6 bars closed above VWAP (was holding above)
    3. Current bar closes below VWAP
    4. Current bar closes in the lower 40% of its range (selling into close)
    """
    if bars.empty or len(bars) < 12:
        return None
    if vwap_series is None or vwap_series.empty:
        return None

    current_vwap = float(vwap_series.iloc[-1])
    if current_vwap <= 0:
        return None

    last_bar = bars.iloc[-1]
    last_close = float(last_bar["Close"])
    last_high = float(last_bar["High"])
    last_low = float(last_bar["Low"])
    bar_range = last_high - last_low

    # Must close below VWAP
    if last_close >= current_vwap:
        return None

    # Close must be in lower 40% of bar range (selling pressure)
    if bar_range > 0 and (last_close - last_low) / bar_range > 0.4:
        return None

    # Prior bars must have been above VWAP (establishing it as support)
    lookback = min(6, len(bars) - 1)
    prior_bars = bars.iloc[-(lookback + 1):-1]
    prior_vwaps = vwap_series.iloc[-(lookback + 1):-1]

    if len(prior_bars) < 3 or len(prior_vwaps) < 3:
        return None

    bars_above_vwap = sum(
        float(prior_bars.iloc[i]["Close"]) > float(prior_vwaps.iloc[i])
        for i in range(len(prior_bars))
    )

    # At least half the prior bars were above VWAP
    if bars_above_vwap < len(prior_bars) * 0.5:
        return None

    entry = round(last_close, 2)
    stop = round(current_vwap * 1.002, 2)  # stop just above VWAP
    risk = stop - entry
    if risk <= 0:
        return None

    target_1 = round(entry - risk, 2)
    target_2 = round(entry - 2 * risk, 2)

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.VWAP_LOSS,
        direction="SHORT",
        price=last_close,
        entry=entry,
        stop=stop,
        target_1=target_1,
        target_2=target_2,
        confidence="medium",
        message=(
            f"VWAP LOSS — was above VWAP ${current_vwap:.2f} for "
            f"{bars_above_vwap}/{lookback} bars, now closed below at "
            f"${last_close:.2f}. Bearish shift."
        ),
    )


def check_ema_rejection_short(
    symbol: str,
    bars: pd.DataFrame,
    prior_day: dict | None,
) -> AlertSignal | None:
    """Price rallies into a key EMA/MA from below and gets rejected — SHORT.

    Conditions:
    1. At least 12 bars (60 min into session)
    2. Bar high reaches within 0.3% of a key daily EMA/MA (20/50/100/200)
    3. Bar closes in the lower 40% of its range (rejection confirmed)
    4. Price must be BELOW the MA (approaching from below = resistance)
    """
    if bars.empty or len(bars) < 12 or not prior_day:
        return None

    last_bar = bars.iloc[-1]
    last_close = float(last_bar["Close"])
    last_high = float(last_bar["High"])
    last_low = float(last_bar["Low"])
    bar_range = last_high - last_low

    if bar_range <= 0:
        return None

    # Close must be in lower 40% of range (selling pressure = rejection)
    if (last_close - last_low) / bar_range > 0.4:
        return None

    # Check each key MA for rejection
    _ma_levels = [
        ("EMA20", prior_day.get("ema20", 0)),
        ("EMA50", prior_day.get("ema50", 0)),
        ("MA50", prior_day.get("ma50", 0)),
        ("EMA100", prior_day.get("ema100", 0)),
        ("EMA200", prior_day.get("ema200", 0)),
        ("MA200", prior_day.get("ma200", 0)),
    ]

    for ma_name, ma_val in _ma_levels:
        if not ma_val or ma_val <= 0:
            continue
        # Price must be below the MA (approaching from below)
        if last_close >= ma_val:
            continue
        # Bar high must have reached near the MA (within 0.3%)
        proximity = abs(last_high - ma_val) / ma_val
        if proximity > 0.003:
            continue

        # Rejection confirmed
        entry = round(last_close, 2)
        stop = round(ma_val * 1.003, 2)
        risk = stop - entry
        if risk <= 0:
            continue

        target_1 = round(entry - risk, 2)
        target_2 = round(entry - 2 * risk, 2)

        return AlertSignal(
            symbol=symbol,
            alert_type=AlertType.EMA_REJECTION_SHORT,
            direction="SHORT",
            price=last_close,
            entry=entry,
            stop=stop,
            target_1=target_1,
            target_2=target_2,
            confidence="medium",
            message=(
                f"{ma_name} REJECTION — rallied to ${last_high:.2f} near "
                f"{ma_name} ${ma_val:.2f}, rejected and closed ${last_close:.2f}. "
                f"MA acting as resistance."
            ),
        )

    return None


def check_ema_loss_short(
    symbol: str,
    bars: pd.DataFrame,
    prior_day: dict | None,
) -> AlertSignal | None:
    """Price was above a key EMA/MA, now confirms close below — SHORT.

    Like vwap_loss but for moving averages. When a stock loses a key MA
    that was supporting it, institutions adjust positioning.

    Conditions:
    1. At least 12 bars (60 min into session)
    2. Prior 3+ bars had closes above the MA (it was support)
    3. Current bar closes below the MA (support lost)
    4. Close in lower 50% of bar range (not a wick below)
    """
    if bars.empty or len(bars) < 12 or not prior_day:
        return None

    last_bar = bars.iloc[-1]
    last_close = float(last_bar["Close"])
    last_high = float(last_bar["High"])
    last_low = float(last_bar["Low"])
    bar_range = last_high - last_low

    if bar_range <= 0:
        return None

    # Close in lower 50% (not a wick)
    if (last_close - last_low) / bar_range > 0.5:
        return None

    # Check key MAs — only the ones price was recently above
    _ma_levels = [
        ("EMA50", prior_day.get("ema50", 0)),
        ("MA50", prior_day.get("ma50", 0)),
        ("EMA100", prior_day.get("ema100", 0)),
        ("EMA200", prior_day.get("ema200", 0)),
        ("MA200", prior_day.get("ma200", 0)),
    ]

    for ma_name, ma_val in _ma_levels:
        if not ma_val or ma_val <= 0:
            continue
        # Must close below the MA now
        if last_close >= ma_val:
            continue

        # Check prior bars were above this MA (it was support)
        lookback = min(6, len(bars) - 1)
        prior_bars = bars.iloc[-(lookback + 1):-1]
        bars_above = sum(float(b["Close"]) > ma_val for _, b in prior_bars.iterrows())

        if bars_above < 3:
            continue  # MA wasn't established support

        entry = round(last_close, 2)
        stop = round(ma_val * 1.003, 2)
        risk = stop - entry
        if risk <= 0:
            continue

        target_1 = round(entry - risk, 2)
        target_2 = round(entry - 2 * risk, 2)

        return AlertSignal(
            symbol=symbol,
            alert_type=AlertType.EMA_LOSS_SHORT,
            direction="SHORT",
            price=last_close,
            entry=entry,
            stop=stop,
            target_1=target_1,
            target_2=target_2,
            confidence="medium",
            message=(
                f"{ma_name} LOST — was above {ma_name} ${ma_val:.2f} for "
                f"{bars_above}/{lookback} bars, now closed below at "
                f"${last_close:.2f}. Support broken."
            ),
        )

    return None


def check_session_low_breakdown(
    symbol: str,
    bars: pd.DataFrame,
) -> AlertSignal | None:
    """Established session low breaks on volume — SHORT signal.

    The mirror of session_low_reversal. When a session low that held for
    multiple bars finally breaks, it signals sellers overwhelming buyers.

    Conditions:
    1. At least 12 bars (60 min) — need an established low
    2. Session low was tested/held for 3+ bars before breaking
    3. Current bar closes below the prior session low
    4. Volume >= 1.2x average on the breakdown bar
    """
    if bars.empty or len(bars) < 12:
        return None

    last_bar = bars.iloc[-1]
    last_close = float(last_bar["Close"])
    last_low = float(last_bar["Low"])
    last_vol = float(last_bar["Volume"]) if pd.notna(last_bar["Volume"]) else 0

    # Find the prior session low (excluding current bar)
    prior_bars = bars.iloc[:-1]
    if prior_bars.empty:
        return None
    prior_session_low = float(prior_bars["Low"].min())

    if prior_session_low <= 0:
        return None

    # Current bar's low must break below the prior session low
    # Use low (not close) to catch the break in real-time, not after the candle closes
    if last_low >= prior_session_low:
        return None

    # Break must be meaningful (at least 0.05% below)
    break_pct = (prior_session_low - last_low) / prior_session_low
    if break_pct < 0.0005:
        return None

    # Prior low must have been held for 3+ bars (established support)
    # Count bars where low was within 0.3% of the session low
    near_low_bars = prior_bars[
        (prior_bars["Low"] - prior_session_low).abs() / prior_session_low < 0.003
    ]
    if len(near_low_bars) < 2:
        return None  # low wasn't tested enough

    # Volume check
    avg_vol = bars["Volume"].mean()
    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 0
    if vol_ratio < 1.0:
        return None

    # Entry near the break level, not at the close
    entry = round(prior_session_low * 0.999, 2)
    stop = round(prior_session_low * 1.003, 2)
    stop = _cap_risk(stop, entry, symbol=symbol)
    risk = stop - entry
    if risk <= 0:
        return None

    target_1 = round(entry - risk, 2)
    target_2 = round(entry - 2 * risk, 2)

    confidence = "high" if vol_ratio >= 1.5 and break_pct >= 0.002 else "medium"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SESSION_LOW_BREAKDOWN,
        direction="SHORT",
        price=last_close,
        entry=entry,
        stop=stop,
        target_1=target_1,
        target_2=target_2,
        confidence=confidence,
        message=(
            f"SESSION LOW BREAKDOWN — prior low ${prior_session_low:.2f} "
            f"broken on {vol_ratio:.1f}x volume, closed ${last_close:.2f} "
            f"({break_pct:.2%} below)"
        ),
    )


def check_session_low_bounce_to_vwap(
    symbol: str,
    bars: pd.DataFrame,
    vwap_series: pd.Series,
    intraday_supports: list[dict],
    bar_volume: float,
    avg_volume: float,
) -> AlertSignal | None:
    """Session low at hourly support, price bouncing back toward VWAP.

    High-conviction mean-reversion setup:
    1. Session low is near a known hourly support level (within 0.3%)
    2. Price is below VWAP (room for the bounce trade)
    3. Low has held for at least 2 bars (not actively breaking)
    4. Last bar closes above the low (bounce starting)
    5. T1 = VWAP (institutional mean), T2 = VWAP + 1R

    Gate interaction: exempt from YELLOW demotion (being below VWAP
    is the thesis, not a warning).
    """
    if bars.empty or vwap_series.empty or not intraday_supports:
        return None
    if len(bars) < 6:  # need some bars to establish the low
        return None

    # Skip if currently in hourly consolidation — let breakout signal handle it
    hbreak = detect_hourly_consolidation_break(bars)
    if hbreak and hbreak.get("status") == "consolidating":
        return None  # ranging below VWAP is not a bounce, it's chop

    last_bar = bars.iloc[-1]
    current_vwap = vwap_series.iloc[-1] if not vwap_series.empty else 0
    if current_vwap <= 0:
        return None

    # Price must be below VWAP (room to bounce)
    if last_bar["Close"] >= current_vwap:
        return None

    session_low = bars["Low"].min()
    if session_low <= 0:
        return None

    # Session low must be near a known hourly support level
    nearest_support = None
    nearest_dist = float("inf")
    for sup in intraday_supports:
        level = sup.get("level", 0)
        if level <= 0:
            continue
        dist_pct = abs(session_low - level) / level
        if dist_pct < nearest_dist and dist_pct <= 0.003:  # within 0.3%
            nearest_dist = dist_pct
            nearest_support = sup

    if nearest_support is None:
        return None  # session low not at any known support

    support_level = nearest_support["level"]

    # Low must have held — last 2 bars' lows above session_low (not breaking)
    hold_threshold = session_low * 1.001  # tiny buffer
    recent_lows = bars.iloc[-2:]
    if (recent_lows["Low"] < hold_threshold).any():
        return None  # still actively testing / breaking the low

    # Last bar must close above session low (bounce confirmed)
    if last_bar["Close"] <= session_low:
        return None

    # Must have meaningful distance to VWAP (at least 0.15%)
    vwap_distance_pct = (current_vwap - last_bar["Close"]) / last_bar["Close"]
    if vwap_distance_pct < 0.0015:
        return None  # too close to VWAP, not worth the trade

    # Entry = current close (bounce in progress), stop below session low
    entry = round(last_bar["Close"], 2)
    stop = round(session_low * 0.999, 2)  # just below session low
    risk = entry - stop
    if risk <= 0:
        return None

    # T1 = VWAP, T2 = VWAP + 1R
    t1 = round(current_vwap, 2)
    t2 = round(current_vwap + risk, 2)

    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0
    touch_count = nearest_support.get("touch_count", 1)

    # Support fatigue: too many tests weakens the level
    fatigue_warning = ""
    if touch_count >= 4:
        confidence = "medium"
        fatigue_warning = (
            f" | CAUTION: support fatigue — tested {touch_count}x, "
            f"weakening (breakdown risk elevated)"
        )
    elif touch_count >= 2 or vol_ratio >= 1.2:
        confidence = "high"
    else:
        confidence = "medium"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SESSION_LOW_BOUNCE_VWAP,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=t1,
        target_2=t2,
        confidence=confidence,
        message=(
            f"SESSION LOW BOUNCE — low ${session_low:.2f} held at "
            f"hourly support ${support_level:.2f} (tested {touch_count}x). "
            f"Bouncing toward VWAP ${current_vwap:.2f} "
            f"({vwap_distance_pct:.1%} away). Vol {vol_ratio:.1f}x"
            f"{fatigue_warning}"
        ),
    )


# ---------------------------------------------------------------------------
# Rule: SPY Short Entry (SHORT) — gate-confirmed breakdown shorts
# ---------------------------------------------------------------------------


def check_spy_short_entry(
    symbol: str,
    bars: pd.DataFrame,
    prior_day: dict | None,
    bar_volume: float,
    avg_volume: float,
    gate: dict | None,
) -> AlertSignal | None:
    """SHORT entry when gate is RED and price breaks a key level.

    Fires when:
    - Gate is RED (VWAP + EMA both bearish)
    - Price closes below a key support level (PDL, weekly low, or session low)
    - Volume confirms the breakdown
    - Price hasn't reclaimed the level (still below)
    """
    from alert_config import SPY_SHORT_STOP_OFFSET_PCT, SPY_SHORT_SYMBOLS

    if symbol not in SPY_SHORT_SYMBOLS:
        return None
    if not gate or gate.get("gate") != "red":
        return None
    if bars.empty or prior_day is None:
        return None

    last_bar = bars.iloc[-1]

    # Volume confirmation
    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0
    if vol_ratio < 0.8:
        return None

    # Check breakdown levels (best to worst)
    breakdown_levels = []
    pdl = prior_day.get("low", 0)
    if pdl > 0 and last_bar["Close"] < pdl:
        breakdown_levels.append(("Prior Day Low", pdl))

    pw_low = prior_day.get("prior_week_low", 0)
    if pw_low and pw_low > 0 and last_bar["Close"] < pw_low:
        breakdown_levels.append(("Weekly Low", pw_low))

    # Session low (if price is making new session low)
    session_low = bars["Low"].min()
    if last_bar["Low"] <= session_low * 1.001:  # at or near session low
        # Use prior bar's low as the broken level
        if len(bars) >= 3:
            recent_support = bars.iloc[-3:-1]["Low"].min()
            if last_bar["Close"] < recent_support:
                breakdown_levels.append(("Session Support", round(recent_support, 2)))

    if not breakdown_levels:
        return None

    # Use the highest (most significant) broken level
    level_label, level_price = breakdown_levels[0]

    # Verify no immediate reclaim (last 2 bars should be below level)
    if len(bars) >= 2:
        prev_close = bars.iloc[-2]["Close"]
        if prev_close > level_price and last_bar["Close"] > level_price:
            return None  # reclaimed

    entry = round(level_price, 2)
    stop = round(level_price * (1 + SPY_SHORT_STOP_OFFSET_PCT), 2)
    risk = stop - entry
    if risk <= 0:
        return None

    # Find next support below for targets
    next_supports = []
    ma200 = prior_day.get("ma200", 0)
    if ma200 and ma200 > 0 and ma200 < entry:
        next_supports.append(ma200)
    pm_low = prior_day.get("prior_month_low", 0)
    if pm_low and pm_low > 0 and pm_low < entry:
        next_supports.append(pm_low)
    if pw_low and pw_low > 0 and pw_low < entry:
        next_supports.append(pw_low)

    next_supports.sort(reverse=True)  # nearest first
    t1 = round(entry - risk, 2)  # default 1R
    t2 = round(entry - 2 * risk, 2)  # default 2R
    if next_supports:
        t1 = round(next_supports[0], 2)
        if len(next_supports) > 1:
            t2 = round(next_supports[1], 2)

    vwap_dom = gate.get("vwap_dominance", 0)
    confidence = "high" if vol_ratio >= 1.5 and vwap_dom < 0.2 else "medium"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SPY_SHORT_ENTRY,
        direction="SHORT",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=t1,
        target_2=t2,
        confidence=confidence,
        message=(
            f"SHORT — {level_label} ${level_price:.2f} broken, "
            f"gate RED (VWAP {vwap_dom:.0%}, below EMA). "
            f"Vol {vol_ratio:.1f}x. "
            f"Stop above ${stop:.2f}, T1 ${t1:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# Rule: Consolidation Breakout (BUY / SHORT) — per-symbol hourly range break
# ---------------------------------------------------------------------------


def check_consolidation_breakout(
    symbol: str,
    bars_5m: pd.DataFrame,
    bar_volume: float,
    avg_volume: float,
    daily_trend: dict | None = None,
) -> AlertSignal | None:
    """Per-symbol hourly consolidation breakout signal.

    Detects when a symbol breaks out of its own hourly consolidation range.
    Uses ATR-based threshold to adapt to each symbol's volatility.
    Uses daily trend context to adjust confidence (institutions use daily).

    - Break UP   → BUY  (entry at range_high, stop at range_low)
    - Break DOWN → SHORT (entry at range_low, stop at range_high)

    Gate interaction is handled by evaluate_rules():
    - BUY overrides YELLOW gate (blocked by RED)
    - SHORT fires on RED + YELLOW (blocked on GREEN)
    """
    from alert_config import (
        CONSOL_BREAKOUT_ENABLED, CONSOL_BREAKOUT_STOP_OFFSET_PCT,
        CONSOL_BREAKOUT_MIN_VOL_RATIO, HOURLY_CONSOL_MIN_BARS,
    )

    if not CONSOL_BREAKOUT_ENABLED:
        return None

    hbreak = detect_hourly_consolidation_break(bars_5m)
    if not hbreak or hbreak.get("status") != "breakout":
        return None

    # Volume confirmation
    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0
    if vol_ratio < CONSOL_BREAKOUT_MIN_VOL_RATIO:
        return None

    direction = hbreak["direction"]
    range_high = hbreak["range_high"]
    range_low = hbreak["range_low"]
    break_price = hbreak["break_price"]
    range_pct = hbreak["range_pct"]
    hourly_atr = hbreak.get("hourly_atr", 0)

    # Daily trend context — institutions use daily structure
    dt = daily_trend or {}
    daily_bias = dt.get("bias", "neutral")
    daily_structure = dt.get("structure", "none")
    daily_tag = ""

    if direction == "UP":
        if daily_bias == "bearish":
            # BUY breakout against daily trend — demote confidence
            confidence = "medium"
            daily_tag = f" | CAUTION: daily trend bearish"
            if daily_structure == "descending_triangle":
                daily_tag += " (descending triangle — lower highs)"
        elif daily_bias == "bullish":
            confidence = "high"
            daily_tag = " | daily trend aligned (bullish)"
        else:
            confidence = "high"
            if daily_structure == "contracting":
                daily_tag = " | daily range contracting — breakout pending"

        entry = round(range_high, 2)
        stop = round(range_low * (1 - CONSOL_BREAKOUT_STOP_OFFSET_PCT), 2)
        risk = entry - stop
        if risk <= 0:
            return None
        t1 = round(entry + risk, 2)
        t2 = round(entry + 2 * risk, 2)
        return AlertSignal(
            symbol=symbol,
            alert_type=AlertType.CONSOL_BREAKOUT_LONG,
            direction="BUY",
            price=break_price,
            entry=entry,
            stop=stop,
            target_1=t1,
            target_2=t2,
            confidence=confidence,
            message=(
                f"CONSOLIDATION BREAKOUT UP — {HOURLY_CONSOL_MIN_BARS}h range "
                f"${range_low:.2f}-${range_high:.2f} ({range_pct:.1f}%) broken. "
                f"ATR ${hourly_atr:.2f}. Vol {vol_ratio:.1f}x. "
                f"Entry ${entry:.2f}, stop ${stop:.2f}{daily_tag}"
            ),
        )
    elif direction == "DOWN":
        if daily_bias == "bullish":
            # SHORT breakout against daily trend — demote confidence
            confidence = "medium"
            daily_tag = f" | CAUTION: daily trend bullish"
            if daily_structure == "ascending_triangle":
                daily_tag += " (ascending triangle — higher lows)"
        elif daily_bias == "bearish":
            confidence = "high"
            daily_tag = " | daily trend aligned (bearish)"
        else:
            confidence = "high"
            if daily_structure == "contracting":
                daily_tag = " | daily range contracting — breakdown pending"

        entry = round(range_low, 2)
        stop = round(range_high * (1 + CONSOL_BREAKOUT_STOP_OFFSET_PCT), 2)
        risk = stop - entry
        if risk <= 0:
            return None
        t1 = round(entry - risk, 2)
        t2 = round(entry - 2 * risk, 2)
        return AlertSignal(
            symbol=symbol,
            alert_type=AlertType.CONSOL_BREAKOUT_SHORT,
            direction="SHORT",
            price=break_price,
            entry=entry,
            stop=stop,
            target_1=t1,
            target_2=t2,
            confidence=confidence,
            message=(
                f"CONSOLIDATION BREAKDOWN — {HOURLY_CONSOL_MIN_BARS}h range "
                f"${range_low:.2f}-${range_high:.2f} ({range_pct:.1f}%) broken down. "
                f"ATR ${hourly_atr:.2f}. Vol {vol_ratio:.1f}x. "
                f"Entry ${entry:.2f}, stop ${stop:.2f}{daily_tag}"
            ),
        )
    return None


# ---------------------------------------------------------------------------
# Rule: Morning Low Retest (BUY)
# ---------------------------------------------------------------------------


def check_morning_low_retest(
    symbol: str,
    bars: pd.DataFrame,
    opening_range: dict | None,
) -> AlertSignal | None:
    """Price retests the first-hour low after rallying away.

    Classic day trade pattern: morning establishes a low, price rallies,
    then pulls back to test that morning low — bounce entry.

    Conditions:
    1. Must be past first hour (>= MORNING_LOW_RETEST_MIN_BARS)
    2. First-hour low established via opening_range
    3. Price must have rallied >= RALLY_PCT above first-hour low at some point
    4. Last bar low within PROXIMITY_PCT of first-hour low
    5. Last bar closes above first-hour low (bounce confirmed)
    """
    if not opening_range or not opening_range.get("or_complete"):
        return None
    if bars.empty or len(bars) < MORNING_LOW_RETEST_MIN_BARS:
        return None

    first_hour_low = opening_range["or_low"]
    first_hour_high = opening_range["or_high"]
    if first_hour_low <= 0:
        return None

    last_bar = bars.iloc[-1]

    # Must have rallied above first-hour low at some point (the move away)
    post_or_bars = bars.iloc[6:]  # bars after opening range
    if post_or_bars.empty:
        return None
    max_high = post_or_bars["High"].max()
    rally_pct = (max_high - first_hour_low) / first_hour_low
    if rally_pct < MORNING_LOW_RETEST_RALLY_PCT:
        return None

    # Last bar low must be near first-hour low (the retest)
    proximity = (last_bar["Low"] - first_hour_low) / first_hour_low
    if proximity < -MORNING_LOW_RETEST_PROXIMITY_PCT:
        return None  # broke too far below
    if proximity > MORNING_LOW_RETEST_PROXIMITY_PCT:
        return None  # not close enough

    # Must close above first-hour low (bounce confirmed)
    if last_bar["Close"] <= first_hour_low:
        return None

    # Skip if price is still near the opening range (not a retest, still forming)
    # Require at least one bar after the OR that rallied significantly
    rally_bar_count = len(post_or_bars[post_or_bars["Close"] > first_hour_low * (1 + MORNING_LOW_RETEST_RALLY_PCT)])
    if rally_bar_count < 2:
        return None

    entry = round(first_hour_low, 2)
    stop = round(first_hour_low * (1 - MORNING_LOW_RETEST_STOP_OFFSET_PCT), 2)
    stop = _cap_risk(entry, stop, symbol=symbol)
    risk = entry - stop
    if risk <= 0:
        return None

    # T1 = VWAP area or first-hour high, T2 = further
    target_1 = round(entry + risk, 2)
    target_2 = round(first_hour_high, 2) if first_hour_high > target_1 else round(entry + 2 * risk, 2)

    confidence = "high" if rally_pct >= 0.01 else "medium"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MORNING_LOW_RETEST,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=target_1,
        target_2=target_2,
        confidence=confidence,
        message=(
            f"Morning low retest — first-hour low ${first_hour_low:.2f} "
            f"retested after {rally_pct:.1%} rally to ${max_high:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# Rule: Morning Low Breakdown (SELL/SHORT)
# ---------------------------------------------------------------------------


def check_morning_low_breakdown(
    symbol: str,
    bars: pd.DataFrame,
    opening_range: dict | None,
) -> AlertSignal | None:
    """First-hour low broken on volume → SELL/SHORT signal.

    When the established morning low breaks on above-average volume,
    it signals institutional selling and is one of the strongest
    intraday short setups.

    Conditions:
    1. Past first hour (>= 12 bars on 5-min = 60 min)
    2. First-hour low established via opening_range
    3. Last bar closes below first-hour low (breakdown confirmed)
    4. Volume on breakdown bar >= 1.2x session average
    5. Price must have held the low for at least a few bars before breaking
       (not an immediate gap-down opening)
    """
    if not opening_range or not opening_range.get("or_complete"):
        return None
    if bars.empty or len(bars) < 12:
        return None

    first_hour_low = opening_range["or_low"]
    first_hour_high = opening_range["or_high"]
    if first_hour_low <= 0:
        return None

    last_bar = bars.iloc[-1]
    last_close = float(last_bar["Close"])
    last_low = float(last_bar["Low"])
    last_vol = float(last_bar["Volume"]) if pd.notna(last_bar["Volume"]) else 0

    # Bar low must break below first-hour low (real-time detection)
    # Use low instead of close — in fast selloffs, waiting for close
    # means missing the break by $3-4 (today SPY broke $650 but alert
    # didn't fire until $647 close)
    if last_low >= first_hour_low:
        return None

    # Break must be meaningful
    break_pct = (first_hour_low - last_low) / first_hour_low
    if break_pct < 0.0005:
        return None

    # Volume check: breakdown bar must have above-average volume
    avg_vol = bars["Volume"].mean()
    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 0
    if vol_ratio < 1.2:
        return None

    # The low must have been tested/held earlier (not just a gap-down open)
    # At least 3 bars between OR formation and breakdown where low held
    post_or_bars = bars.iloc[6:-1]  # bars after OR, before current
    if len(post_or_bars) < 3:
        return None
    bars_holding_low = (post_or_bars["Low"] >= first_hour_low * 0.998).sum()
    if bars_holding_low < 3:
        return None  # low wasn't established/tested — skip

    # Entry near the break level, not at the close (which may be far below)
    entry = round(first_hour_low * 0.999, 2)  # just below the broken level
    stop = round(first_hour_low * 1.003, 2)   # stop above the broken low
    stop = _cap_risk(stop, entry, symbol=symbol)
    risk = stop - entry
    if risk <= 0:
        return None

    target_1 = round(entry - risk, 2)
    target_2 = round(entry - 2 * risk, 2)

    confidence = "high" if vol_ratio >= 1.5 and break_pct >= 0.002 else "medium"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MORNING_LOW_BREAKDOWN,
        direction="SHORT",
        price=last_close,
        entry=entry,
        stop=stop,
        target_1=target_1,
        target_2=target_2,
        confidence=confidence,
        message=(
            f"Morning low BREAKDOWN — first-hour low ${first_hour_low:.2f} "
            f"broken on {vol_ratio:.1f}x volume, closed ${last_close:.2f} "
            f"({break_pct:.2%} below)"
        ),
    )


# ---------------------------------------------------------------------------
# Rule: First Hour High Breakout (BUY)
# ---------------------------------------------------------------------------


def check_first_hour_high_breakout(
    symbol: str,
    bars: pd.DataFrame,
    opening_range: dict | None,
    bar_volume: float,
    avg_volume: float,
) -> AlertSignal | None:
    """Price breaks above first-hour high later in the session.

    Conditions:
    1. Must be past first hour
    2. Last bar closes above first-hour high
    3. Volume confirmation
    4. Entry = first-hour high, Stop = first-hour low or VWAP
    """
    if not opening_range or not opening_range.get("or_complete"):
        return None
    if bars.empty or len(bars) < FIRST_HOUR_HIGH_BREAKOUT_MIN_BARS:
        return None

    first_hour_high = opening_range["or_high"]
    first_hour_low = opening_range["or_low"]
    or_range = opening_range["or_range"]
    if first_hour_high <= 0 or or_range <= 0:
        return None

    last_bar = bars.iloc[-1]
    if last_bar["Close"] <= first_hour_high:
        return None

    # Volume check
    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0
    if vol_ratio < FIRST_HOUR_HIGH_BREAKOUT_VOLUME_RATIO:
        return None

    entry = round(first_hour_high, 2)
    stop = round(first_hour_low, 2)
    stop = _cap_risk(entry, stop, symbol=symbol)
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.FIRST_HOUR_HIGH_BREAKOUT,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + or_range, 2),
        target_2=round(entry + 2 * or_range, 2),
        confidence="high" if vol_ratio >= 1.5 else "medium",
        message=(
            f"First hour high breakout — closed above ${first_hour_high:.2f} "
            f"(range ${or_range:.2f}, vol {vol_ratio:.1f}x)"
        ),
    )


# ---------------------------------------------------------------------------
# Rule: MA/EMA Reclaim (BUY) — price crosses above key daily MA/EMA
# ---------------------------------------------------------------------------


def check_ma_ema_reclaim(
    symbol: str,
    bars: pd.DataFrame,
    ma_level: float | None,
    prior_close: float | None,
    alert_type: "AlertType",
    ma_label: str,
) -> AlertSignal | None:
    """Price crosses above a key daily MA/EMA from below.

    Conditions:
    - Prior close was below the MA (approaching from below)
    - Last bar closes above the MA (reclaim confirmed)
    - Price hasn't run too far above (staleness guard)
    - Entry = MA level, Stop = MA - offset
    """
    if ma_level is None or ma_level <= 0:
        return None
    if prior_close is None or prior_close <= 0:
        return None
    if bars.empty:
        return None

    # Prior close must be below the MA (was trading under it)
    if prior_close >= ma_level:
        return None

    last_bar = bars.iloc[-1]

    # Must close above the MA now
    if last_bar["Close"] <= ma_level:
        return None

    # Skip if price already ran too far above (stale)
    distance = (last_bar["Close"] - ma_level) / ma_level
    if distance > MA_RECLAIM_MAX_DISTANCE_PCT:
        return None

    entry = round(ma_level, 2)
    stop = round(ma_level * (1 - MA_RECLAIM_STOP_OFFSET_PCT), 2)
    stop = _cap_risk(entry, stop, symbol=symbol)
    risk = entry - stop
    if risk <= 0:
        return None

    confidence = "high" if distance <= 0.005 else "medium"

    return AlertSignal(
        symbol=symbol,
        alert_type=alert_type,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence=confidence,
        message=(
            f"{ma_label} reclaim — prior close ${prior_close:.2f} was below "
            f"${ma_level:.2f}, now closed above at ${last_bar['Close']:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# Rule: Session High Retracement (BUY)
# ---------------------------------------------------------------------------


def check_session_high_retracement(
    symbol: str,
    bars: pd.DataFrame,
    last_bar: pd.Series,
    bar_volume: float,
    avg_volume: float,
) -> AlertSignal | None:
    """Stock rallies from open, then retraces back near session low — buy the dip.

    Pattern: price makes a significant intraday high, then pulls back most/all
    of the rally, returning near the session low.  The prior rally proves demand
    at these levels; the retracement is a potential re-entry.

    Conditions:
    1. Session high >= open * (1 + RETRACEMENT_MIN_RALLY_PCT) — meaningful rally
    2. Session high was set >= RETRACEMENT_MIN_AGE_BARS ago — not an early spike
    3. Last bar low within RETRACEMENT_PROXIMITY_PCT of session low
    4. Last bar closes above session low (bounce confirmed, not free-falling)
    """
    min_bars = RETRACEMENT_MIN_AGE_BARS + 2
    if len(bars) < min_bars:
        return None

    open_price = bars["Open"].iloc[0]
    session_high = bars["High"].max()
    session_low = bars["Low"].min()

    if open_price <= 0 or session_low <= 0:
        return None

    # 1. Meaningful rally from open
    rally_pct = (session_high - open_price) / open_price
    if rally_pct < RETRACEMENT_MIN_RALLY_PCT:
        return None

    # 2. Session high must be old enough (not a spike on the current bar)
    high_idx = bars["High"].idxmax()
    high_pos = bars.index.get_loc(high_idx)
    bars_since_high = len(bars) - 1 - high_pos
    if bars_since_high < RETRACEMENT_MIN_AGE_BARS:
        return None

    # 3. Last bar low near session low
    proximity = abs(last_bar["Low"] - session_low) / session_low
    if proximity > RETRACEMENT_PROXIMITY_PCT:
        return None

    # 4. Bounce confirmed — close above session low
    if last_bar["Close"] <= session_low:
        return None

    # Entry/stop/targets
    entry = round(session_low, 2)
    stop = round(session_low * (1 - RETRACEMENT_STOP_OFFSET_PCT), 2)
    stop = _cap_risk(entry, stop, symbol=symbol)
    risk = entry - stop
    if risk <= 0:
        return None

    target_1 = round(entry + risk, 2)
    target_2 = round(entry + 2 * risk, 2)

    # Skip if price already ran past T1
    if last_bar["Close"] > target_1:
        return None

    # Confidence: high on exhaustion volume (sellers drying up)
    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0
    confidence = "high" if vol_ratio < 0.8 else "medium"

    retracement_pct = (session_high - last_bar["Low"]) / (session_high - session_low) * 100 if session_high > session_low else 0

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SESSION_HIGH_RETRACEMENT,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=target_1,
        target_2=target_2,
        confidence=confidence,
        message=(
            f"Session high retracement — rallied {rally_pct:.1%} to ${session_high:.2f}, "
            f"pulled back {retracement_pct:.0f}% to session low ${session_low:.2f}"
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
    3. Last bar low within SESSION_LOW_PROXIMITY_PCT of session low (allows slight undercut)
    4. Last bar closes above session low (bounce confirmed)
    5. First touch: earliest bar (excl. last) with low within proximity of session low
    6. First touch >= SESSION_LOW_MIN_AGE_BARS bars ago
    7. Recovery: >= SESSION_LOW_MIN_RECOVERY_BARS consecutive bars with low > session_low * (1 + RECOVERY_PCT)
    """
    min_bars = SESSION_LOW_MIN_AGE_BARS + SESSION_LOW_MIN_RECOVERY_BARS + 1
    if len(bars) < min_bars:
        return None

    session_low = bars["Low"].min()
    if session_low <= 0:
        return None

    # Last bar low must be near session low — use abs() to allow slight undercuts
    # (second touch can go marginally below first touch and still be a double bottom)
    proximity = abs(last_bar["Low"] - session_low) / session_low
    if proximity > SESSION_LOW_PROXIMITY_PCT:
        return None

    # Last bar must close above session low (bounce confirmed)
    if last_bar["Close"] <= session_low:
        return None

    # Find first touch: earliest bar (excluding last few bars) with low near session low
    first_touch_idx = None
    for i in range(len(bars) - SESSION_LOW_MIN_AGE_BARS):
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

    # True double bottom: retest must not make a significantly lower low
    # than the first touch. Reject descending lows masquerading as double bottoms.
    first_touch_low = bars["Low"].iloc[first_touch_idx]
    if last_bar["Low"] < first_touch_low * (1 - SESSION_LOW_PROXIMITY_PCT):
        return None

    # Entry/Stop/Targets — use session low as structural stop with buffer
    entry = session_low
    stop = round(session_low * (1 - SESSION_LOW_STOP_OFFSET_PCT), 2)
    risk = entry - stop
    if risk <= 0:
        return None

    # Boost confidence on volume exhaustion (low volume retest = sellers drying up)
    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0
    confidence = "high" if vol_ratio < SESSION_LOW_MAX_RETEST_VOL_RATIO else "medium"

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.SESSION_LOW_DOUBLE_BOTTOM,
        direction="BUY",
        price=last_bar["Close"],
        entry=round(entry, 2),
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence=confidence,
        message=(
            f"Session low double-bottom — ${session_low:.2f} tested twice, "
            f"recovery confirmed, bounce at ${last_bar['Close']:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# Rule 13b: Multi-Day Double Bottom (daily swing lows tested 2+ times)
# ---------------------------------------------------------------------------


def check_multi_day_double_bottom(
    symbol: str,
    intraday_bars: pd.DataFrame,
    daily_double_bottoms: list[dict],
    bar_volume: float,
    avg_volume: float,
    prior_day: dict | None = None,
) -> AlertSignal | None:
    """Multi-day double bottom: daily swing low zone tested 2+ times, now retesting intraday.

    Conditions:
    1. ``daily_double_bottoms`` is non-empty (pre-computed by detect_daily_double_bottoms)
    2. Last intraday bar's low is within DAILY_DB_INTRADAY_PROXIMITY_PCT of a zone
    3. Last bar closes above the zone level (bounce confirmed)
    4. Price hasn't already run >DAILY_DB_MAX_DISTANCE_PCT above zone (stale guard)
    5. Not making a significantly lower low than the zone (no descending lows)
    6. **NEW**: Zone must be near a structural support level (PDL, MA50/100/200,
       weekly low) — prevents firing on mid-range daily bar clusters that aren't
       real support.

    Uses the nearest qualifying zone so the alert references the correct level.
    """
    if not daily_double_bottoms or intraday_bars.empty:
        return None

    if len(intraday_bars) < 3:
        return None

    last_bar = intraday_bars.iloc[-1]
    last_close = float(last_bar["Close"])
    last_low = float(last_bar["Low"])

    # Find the nearest double-bottom zone to the current price
    best_zone: dict | None = None
    best_distance = float("inf")

    for zone in daily_double_bottoms:
        level = zone["level"]
        if level <= 0:
            continue

        # How close is bar low to the zone?
        proximity = abs(last_low - level) / level
        if proximity > DAILY_DB_INTRADAY_PROXIMITY_PCT:
            continue

        # Must close above zone level (bounce confirmed)
        if last_close <= level:
            continue

        # Stale guard: price can't have run too far above zone (tighter for crypto)
        _is_crypto = symbol.endswith("-USD")
        _max_dist = DAILY_DB_MAX_DISTANCE_CRYPTO_PCT if _is_crypto else DAILY_DB_MAX_DISTANCE_PCT
        distance_above = (last_close - level) / level
        if distance_above > _max_dist:
            continue

        # Not making a lower low — reject descending lows
        if last_low < level * (1 - DAILY_DB_INTRADAY_PROXIMITY_PCT):
            continue

        if proximity < best_distance:
            best_distance = proximity
            best_zone = zone

    if best_zone is None:
        return None

    level = best_zone["level"]
    zone_high = best_zone["zone_high"]
    touch_count = best_zone["touch_count"]

    # ── Structural support proximity check ──────────────────────────────
    # The double bottom zone must be within 1.5% of a key structural level.
    # This prevents firing on mid-range daily bar clusters ($180 on NVDA
    # when real support is $171-175, or $253 on AAPL when support is $249).
    _STRUCT_PROXIMITY_PCT = 0.015  # 1.5%
    _near_structural_support = False
    _structural_level_name = ""

    if prior_day:
        _struct_levels = [
            ("PDL", prior_day.get("low", 0)),
            ("MA50", prior_day.get("ma50", 0)),
            ("MA100", prior_day.get("ma100", 0)),
            ("MA200", prior_day.get("ma200", 0)),
            ("EMA50", prior_day.get("ema50", 0)),
            ("EMA100", prior_day.get("ema100", 0)),
            ("EMA200", prior_day.get("ema200", 0)),
            ("Week Low", prior_day.get("prior_week_low", 0)),
        ]
        for name, val in _struct_levels:
            if val and val > 0:
                dist = abs(level - val) / val
                if dist <= _STRUCT_PROXIMITY_PCT:
                    _near_structural_support = True
                    _structural_level_name = name
                    break

    # Also check: is the zone near today's session low?
    session_low = float(intraday_bars["Low"].min())
    if session_low > 0 and abs(level - session_low) / session_low <= _STRUCT_PROXIMITY_PCT:
        _near_structural_support = True
        _structural_level_name = _structural_level_name or "Session Low"

    if not _near_structural_support:
        logger.info(
            "%s: multi_day_double_bottom at $%.2f REJECTED — not near any "
            "structural support (PDL, MA, weekly low, session low)",
            symbol, level,
        )
        return None

    # Entry/Stop/Targets
    entry = level
    stop = round(level * (1 - DAILY_DB_STOP_OFFSET_PCT), 2)
    risk = entry - stop
    if risk <= 0:
        return None

    target_1 = round(entry + risk, 2)
    target_2 = round(entry + 2 * risk, 2)

    # Confidence: high for 3+ touches or volume exhaustion; medium for 2 touches
    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0
    if touch_count >= 3 or vol_ratio < 0.8:
        confidence = "high"
    else:
        confidence = "medium"

    zone_label = (
        f"${level:.2f}" if level == zone_high
        else f"${level:.2f}–${zone_high:.2f}"
    )

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MULTI_DAY_DOUBLE_BOTTOM,
        direction="BUY",
        price=last_close,
        entry=round(entry, 2),
        stop=stop,
        target_1=target_1,
        target_2=target_2,
        confidence=confidence,
        message=(
            f"Multi-day double bottom — zone {zone_label} tested "
            f"{touch_count}x across daily bars, bounce at ${last_close:.2f}"
            f" | Confirmed by {_structural_level_name} support"
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
# First Hour Close Summary (NOTICE — fires once per symbol after first hour)
# ---------------------------------------------------------------------------


def check_first_hour_summary(
    symbol: str,
    intraday_bars: pd.DataFrame,
    prior_day: dict | None,
    fired_today: set[tuple[str, str]] | None = None,
) -> AlertSignal | None:
    """Summarise the first hour of trading after it closes.

    Fires once per symbol per session when we have >= 13 bars (12 bars =
    60 min at 5-min cadence, plus 1 confirmation bar).

    Computes:
    - Direction (bullish / bearish / flat) from first-hour open vs close
    - First-hour range as % of open
    - Close position within the range (strong / weak / mid finish)
    - Volume vs rest-of-day average (when available)
    """
    if prior_day is None:
        return None

    if intraday_bars is None or len(intraday_bars) < 13:
        return None

    # Dedup — only fire once per session
    if fired_today and (symbol, AlertType.FIRST_HOUR_SUMMARY.value) in fired_today:
        return None

    first_hour = intraday_bars.iloc[:12]
    fh_open = first_hour["Open"].iloc[0]
    fh_close = first_hour["Close"].iloc[-1]
    fh_high = first_hour["High"].max()
    fh_low = first_hour["Low"].min()

    if fh_open <= 0:
        return None

    # Direction
    change_pct = (fh_close - fh_open) / fh_open * 100
    if change_pct > 0.1:
        direction_label = "BULLISH"
    elif change_pct < -0.1:
        direction_label = "BEARISH"
    else:
        direction_label = "FLAT"

    # Range as % of open
    fh_range = fh_high - fh_low
    range_pct = fh_range / fh_open * 100

    # Close position in range (0 = at low, 1 = at high)
    if fh_range > 0:
        close_position = (fh_close - fh_low) / fh_range
    else:
        close_position = 0.5

    if close_position >= 0.7:
        finish = "strong finish (near high)"
    elif close_position <= 0.3:
        finish = "weak finish (near low)"
    else:
        finish = "mid-range finish"

    # Volume context: first-hour avg vs overall avg
    fh_avg_vol = first_hour["Volume"].mean()
    overall_avg_vol = intraday_bars["Volume"].mean()
    vol_note = ""
    if overall_avg_vol > 0:
        vol_ratio = fh_avg_vol / overall_avg_vol
        if vol_ratio >= 1.5:
            vol_note = " | heavy volume"
        elif vol_ratio <= 0.6:
            vol_note = " | light volume"

    # Key levels touched
    level_tags = []
    prior_high = prior_day.get("high", 0)
    prior_low = prior_day.get("low", 0)
    if prior_high and fh_high >= prior_high:
        level_tags.append("touched prior high")
    if prior_low and fh_low <= prior_low:
        level_tags.append("touched prior low")

    ma20 = prior_day.get("ma20")
    ma50 = prior_day.get("ma50")
    for ma_val, ma_name in [(ma20, "20MA"), (ma50, "50MA")]:
        if ma_val and fh_low <= ma_val <= fh_high:
            level_tags.append(f"{ma_name} in range")

    levels_str = f" | {', '.join(level_tags)}" if level_tags else ""

    message = (
        f"First hour close: {direction_label} ({change_pct:+.1f}%) "
        f"| range {range_pct:.1f}% | {finish}{vol_note}{levels_str}"
    )

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.FIRST_HOUR_SUMMARY,
        direction="NOTICE",
        price=fh_close,
        confidence="info",
        message=message,
    )


# ---------------------------------------------------------------------------
# Rule 16: Planned Level Touch (BUY)
# ---------------------------------------------------------------------------


def check_planned_level_touch(
    symbol: str,
    bars: pd.DataFrame,
    plan: dict | None,
    today_open: float = 0,
) -> AlertSignal | None:
    """Price touches the Scanner's daily plan levels and bounces — potential BUY entry.

    Uses the daily plan from the DB (single source of truth computed by Scanner)
    instead of recalculating levels from prior_day.

    Scans last MA_BOUNCE_LOOKBACK_BARS bars for a touch near plan levels.

    Conditions:
    1. A daily plan exists for this symbol
    2. Any recent bar low within BUY_ZONE_PROXIMITY_PCT of a plan level
    3. Last bar close >= that level (bounce/hold confirmed)
    4. Risk > 0
    """
    if plan is None:
        return None
    if bars.empty:
        return None

    entry = plan.get("entry") or 0
    stop = plan.get("stop") or 0
    support = plan.get("support") or 0
    target_1 = plan.get("target_1") or 0
    target_2 = plan.get("target_2") or 0
    pattern = plan.get("pattern", "normal")

    # Skip stale plan on significant gap-down: if plan entry is far above
    # today's open (>2%), it's overhead resistance, not a buy level.
    if today_open > 0 and entry > today_open * 1.02:
        return None

    # Check each level for proximity — entry and support are the primary BUY zone levels
    levels_to_check = []
    if entry > 0:
        levels_to_check.append((entry, "entry"))
    if support > 0 and support != entry:
        levels_to_check.append((support, plan.get("support_label", "support")))

    if not levels_to_check:
        return None

    # Scan lookback window for a touch near any plan level
    lookback = bars.tail(MA_BOUNCE_LOOKBACK_BARS)
    last_bar = bars.iloc[-1]
    bar_close = last_bar["Close"]

    touched_level = None
    touched_label = None

    for lvl, label in levels_to_check:
        # Last bar must close at or above the level (bounce confirmed)
        if bar_close < lvl:
            continue
        # Scan lookback for any bar that touched the level
        for _, row in lookback.iterrows():
            proximity = abs(row["Low"] - lvl) / lvl
            if proximity <= BUY_ZONE_PROXIMITY_PCT:
                if touched_level is None or abs(row["Low"] - lvl) < abs(row["Low"] - (touched_level or 0)):
                    touched_level = lvl
                    touched_label = label
                break  # found a touch for this level

    if touched_level is None:
        return None

    # When the touch is on the support level (not the plan entry), override
    # entry/stop — the plan entry may be a breakout level far above price.
    if touched_label != "entry":
        entry = round(touched_level, 2)
        stop = round(touched_level * (1 - BUY_ZONE_PROXIMITY_PCT), 2)

    if entry <= 0 or stop <= 0:
        return None

    capped_stop = _cap_risk(entry, stop, symbol=symbol)
    risk = entry - capped_stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.PLANNED_LEVEL_TOUCH,
        direction="BUY",
        price=bar_close,
        entry=round(entry, 2),
        stop=round(capped_stop, 2),
        target_1=round(target_1, 2) if target_1 > 0 else None,
        target_2=round(target_2, 2) if target_2 > 0 else None,
        confidence="high",
        message=(
            f"Planned level touch ({pattern}) — "
            f"price at {touched_label} ${touched_level:.2f}, "
            f"entry=${entry:.2f}, T1=${target_1:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# Rule 17: Weekly Level Touch (BUY)
# ---------------------------------------------------------------------------


def check_weekly_level_touch(
    symbol: str,
    bars: pd.DataFrame,
    prior_day: dict,
) -> AlertSignal | None:
    """Price touches prior week low and bounces — bullish entry at institutional level.

    Scans last MA_BOUNCE_LOOKBACK_BARS bars for a touch near prior week low
    (same lookback window as MA bounce rules).

    Conditions:
    1. prior_week_high and prior_week_low available and > 0
    2. Weekly range > 0
    3. Any recent bar low within WEEKLY_LEVEL_PROXIMITY_PCT of prior_week_low
    4. Last bar close > prior_week_low (bounce confirmed)
    5. Risk > 0 (after _cap_risk)
    """
    pw_high = prior_day.get("prior_week_high")
    pw_low = prior_day.get("prior_week_low")
    if pw_high is None or pw_low is None:
        return None
    if pw_high <= 0 or pw_low <= 0:
        return None
    if bars.empty:
        return None

    weekly_range = pw_high - pw_low
    if weekly_range <= 0:
        return None

    # Scan lookback window for a touch near prior week low
    lookback = bars.tail(MA_BOUNCE_LOOKBACK_BARS)
    touched = False
    for _, row in lookback.iterrows():
        prox = abs(row["Low"] - pw_low) / pw_low
        if prox <= WEEKLY_LEVEL_PROXIMITY_PCT:
            touched = True
            break

    if not touched:
        return None

    last_bar = bars.iloc[-1]
    if last_bar["Close"] <= pw_low:
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
        direction="BUY",
        price=last_bar["Close"],
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
# Rule 18: Hourly Resistance Approach (SELL)
# ---------------------------------------------------------------------------


def check_hourly_resistance_approach(
    symbol: str,
    bar: pd.Series,
    hourly_resistance: list[float],
    has_active_entry: bool,
    prior_close: float | None = None,
) -> AlertSignal | None:
    """Active trade approaching hourly swing high resistance — tighten or take profits.

    Conditions:
    - has_active_entry is True
    - At least one hourly resistance level exists above current price
    - Bar high within HOURLY_RESISTANCE_APPROACH_PCT of an hourly resistance level
    - Prior close was BELOW the level (approaching from below = resistance)
      If prior close was above, the level is support, not resistance — skip.
    """
    if not has_active_entry or not hourly_resistance:
        return None

    # Find nearest hourly resistance at or above bar high
    for level in sorted(hourly_resistance):
        if level < bar["High"]:
            continue
        # Direction check: if prior close was above this level, price is
        # falling into it — the level is acting as support, not resistance.
        if prior_close is not None and prior_close > level:
            break
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
# SHORT Rule: Hourly Resistance Rejection
# ---------------------------------------------------------------------------


def check_hourly_resistance_rejection_short(
    symbol: str,
    bars: pd.DataFrame,
    hourly_resistance: list[float],
    prior_close: float | None = None,
) -> AlertSignal | None:
    """Price rallies into hourly horizontal resistance and gets rejected — SHORT.

    Unlike EMA rejection (diagonal levels), this detects rejection off horizontal
    supply zones where sellers repeatedly step in.

    Conditions:
    1. At least 12 bars (60 min into session)
    2. Bar high reaches within HOURLY_RES_REJECTION_PROXIMITY_PCT of an hourly resistance level
    3. Bar closes in lower 40% of its range (rejection candle confirmed)
    4. Price must be BELOW the resistance (approaching from below)
    5. Prior close was below the level (not falling into it from above)
    """
    if bars.empty or len(bars) < HOURLY_RES_REJECTION_MIN_BARS or not hourly_resistance:
        return None

    last_bar = bars.iloc[-1]
    last_close = float(last_bar["Close"])
    last_high = float(last_bar["High"])
    last_low = float(last_bar["Low"])
    bar_range = last_high - last_low

    if bar_range <= 0:
        return None

    # Close must be in lower 40% of range (selling pressure = rejection)
    if (last_close - last_low) / bar_range > HOURLY_RES_REJECTION_CLOSE_PCT:
        return None

    # Find nearest hourly resistance at or above current price
    for level in sorted(hourly_resistance):
        if level <= 0 or level < last_close:
            continue

        # Direction guard: if prior close was above this level, price is
        # falling into it — the level is support, not resistance. Skip.
        if prior_close is not None and prior_close > level:
            continue

        # Bar high must have reached near the resistance (within proximity)
        proximity = abs(last_high - level) / level
        if proximity > HOURLY_RES_REJECTION_PROXIMITY_PCT:
            continue

        # Rejection confirmed
        entry = round(last_close, 2)
        stop = round(level * (1 + HOURLY_RES_REJECTION_STOP_OFFSET_PCT), 2)
        risk = stop - entry
        if risk <= 0:
            continue

        target_1 = round(entry - risk, 2)
        target_2 = round(entry - 2 * risk, 2)

        return AlertSignal(
            symbol=symbol,
            alert_type=AlertType.HOURLY_RESISTANCE_REJECTION_SHORT,
            direction="SHORT",
            price=last_close,
            entry=entry,
            stop=stop,
            target_1=target_1,
            target_2=target_2,
            confidence="medium",
            message=(
                f"HOURLY RESISTANCE REJECTION at ${level:.2f}"
                f" — rallied to ${last_high:.2f}, rejected and closed ${last_close:.2f}"
            ),
        )

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
        # Direction check: if prior close was ABOVE this MA, price is falling
        # into it — the MA is acting as SUPPORT, not resistance.  Skip.
        if prior_close is not None and prior_close > ma_val:
            continue
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
    prior_close: float | None = None,
    today_open: float | None = None,
) -> AlertSignal | None:
    """Price rallies up to prior day low from below and gets rejected.

    Conditions:
    - prior_day_low > 0
    - Direction: price must be trading BELOW prior day low.
      Either prior close was already below, OR today gapped down below it.
    - Bar high within RESISTANCE_PROXIMITY_PCT of prior day low
    - Bar close below prior day low (rejection confirmed)
    """
    if prior_day_low <= 0:
        return None
    # Direction check: PDL is resistance when price is below it.
    # True when prior close was already below OR today gapped below.
    gapped_below = today_open is not None and today_open < prior_day_low
    closed_below = prior_close is not None and prior_close < prior_day_low
    if not gapped_below and not closed_below:
        return None
    proximity = abs(bar["High"] - prior_day_low) / prior_day_low
    if proximity > RESISTANCE_PROXIMITY_PCT:
        return None
    if bar["Close"] >= prior_day_low:
        return None  # reclaimed = not rejection
    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.RESISTANCE_PRIOR_LOW,
        direction="NOTICE",
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
        "prior close": prior_day.get("close"),
        "prior low": prior_day.get("low"),  # PDL as resistance when buying below it
        "MA20": prior_day.get("ma20"),
        "MA50": prior_day.get("ma50"),
        "MA100": prior_day.get("ma100"),
        "MA200": prior_day.get("ma200"),
        "EMA20": prior_day.get("ema20"),
        "EMA50": prior_day.get("ema50"),
        "EMA100": prior_day.get("ema100"),
        "prior week high": prior_day.get("prior_week_high"),
        "prior month high": prior_day.get("prior_month_high"),
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

    # When buying from below VWAP, VWAP is the natural T1 regardless of R:R.
    # It's the first resistance to clear and where sellers often step in.
    vwap_t1 = None
    if current_vwap and current_vwap > entry and current_vwap < min_target:
        vwap_t1 = current_vwap

    # T1 = VWAP (if below it) or first level >= min_target
    t1 = None
    t1_label = ""
    if vwap_t1:
        t1 = vwap_t1
        t1_label = "VWAP"
    else:
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
# MA defense / rejection context
# ---------------------------------------------------------------------------

MA_CONTEXT_BAND_PCT = 0.005  # 0.5% proximity threshold


def _detect_ma_context(
    price: float,
    ma20: float | None,
    ma50: float | None,
    ma100: float | None,
    ma200: float | None,
    ema20: float | None,
    ema50: float | None,
    ema100: float | None,
) -> tuple[str, str]:
    """Detect which MA price is defending (support) and rejected by (resistance).

    Returns (defending: str, rejected_by: str).
    Defending: nearest MA within 0.5% BELOW price.
    Rejected: nearest MA within 0.5% ABOVE price.
    """
    if price <= 0:
        return "", ""

    candidates = [
        ("20MA", ma20), ("50MA", ma50), ("100MA", ma100), ("200MA", ma200),
        ("20EMA", ema20), ("50EMA", ema50), ("100EMA", ema100),
    ]

    defending = ""
    defending_dist = float("inf")
    rejected_by = ""
    rejected_dist = float("inf")

    for label, ma in candidates:
        if ma is None or ma <= 0:
            continue
        pct_diff = (price - ma) / price
        if 0 < pct_diff <= MA_CONTEXT_BAND_PCT:
            # MA is below price (potential support / defending)
            if pct_diff < defending_dist:
                defending_dist = pct_diff
                defending = label
        elif 0 < -pct_diff <= MA_CONTEXT_BAND_PCT:
            # MA is above price (potential resistance / rejection)
            abs_diff = -pct_diff
            if abs_diff < rejected_dist:
                rejected_dist = abs_diff
                rejected_by = label

    return defending, rejected_by


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


def _score_alert_v2(
    sig: AlertSignal,
    ma20: float | None,
    ma50: float | None,
    close: float,
    vol_ratio: float,
) -> tuple[int, dict]:
    """Signal-type-aware score (0-100) with factor breakdown.

    For bounce/dip-buy signals, adjusts MA position and VWAP factors to
    reflect that being below MAs and VWAP is *expected* (mean-reversion).
    Adds R:R bonus when T1 reward/risk >= threshold.
    For breakout signals, identical to v1 (plus R:R bonus).

    Returns (score, factors_dict) where factors_dict maps component names
    to their point contributions.
    """
    alert_type_str = sig.alert_type.value
    is_bounce = alert_type_str in BOUNCE_ALERT_TYPES
    is_ma_bounce = alert_type_str in MA_BOUNCE_ALERT_TYPES

    factors: dict[str, int] = {}
    score = 0

    # --- MA position (25) ---
    above_20 = ma20 is not None and close > ma20
    above_50 = ma50 is not None and close > ma50
    if is_ma_bounce:
        ma_pts = 25
    elif is_bounce:
        ma_pts = 25 if (above_20 and above_50) else (15 if (above_20 or above_50) else 10)
    else:
        ma_pts = 25 if (above_20 and above_50) else (15 if (above_20 or above_50) else 0)
    factors["ma"] = ma_pts
    score += ma_pts

    # --- Volume (25): same as v1 ---
    vol_pts = 25 if vol_ratio >= 1.2 else (15 if vol_ratio >= 0.8 else 5)
    factors["vol"] = vol_pts
    score += vol_pts

    # --- Confidence (25): same as v1 ---
    conf_pts = 25 if sig.confidence == "high" else 15
    factors["conf"] = conf_pts
    score += conf_pts

    # --- VWAP alignment (25) ---
    vwap_aligned = (
        (sig.direction == "BUY" and sig.vwap_position == "above VWAP")
        or (sig.direction == "SHORT" and sig.vwap_position == "below VWAP")
    )
    if vwap_aligned:
        vwap_pts = 25
    elif is_bounce:
        vwap_pts = 15
    else:
        vwap_pts = 10
    factors["vwap"] = vwap_pts
    score += vwap_pts

    # --- R:R bonus (BUY entries only) ---
    rr_pts = 0
    if (
        sig.direction == "BUY"
        and sig.entry is not None
        and sig.stop is not None
        and sig.target_1 is not None
    ):
        risk = sig.entry - sig.stop
        if risk > 0:
            reward = sig.target_1 - sig.entry
            if reward / risk >= SCORE_V2_RR_BONUS_THRESHOLD:
                rr_pts = SCORE_V2_RR_BONUS_POINTS
    if rr_pts:
        factors["rr"] = rr_pts
        score += rr_pts

    return min(100, score), factors


# ---------------------------------------------------------------------------
# Professional rules — MACD Histogram Flip
# ---------------------------------------------------------------------------


def _compute_macd(bars: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Compute MACD line, signal line, and histogram from close prices."""
    close = bars["Close"]
    ema_fast = close.ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow = close.ewm(span=MACD_SLOW, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def check_macd_histogram_flip(
    symbol: str,
    bars: pd.DataFrame,
    prior_day: dict | None,
) -> AlertSignal | None:
    """MACD histogram flips from negative to positive → bullish momentum shift.

    Conditions:
    - At least MACD_SLOW + MACD_SIGNAL bars available
    - Previous histogram bar was negative
    - Current histogram bar is positive (flip)
    - Close above prior close (confirmation)
    """
    min_bars = MACD_SLOW + MACD_SIGNAL
    if len(bars) < min_bars:
        return None

    _, _, histogram = _compute_macd(bars)
    if len(histogram) < 2:
        return None

    prev_hist = histogram.iloc[-2]
    curr_hist = histogram.iloc[-1]

    # Flip: negative → positive
    if prev_hist >= 0 or curr_hist <= 0:
        return None

    last_bar = bars.iloc[-1]
    prior_close = prior_day.get("close", 0) if prior_day else 0
    if prior_close > 0 and last_bar["Close"] <= prior_close:
        return None  # no bullish confirmation

    price = last_bar["Close"]
    # Use session low as stop, 1R/2R targets
    session_low = bars["Low"].min()
    entry = round(price, 2)
    stop = round(session_low * 0.998, 2)  # 0.2% below session low
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MACD_HISTOGRAM_FLIP,
        direction="BUY",
        price=price,
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high" if curr_hist > abs(prev_hist) else "medium",
        message=(
            f"MACD histogram flip — momentum turning bullish "
            f"(hist {prev_hist:.4f} → {curr_hist:.4f})"
        ),
    )


# ---------------------------------------------------------------------------
# Professional rules — Bollinger Band Squeeze & Breakout
# ---------------------------------------------------------------------------


def check_bb_squeeze_breakout(
    symbol: str,
    bars: pd.DataFrame,
) -> AlertSignal | None:
    """BB width contracts to squeeze, then close breaks above upper band → BUY.

    Conditions:
    - At least BB_PERIOD + BB_SQUEEZE_LOOKBACK bars available
    - BB width is in bottom BB_SQUEEZE_PERCENTILE of recent lookback
    - Close is above upper Bollinger Band
    """
    min_bars = BB_PERIOD + BB_SQUEEZE_LOOKBACK
    if len(bars) < min_bars:
        return None

    close = bars["Close"]
    sma = close.rolling(BB_PERIOD).mean()
    std = close.rolling(BB_PERIOD).std()
    upper = sma + BB_STD_DEV * std
    lower = sma - BB_STD_DEV * std
    width = (upper - lower) / sma  # normalized bandwidth

    if width.iloc[-1] is None or pd.isna(width.iloc[-1]):
        return None

    # Check squeeze: current width in bottom percentile of lookback
    recent_widths = width.iloc[-BB_SQUEEZE_LOOKBACK:]
    threshold = recent_widths.quantile(BB_SQUEEZE_PERCENTILE / 100.0)
    if width.iloc[-1] > threshold:
        return None  # not in squeeze

    last_bar = bars.iloc[-1]
    upper_val = upper.iloc[-1]
    middle_val = sma.iloc[-1]
    if pd.isna(upper_val) or pd.isna(middle_val):
        return None

    # Close must break above upper band
    if last_bar["Close"] <= upper_val:
        return None

    entry = round(upper_val, 2)
    stop = round(middle_val, 2)  # middle band as stop
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.BB_SQUEEZE_BREAKOUT,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high",
        message=(
            f"Bollinger squeeze breakout — bandwidth at "
            f"{width.iloc[-1]:.4f} (squeeze), close above upper band "
            f"${upper_val:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# Professional rules — ATR-Based Dynamic Stops
# ---------------------------------------------------------------------------


def compute_atr(bars: pd.DataFrame, period: int = ATR_PERIOD) -> float | None:
    """Compute Average True Range over the given period."""
    if len(bars) < period + 1:
        return None
    high = bars["High"]
    low = bars["Low"]
    close = bars["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    val = atr.iloc[-1]
    return float(val) if not pd.isna(val) else None


def atr_adjusted_stop(entry: float, atr: float | None, symbol: str | None = None) -> float:
    """Return ATR-based stop if USE_ATR_STOPS is True and ATR is available.

    Falls back to fixed % stop from _cap_risk() when ATR is unavailable.
    """
    if not USE_ATR_STOPS or atr is None or atr <= 0:
        rate = PER_SYMBOL_RISK.get(symbol, DAY_TRADE_MAX_RISK_PCT) if symbol else DAY_TRADE_MAX_RISK_PCT
        return round(entry * (1 - rate), 2)
    return round(entry - atr * ATR_DAY_TRADE_MULTIPLIER, 2)


# ---------------------------------------------------------------------------
# Professional rules — Trailing Stop
# ---------------------------------------------------------------------------


def check_trailing_stop_hit(
    symbol: str,
    bar: pd.Series,
    trailing_stop_level: float,
) -> AlertSignal | None:
    """Fire when bar low breaches the trailing stop level.

    The trailing stop level is computed externally (highest high - ATR * multiplier)
    and passed in from the caller.
    """
    if not ENABLE_TRAILING_STOPS or trailing_stop_level <= 0:
        return None
    if bar["Low"] > trailing_stop_level:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.TRAILING_STOP_HIT,
        direction="SELL",
        price=bar["Close"],
        message=(
            f"Trailing stop hit — low ${bar['Low']:.2f} breached "
            f"trail ${trailing_stop_level:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# Professional rules — Gap-and-Go
# ---------------------------------------------------------------------------


def check_gap_and_go(
    symbol: str,
    bars: pd.DataFrame,
    prior_close: float | None,
    bar_vol: float,
    avg_vol: float,
) -> AlertSignal | None:
    """Gap up >1% + first-bar volume >2x avg → momentum continuation BUY.

    Conditions:
    - Gap up >= GAP_AND_GO_MIN_PCT
    - First 5-min bar volume >= GAP_AND_GO_VOLUME_RATIO * average
    - Current bar (latest) closes above the gap open
    """
    if bars.empty or prior_close is None or prior_close <= 0:
        return None

    today_open = bars["Open"].iloc[0]
    gap_pct = (today_open - prior_close) / prior_close
    if gap_pct < GAP_AND_GO_MIN_PCT:
        return None

    # First bar volume confirmation
    first_bar_vol = bars["Volume"].iloc[0]
    if avg_vol <= 0 or first_bar_vol < GAP_AND_GO_VOLUME_RATIO * avg_vol:
        return None

    last_bar = bars.iloc[-1]
    # Must still be above the gap open (not a gap-and-fade)
    if last_bar["Close"] <= today_open:
        return None

    entry = round(today_open, 2)
    stop = round(prior_close, 2)  # stop at gap fill
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.GAP_AND_GO,
        direction="BUY",
        price=last_bar["Close"],
        entry=entry,
        stop=stop,
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high" if gap_pct >= 0.02 else "medium",
        message=(
            f"Gap-and-Go — gap up {gap_pct:.1%} with {first_bar_vol / avg_vol:.1f}x "
            f"volume on first bar. Momentum continuation."
        ),
    )


# ---------------------------------------------------------------------------
# Professional rules — Fibonacci Retracement Bounce
# ---------------------------------------------------------------------------


def check_fib_retracement_bounce(
    symbol: str,
    bar: pd.Series,
    prior_high: float,
    prior_low: float,
) -> AlertSignal | None:
    """Bar low touches 50% or 61.8% fib retracement of prior day range and bounces.

    Conditions:
    - Prior range is meaningful (> 0)
    - Bar low within FIB_BOUNCE_PROXIMITY_PCT of a key fib level (50% or 61.8%)
    - Bar closes above the fib level (bounce confirmed)
    """
    if prior_high <= prior_low or prior_high <= 0:
        return None

    swing_range = prior_high - prior_low
    # Require meaningful range (at least 3% of price) to avoid noise on tiny ranges
    if swing_range / prior_high < 0.03:
        return None

    for fib_pct in FIB_LEVELS:
        # Fib levels measured as retracement from high
        fib_level = prior_high - swing_range * fib_pct
        if fib_level <= 0:
            continue

        proximity = abs(bar["Low"] - fib_level) / fib_level
        if proximity > FIB_BOUNCE_PROXIMITY_PCT:
            continue

        # Must bounce: close above the fib level
        if bar["Close"] <= fib_level:
            continue

        entry = round(fib_level, 2)
        # Stop below next fib level or prior low
        next_fibs = [prior_high - swing_range * f for f in FIB_LEVELS if f > fib_pct]
        stop_level = next_fibs[0] if next_fibs else prior_low
        stop = round(stop_level * 0.998, 2)  # small buffer
        risk = entry - stop
        if risk <= 0:
            continue

        fib_label = f"{fib_pct:.1%}"
        confidence = "high" if fib_pct >= 0.5 else "medium"

        return AlertSignal(
            symbol=symbol,
            alert_type=AlertType.FIB_RETRACEMENT_BOUNCE,
            direction="BUY",
            price=bar["Close"],
            entry=entry,
            stop=stop,
            target_1=round(entry + risk, 2),
            target_2=round(entry + 2 * risk, 2),
            confidence=confidence,
            message=(
                f"Fibonacci {fib_label} retracement bounce — "
                f"low ${bar['Low']:.2f} touched fib ${fib_level:.2f}, "
                f"bounced to ${bar['Close']:.2f}"
            ),
        )

    return None


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

        # Use the BEST (lowest) entry from all signals — first touch is best entry
        best_entry = primary.entry
        best_stop = primary.stop
        for s in others:
            if s.entry and best_entry and s.entry < best_entry:
                best_entry = s.entry
            if s.stop and best_stop and s.stop < best_stop:
                best_stop = s.stop
        if best_entry and best_entry < (primary.entry or float("inf")):
            primary.entry = best_entry
            primary.stop = best_stop
            # Recalculate targets from better entry
            risk = primary.entry - primary.stop if primary.stop else 0
            if risk > 0:
                primary.target_1 = round(primary.entry + risk, 2)
                primary.target_2 = round(primary.entry + 2 * risk, 2)

        # Boost score (v1 and v2)
        boost = min(len(others) * CONSOLIDATION_SCORE_BOOST, CONSOLIDATION_MAX_BOOST)
        primary.score = min(100, primary.score + boost)
        primary.score_v2 = min(100, primary.score_v2 + boost)
        if boost and primary.score_factors is not None:
            primary.score_factors["consolidation"] = boost

        # Recalculate score labels
        primary.score_label = (
            "Strong" if primary.score >= 80
            else "Moderate" if primary.score >= 60
            else "Weak" if primary.score >= 40
            else "Caution"
        )
        primary.score_v2_label = (
            "Strong" if primary.score_v2 >= 80
            else "Moderate" if primary.score_v2 >= 60
            else "Weak" if primary.score_v2 >= 40
            else "Caution"
        )

        # Append confirming signal types to message
        types = [s.alert_type.value.replace("_", " ").title() for s in others]
        primary.message += f" [+{len(others)} confirming: {', '.join(types)}]"

        result.append(primary)

    return result


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def _compute_crypto_opening_range(bars: pd.DataFrame) -> dict | None:
    """Compute opening range for crypto from the first 6 bars of the day.

    Uses the same dict format as compute_opening_range() so downstream ORB
    rules work identically.
    """
    if bars.empty or len(bars) < 6:
        return None
    first_6 = bars.iloc[:6]
    or_high = first_6["High"].max()
    or_low = first_6["Low"].min()
    or_range = or_high - or_low
    or_range_pct = or_range / or_low if or_low > 0 else 0.0
    return {
        "or_high": or_high,
        "or_low": or_low,
        "or_range": or_range,
        "or_range_pct": or_range_pct,
        "or_complete": True,
    }


def detect_hourly_consolidation_break(
    bars_5m: pd.DataFrame,
) -> dict | None:
    """Detect hourly consolidation range breakout from 5-min bars.

    Resamples 5-min bars to 1-hour, checks if recent hourly bars
    formed a tight range (< 1.2x hourly ATR), and if the current bar
    breaks out.

    Uses ATR-based threshold instead of fixed % — adapts to each
    symbol's volatility and current market regime.

    Returns dict with:
      direction: "UP", "DOWN", or "RANGE"
      status: "breakout" or "consolidating"
      range_high: float
      range_low: float
      range_pct: float (% width)
      break_price: float
      hourly_atr: float (for logging)
    Or None if no consolidation detected.
    """
    from alert_config import (
        HOURLY_CONSOL_ATR_LOOKBACK, HOURLY_CONSOL_ATR_MULT,
        HOURLY_CONSOL_MAX_RANGE_PCT, HOURLY_CONSOL_MIN_BARS,
    )

    if bars_5m.empty or len(bars_5m) < 12 * (HOURLY_CONSOL_MIN_BARS + 1):
        return None

    # Resample 5-min bars to 1-hour
    hourly = bars_5m.resample("1h").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }).dropna()

    if len(hourly) < HOURLY_CONSOL_MIN_BARS + 1:
        return None

    # Compute hourly ATR (true range = High - Low for intraday)
    hourly_tr = hourly["High"] - hourly["Low"]
    atr_bars = min(len(hourly) - 1, HOURLY_CONSOL_ATR_LOOKBACK)
    if atr_bars < 2:
        return None
    hourly_atr = hourly_tr.iloc[-(atr_bars + 1):-1].mean()
    if hourly_atr <= 0:
        return None

    # Check if the prior N hourly bars form a tight range
    consol_window = hourly.iloc[-(HOURLY_CONSOL_MIN_BARS + 1):-1]
    range_high = consol_window["High"].max()
    range_low = consol_window["Low"].min()
    if range_low <= 0:
        return None

    range_width = range_high - range_low
    range_pct = range_width / range_low
    atr_threshold = hourly_atr * HOURLY_CONSOL_ATR_MULT

    # ATR-based check: range must be tighter than 1.2x ATR
    if range_width > atr_threshold:
        return None  # range too wide relative to recent volatility

    # Absolute cap: safety net for extreme cases
    if range_pct > HOURLY_CONSOL_MAX_RANGE_PCT:
        return None  # range too wide in absolute terms

    # Check current hourly bar for breakout
    current = hourly.iloc[-1]
    base = {
        "range_high": round(range_high, 2),
        "range_low": round(range_low, 2),
        "range_pct": round(range_pct * 100, 2),
        "break_price": round(float(current["Close"]), 2),
        "hourly_atr": round(float(hourly_atr), 2),
    }

    if current["Close"] > range_high:
        return {"direction": "UP", "status": "breakout", **base}
    elif current["Close"] < range_low:
        return {"direction": "DOWN", "status": "breakout", **base}

    # Still in range — consolidation forming
    return {"direction": "RANGE", "status": "consolidating", **base}


def compute_spy_gate(spy_bars: pd.DataFrame, spy_vwap: pd.Series | None) -> dict:
    """Compute SPY gate status for BUY alert suppression.

    Returns dict with:
      gate: "green" | "yellow" | "red"
      vwap_dominance: float (0-1, % of recent bars above VWAP)
      above_ema: bool (price above 60-period EMA on 5-min ≈ 20 EMA on 15-min)
      reason: str (human-readable explanation)
    """
    from alert_config import (
        SPY_GATE_LOOKBACK_BARS, SPY_GATE_GREEN_PCT, SPY_GATE_RED_PCT,
        SPY_GATE_EMA_PERIOD,
    )

    result = {"gate": "green", "vwap_dominance": 1.0, "above_ema": True, "hourly_break": None, "reason": ""}

    if spy_bars.empty:
        return result

    # 1. VWAP dominance: % of recent bars closing above VWAP
    if spy_vwap is not None and not spy_vwap.empty:
        lookback = min(SPY_GATE_LOOKBACK_BARS, len(spy_bars))
        recent_closes = spy_bars["Close"].iloc[-lookback:]
        recent_vwap = spy_vwap.iloc[-lookback:]
        if len(recent_closes) == len(recent_vwap) and lookback > 0:
            above = (recent_closes.values > recent_vwap.values).sum()
            result["vwap_dominance"] = above / lookback
        else:
            result["vwap_dominance"] = 0.5  # can't compute, assume neutral

    # 2. Intraday EMA trend (60-bar EMA on 5-min ≈ 20 EMA on 15-min)
    if len(spy_bars) >= SPY_GATE_EMA_PERIOD:
        ema = spy_bars["Close"].ewm(span=SPY_GATE_EMA_PERIOD, adjust=False).mean()
        result["above_ema"] = float(spy_bars["Close"].iloc[-1]) > float(ema.iloc[-1])
    else:
        result["above_ema"] = True  # not enough data, assume neutral

    # 3. Hourly consolidation breakout detection
    from alert_config import HOURLY_CONSOL_ENABLED
    if HOURLY_CONSOL_ENABLED:
        hbreak = detect_hourly_consolidation_break(spy_bars)
        if hbreak:
            result["hourly_break"] = hbreak
            logger.info(
                "Hourly consolidation break: %s (range %.2f%%, high $%.2f, low $%.2f)",
                hbreak["direction"], hbreak["range_pct"],
                hbreak["range_high"], hbreak["range_low"],
            )

    # 4. Determine gate level
    vd = result["vwap_dominance"]
    ae = result["above_ema"]
    hb = result.get("hourly_break")

    # Hourly breakout overrides — highest conviction signal (only on actual breakouts)
    if hb and hb.get("status") == "breakout":
        if hb["direction"] == "UP" and ae:
            result["gate"] = "green"
            result["reason"] = (
                f"HOURLY BREAKOUT UP ${hb['break_price']} "
                f"(range {hb['range_pct']:.1f}%) + above EMA"
            )
            return result
        elif hb["direction"] == "DOWN" and not ae:
            result["gate"] = "red"
            result["reason"] = (
                f"HOURLY BREAKDOWN ${hb['break_price']} "
                f"(range {hb['range_pct']:.1f}%) + below EMA — NO LONGS"
            )
            return result

    # Standard VWAP + EMA gate
    if vd >= SPY_GATE_GREEN_PCT and ae:
        result["gate"] = "green"
        result["reason"] = f"SPY above VWAP ({vd:.0%}) + above 15m EMA"
    elif vd < SPY_GATE_RED_PCT and not ae:
        result["gate"] = "red"
        result["reason"] = f"SPY below VWAP ({vd:.0%}) + below 15m EMA — NO LONGS"
    elif vd < SPY_GATE_RED_PCT or not ae:
        result["gate"] = "yellow"
        result["reason"] = f"SPY mixed — VWAP {vd:.0%}, EMA {'above' if ae else 'below'}"
    else:
        result["gate"] = "yellow"
        result["reason"] = f"SPY neutral — VWAP {vd:.0%}"

    return result


def evaluate_rules(
    symbol: str,
    intraday_bars: pd.DataFrame,
    prior_day: dict | None,
    active_entries: list[dict] | None = None,
    spy_context: dict | None = None,
    auto_stop_entries: dict | None = None,
    is_cooled_down: bool = False,
    fired_today: set[tuple[str, str]] | None = None,
    daily_plan: dict | None = None,
    is_crypto: bool = False,
    spy_gate: dict | None = None,
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
        daily_plan: Dict from get_daily_plan() with Scanner's planned levels.
        is_crypto: If True, use 24h crypto session logic and skip SPY demotion.

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
    ema20 = prior_day.get("ema20")
    ema50 = prior_day.get("ema50")
    ema100 = prior_day.get("ema100")
    ema200 = prior_day.get("ema200")
    prior_close = prior_day.get("close")
    prior_high = prior_day.get("high", 0)
    prior_low = prior_day.get("low", 0)
    # NaN guard: yfinance can return NaN for missing data
    if prior_high is None or (isinstance(prior_high, float) and math.isnan(prior_high)):
        prior_high = 0
    if prior_low is None or (isinstance(prior_low, float) and math.isnan(prior_low)):
        prior_low = 0
    if prior_low > 0:
        logger.debug("%s: prior_low=%.2f prior_high=%.2f", symbol, prior_low, prior_high)
    sym_rsi14 = prior_day.get("rsi14")

    # --- Context filters ---
    spy = spy_context or {}
    spy_trend = spy.get("trend", "neutral")
    if is_crypto:
        phase = get_session_phase_for_symbol(symbol)
        entries_allowed = True  # crypto markets are always open
    else:
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
    if is_crypto:
        opening_range = _compute_crypto_opening_range(intraday_bars)
    else:
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

    # ATR for dynamic stops
    current_atr = compute_atr(intraday_bars)

    # Fetch multi-day 1h bars (used for both hourly resistance and hourly support)
    from analytics.intraday_data import (
        fetch_hourly_bars, detect_hourly_resistance,
        detect_hourly_support, detect_intraday_supports, detect_5m_swing_lows,
    )
    hourly_resistance: list[float] = []
    bars_1h = pd.DataFrame()
    try:
        bars_1h = fetch_hourly_bars(symbol)
        if not bars_1h.empty:
            hourly_resistance = detect_hourly_resistance(bars_1h)
    except Exception:
        pass

    # Detect intraday supports (used by both bounce BUY rule and breakdown SHORT)
    intraday_supports = detect_intraday_supports(intraday_bars)

    # Merge multi-day hourly swing low supports (catches prior-day levels)
    try:
        if not bars_1h.empty:
            for lvl in detect_hourly_support(bars_1h):
                is_dup = any(
                    abs(s["level"] - lvl) / lvl <= 0.003
                    for s in intraday_supports
                ) if intraday_supports else False
                if not is_dup:
                    intraday_supports.append({
                        "level": round(lvl, 2),
                        "touch_count": 1,
                        "hold_hours": 0,
                        "strength": "weak",
                    })
    except Exception:
        pass

    # Merge 5-min swing lows for faster support detection (~15 min vs ~2 hours)
    for sl in detect_5m_swing_lows(intraday_bars):
        is_dup = any(
            abs(s["level"] - sl["level"]) / sl["level"] <= 0.003
            for s in intraday_supports
        ) if intraday_supports else False
        if not is_dup:
            intraday_supports.append(sl)

    # --- BUY rules ---
    spy_regime = spy.get("regime", "CHOPPY")
    caution_notes = []
    if not is_crypto:
        if spy_trend == "bearish":
            caution_notes.append("SPY bearish (below 20MA)")
        if spy_regime == "CHOPPY":
            caution_notes.append(f"SPY regime: {spy_regime}")
        if spy_regime == "TRENDING_DOWN":
            caution_notes.append("SPY TRENDING DOWN — reduced confidence")
    if not entries_allowed:
        caution_notes.append(f"session: {phase}")
    caution_suffix = f" | CAUTION: {', '.join(caution_notes)}" if caution_notes else ""

    # ── Gate 1: Wait 15 min after open before any BUY alerts ──────────────
    # First 15 min (3 bars on 5-min) is opening auction noise — no real
    # price discovery.  SELL/SHORT/NOTICE always pass through.
    # Crypto is exempt (24h market, no opening auction).
    _OPENING_WAIT_BARS = 3  # 3 × 5-min = 15 min
    _in_opening_wait = (
        not is_crypto
        and phase == "opening_range"
        and len(intraday_bars) < _OPENING_WAIT_BARS
    )

    # ── Gate 2: SPY below VWAP = suppress non-SPY equity longs ───────────
    # Simple real-time check: is SPY's current price below its VWAP?
    # If yes, no equity BUY alerts except SPY itself.
    # This replaces the rolling-average vwap_dominance check with an
    # immediate price-vs-VWAP comparison.
    _spy_currently_below_vwap = False
    if (
        not is_crypto
        and symbol != "SPY"
        and spy_gate
    ):
        _spy_vwap_dom = spy_gate.get("vwap_dominance", 1.0)
        _spy_above_ema = spy_gate.get("above_ema", True)
        # SPY below VWAP: dominance < 50% OR gate explicitly red/yellow
        if _spy_vwap_dom < 0.5 or spy_gate.get("gate") == "red":
            _spy_currently_below_vwap = True

    if not is_cooled_down:
        sig = check_ma_bounce_20(symbol, intraday_bars, ma20, ma50)
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

        sig = check_ma_bounce_50(symbol, intraday_bars, ma20, ma50, prior_close)
        if sig:
            sig.message += f" ({phase})"
            if vwap_pos:
                sig.message += f" — price {vwap_pos}"
            sig.message += caution_suffix
            signals.append(sig)

        sig = check_ma_bounce_100(symbol, intraday_bars, ma100, prior_close)
        if sig:
            sig.message += f" ({phase})"
            if vwap_pos:
                sig.message += f" — price {vwap_pos}"
            sig.message += caution_suffix
            signals.append(sig)

        sig = check_ma_bounce_200(symbol, intraday_bars, ma200, prior_close)
        if sig:
            sig.message += f" ({phase})"
            if vwap_pos:
                sig.message += f" — price {vwap_pos}"
            sig.message += caution_suffix
            signals.append(sig)

        # --- EMA Bounces ---
        if AlertType.EMA_BOUNCE_20.value in ENABLED_RULES:
            sig = check_ema_bounce_20(symbol, intraday_bars, ema20, ema50)
            if sig:
                sig.message += f" ({phase})"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        if AlertType.EMA_BOUNCE_50.value in ENABLED_RULES:
            sig = check_ema_bounce_50(symbol, intraday_bars, ema50, ema20, prior_close)
            if sig:
                sig.message += f" ({phase})"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        if AlertType.EMA_BOUNCE_100.value in ENABLED_RULES:
            sig = check_ema_bounce_100(symbol, intraday_bars, ema100, prior_close)
            if sig:
                sig.message += f" ({phase})"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        if AlertType.EMA_BOUNCE_200.value in ENABLED_RULES:
            sig = check_ema_bounce_200(symbol, intraday_bars, ema200, prior_close)
            if sig:
                sig.message += f" ({phase})"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        # --- MA/EMA Approach Notices (heads-up before bounce triggers) ---
        if AlertType.MA_APPROACH.value in ENABLED_RULES:
            _approach_levels = [
                (ma20, MA_APPROACH_PROXIMITY_PCT, MA_BOUNCE_PROXIMITY_PCT, "20MA"),
                (ma50, MA_APPROACH_PROXIMITY_PCT, MA_BOUNCE_PROXIMITY_PCT, "50MA"),
                (ma100, MA100_APPROACH_PROXIMITY_PCT, MA100_BOUNCE_PROXIMITY_PCT, "100MA"),
                (ma200, MA200_APPROACH_PROXIMITY_PCT, MA200_BOUNCE_PROXIMITY_PCT, "200MA"),
                (ema20, MA_APPROACH_PROXIMITY_PCT, MA_BOUNCE_PROXIMITY_PCT, "EMA20"),
                (ema50, MA_APPROACH_PROXIMITY_PCT, MA_BOUNCE_PROXIMITY_PCT, "EMA50"),
                (ema100, MA100_APPROACH_PROXIMITY_PCT, MA100_BOUNCE_PROXIMITY_PCT, "EMA100"),
                (ema200, MA200_APPROACH_PROXIMITY_PCT, MA200_BOUNCE_PROXIMITY_PCT, "EMA200"),
            ]
            for _ma, _approach, _bounce, _label in _approach_levels:
                if _ma:
                    sig = check_ma_approach(symbol, intraday_bars, _ma, _approach, _bounce, _label)
                    if sig:
                        sig.message += f" ({phase})"
                        signals.append(sig)
                        break  # only one approach notice per poll

        if AlertType.PRIOR_DAY_LOW_RECLAIM.value in ENABLED_RULES:
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

        if AlertType.PRIOR_DAY_LOW_BOUNCE.value in ENABLED_RULES:
            sig = check_prior_day_low_bounce(symbol, intraday_bars, prior_low)
            if sig:
                sig.message += f" ({phase})"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        # --- Prior Day High Breakout ---
        if AlertType.PRIOR_DAY_HIGH_BREAKOUT.value in ENABLED_RULES:
            sig = check_prior_day_high_breakout(
                symbol, intraday_bars, prior_high, bar_vol, avg_vol,
            )
            if sig:
                sig.message += f" ({phase})"
                sig.message += caution_suffix
                signals.append(sig)

        # --- Prior Day High Retest & Hold ---
        if AlertType.PDH_RETEST_HOLD.value in ENABLED_RULES:
            sig = check_pdh_retest_hold(symbol, intraday_bars, prior_high)
            if sig:
                sig.message += f" ({phase})"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        # --- Weekly High Breakout ---
        if AlertType.WEEKLY_HIGH_BREAKOUT.value in ENABLED_RULES:
            sig = check_weekly_high_breakout(
                symbol, intraday_bars, prior_day, bar_vol, avg_vol,
            )
            if sig:
                sig.message += f" ({phase})"
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

        # --- Inside Day Reclaim (failed breakdown trap) ---
        if AlertType.INSIDE_DAY_RECLAIM.value in ENABLED_RULES:
            sig = check_inside_day_reclaim(symbol, intraday_bars, prior_day)
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
                symbol, intraday_bars, intraday_supports, bar_vol, avg_vol,
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

        # --- Multi-Day Double Bottom ---
        if AlertType.MULTI_DAY_DOUBLE_BOTTOM.value in ENABLED_RULES:
            daily_dbs = prior_day.get("daily_double_bottoms", [])
            if daily_dbs:
                sig = check_multi_day_double_bottom(
                    symbol, intraday_bars, daily_dbs, bar_vol, avg_vol,
                    prior_day=prior_day,
                )
                if sig:
                    sig.message += f" ({phase})"
                    if spy.get("spy_bouncing"):
                        sig.confidence = "high"
                        sig.message += " | SPY also bouncing"
                    sig.message += caution_suffix
                    signals.append(sig)

        # --- VWAP Reclaim (Morning Reversal) ---
        if AlertType.VWAP_RECLAIM.value in ENABLED_RULES and symbol in VWAP_SYMBOLS:
            sig = check_vwap_reclaim(
                symbol, intraday_bars, vwap_series, bar_vol, avg_vol,
            )
            if sig:
                sig.message += f" ({phase})"
                sig.message += caution_suffix
                signals.append(sig)

        # --- VWAP Bounce (Pullback to VWAP that holds) ---
        if AlertType.VWAP_BOUNCE.value in ENABLED_RULES and symbol in VWAP_SYMBOLS:
            sig = check_vwap_bounce(
                symbol, intraday_bars, vwap_series, bar_vol, avg_vol,
            )
            if sig:
                sig.message += f" ({phase})"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        # --- Session Low Bounce at Hourly Support → VWAP ---
        if AlertType.SESSION_LOW_BOUNCE_VWAP.value in ENABLED_RULES:
            sig = check_session_low_bounce_to_vwap(
                symbol, intraday_bars, vwap_series,
                intraday_supports, bar_vol, avg_vol,
            )
            if sig:
                sig.message += f" ({phase})"
                signals.append(sig)

        # --- Session Low Reversal (reversal candle + volume at the low) ---
        if AlertType.SESSION_LOW_REVERSAL.value in ENABLED_RULES:
            sig = check_session_low_reversal(symbol, intraday_bars)
            if sig:
                sig.message += f" ({phase})"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        # --- Session Low Breakdown (SHORT) ---
        if AlertType.SESSION_LOW_BREAKDOWN.value in ENABLED_RULES:
            sig = check_session_low_breakdown(symbol, intraday_bars)
            if sig:
                sig.message += f" ({phase})"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        # --- VWAP Loss (SHORT) — was above VWAP, confirmed close below ---
        if AlertType.VWAP_LOSS.value in ENABLED_RULES:
            sig = check_vwap_loss(symbol, intraday_bars, vwap_series)
            if sig:
                sig.message += f" ({phase})"
                sig.message += caution_suffix
                signals.append(sig)

        # --- EMA Rejection SHORT (rallied into MA, got rejected) ---
        if AlertType.EMA_REJECTION_SHORT.value in ENABLED_RULES:
            sig = check_ema_rejection_short(symbol, intraday_bars, prior_day)
            if sig:
                sig.message += f" ({phase})"
                sig.message += caution_suffix
                signals.append(sig)

        # --- EMA Loss SHORT (was above MA, closed below) ---
        if AlertType.EMA_LOSS_SHORT.value in ENABLED_RULES:
            sig = check_ema_loss_short(symbol, intraday_bars, prior_day)
            if sig:
                sig.message += f" ({phase})"
                sig.message += caution_suffix
                signals.append(sig)

        # --- Opening Low Base ---
        if AlertType.OPENING_LOW_BASE.value in ENABLED_RULES:
            sig = check_opening_low_base(symbol, intraday_bars)
            if sig:
                sig.message += f" ({phase})"
                if spy.get("spy_bouncing"):
                    sig.confidence = "high"
                    sig.message += " | SPY also basing"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        # --- Morning Low Retest ---
        if AlertType.MORNING_LOW_RETEST.value in ENABLED_RULES:
            sig = check_morning_low_retest(symbol, intraday_bars, opening_range)
            if sig:
                sig.message += f" ({phase})"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        # --- Morning Low Breakdown (SHORT) ---
        if AlertType.MORNING_LOW_BREAKDOWN.value in ENABLED_RULES:
            sig = check_morning_low_breakdown(symbol, intraday_bars, opening_range)
            if sig:
                sig.message += f" ({phase})"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        # --- First Hour High Breakout ---
        if AlertType.FIRST_HOUR_HIGH_BREAKOUT.value in ENABLED_RULES:
            sig = check_first_hour_high_breakout(
                symbol, intraday_bars, opening_range, bar_vol, avg_vol,
            )
            if sig:
                sig.message += f" ({phase})"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        # --- MA/EMA Reclaim ---
        _reclaim_pairs = [
            (AlertType.MA_RECLAIM_20, ma20, "20MA"),
            (AlertType.MA_RECLAIM_50, ma50, "50MA"),
            (AlertType.MA_RECLAIM_100, ma100, "100MA"),
            (AlertType.MA_RECLAIM_200, ma200, "200MA"),
            (AlertType.EMA_RECLAIM_20, ema20, "EMA20"),
            (AlertType.EMA_RECLAIM_50, ema50, "EMA50"),
            (AlertType.EMA_RECLAIM_100, ema100, "EMA100"),
            (AlertType.EMA_RECLAIM_200, ema200, "EMA200"),
        ]
        for _at, _ma, _label in _reclaim_pairs:
            if _at.value in ENABLED_RULES and _ma:
                sig = check_ma_ema_reclaim(
                    symbol, intraday_bars, _ma, prior_close, _at, _label,
                )
                if sig:
                    sig.message += f" ({phase})"
                    if vwap_pos:
                        sig.message += f" — price {vwap_pos}"
                    sig.message += caution_suffix
                    signals.append(sig)

        # --- Session High Retracement ---
        if AlertType.SESSION_HIGH_RETRACEMENT.value in ENABLED_RULES:
            sig = check_session_high_retracement(
                symbol, intraday_bars, last_bar, bar_vol, avg_vol,
            )
            if sig:
                sig.message += f" ({phase})"
                if spy.get("spy_bouncing"):
                    sig.confidence = "high"
                    sig.message += " | SPY also pulling back"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        # --- Planned Level Touch (uses daily plan from DB) ---
        if daily_plan is not None:
            sig = check_planned_level_touch(symbol, intraday_bars, daily_plan, today_open)
            if sig:
                sig.message += f" ({phase})"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        # --- Weekly Level Touch ---
        sig = check_weekly_level_touch(symbol, intraday_bars, prior_day)
        if sig:
            sig.message += f" ({phase})"
            if vwap_pos:
                sig.message += f" — price {vwap_pos}"
            sig.message += caution_suffix
            signals.append(sig)

        # --- Monthly Level Touch ---
        if AlertType.MONTHLY_LEVEL_TOUCH.value in ENABLED_RULES:
            sig = check_monthly_level_touch(symbol, intraday_bars, prior_day)
            if sig:
                sig.message += f" ({phase})"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        # --- Monthly High Breakout ---
        if AlertType.MONTHLY_HIGH_BREAKOUT.value in ENABLED_RULES:
            sig = check_monthly_high_breakout(
                symbol, intraday_bars, prior_day, bar_vol, avg_vol,
            )
            if sig:
                sig.message += f" ({phase})"
                sig.message += caution_suffix
                signals.append(sig)

        # --- MACD Histogram Flip ---
        if AlertType.MACD_HISTOGRAM_FLIP.value in ENABLED_RULES:
            sig = check_macd_histogram_flip(symbol, intraday_bars, prior_day)
            if sig:
                sig.message += f" ({phase})"
                if vwap_pos:
                    sig.message += f" — price {vwap_pos}"
                sig.message += caution_suffix
                signals.append(sig)

        # --- Bollinger Band Squeeze Breakout ---
        if AlertType.BB_SQUEEZE_BREAKOUT.value in ENABLED_RULES:
            sig = check_bb_squeeze_breakout(symbol, intraday_bars)
            if sig:
                sig.message += f" ({phase})"
                sig.message += caution_suffix
                signals.append(sig)

        # --- Gap-and-Go ---
        if AlertType.GAP_AND_GO.value in ENABLED_RULES:
            # Suppress gap_and_go in bearish SPY regime — gap-ups get sold
            _gap_regime_ok = True
            if not is_crypto and spy_regime == "TRENDING_DOWN":
                _gap_regime_ok = False
            if _gap_regime_ok:
                sig = check_gap_and_go(
                    symbol, intraday_bars, prior_close, bar_vol, avg_vol,
                )
                if sig:
                    sig.message += f" ({phase})"
                    sig.message += caution_suffix
                    signals.append(sig)

        # --- Fibonacci Retracement Bounce ---
        if AlertType.FIB_RETRACEMENT_BOUNCE.value in ENABLED_RULES:
            sig = check_fib_retracement_bounce(
                symbol, last_bar, prior_high, prior_low,
            )
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

    # --- First Hour Summary (NOTICE — fires once per symbol after first hour) ---
    if AlertType.FIRST_HOUR_SUMMARY.value in ENABLED_RULES:
        sig = check_first_hour_summary(symbol, intraday_bars, prior_day, fired_today)
        if sig:
            sig.session_phase = phase
            signals.append(sig)

    # --- Inside Day Forming (NOTICE — fires once after first hour) ---
    is_inside_day_forming = False
    if AlertType.INSIDE_DAY_FORMING.value in ENABLED_RULES:
        sig = check_inside_day_forming(symbol, intraday_bars, prior_high, prior_low)
        if sig:
            is_inside_day_forming = True
            sig.session_phase = phase
            signals.append(sig)

    # --- SELL rules (always fire regardless of SPY/session) ---

    entries = active_entries or []
    has_active = len(entries) > 0

    sig = check_resistance_prior_high(symbol, last_bar, prior_high, has_active)
    if sig:
        signals.append(sig)

    if AlertType.PDH_TEST.value in ENABLED_RULES:
        sig = check_pdh_test(symbol, last_bar, prior_high, prior_close)
        if sig:
            sig.session_phase = phase
            signals.append(sig)

    sig = check_pdh_rejection(symbol, last_bar, prior_high, prior_close)
    if sig:
        signals.append(sig)

    # --- PDH Failed Breakout (SHORT) ---
    if AlertType.PDH_FAILED_BREAKOUT.value in ENABLED_RULES:
        sig = check_pdh_failed_breakout(symbol, intraday_bars, prior_high)
        if sig:
            sig.message += f" ({phase})"
            if vwap_pos:
                sig.message += f" — price {vwap_pos}"
            sig.message += caution_suffix
            signals.append(sig)

    sig = check_hourly_resistance_approach(symbol, last_bar, hourly_resistance, has_active, prior_close)
    if sig:
        signals.append(sig)

    # --- Hourly Resistance Rejection SHORT ---
    if AlertType.HOURLY_RESISTANCE_REJECTION_SHORT.value in ENABLED_RULES:
        sig = check_hourly_resistance_rejection_short(
            symbol, intraday_bars, hourly_resistance, prior_close,
        )
        if sig:
            sig.message += caution_suffix
            signals.append(sig)

    sig = check_ma_resistance(symbol, last_bar, ma20, ma50, ma100, ma200, prior_close)
    if sig:
        signals.append(sig)

    sig = check_resistance_prior_low(symbol, last_bar, prior_low, prior_close, today_open)
    if sig:
        signals.append(sig)

    # --- Prior Day Low Breakdown ---
    if AlertType.PRIOR_DAY_LOW_BREAKDOWN.value in ENABLED_RULES:
        sig = check_prior_day_low_breakdown(
            symbol, intraday_bars, prior_low, bar_vol, avg_vol,
        )
        if sig:
            sig.message += f" ({phase})"
            signals.append(sig)

    # --- Prior Day Low as Resistance (after breakdown) ---
    if AlertType.PRIOR_DAY_LOW_RESISTANCE.value in ENABLED_RULES:
        sig = check_prior_day_low_resistance(symbol, intraday_bars, prior_low)
        if sig:
            sig.message += f" ({phase})"
            signals.append(sig)

    # --- SPY Short Entry (gate-confirmed breakdown) ---
    if AlertType.SPY_SHORT_ENTRY.value in ENABLED_RULES:
        from alert_config import SPY_SHORT_ENABLED
        if SPY_SHORT_ENABLED:
            sig = check_spy_short_entry(
                symbol, intraday_bars, prior_day, bar_vol, avg_vol,
                gate=spy_gate,
            )
            if sig:
                sig.message += f" ({phase})"
                signals.append(sig)

    # --- Per-Symbol Consolidation Breakout (BUY / SHORT) ---
    if (AlertType.CONSOL_BREAKOUT_LONG.value in ENABLED_RULES
            or AlertType.CONSOL_BREAKOUT_SHORT.value in ENABLED_RULES):
        sig = check_consolidation_breakout(
            symbol, intraday_bars, bar_vol, avg_vol,
            daily_trend=prior_day.get("daily_trend") if prior_day else None,
        )
        if sig:
            sig.message += f" ({phase})"
            signals.append(sig)

    # --- Weekly High Test (wick above, no close) ---
    if AlertType.WEEKLY_HIGH_TEST.value in ENABLED_RULES:
        sig = check_weekly_high_test(symbol, last_bar, prior_day, prior_close)
        if sig:
            sig.session_phase = phase
            signals.append(sig)

    # --- Weekly High Resistance ---
    if AlertType.WEEKLY_HIGH_RESISTANCE.value in ENABLED_RULES:
        sig = check_weekly_high_resistance(symbol, last_bar, prior_day)
        if sig:
            signals.append(sig)

    # --- Weekly Low Test (wick below, no close) ---
    if AlertType.WEEKLY_LOW_TEST.value in ENABLED_RULES:
        sig = check_weekly_low_test(symbol, last_bar, prior_day, prior_close)
        if sig:
            sig.session_phase = phase
            signals.append(sig)

    # --- Weekly Low Breakdown (close below prior week low) ---
    if AlertType.WEEKLY_LOW_BREAKDOWN.value in ENABLED_RULES:
        sig = check_weekly_low_breakdown(
            symbol, last_bar, prior_day, bar_vol, avg_vol, prior_close,
        )
        if sig:
            sig.message += f" ({phase})"
            signals.append(sig)

    # --- Monthly High Test (wick above, no close) ---
    if AlertType.MONTHLY_HIGH_TEST.value in ENABLED_RULES:
        sig = check_monthly_high_test(symbol, last_bar, prior_day, prior_close)
        if sig:
            sig.session_phase = phase
            signals.append(sig)

    # --- Monthly High Resistance ---
    if AlertType.MONTHLY_HIGH_RESISTANCE.value in ENABLED_RULES:
        sig = check_monthly_high_resistance(symbol, last_bar, prior_day)
        if sig:
            signals.append(sig)

    # --- Monthly Low Test (wick below, no close) ---
    if AlertType.MONTHLY_LOW_TEST.value in ENABLED_RULES:
        sig = check_monthly_low_test(symbol, last_bar, prior_day, prior_close)
        if sig:
            sig.session_phase = phase
            signals.append(sig)

    # --- Monthly Low Breakdown (close below prior month low) ---
    if AlertType.MONTHLY_LOW_BREAKDOWN.value in ENABLED_RULES:
        sig = check_monthly_low_breakdown(
            symbol, last_bar, prior_day, bar_vol, avg_vol, prior_close,
        )
        if sig:
            sig.message += f" ({phase})"
            signals.append(sig)

    # --- EMA Resistance ---
    if AlertType.EMA_RESISTANCE.value in ENABLED_RULES:
        sig = check_ema_resistance(symbol, last_bar, ema20, ema50, prior_close, ema100=ema100, ema200=ema200)
        if sig:
            signals.append(sig)

    # --- Opening Range Breakdown (SELL — informational) ---
    if AlertType.OPENING_RANGE_BREAKDOWN.value in ENABLED_RULES:
        sig = check_orb_breakdown(symbol, last_bar, opening_range, bar_vol, avg_vol)
        if sig:
            sig.message += f" ({phase})"
            signals.append(sig)

    # --- Inside Day Breakdown (SELL — informational) ---
    if AlertType.INSIDE_DAY_BREAKDOWN.value in ENABLED_RULES:
        sig = check_inside_day_breakdown(symbol, last_bar, prior_day)
        if sig:
            sig.message += f" ({phase})"
            signals.append(sig)

    # Use last_bar (most recent 5-min bar) for target/stop detection.
    # Previously used a session_bar spanning all intraday highs/lows, but
    # that caused false T1/T2 hits when entries were created mid-session
    # (session high from BEFORE the entry would trigger "target hit").
    _entry_signal_types_seen: set[str] = set()
    for entry in entries:
        ep = entry.get("entry_price") or 0
        t1 = entry.get("target_1") or 0
        t2 = entry.get("target_2") or 0
        sp = entry.get("stop_price") or 0

        sig = check_target_1_hit(symbol, last_bar, ep, t1)
        if sig and sig.alert_type.value not in _entry_signal_types_seen:
            _entry_signal_types_seen.add(sig.alert_type.value)
            signals.append(sig)

        sig = check_target_2_hit(symbol, last_bar, ep, t2)
        if sig and sig.alert_type.value not in _entry_signal_types_seen:
            _entry_signal_types_seen.add(sig.alert_type.value)
            signals.append(sig)

        sig = check_stop_loss_hit(symbol, last_bar, ep, sp)
        if sig and sig.alert_type.value not in _entry_signal_types_seen:
            _entry_signal_types_seen.add(sig.alert_type.value)
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

    # --- EMA Crossover 5/20 (BUY) ---
    if not is_cooled_down and AlertType.EMA_CROSSOVER_5_20.value in ENABLED_RULES:
        sig = check_ema_crossover_5_20(symbol, intraday_bars)
        if sig:
            sig.message += f" ({phase})"
            sig.message += caution_suffix
            signals.append(sig)

    # --- TRENDING_DOWN regime: suppress weak BUY types that chase the knife ---
    # These rules have 0% win rate in bearish conditions based on live data.
    # They remain active in CHOPPY and TRENDING_UP regimes.
    if not is_crypto and spy_regime == "TRENDING_DOWN":
        _weak_in_downtrend = {
            AlertType.VWAP_BOUNCE.value,
            AlertType.VWAP_RECLAIM.value,
            AlertType.PDH_RETEST_HOLD.value,
        }
        pre_regime = signals[:]
        signals = [
            s for s in signals
            if not (s.direction == "BUY" and s.alert_type.value in _weak_in_downtrend)
        ]
        for s in pre_regime:
            if s.direction == "BUY" and s.alert_type.value in _weak_in_downtrend and s not in signals:
                logger.info(
                    "%s: TRENDING_DOWN filter dropped %s (0%% win rate in bearish regime)",
                    symbol, s.alert_type.value,
                )

    # --- Opening wait: suppress ALL BUY in first 15 min ---
    if _in_opening_wait:
        pre_open = signals[:]
        signals = [s for s in signals if s.direction != "BUY"]
        for s in pre_open:
            if s.direction == "BUY" and s not in signals:
                logger.info(
                    "%s: OPENING WAIT suppressed BUY %s (only %d bars, need %d)",
                    symbol, s.alert_type.value, len(intraday_bars), _OPENING_WAIT_BARS,
                )

    # --- SPY below VWAP: suppress non-SPY equity BUY ---
    if _spy_currently_below_vwap:
        # Key support types pass through (relative strength)
        _vwap_gate_exempt = {
            AlertType.PRIOR_DAY_LOW_RECLAIM.value,
            AlertType.PRIOR_DAY_LOW_BOUNCE.value,
            AlertType.SESSION_LOW_DOUBLE_BOTTOM.value,
            AlertType.MULTI_DAY_DOUBLE_BOTTOM.value,
            AlertType.SESSION_LOW_BOUNCE_VWAP.value,
            AlertType.SESSION_LOW_REVERSAL.value,
            AlertType.MA_BOUNCE_50.value,
            AlertType.MA_BOUNCE_200.value,
            AlertType.EMA_BOUNCE_50.value,
            AlertType.EMA_BOUNCE_200.value,
            AlertType.EMA_RECLAIM_50.value,
            AlertType.EMA_RECLAIM_200.value,
            AlertType.INSIDE_DAY_BREAKOUT.value,
            AlertType.BB_SQUEEZE_BREAKOUT.value,
            AlertType.PRIOR_DAY_HIGH_BREAKOUT.value,
        }
        # Tag non-SPY BUY signals: key support types get demoted,
        # all others get tagged to skip Telegram (still recorded to DB/dashboard)
        for s in signals:
            if s.direction != "BUY":
                continue
            if s.alert_type.value in _vwap_gate_exempt:
                # Key support — keep in Telegram but demote
                s.message += " | SPY below VWAP — relative strength"
                if s.confidence == "high":
                    s.confidence = "medium"
                s.score = min(s.score, 65)
                s.score_label = (
                    "Strong" if s.score >= 80
                    else "Moderate" if s.score >= 60
                    else "Weak" if s.score >= 40
                    else "Caution"
                )
            else:
                # Non-key-support BUY — demote but still send to Telegram
                s.message += " | SPY below VWAP — reduced confidence"
                if s.confidence == "high":
                    s.confidence = "medium"
                s.score = min(s.score, 55)
                s.score_label = (
                    "Strong" if s.score >= 80
                    else "Moderate" if s.score >= 60
                    else "Weak" if s.score >= 40
                    else "Caution"
                )

    # --- 15-min range filter: suppress BUY when symbol is in a tight range ---
    # If the hourly bars show consolidation (no breakout), BUY signals are
    # just catching knives inside a range — suppress them.
    # Exception: inside_day_breakout and bb_squeeze_breakout are specifically
    # designed for range-breaking and should not be suppressed.
    _range_exempt_types = {
        AlertType.INSIDE_DAY_BREAKOUT.value,
        AlertType.BB_SQUEEZE_BREAKOUT.value,
        AlertType.CONSOL_BREAKOUT_LONG.value,
    }
    _consol_check = detect_hourly_consolidation_break(intraday_bars)
    if _consol_check and _consol_check.get("status") == "consolidating":
        _range_pct = _consol_check.get("range_pct", 0)
        pre_range = signals[:]
        signals = [
            s for s in signals
            if s.direction != "BUY"
            or s.alert_type.value in _range_exempt_types
        ]
        for s in pre_range:
            if s.direction == "BUY" and s not in signals:
                logger.info(
                    "%s: RANGE FILTER suppressed BUY %s (consolidating, range %.1f%%)",
                    symbol, s.alert_type.value, _range_pct * 100,
                )

    # --- Contradictory signal filter: active SHORT in same cycle suppresses BUY ---
    # If the system fires a SHORT with entry/stop/targets at the same time as
    # a BUY, the SHORT wins — the market is showing weakness at the same level.
    # Passive SELL signals (rejection, resistance, target hits, stops) do NOT
    # suppress BUYs — they are informational or exit-only.
    _active_short_in_cycle = any(
        s.direction == "SHORT"
        and s.entry is not None
        for s in signals
    )
    # Also suppress if PDH failed breakout or morning low breakdown fires
    _bearish_breakdown_in_cycle = any(
        s.alert_type in (
            AlertType.PDH_FAILED_BREAKOUT,
            AlertType.MORNING_LOW_BREAKDOWN,
            AlertType.SUPPORT_BREAKDOWN,
        )
        for s in signals
    )
    if _active_short_in_cycle or _bearish_breakdown_in_cycle:
        dropped = [s for s in signals if s.direction == "BUY"]
        if dropped:
            _bear_names = ", ".join(
                s.alert_type.value for s in signals
                if s.direction in ("SELL", "SHORT")
            )
            for s in dropped:
                logger.info(
                    "%s: contradictory filter dropped BUY %s (bearish signals: %s)",
                    symbol, s.alert_type.value, _bear_names,
                )
            signals = [s for s in signals if s.direction != "BUY"]

    # --- Bounce Quality Tagging ---
    # Tag all bounce-type BUY signals with quality assessment
    for s in signals:
        if s.direction == "BUY" and s.alert_type.value in BOUNCE_ALERT_TYPES:
            bounce_level = s.entry or s.stop or 0
            bq = classify_bounce_quality(
                intraday_bars, vwap_series, bar_vol, avg_vol, bounce_level,
            )
            s.message += bq["tag"]

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

    # --- Hourly Consolidation Notice ---
    # When price is in a tight hourly range, send a NOTICE so user knows
    # the system is watching and waiting for direction, not broken.
    _consol_gate = spy_gate if not is_crypto else None
    if is_crypto and len(intraday_bars) >= 36:
        from analytics.intraday_data import compute_vwap as _cv2
        _crypto_vwap2 = _cv2(intraday_bars)
        _consol_gate = compute_spy_gate(intraday_bars, _crypto_vwap2)
    if (_consol_gate and _consol_gate.get("hourly_break")
            and _consol_gate["hourly_break"].get("status") == "consolidating"
            and AlertType.HOURLY_CONSOLIDATION.value in ENABLED_RULES):
        _hb = _consol_gate["hourly_break"]
        _consol_key = (symbol, AlertType.HOURLY_CONSOLIDATION.value)
        if _consol_key not in (fired_today or set()):
            signals.append(AlertSignal(
                symbol=symbol,
                alert_type=AlertType.HOURLY_CONSOLIDATION,
                direction="NOTICE",
                price=last_bar["Close"],
                entry=round(_hb["range_high"], 2),
                stop=round(_hb["range_low"], 2),
                confidence="info",
                message=(
                    f"HOURLY CONSOLIDATION — range ${_hb['range_low']:.2f}-${_hb['range_high']:.2f} "
                    f"({_hb['range_pct']:.1f}%). Waiting for breakout direction. "
                    f"BUY above ${_hb['range_high']:.2f}, SHORT below ${_hb['range_low']:.2f}"
                ),
            ))

    # --- SPY/Crypto Gate: suppress/demote BUY signals when trend is bearish ---
    # For equities: uses SPY gate (computed once per poll cycle)
    # For crypto: uses the symbol's own VWAP + EMA as self-gate
    from alert_config import SPY_GATE_ENABLED
    _active_gate = spy_gate
    if is_crypto and SPY_GATE_ENABLED and len(intraday_bars) >= 6:
        # Compute self-gate for crypto using its own VWAP + EMA
        from analytics.intraday_data import compute_vwap as _cv
        _crypto_vwap = _cv(intraday_bars)
        _active_gate = compute_spy_gate(intraday_bars, _crypto_vwap)
        if _active_gate["gate"] != "green":
            logger.debug(
                "%s: crypto self-gate %s (%s)",
                symbol, _active_gate["gate"], _active_gate["reason"],
            )

    # Types exempt from YELLOW demotion (high-conviction setups where
    # being below VWAP or in mixed conditions is part of the thesis)
    _yellow_exempt = {
        AlertType.CONSOL_BREAKOUT_LONG.value,
        AlertType.SESSION_LOW_BOUNCE_VWAP.value,
    }

    # SPY itself is NEVER suppressed by the SPY gate — the gate protects
    # other equities from SPY weakness, not SPY from itself.
    # Crypto uses its own self-gate independently.
    _is_spy = symbol == "SPY"

    if SPY_GATE_ENABLED and _active_gate:
        _gate = _active_gate.get("gate", "green")
        _gate_reason = _active_gate.get("reason", "")

        # ── Immediate VWAP check (stricter than 6-bar average) ──────────
        # If SPY's last close is below VWAP right now, treat as RED for
        # non-SPY equities.  SPY itself keeps all alerts.  Crypto uses
        # its own self-gate.
        _spy_below_vwap_now = False
        if (
            not is_crypto
            and not _is_spy
            and spy_gate
            and spy_gate.get("vwap_dominance", 1.0) < 0.5
        ):
            _spy_below_vwap_now = True

        if _is_spy:
            # SPY keeps ALL its alerts — never suppressed by its own gate
            pass
        elif is_crypto and _gate == "red":
            # Crypto with own red gate: only allow session_low_bounce_vwap
            _red_exempt_types = {AlertType.SESSION_LOW_BOUNCE_VWAP.value}
            _effective_reason = _gate_reason or "Crypto self-gate RED"
            pre_gate = signals[:]
            signals = [
                s for s in signals
                if s.direction != "BUY"
                or s.alert_type.value in _red_exempt_types
            ]
            for s in pre_gate:
                if s.direction == "BUY" and s not in signals:
                    logger.info(
                        "%s: CRYPTO GATE suppressed %s (%s)",
                        symbol, s.alert_type.value, _effective_reason,
                    )
        elif _gate == "red" or (_spy_below_vwap_now and _gate != "green"):
            # Non-SPY equities: suppress weak BUY signals when SPY bearish
            # BUT allow through signals where the stock is holding key support
            # (relative strength — institutional buyers defending the name)
            _key_support_types = {
                AlertType.VWAP_RECLAIM.value,
                AlertType.VWAP_BOUNCE.value,
                AlertType.PRIOR_DAY_LOW_RECLAIM.value,
                AlertType.PRIOR_DAY_LOW_BOUNCE.value,
                AlertType.SESSION_LOW_DOUBLE_BOTTOM.value,
                AlertType.MULTI_DAY_DOUBLE_BOTTOM.value,
                AlertType.SESSION_LOW_BOUNCE_VWAP.value,
                AlertType.INTRADAY_SUPPORT_BOUNCE.value,
                AlertType.MA_BOUNCE_50.value,
                AlertType.MA_BOUNCE_200.value,
                AlertType.EMA_BOUNCE_50.value,
                AlertType.EMA_BOUNCE_200.value,
                AlertType.EMA_RECLAIM_50.value,
                AlertType.EMA_RECLAIM_200.value,
                AlertType.INSIDE_DAY_BREAKOUT.value,
                AlertType.BB_SQUEEZE_BREAKOUT.value,
                AlertType.PRIOR_DAY_HIGH_BREAKOUT.value,
            }
            _effective_reason = _gate_reason or "SPY below VWAP — equity BUY suppressed"
            pre_gate = signals[:]
            signals = [
                s for s in signals
                if s.direction != "BUY"
                or s.alert_type.value in _key_support_types
            ]
            # Demote allowed-through signals: add caution, cap score
            for s in signals:
                if s.direction == "BUY" and s.alert_type.value in _key_support_types:
                    s.message += f" | RELATIVE STRENGTH: holding support despite SPY weakness"
                    if s.confidence == "high":
                        s.confidence = "medium"
                    s.score = min(s.score, 65)
                    s.score_label = (
                        "Strong" if s.score >= 80
                        else "Moderate" if s.score >= 60
                        else "Weak" if s.score >= 40
                        else "Caution"
                    )
            for s in pre_gate:
                if s.direction == "BUY" and s not in signals:
                    logger.info(
                        "%s: SPY GATE suppressed %s (gate=%s, %s)",
                        symbol, s.alert_type.value, _gate, _effective_reason,
                    )
        elif _gate == "yellow":
            # Demote: reduce BUY confidence and add caution
            # Consolidation breakout BUY is exempt (has its own momentum)
            for s in signals:
                if s.direction == "BUY" and s.alert_type.value not in _yellow_exempt:
                    if s.confidence == "high":
                        s.confidence = "medium"
                    s.message += f" | SPY GATE YELLOW: {_gate_reason}"
                    # Cap score at C level
                    s.score = min(s.score, 40)
                    s.score_label = "Caution"

        # Block SHORT consolidation breakout on GREEN (don't short bull tape)
        if _gate == "green":
            pre_short = signals[:]
            signals = [
                s for s in signals
                if not (s.alert_type == AlertType.CONSOL_BREAKOUT_SHORT
                        and s.direction == "SHORT")
            ]
            for s in pre_short:
                if (s.alert_type == AlertType.CONSOL_BREAKOUT_SHORT
                        and s.direction == "SHORT"):
                    logger.info(
                        "%s: SPY GATE GREEN blocked SHORT %s (%s)",
                        symbol, s.alert_type.value, _gate_reason,
                    )

    # --- ADX trend filter: demote BUY signals in choppy (low-ADX) markets ---
    _adx = prior_day.get("adx14") if prior_day else None
    if _adx is not None and _adx < 20:
        for s in signals:
            if s.direction == "BUY":
                s.score = max(0, s.score - 10)
                s.score_label = (
                    "Strong" if s.score >= 80
                    else "Moderate" if s.score >= 60
                    else "Weak" if s.score >= 40
                    else "Caution"
                )
                s.message = (s.message or "") + f" | ADX={_adx:.0f} (low trend)"
                s.confidence = "low" if s.confidence == "medium" else s.confidence
                logger.debug(
                    "%s: ADX filter demoted %s (ADX=%.1f < 20)",
                    symbol, s.alert_type.value, _adx,
                )

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
    # Exempt breakout alerts — price is supposed to run above entry on breakouts.
    # Exempt MA bounce + PDL — these are "level" signals; price running confirms thesis.
    _staleness_exempt = {
        AlertType.PRIOR_DAY_HIGH_BREAKOUT.value,
        AlertType.INSIDE_DAY_BREAKOUT.value,
        AlertType.OUTSIDE_DAY_BREAKOUT.value,
        AlertType.WEEKLY_HIGH_BREAKOUT.value,
        AlertType.OPENING_RANGE_BREAKOUT.value,
        AlertType.MA_BOUNCE_100.value,
        AlertType.MA_BOUNCE_200.value,
        AlertType.EMA_BOUNCE_100.value,
        AlertType.EMA_BOUNCE_200.value,
        AlertType.PRIOR_DAY_LOW_RECLAIM.value,
        AlertType.PRIOR_DAY_LOW_BOUNCE.value,
    }
    current_price = last_bar["Close"]
    pre_stale = signals[:]
    signals = [
        s for s in signals
        if not (s.direction == "BUY" and s.entry and s.stop
                and s.alert_type.value not in _staleness_exempt
                and current_price > s.entry + (s.entry - s.stop))
    ]
    for s in pre_stale:
        if (s.direction == "BUY" and s.entry and s.stop
                and s.alert_type.value not in _staleness_exempt
                and current_price > s.entry + (s.entry - s.stop)):
            logger.debug(
                "%s: staleness filter dropped %s (price=%.2f > entry+1R=%.2f)",
                symbol, s.alert_type.value, current_price,
                s.entry + (s.entry - s.stop),
            )

    # --- Overhead MA resistance filter: suppress BUY heading into nearby MA above ---
    # Exempt MA bounce (the MA IS the entry) and PDL (nearby MA is a target, not blocker).
    _overhead_exempt = {
        AlertType.MA_BOUNCE_100.value,
        AlertType.MA_BOUNCE_200.value,
        AlertType.EMA_BOUNCE_100.value,
        AlertType.EMA_BOUNCE_200.value,
        AlertType.PRIOR_DAY_LOW_RECLAIM.value,
        AlertType.PRIOR_DAY_LOW_BOUNCE.value,
    }
    pre_overhead = signals[:]
    filtered_signals: list[AlertSignal] = []
    for s in signals:
        if s.direction == "BUY" and s.entry and s.alert_type.value not in _overhead_exempt:
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

    # --- Wick rejection filter: demote confidence for wick-only touches ---
    # In choppy markets, wicks create false touches — price wicks to a level
    # but the body (close) is far away. Demote confidence when the touch was
    # only a wick and the close is far from the support level.
    _WICK_FILTER_TYPES = {
        AlertType.MA_BOUNCE_20, AlertType.MA_BOUNCE_50,
        AlertType.MA_BOUNCE_100, AlertType.MA_BOUNCE_200,
        AlertType.EMA_BOUNCE_20, AlertType.EMA_BOUNCE_50,
        AlertType.EMA_BOUNCE_100, AlertType.EMA_BOUNCE_200,
        AlertType.PRIOR_DAY_LOW_BOUNCE, AlertType.PRIOR_DAY_LOW_RECLAIM,
        AlertType.INTRADAY_SUPPORT_BOUNCE, AlertType.SESSION_LOW_DOUBLE_BOTTOM,
        AlertType.MORNING_LOW_RETEST, AlertType.WEEKLY_LEVEL_TOUCH,
    }
    from alert_config import WICK_REJECTION_CLOSE_PCT, WICK_REJECTION_RATIO
    for sig in signals:
        if (sig.direction == "BUY" and sig.alert_type in _WICK_FILTER_TYPES
                and sig.entry and last_bar is not None):
            close_distance = (last_bar["Close"] - sig.entry) / sig.entry if sig.entry > 0 else 0
            bar_range = last_bar["High"] - last_bar["Low"] if last_bar["High"] > last_bar["Low"] else 0.01
            wick_ratio = (last_bar["Close"] - last_bar["Low"]) / bar_range if bar_range > 0 else 0

            # Long lower wick (wick > 60% of range) + close far from entry = wick rejection
            if wick_ratio > WICK_REJECTION_RATIO and close_distance > WICK_REJECTION_CLOSE_PCT:
                sig.confidence = "medium" if sig.confidence == "high" else sig.confidence
                sig.message += " | wick touch only (close far from level)"
                logger.debug(
                    "%s: wick filter demoted %s (close_dist=%.2f%%, wick_ratio=%.2f)",
                    symbol, sig.alert_type.value, close_distance * 100, wick_ratio,
                )

    # --- Candle pattern filter: demote MA/EMA bounce signals without reversal candle ---
    # If the touch bar doesn't show bullish reversal characteristics (hammer,
    # long lower wick, bullish engulfing), demote confidence to "low" rather
    # than suppress — educational platform should still show these signals.
    _CANDLE_FILTER_TYPES = {
        AlertType.MA_BOUNCE_20, AlertType.MA_BOUNCE_50,
        AlertType.MA_BOUNCE_100, AlertType.MA_BOUNCE_200,
        AlertType.EMA_BOUNCE_20, AlertType.EMA_BOUNCE_50,
        AlertType.EMA_BOUNCE_100, AlertType.EMA_BOUNCE_200,
    }
    if len(intraday_bars) >= 2:
        # Find the best touch bar in lookback window for each signal
        for sig in signals:
            if sig.direction == "BUY" and sig.alert_type in _CANDLE_FILTER_TYPES and sig.entry:
                _lookback = intraday_bars.tail(MA_BOUNCE_LOOKBACK_BARS)
                _touch_idx = None
                _best_prox = float("inf")
                for _li in range(len(_lookback)):
                    _row = _lookback.iloc[_li]
                    _lp = abs(_row["Low"] - sig.entry) / sig.entry if sig.entry > 0 else float("inf")
                    _cp = abs(_row["Close"] - sig.entry) / sig.entry if sig.entry > 0 else float("inf")
                    _p = min(_lp, _cp)
                    if _p < _best_prox:
                        _best_prox = _p
                        # Convert lookback-relative index to full bars index
                        _touch_idx = len(intraday_bars) - len(_lookback) + _li
                if _touch_idx is not None and not _is_reversal_candle(intraday_bars, _touch_idx):
                    if sig.confidence != "low":
                        sig.confidence = "low"
                        sig.message += " | no reversal candle at touch"
                        logger.debug(
                            "%s: candle filter demoted %s (no reversal at bar %d)",
                            symbol, sig.alert_type.value, _touch_idx,
                        )

    # --- Heikin Ashi confirmation: demote BUY signals when HA candle is bearish ---
    # HA candles filter wick noise and show the real trend direction.
    # If the HA candle is bearish (HA close < HA open) on the signal bar,
    # there's no real buying pressure — demote confidence.
    if len(intraday_bars) >= 2:
        _ha_close = (
            last_bar["Open"] + last_bar["High"] + last_bar["Low"] + last_bar["Close"]
        ) / 4
        _prev = intraday_bars.iloc[-2]
        _ha_open = (_prev["Open"] + _prev["Close"]) / 2
        _ha_bullish = _ha_close > _ha_open

        if not _ha_bullish:
            for sig in signals:
                if (sig.direction == "BUY" and sig.alert_type in _WICK_FILTER_TYPES
                        and sig.confidence == "high"):
                    sig.confidence = "medium"
                    sig.message += " | HA bearish (no buying pressure)"
                    logger.debug(
                        "%s: HA filter demoted %s (HA close=%.2f < HA open=%.2f)",
                        symbol, sig.alert_type.value, _ha_close, _ha_open,
                    )

    # --- Relative Strength filter ---
    spy_intraday_change = spy.get("intraday_change_pct", 0.0)

    # --- Enrich all signals with context ---
    _MA_BOUNCE_RULES = {
        AlertType.MA_BOUNCE_20, AlertType.MA_BOUNCE_50,
        AlertType.MA_BOUNCE_100, AlertType.MA_BOUNCE_200,
        AlertType.EMA_BOUNCE_20, AlertType.EMA_BOUNCE_50,
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

        # ATR-based dynamic stop (feature flag: USE_ATR_STOPS)
        if sig.direction == "BUY" and sig.entry and sig.stop and current_atr:
            atr_stop = atr_adjusted_stop(sig.entry, current_atr, symbol=symbol)
            # Use ATR stop only if it's tighter (higher) than current stop
            if atr_stop > sig.stop:
                sig.stop = atr_stop
                risk = sig.entry - sig.stop
                if risk > 0:
                    sig.target_1 = round(sig.entry + risk, 2)
                    sig.target_2 = round(sig.entry + 2 * risk, 2)

        # Smart resistance-based targets for all BUY signals
        smart = None
        if (sig.direction == "BUY" and sig.entry and sig.stop):
            smart = _find_resistance_targets(
                sig.entry, sig.stop, prior_day, current_vwap,
                hourly_resistance=hourly_resistance,
            )
            if smart:
                sig.target_1, sig.target_2, t1_label, t2_label = smart
                sig.message += f" | T1: {t1_label} ${sig.target_1:.2f}, T2: {t2_label} ${sig.target_2:.2f}"

        # Minimum target distance: prevent tiny T1/T2 on chased entries.
        # Skip if T1 is VWAP (natural resistance even if close to entry).
        _t1_is_vwap = (smart and smart[2] == "VWAP") if smart else False
        if (sig.direction == "BUY" and sig.entry and sig.target_1 is not None
                and not _t1_is_vwap):
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

        # Day pattern tag (from prior_day)
        if prior_day:
            sig.day_pattern = prior_day.get("pattern", "normal")

        # MA defense/rejection context
        if sig.direction == "BUY":
            defending, rejected_by = _detect_ma_context(
                current_price, ma20, ma50, ma100, ma200, ema20, ema50, ema100,
            )
            sig.ma_defending = defending
            sig.ma_rejected_by = rejected_by
            if defending:
                sig.message += f" | Defending {defending}"
            if rejected_by:
                sig.message += f" | Overhead {rejected_by}"

        # Volume exhaustion detection
        exhaustion_type, exhaustion_msg = _detect_volume_exhaustion(intraday_bars, avg_vol)
        if sig.direction == "BUY" and exhaustion_type == "seller_exhaustion":
            if sig.confidence == "medium":
                sig.confidence = "high"
            sig.message += f" | {exhaustion_msg}"
        elif sig.direction == "BUY" and exhaustion_type == "buyer_exhaustion":
            sig.message += f" | CAUTION: {exhaustion_msg}"

        # RS filter: demote BUY confidence when severely underperforming SPY (equities only)
        if not is_crypto and sig.direction == "BUY" and spy_intraday_change != 0:
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

        # Regime demotion: reduce BUY confidence in CHOPPY markets (equities only)
        if not is_crypto and sig.direction == "BUY" and spy_regime == "CHOPPY":
            if sig.confidence == "high":
                sig.confidence = "medium"
            sig.message += " | CHOPPY market — reduced confidence"

        # SPY TRENDING_DOWN: strongest demotion (equities only)
        if not is_crypto and sig.direction == "BUY" and spy_regime == "TRENDING_DOWN":
            if sig.confidence == "high":
                sig.confidence = "medium"
            sig.message += " | SPY TRENDING DOWN — use extreme caution"

        # SPY S/R level reaction: adjust BUY confidence based on SPY position
        if not is_crypto and sig.direction == "BUY":
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
        sig.score_v2, factors = _score_alert_v2(sig, ma20, ma50, last_bar["Close"], vol_ratio)
        sig.score_factors = dict(factors)  # copy before boosts

        # Confluence score boost (v1 + v2)
        if sig.confluence:
            sig.score = min(100, sig.score + 10)
            sig.score_v2 = min(100, sig.score_v2 + 10)
            sig.score_factors["confluence"] = 10

        # MTF alignment score boost (v1 + v2)
        if sig.direction == "BUY" and mtf["mtf_aligned"]:
            sig.score = min(100, sig.score + 10)
            sig.score_v2 = min(100, sig.score_v2 + 10)
            sig.score_factors["mtf"] = 10

        # Inside day forming score boost: boundary alerts (PDL/PDH) are higher
        # conviction when the day is range-bound — these are the only tradeable
        # levels on an inside day.
        _INSIDE_DAY_BOUNDARY_TYPES = {
            AlertType.PRIOR_DAY_LOW_RECLAIM.value,
            AlertType.PRIOR_DAY_LOW_BOUNCE.value,
            AlertType.PRIOR_DAY_HIGH_BREAKOUT.value,
            AlertType.PDH_TEST.value,
        }
        if is_inside_day_forming and sig.alert_type.value in _INSIDE_DAY_BOUNDARY_TYPES:
            sig.score = min(100, sig.score + INSIDE_DAY_SCORE_BOOST)
            sig.score_v2 = min(100, sig.score_v2 + INSIDE_DAY_SCORE_BOOST)
            sig.score_factors["inside_day"] = INSIDE_DAY_SCORE_BOOST
            sig.message += " | INSIDE DAY — boundary level (boosted)"

        sig.score_label = (
            "Strong" if sig.score >= 80
            else "Moderate" if sig.score >= 60
            else "Weak" if sig.score >= 40
            else "Caution"
        )
        sig.score_v2_label = (
            "A+" if sig.score_v2 >= 90
            else "A" if sig.score_v2 >= 75
            else "B" if sig.score_v2 >= 50
            else "C"
        )

    # --- Consolidate same-symbol BUY signals ---
    signals = _consolidate_signals(signals)

    # --- Minimum score cutoff: drop BUY alerts below 40 (Caution level) ---
    # These have too many headwinds to be educational — just noise.
    # SELL/SHORT/NOTICE always pass through (exits and warnings are critical).
    MIN_BUY_SCORE = 0  # DISABLED — send all BUY alerts for evaluation
    pre_cutoff = signals[:]
    signals = [
        s for s in signals
        if s.direction != "BUY" or s.score >= MIN_BUY_SCORE
    ]
    for s in pre_cutoff:
        if s.direction == "BUY" and s.score < MIN_BUY_SCORE:
            logger.info(
                "%s: MIN SCORE cutoff dropped BUY %s (score=%d < %d)",
                symbol, s.alert_type.value, s.score, MIN_BUY_SCORE,
            )

    return signals
