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
    BREAKDOWN_CONVICTION_PCT,
    BREAKDOWN_VOLUME_RATIO,
    DAY_TRADE_MAX_RISK_PCT,
    EMA_MIN_BARS,
    LOW_VOLUME_SKIP_RATIO,
    MA_BOUNCE_PROXIMITY_PCT,
    MA_STOP_OFFSET_PCT,
    ORB_MIN_RANGE_PCT,
    ORB_VOLUME_RATIO,
    PDL_DIP_MIN_PCT,
    PER_SYMBOL_RISK,
    PLANNED_LEVEL_PROXIMITY_PCT,
    RESISTANCE_PROXIMITY_PCT,
    RS_UNDERPERFORM_FACTOR,
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
    INTRADAY_SUPPORT_BOUNCE = "intraday_support_bounce"
    SESSION_LOW_DOUBLE_BOTTOM = "session_low_double_bottom"
    GAP_FILL = "gap_fill"
    PLANNED_LEVEL_TOUCH = "planned_level_touch"


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

    entry = bar["Close"]
    stop = max(bar["Low"], ma20 * (1 - MA_STOP_OFFSET_PCT))
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
    stop = max(bar["Low"], ma50 * (1 - MA_STOP_OFFSET_PCT))
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
    """5-bar EMA crosses above 20-bar EMA on a mega-cap stock — bullish entry.

    Conditions:
    - Symbol is in MEGA_CAP set
    - At least EMA_MIN_BARS bars available
    - Previous bar: EMA5 <= EMA20; current bar: EMA5 > EMA20
    """
    if not is_mega_cap:
        return None
    if len(bars) < EMA_MIN_BARS:
        return None

    ema5 = bars["Close"].ewm(span=5, adjust=False).mean()
    ema20 = bars["Close"].ewm(span=20, adjust=False).mean()

    if len(ema5) < 2:
        return None
    prev_cross = ema5.iloc[-2] <= ema20.iloc[-2]
    curr_cross = ema5.iloc[-1] > ema20.iloc[-1]
    if not (prev_cross and curr_cross):
        return None  # no crossover

    last_bar = bars.iloc[-1]
    entry = last_bar["Close"]
    recent_low = bars["Low"].iloc[-3:].min()  # recent swing low as stop
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
            f"5/20 EMA bullish crossover — EMA5 ${ema5.iloc[-1]:.2f} "
            f"crossed above EMA20 ${ema20.iloc[-1]:.2f}"
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
# Rule 13: Intraday Support Bounce (BUY)
# ---------------------------------------------------------------------------


def check_intraday_support_bounce(
    symbol: str,
    bar: pd.Series,
    intraday_supports: list[float],
    bar_volume: float,
    avg_volume: float,
) -> AlertSignal | None:
    """Price bounces off a held intraday support level — bullish entry.

    Conditions:
    - At least one intraday support exists
    - Bar low is within SUPPORT_BOUNCE_PROXIMITY_PCT of a support level
    - Bar close > support (bounce confirmed)
    - Volume >= LOW_VOLUME_SKIP_RATIO (not noise)
    """
    if not intraday_supports:
        return None

    vol_ratio = bar_volume / avg_volume if avg_volume > 0 else 1.0
    if vol_ratio < LOW_VOLUME_SKIP_RATIO:
        return None

    # Find closest support at or below bar low within proximity threshold
    best_support = None
    for lvl in sorted(intraday_supports, reverse=True):
        if lvl > bar["Low"]:
            continue
        proximity = (bar["Low"] - lvl) / lvl if lvl > 0 else float("inf")
        if proximity <= SUPPORT_BOUNCE_PROXIMITY_PCT:
            best_support = lvl
            break

    if best_support is None:
        return None
    if bar["Close"] <= best_support:
        return None  # didn't bounce above

    entry = best_support
    stop = bar["Low"] if bar["Low"] < best_support else best_support * (1 - 0.005)
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.INTRADAY_SUPPORT_BOUNCE,
        direction="BUY",
        price=bar["Close"],
        entry=round(entry, 2),
        stop=round(stop, 2),
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="medium",
        message=(
            f"Intraday support bounce — held ${best_support:.2f}, "
            f"closed above at ${bar['Close']:.2f}"
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
        direction="BUY",
        price=bar["Close"],
        entry=round(entry, 2),
        stop=round(stop, 2),
        target_1=round(levels["target_1"], 2),
        target_2=round(levels["target_2"], 2),
        confidence="high",
        message=(
            f"Planned level touch ({levels['pattern']}) — "
            f"bounced at ${entry:.2f}, T1=${levels['target_1']:.2f}"
        ),
    )


# ---------------------------------------------------------------------------
# Noise filter
# ---------------------------------------------------------------------------


def _should_skip_noise(signal: AlertSignal, vol_ratio: float) -> bool:
    """Skip BUY signals on very low volume — likely noise."""
    if signal.direction != "BUY":
        return False
    return vol_ratio < LOW_VOLUME_SKIP_RATIO


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
    prior_close = prior_day.get("close")
    prior_high = prior_day.get("high", 0)
    prior_low = prior_day.get("low", 0)

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

    # Detect intraday supports (used by both bounce BUY rule and breakdown SHORT)
    from analytics.intraday_data import detect_intraday_supports
    intraday_supports = detect_intraday_supports(intraday_bars)

    # --- BUY rules (context adds caution notes, never blocks signals) ---
    spy_regime = spy.get("regime", "CHOPPY")

    caution_notes = []
    if spy_trend == "bearish":
        caution_notes.append("SPY bearish (below 20MA)")
    if spy_regime in ("CHOPPY", "TRENDING_DOWN"):
        caution_notes.append(f"SPY regime: {spy_regime}")
    if not entries_allowed:
        caution_notes.append(f"session: {phase}")
    caution_suffix = f" | CAUTION: {', '.join(caution_notes)}" if caution_notes else ""

    if not is_cooled_down:  # skip BUY rules during post stop-out cooldown
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

        sig = check_inside_day_breakout(symbol, last_bar, prior_day)
        if sig:
            sig.message += f" ({phase})"
            if vwap_pos:
                sig.message += f" — price {vwap_pos}"
            sig.message += caution_suffix
            signals.append(sig)

        # --- Opening Range Breakout ---
        sig = check_opening_range_breakout(
            symbol, last_bar, opening_range, bar_vol, avg_vol,
        )
        if sig:
            sig.message += f" ({phase})"
            sig.message += caution_suffix
            signals.append(sig)

        # --- Intraday Support Bounce ---
        sig = check_intraday_support_bounce(
            symbol, last_bar, intraday_supports, bar_vol, avg_vol,
        )
        if sig:
            sig.message += f" ({phase})"
            # SPY bounce correlation — boost confidence
            if spy.get("spy_bouncing"):
                sig.confidence = "high"
                spy_low = spy.get("spy_intraday_low", 0)
                sig.message += f" | SPY also bouncing from session low ${spy_low:.2f}"
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

    # --- Gap Fill (INFO — fires regardless of cooldown) ---
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

    # --- Auto Stop-Out (SELL — tracked BUY entries) ---
    if auto_stop_entries:
        sig = check_auto_stop_out(symbol, last_bar, auto_stop_entries)
        if sig:
            signals.append(sig)

    # --- Support Breakdown (SHORT) ---
    from analytics.signal_engine import _find_nearest_support

    nearest_support, _ = _find_nearest_support(last_bar["Close"], prior_low, ma20, ma50)

    # Include intraday hourly supports — use closest below current price
    for lvl in sorted(intraday_supports, reverse=True):
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
            sig.message += f" | intraday supports: {intraday_supports}"
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
        signals.append(sig)

    # --- EMA Crossover 5/20 (BUY — mega-cap only) ---
    if not is_cooled_down:
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
        signals = [s for s in signals if s.direction != "BUY"]

    # --- Dedup: remove signals already fired today ---
    if fired_today:
        signals = [
            s for s in signals
            if (symbol, s.alert_type.value) not in fired_today
        ]

    # --- Noise filter: drop low-volume BUY signals ---
    vol_ratio = bar_vol / avg_vol if avg_vol > 0 else 1.0
    signals = [s for s in signals if not _should_skip_noise(s, vol_ratio)]

    # --- Relative Strength filter ---
    spy_intraday_change = spy.get("intraday_change_pct", 0.0)

    # --- Enrich all signals with context ---
    for sig in signals:
        # Apply per-symbol risk cap to all BUY signals and recalculate targets
        if sig.direction == "BUY" and sig.entry and sig.stop:
            capped_stop = _cap_risk(sig.entry, sig.stop, symbol=symbol)
            if capped_stop != sig.stop:
                sig.stop = capped_stop
                risk = sig.entry - sig.stop
                sig.target_1 = round(sig.entry + risk, 2)
                sig.target_2 = round(sig.entry + 2 * risk, 2)

        sig.spy_trend = spy_trend
        sig.session_phase = phase
        sig.volume_label = vol_label
        sig.vwap_position = vwap_pos
        sig.gap_info = gap_info
        if sig.direction == "BUY" and vol_label:
            sig.message += f" | {vol_label}"
        if gap_info and sig.direction == "BUY":
            sig.message += f" | {gap_info}"

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

        # MTF alignment enrichment
        sig.mtf_aligned = mtf["mtf_aligned"]
        if sig.direction == "BUY":
            if mtf["mtf_aligned"]:
                sig.message += " | 15m trend aligned"
            else:
                sig.message += " | 15m trend NOT aligned (caution)"

        sig.score = _score_alert(sig, ma20, ma50, last_bar["Close"], vol_ratio)

        # MTF alignment score boost
        if sig.direction == "BUY" and mtf["mtf_aligned"]:
            sig.score = min(100, sig.score + 10)

        sig.score_label = (
            "A+" if sig.score >= 90
            else "A" if sig.score >= 75
            else "B" if sig.score >= 50
            else "C"
        )

    return signals
