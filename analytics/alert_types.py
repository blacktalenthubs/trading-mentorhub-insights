"""Canonical alert types + target-computation primitives for the V2 path.

Extracted from `analytics/intraday_rules.py` per Spec 49 FR-407 (amended A1/A2).
The V1 rule-engine body that surrounded these symbols is being deleted; this
module is the single place V2 consumers (tv_webhook, ai_coach, settings,
notifier, alert_store, tv_signal_adapter) import the alert type vocabulary
and the target-computation helpers.

Public surface:
  - AlertType         — str-enum of every alert kind Pine can emit
  - AlertSignal       — dataclass describing one fired alert
  - targets_for_long  — compute (T1, T2) for a LONG entry (was _targets_for_long)
  - targets_for_short — compute (T1, T2) for a SHORT entry (was _targets_for_short)
  - _resistance_ladder, _compute_targets — internal helpers used by the targets
    functions; kept private-named to signal they're not the intended API.

Dependency closure (no `analytics.*` imports):
  - stdlib: dataclasses, enum
  - alert_config: STRUCTURAL_TARGETS_ENABLED, STRUCTURAL_LADDER_DEDUPE_PCT,
                  STRUCTURAL_T1_ATR_MULT, STRUCTURAL_TARGET_T2_MIN_GAP_R
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from alert_config import (
    STRUCTURAL_LADDER_DEDUPE_PCT,
    STRUCTURAL_T1_ATR_MULT,
    STRUCTURAL_TARGET_T2_MIN_GAP_R,
    STRUCTURAL_TARGETS_ENABLED,
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
    MONTHLY_EMA_TOUCH = "monthly_ema_touch"
    # Phase 3b (2026-04-23 evening) — EMA8 / EMA21 added per trader directive.
    # Final EMA set: 8 / 21 / 50 / 100 / 200. EMA_BOUNCE_20 / EMA_RECLAIM_20
    # remain as enum values for DB-historical-row compatibility but are no
    # longer in ENABLED_RULES — they don't fire.
    EMA_BOUNCE_8 = "ema_bounce_8"
    EMA_BOUNCE_21 = "ema_bounce_21"
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
    # Per-symbol consolidation breakout (hourly + 15-min)
    CONSOL_BREAKOUT_LONG = "consol_breakout_long"
    CONSOL_BREAKOUT_SHORT = "consol_breakout_short"
    CONSOL_15M_BREAKOUT_LONG = "consol_15m_breakout_long"
    CONSOL_15M_BREAKOUT_SHORT = "consol_15m_breakout_short"
    # Session low bounce at hourly support → VWAP
    SESSION_LOW_BOUNCE_VWAP = "session_low_bounce_vwap"
    SESSION_HIGH_DOUBLE_TOP = "session_high_double_top"
    INTRADAY_EMA_REJECTION_SHORT = "intraday_ema_rejection_short"
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
    # Phase 3b — EMA8 / EMA21 reclaim variants (final set 8/21/50/100/200).
    EMA_RECLAIM_8 = "ema_reclaim_8"
    EMA_RECLAIM_21 = "ema_reclaim_21"
    EMA_RECLAIM_20 = "ema_reclaim_20"
    EMA_RECLAIM_50 = "ema_reclaim_50"
    EMA_RECLAIM_100 = "ema_reclaim_100"
    EMA_RECLAIM_200 = "ema_reclaim_200"
    # Informational — inside day forming (today's range within yesterday's)
    INSIDE_DAY_FORMING = "inside_day_forming"
    # Phase 5a (2026-04-25) — generic catch-all for TradingView webhook ingest.
    # The specific Pine Script rule (e.g. "rsi_div_bullish_daily") rides in the
    # AlertSignal.message and the alerts table's alert_type column gets the
    # full string `tv_<rule>`. This single enum is for dedup-key continuity.
    TV_WEBHOOK = "tv_webhook"
    # Phase 5b (2026-04-25 evening) — heads-up NOTICE that a daily EMA is
    # acting as overhead resistance. Fires when price is BELOW an EMA within
    # a wider proximity (no rejection candle required — pure context). Not a
    # tradable signal; use it to know an EMA is approaching as resistance.
    EMA_OVERHEAD_RESISTANCE = "ema_overhead_resistance"
    # User-pinned Best Setups picks (fired via "Alert" button on dashboard)
    BEST_SETUP_DAY = "best_setup_day"
    BEST_SETUP_SWING = "best_setup_swing"


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


# ---------------------------------------------------------------------------
# Target-computation primitives — extracted from intraday_rules.py.
# These power the structural T1/T2 calculations used by the V2 tv_webhook
# path. Behind STRUCTURAL_TARGETS_ENABLED flag for fail-open behavior.
# ---------------------------------------------------------------------------


def _resistance_ladder(
    prior_day: dict | None,
    current_price: float,
    emas: dict[str, float | None] | None = None,
    direction: str = "LONG",
    session_high: float | None = None,
    session_low: float | None = None,
    breakout_triggered: bool = False,
) -> list[tuple[float, str]]:
    """Return ordered list of structural levels for target capping.

    For LONG (direction="LONG"): resistance ladder *above* current_price,
        sorted ascending (nearest first).
    For SHORT (direction="SHORT"): support ladder *below* current_price,
        sorted descending (nearest first).

    Sources (LONG):
        - PDH (`prior_day["high"]`)
        - Prior-week high (`prior_day["prior_week_high"]`)
        - Prior-month high (`prior_day["prior_month_high"]`)
        - Daily EMAs (EMA21/50/100/200) above current_price
        - Today's session high — only if breakout_triggered=True
    SHORT mirrors with PDL, prior-week/month low, EMAs below, session low.

    Dedupe: levels within STRUCTURAL_LADDER_DEDUPE_PCT (0.3%) keep only
    the nearest. Keeps first 4 candidates so T1 and T2 have room.
    """
    if prior_day is None or current_price <= 0:
        return []

    is_long = (direction or "LONG").upper() in ("LONG", "BUY")

    candidates: list[tuple[float, str]] = []

    def _add(level: float | None, label: str) -> None:
        if level is None or level <= 0:
            return
        if is_long and level > current_price:
            candidates.append((float(level), label))
        elif (not is_long) and level < current_price:
            candidates.append((float(level), label))

    # Session highs / lows only count when a breakout/breakdown fired — we
    # don't want to cap at today's running high when price is still climbing
    # to set it.
    if breakout_triggered:
        if is_long:
            _add(session_high, "session_high")
        else:
            _add(session_low, "session_low")

    if is_long:
        _add(prior_day.get("high"), "PDH")
        _add(prior_day.get("prior_week_high"), "prior_week_high")
        _add(prior_day.get("prior_month_high"), "prior_month_high")
    else:
        _add(prior_day.get("low"), "PDL")
        _add(prior_day.get("prior_week_low"), "prior_week_low")
        _add(prior_day.get("prior_month_low"), "prior_month_low")

    # Daily EMAs that sit on the far side of entry.
    for label, value in (emas or {}).items():
        _add(value, label)

    # Sort nearest first.
    if is_long:
        candidates.sort(key=lambda pair: pair[0])
    else:
        candidates.sort(key=lambda pair: pair[0], reverse=True)

    # Dedupe within STRUCTURAL_LADDER_DEDUPE_PCT.
    deduped: list[tuple[float, str]] = []
    for price, label in candidates:
        if not deduped:
            deduped.append((price, label))
            continue
        last_price = deduped[-1][0]
        if abs(price - last_price) / last_price <= STRUCTURAL_LADDER_DEDUPE_PCT:
            continue  # same level, skip
        deduped.append((price, label))

    return deduped[:4]


def _compute_targets(
    entry: float,
    stop: float,
    atr_daily: float | None,
    ladder: list[tuple[float, str]],
    direction: str = "LONG",
) -> tuple[float, float]:
    """Hybrid structural / ATR targets — returns (T1, T2) for a signal.

    LONG:
        T1_floor = entry + max(1*risk, 1*ATR)
        T2_floor = entry + max(2*risk, 2*ATR)
        T1 = first resistance >= T1_floor, else T1_floor
        T2 = first resistance > T1 AND >= T2_floor, else T2_floor
        T2 = max(T2, T1 + 0.5*risk)  # force min gap
    SHORT mirrors (entry - max, support ladder, T2 = min gap below T1).

    Fail-open: when ATR is None or ladder is empty, reduces to %-based
    targets that match the old behavior. Never raises.
    """
    is_long = (direction or "LONG").upper() in ("LONG", "BUY")
    risk = abs(entry - stop)
    if risk <= 0:
        # Defensive; caller should have short-circuited already.
        return (round(entry, 2), round(entry, 2))

    atr_val = atr_daily if atr_daily and atr_daily > 0 else risk

    if is_long:
        t1_floor = entry + max(risk, STRUCTURAL_T1_ATR_MULT * atr_val)
        t2_floor = entry + max(2 * risk, 2 * STRUCTURAL_T1_ATR_MULT * atr_val)
    else:
        t1_floor = entry - max(risk, STRUCTURAL_T1_ATR_MULT * atr_val)
        t2_floor = entry - max(2 * risk, 2 * STRUCTURAL_T1_ATR_MULT * atr_val)

    # Pick T1: nearest ladder level that's >= floor (LONG) or <= floor (SHORT).
    t1 = t1_floor
    for price, _ in ladder:
        if is_long and price >= t1_floor:
            t1 = price
            break
        if (not is_long) and price <= t1_floor:
            t1 = price
            break

    # Pick T2: next ladder level beyond T1 that's also >= floor.
    t2 = t2_floor
    for price, _ in ladder:
        if is_long:
            if price > t1 and price >= t2_floor:
                t2 = price
                break
        else:
            if price < t1 and price <= t2_floor:
                t2 = price
                break

    # Guarantee min gap between T1 and T2 (avoid stacked structural levels
    # producing T2 = T1 + $0.10).
    min_gap = STRUCTURAL_TARGET_T2_MIN_GAP_R * risk
    if is_long:
        t2 = max(t2, t1 + min_gap)
    else:
        t2 = min(t2, t1 - min_gap)

    return (round(t1, 2), round(t2, 2))


def targets_for_long(
    entry: float,
    stop: float,
    prior_day: dict | None,
    emas_above: dict[str, float | None] | None = None,
    session_high: float | None = None,
    breakout_triggered: bool = False,
) -> tuple[float, float]:
    """Convenience wrapper — builds the LONG ladder + computes T1/T2.

    Rules call this instead of hardcoded `entry + N*risk`. Falls back to
    %-based targets when STRUCTURAL_TARGETS_ENABLED is false or when the
    ladder / ATR data are unavailable.

    Promoted from `_targets_for_long` per Spec 49 amendment A2 — public
    because `api/app/routers/tv_webhook.py` is a direct V2 consumer.
    """
    risk = entry - stop
    if risk <= 0:
        return (round(entry, 2), round(entry, 2))
    if not STRUCTURAL_TARGETS_ENABLED:
        return (round(entry + risk, 2), round(entry + 2 * risk, 2))
    if prior_day is None:
        return (round(entry + risk, 2), round(entry + 2 * risk, 2))
    atr_daily = prior_day.get("atr_daily")
    ladder = _resistance_ladder(
        prior_day,
        entry,
        emas_above,
        direction="LONG",
        session_high=session_high,
        breakout_triggered=breakout_triggered,
    )
    return _compute_targets(entry, stop, atr_daily, ladder, "LONG")


def targets_for_short(
    entry: float,
    stop: float,
    prior_day: dict | None,
    emas_below: dict[str, float | None] | None = None,
    session_low: float | None = None,
    breakdown_triggered: bool = False,
) -> tuple[float, float]:
    """Convenience wrapper — builds the SHORT support ladder + T1/T2.

    Same fallback behavior as targets_for_long. Promoted from
    `_targets_for_short` per Spec 49 amendment A2.
    """
    risk = stop - entry
    if risk <= 0:
        return (round(entry, 2), round(entry, 2))
    if not STRUCTURAL_TARGETS_ENABLED:
        return (round(entry - risk, 2), round(entry - 2 * risk, 2))
    if prior_day is None:
        return (round(entry - risk, 2), round(entry - 2 * risk, 2))
    atr_daily = prior_day.get("atr_daily")
    ladder = _resistance_ladder(
        prior_day,
        entry,
        emas_below,
        direction="SHORT",
        session_low=session_low,
        breakout_triggered=breakdown_triggered,
    )
    return _compute_targets(entry, stop, atr_daily, ladder, "SHORT")
