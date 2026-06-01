"""Phase 5a (2026-04-25) — TradingView webhook ingest endpoint.

Accepts POST `/tv/webhook` from TradingView's alert webhook system. The body
is parsed by `analytics.tv_signal_adapter.payload_to_alert_signal`, then
pushed through the same pipeline as rule-engine alerts:

    1. (optional) IP allowlist for defense-in-depth
    2. Pydantic validation (returns 400 on bad payload — TV does not retry 4xx)
    3. Adapter conversion → AlertSignal
    4. HTF bias gate (Phase 2) — counter-trend LONG/SHORT suppressed
    5. Phase 4a structural targets (T1/T2 capped at PDH/weekly/EMA above entry)
    6. Level-based dedup (30-min window) against the alerts table
    7. Insert Alert row (per matching user) → notifier.notify() → Telegram

Response is 200 fast; TV retries on 5xx, so we swallow internal errors and
log them rather than letting them propagate. Body validation errors return
400 (TV does NOT retry on 4xx).

Behind env flag `TV_WEBHOOK_ENABLED` (default false). Endpoint returns
503 when disabled so a forgotten TV alert can't accidentally fire.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from alert_config import (
    LEVEL_CONFLUENCE_PCT,
    LEVEL_CONFLUENCE_WINDOW_MIN,
    SYMBOL_SESSION_DEDUP,
    TV_WEBHOOK_ALLOWED_IPS,
    TV_WEBHOOK_ENABLED,
)
from analytics.intraday_rules import AlertType
from analytics.tv_signal_adapter import (
    TVAdapterError,
    payload_to_alert_signal,
)

logger = logging.getLogger("tv_webhook")
router = APIRouter()


# ---------------------------------------------------------------------------
# Confluence twin suppression — when today's open is at PDH/PDL, the
# open-line indicator (`open_reclaimed` / `open_lost`) and the levels-day-vwap
# indicator (`staged_pdh_break` / `staged_pdl_break`) fire on the same bar
# for the same setup. To avoid double-firing Telegram, we track recent fires
# per (symbol, session_date) in memory; whichever twin arrives second gets
# suppressed.
#
# In-memory state is fine here — both twins always arrive within seconds of
# each other (same bar close → same TV webhook batch). Process restart loses
# state, but the 60-min identity dedup on (user, symbol, direction, type)
# still prevents same-alert-type retriggers across restarts.
# ---------------------------------------------------------------------------

_CONFLUENCE_WINDOW = timedelta(minutes=5)
# Key: (symbol, session_date) -> list of (alert_type, fired_at, near_pdh, near_pdl)
_recent_confluence_fires: dict[tuple[str, str], list[tuple[str, datetime, bool, bool]]] = {}


def _prune_confluence(key: tuple[str, str]) -> list[tuple[str, datetime, bool, bool]]:
    """Drop entries older than the confluence window. Returns the live list."""
    now = datetime.utcnow()
    fires = _recent_confluence_fires.get(key, [])
    fires = [t for t in fires if now - t[1] < _CONFLUENCE_WINDOW]
    _recent_confluence_fires[key] = fires
    return fires


def _check_confluence_twin(
    symbol: str,
    session_date: str,
    alert_type: str,
    near_pdh: bool,
    near_pdl: bool,
) -> Optional[str]:
    """Return the twin alert_type if one fired recently and this one should
    be suppressed. None if this alert should proceed normally.

    Twin pairs (within 5 min, same symbol+session):
      • tv_open_reclaimed (near_pdh=true) ↔ tv_staged_pdh_break
      • tv_open_lost      (near_pdl=true) ↔ tv_staged_pdl_break
    """
    fires = _prune_confluence((symbol, session_date))
    if alert_type == "tv_open_reclaimed" and near_pdh:
        for at, _, _, _ in fires:
            if at == "tv_staged_pdh_break":
                return at
    elif alert_type == "tv_staged_pdh_break":
        for at, _, np, _ in fires:
            if at == "tv_open_reclaimed" and np:
                return at
    elif alert_type == "tv_open_lost" and near_pdl:
        for at, _, _, _ in fires:
            if at == "tv_staged_pdl_break":
                return at
    elif alert_type == "tv_staged_pdl_break":
        for at, _, _, npl in fires:
            if at == "tv_open_lost" and npl:
                return at
    return None


def _record_confluence_fire(
    symbol: str,
    session_date: str,
    alert_type: str,
    near_pdh: bool,
    near_pdl: bool,
) -> None:
    """Record this alert in the confluence tracker so a later twin can
    detect it. Only call for alerts that are confluence-eligible (the four
    twin types above). Other alerts can skip this."""
    if alert_type not in (
        "tv_open_reclaimed",
        "tv_open_lost",
        "tv_staged_pdh_break",
        "tv_staged_pdl_break",
    ):
        return
    key = (symbol, session_date)
    _recent_confluence_fires.setdefault(key, []).append(
        (alert_type, datetime.utcnow(), near_pdh, near_pdl)
    )


# ---------------------------------------------------------------------------
# Spec 58 — confluence annotation (2026-05-22)
# ---------------------------------------------------------------------------
# When an entry's support level clusters within CONFLUENCE_BAND_PCT % of
# another support (a second MA, a prior high/low, or a monthly AVWAP), we
# flag the confluence INLINE in the alert message — never as a second alert.
# Pure functions; no I/O. The Pine script passes `nearby_levels` in the
# webhook payload; this module checks them against the entry level.
# Validation examples (2026-05-22):
#   AVGO  — EMA 21 $413.02 confluent with PDL $410.50 (0.61% spread)
#   AAOI  — EMA 21 $171.47 confluent with weekly 21 EMA (~$171, sub-1%)
#   NVDA  — MTD $217.02 NOT confluent with PM $205.10 (5.6% spread, outside band)
# ---------------------------------------------------------------------------

CONFLUENCE_BAND_PCT = 1.0  # % distance within which two levels count as confluent


# ---------------------------------------------------------------------------
# Futures session-window filter (spec 2026-05-24)
# ---------------------------------------------------------------------------
# Globex (CME's electronic session) runs Sun 5pm CT → Fri 4pm CT — 23 hours
# a day. Most overnight fires are algorithmic noise; the actionable window
# for a discretionary trader is roughly European-mature → US RTH close.
#
# Window: 04:00 – 16:00 America/New_York, Monday-Friday only.
#   • 04:00 ET = European session is mature, US pre-market is starting
#   • 16:00 ET = US stock close + futures cool-down
#   • Mon-Fri = no Sunday-night/weekend chop (futures DO trade Sun 5pm CT
#     onwards, but we treat that as outside the practical attention window;
#     can expand later if it proves valuable)
#
# Stocks already self-gate to RTH via Pine alert config. Crypto is left
# 24/7 per user preference (could be added to this list if BTC/ETH overnight
# chop becomes intolerable post-Monday data).
FUTURES_SESSION_SYMBOLS: frozenset[str] = frozenset({
    "ES1!", "NQ1!", "MES1!", "MNQ1!",
})


def is_outside_session_window(symbol: str, now: Optional[datetime] = None) -> bool:
    """Returns True if a futures symbol's alert fires outside the trading window.

    For symbols in FUTURES_SESSION_SYMBOLS, suppress alerts outside of
    04:00 – 16:00 America/New_York, Mon-Fri. All other symbols always
    return False (no window applied — they use their own existing routing).

    `now` is optional for testability — defaults to current ET time.
    """
    if symbol not in FUTURES_SESSION_SYMBOLS:
        return False
    try:
        from zoneinfo import ZoneInfo
        et = ZoneInfo("America/New_York")
    except ImportError:
        # Py < 3.9 fallback — unlikely in our env, but defensive
        return False
    if now is None:
        now = datetime.now(et)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=et)
    now_et = now.astimezone(et)
    # weekday(): Mon=0 … Sun=6
    if now_et.weekday() >= 5:  # Saturday or Sunday
        return True
    return now_et.hour < 4 or now_et.hour >= 16


def is_basing_chop(
    stage: Optional[str],
    vwap_slope_pct: Optional[float],
) -> bool:
    """Spec 58 (2026-05-24) — pure basing/chop regime detection.

    Returns True iff BOTH signals agree the regime is "WAIT, no edge":
      • stage classifier contains 'BASING' (Pine's day-type machine)
      • |vwap_slope_pct| < 0.3 (VWAP essentially flat — no directional bias)

    Refined 2026-05-24: dropped the `inside_day` requirement after user
    observation that inside-day is too common a flag — many real PDL/PWL
    holds happen on inside days. Inside-day alone isn't noise; only when
    the stage AND the VWAP both say "no momentum" do we suppress.

    Originated from the BTC 2026-05-23 case: 12+ staged_pwl_held alerts
    fired in basing chop over 70 minutes because price kept wicking PWL
    by pennies. The payload already encoded the regime ('STAGE 1: BASING
    — inside range + VWAP flat — WAIT — sweeps only') — we just hadn't
    used it to gate.

    Missing data (Pine pre-spec-58 sending no stage / no vwap_slope) →
    returns False (let alert through, backward compat).
    """
    if not stage or "BASING" not in stage:
        return False
    if vwap_slope_pct is None:
        return False
    if abs(vwap_slope_pct) >= 0.3:
        return False
    return True


def is_uptrend_gate_rejected(
    alert_type: str,
    direction: Optional[str],
    uptrend_pass: Optional[bool],
) -> bool:
    """Spec 58 (FR-001 / FR-003, refined 2026-05-23) — uptrend gate predicate.

    Returns True iff the alert should be rejected for failing the gate.

    Only **MA-based BUY entries** (alert types prefixed `tv_ma_`) are gated
    by `uptrend_pass=False`. Level-based BUYs (PDH/PDL/PWH/PWL/PMH/PML
    reclaim or hold) pass through regardless of MA stack — per the
    refinement, downtrend stocks remain tradeable via levels with the
    overhead MAs acting as targets / resistance.

    Backward-compat: `uptrend_pass=None` (legacy Pine sending no field)
    is treated as "let through" so a Pine rollback doesn't kill delivery.
    """
    if uptrend_pass is not False:
        return False  # legacy (None) or explicit True → pass
    if not alert_type.startswith("tv_ma_"):
        return False  # level-based — refined FR-003, fires in any regime
    if (direction or "").upper() != "BUY":
        return False  # shorts / NOTICEs not in spec-58 scope
    if alert_type.endswith("_short_v3"):
        return False  # belt-and-suspenders against mis-tagged shorts
    return True


def find_confluences(
    entry_level: float, nearby_levels: list[dict]
) -> list[dict]:
    """Return the subset of nearby_levels within CONFLUENCE_BAND_PCT of
    entry_level. The entry's own level (exact value match) is filtered out
    so the EMA 21 alert doesn't list "confluent with EMA 21".

    Each input level is a dict with at least {"value": float, "label": str}
    (and typically "kind": str). The returned list preserves the input shape.
    """
    if not entry_level or not nearby_levels:
        return []
    band = abs(entry_level) * (CONFLUENCE_BAND_PCT / 100.0)
    out: list[dict] = []
    for lvl in nearby_levels:
        v = lvl.get("value") if isinstance(lvl, dict) else None
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if v == float(entry_level):
            continue  # the entry's own level
        if abs(v - float(entry_level)) <= band:
            out.append(lvl)
    return out


def format_confluence_annotation(confluences: list[dict]) -> str:
    """Render the confluence list as a single-line annotation. Returns ""
    when empty (caller appends nothing). Example output:
        Confluence: PDL ($410.50), MTD AVWAP ($420.92)
    """
    if not confluences:
        return ""
    parts: list[str] = []
    for c in confluences:
        label = c.get("label") or c.get("kind") or "level"
        try:
            value = float(c.get("value"))
        except (TypeError, ValueError):
            continue
        parts.append(f"{label} (${value:.2f})")
    if not parts:
        return ""
    return "Confluence: " + ", ".join(parts)


# ---------------------------------------------------------------------------
# Cross-level confluence dedup (2026-05-16)
# ---------------------------------------------------------------------------
# When a level alert fires on a symbol, suppress any same-side level alert
# that arrives within LEVEL_CONFLUENCE_WINDOW_MIN minutes AND within
# LEVEL_CONFLUENCE_PCT % of the first alert's entry price.
#
# Side detection: alert_type containing _pdh_/_pwh_/_pmh_ → "high" (resistance
# events); _pdl_/_pwl_/_pml_ → "low" (support events). First-fires-wins.
#
# Key: (symbol, side) where side ∈ {"high", "low"}
# Value: list of (alert_type, entry_price, fired_at)
#
# Example (MSTR Friday): PDL $174.64 reclaim @ entry $175.28 fires first.
# 30 min later PWL $175.72 reclaim @ entry $176 arrives — within 1% of $175.28
# AND within 30 min — suppressed. EOD report still logs the suppression for
# audit ("PDL reclaim delivered · PWL reclaim stacked-suppressed").
# ---------------------------------------------------------------------------

_recent_level_fires: dict[
    tuple[str, str],
    list[tuple[str, float, datetime]],
] = {}


def _level_side(alert_type: str) -> Optional[str]:
    """Return 'high' for *h_break/rejection/failed_short, 'low' for
    *l_reclaim/break. None for non-level alerts (open-line, MA, VWAP,
    proximity NOTICEs, hold/wick_reclaim which fire per-level already)."""
    if not alert_type.startswith("tv_staged_"):
        return None
    # tv_staged_pdh_break / tv_staged_pwh_break / tv_staged_pmh_break / *_rejection / *_failed_short
    if "_pdh_" in alert_type or "_pwh_" in alert_type or "_pmh_" in alert_type:
        return "high"
    if "_pdl_" in alert_type or "_pwl_" in alert_type or "_pml_" in alert_type:
        return "low"
    return None


def _check_level_confluence(
    symbol: str,
    side: str,
    entry: float,
    alert_type: str,
) -> Optional[dict]:
    """If a prior same-side level alert fired on this symbol within the
    confluence window AND within the proximity %, return suppression info.
    None means this alert should proceed normally."""
    if entry is None or entry == 0:
        return None
    key = (symbol, side)
    now = datetime.utcnow()
    window = timedelta(minutes=LEVEL_CONFLUENCE_WINDOW_MIN)
    pct = LEVEL_CONFLUENCE_PCT / 100.0

    fires = _recent_level_fires.get(key, [])
    # Prune expired
    fires = [(at, ep, t) for (at, ep, t) in fires if now - t < window]
    _recent_level_fires[key] = fires

    for prior_type, prior_entry, prior_time in fires:
        if prior_entry == 0 or prior_type == alert_type:
            continue  # identity dedup handles same-type re-fires
        if abs(entry - prior_entry) / prior_entry > pct:
            continue  # too far apart price-wise
        return {
            "winner_type": prior_type,
            "winner_entry": prior_entry,
            "winner_time": prior_time,
            "spread_pct": abs(entry - prior_entry) / prior_entry * 100.0,
        }
    return None


def _record_level_fire(
    symbol: str,
    side: Optional[str],
    entry: float,
    alert_type: str,
) -> None:
    """Track this level-alert fire so later same-side alerts on the same
    symbol can dedup against it."""
    if side is None or entry is None or entry == 0:
        return
    key = (symbol, side)
    _recent_level_fires.setdefault(key, []).append(
        (alert_type, entry, datetime.utcnow())
    )


# ---------------------------------------------------------------------------
# Spec 60 — generic same-bar confluence collapser. Existing twin
# (_check_confluence_twin) handles open-line + level pairs; level confluence
# (_check_level_confluence) handles same-side level pairs. This NEW
# collapser handles the residual case: different rule families firing on
# the same symbol within 10 min (e.g., PDH break + VWAP reclaim + MA
# bounce all triggering on the same breakout candle). First-fires-wins;
# later alerts persisted unrouted with suppressed_reason=
# "confluence_collapsed:<prior_type>" so EOD review still shows them.
# Env-tunable. Default 10 min window matches Pine bar interval.
# ---------------------------------------------------------------------------

_same_bar_fires: dict[str, list[tuple[str, datetime]]] = {}  # symbol → [(type, time)]


def _check_same_bar_collapse(
    symbol: str, alert_type_full: str
) -> Optional[dict]:
    """Look for any OTHER rule that fired for this symbol within the
    collapse window. Returns prior fire info if found."""
    if os.environ.get("V2_SAME_BAR_COLLAPSE_ENABLED", "true").lower() in ("0", "false", "no"):
        return None
    try:
        win_min = int(_envf("V2_SAME_BAR_COLLAPSE_MIN", 10))
    except Exception:
        win_min = 10
    now = datetime.utcnow()
    window = timedelta(minutes=win_min)
    fires = _same_bar_fires.get(symbol, [])
    # Prune expired
    fires = [(t_at, t_time) for (t_at, t_time) in fires if now - t_time < window]
    _same_bar_fires[symbol] = fires
    for prior_type, prior_time in fires:
        if prior_type == alert_type_full:
            continue  # identity dedup handles same-type re-fires
        return {
            "prior_type": prior_type,
            "prior_time": prior_time,
            "minutes_ago": (now - prior_time).total_seconds() / 60.0,
        }
    return None


def _record_same_bar_fire(symbol: str, alert_type_full: str) -> None:
    """Track this fire for the generic same-bar collapser."""
    _same_bar_fires.setdefault(symbol, []).append(
        (alert_type_full, datetime.utcnow())
    )


# ---------------------------------------------------------------------------
# Pydantic schema — matches the JSON template in pine_scripts/.
# ---------------------------------------------------------------------------


class TVWebhookPayload(BaseModel):
    """Schema TradingView Pine Script alerts must POST to /tv/webhook.

    Required: symbol, price, rule, direction.
    Optional: exchange, interval, high, low, volume, entry, stop,
              target_1, target_2, fired_at.
    """

    symbol: str = Field(..., min_length=1, max_length=30)
    price: str = Field(..., description="String per TV's payload format")
    rule: str = Field(..., min_length=1, max_length=80)
    direction: str = Field(default="NOTICE")
    exchange: Optional[str] = ""
    interval: Optional[str] = ""
    high: Optional[str] = None
    low: Optional[str] = None
    volume: Optional[str] = None
    entry: Optional[str] = None
    stop: Optional[str] = None
    target_1: Optional[str] = None
    target_2: Optional[str] = None
    fired_at: Optional[str] = None
    # Staged indicator extras — drive Telegram formatting for TV-native alerts
    stage: Optional[str] = None
    vwap: Optional[str] = None
    vwap_slope_pct: Optional[str] = None
    above_vwap: Optional[str] = None
    ma_tag: Optional[str] = None
    # v2 Pine order-flow extras (volume confirmation + CVD divergence)
    volume_ratio: Optional[str] = None
    cvd_delta: Optional[str] = None
    cvd_diverging: Optional[str] = None
    # 2026-05-05 Pine batch (C1 + C2): gap-and-go context + weekly levels.
    # Strings per TV's payload format. Telegram template work to surface
    # these is deferred — fields are accepted now so they're available
    # downstream when the formatter is updated.
    gap_context: Optional[str] = None
    pwh: Optional[str] = None
    pwl: Optional[str] = None
    # 2026-05-06: confluence_count = number of timeframe levels (PDH/PWH/PMH
    # or PDL/PWL/PML) stacked within 1% of the broken/reclaimed level.
    # 1 = single-level event, 2 = two stacked, 3 = full confluence.
    # Higher count = stronger institutional memory at that price = bigger
    # conviction for execution.
    confluence_count: Optional[str] = None
    # 2026-05-13: open-line confluence flags. `near_pdh` = today_open within
    # 0.3% of PDH (gap-up scenario where open_reclaimed and staged_pdh_break
    # fire on the same setup). `near_pdl` = today_open within 0.3% of PDL.
    # Used by twin-alert suppression — see _check_confluence_twin().
    near_pdh: Optional[str] = None
    near_pdl: Optional[str] = None
    # 2026-05-14: inside_day = today_open is between yesterday's PDH and PDL
    # (no gap). Inside days tend to range — triage agent uses this to
    # degrade conviction since directional setups have lower hit rate.
    inside_day: Optional[str] = None
    today_open: Optional[str] = None


# ---------------------------------------------------------------------------
# Alert Quality v2 — pipeline-side gates (spec 60-alert-quality-v2)
# ---------------------------------------------------------------------------
# All thresholds env-tunable so we can iterate without redeploys. Defaults
# come straight from today's CSV analysis. The principle: every rule has
# a slope gate (threshold differs by trade thesis: positive for continuation,
# non-freefall for support reversal). Volume floors are asymmetric — tighter
# for continuation rules, looser for level-defense rules where structural
# stop limits downside.

def _envf(name: str, default: float) -> float:
    """Read a float env var with a default fallback."""
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# Volume floors — alert_type suffix (after 'tv_') → minimum volume_ratio.
# Resistance-side and continuation rules require real participation.
# Support-side rules have lower floors because tight structural stop
# already limits loss.
def _volume_floor(alert_type_full: str) -> float:
    name = alert_type_full.replace("tv_", "", 1)
    # Continuation family — pullback, MA bounce. (FR-001, FR-017)
    if name == "pullback_long" or name.startswith("ma_bounce_long_v3"):
        return _envf("V2_VOL_FLOOR_PULLBACK", 1.2)
    # Resistance break (P2b — once Pine emits these). Already gated in Pine
    # logic; soft floor here as defense in depth.
    if name.startswith("staged_") and "_break" in name:
        return _envf("V2_VOL_FLOOR_BREAK", 2.0)
    # Gap-and-go (P2c — Pine work). Soft floor in pipeline.
    if name == "gap_up_continuation_long":
        return _envf("V2_VOL_FLOOR_GAP", 1.5)
    # AVWAP-family defense (P2.6, FR-013) — soft floor.
    if "_avwap_held" in name:
        return _envf("V2_VOL_FLOOR_AVWAP_HELD", 1.0)
    # Former-resistance defense from above (PDH/PWH/PMH held).
    if name in ("staged_pdh_held", "staged_pwh_held", "staged_pmh_held"):
        return _envf("V2_VOL_FLOOR_HIGH_HELD", 1.2)
    # Support defense from above (PDL/PWL/PML held). Lower floor — level
    # IS the risk control (FR-018).
    if name in ("staged_pdl_held", "staged_pwl_held", "staged_pml_held"):
        return _envf("V2_VOL_FLOOR_LOW_HELD", 0.8)
    # Support recovery (PDL/PWL/PML reclaim) — LOOSENED 2026-06-01 per
    # founder request: at support, both volume and VWAP slope can be weak
    # (the nature of a quiet bounce). Previously 1.0× floor was dropping
    # legitimate support bounces. Grading (A/B/C) still labels quality so
    # the user can triage in-feed without delivery being silently gated.
    # Env-overridable to re-tighten when noise becomes an issue.
    if name in ("staged_pdl_reclaim", "staged_pwl_reclaim", "staged_pml_reclaim"):
        return _envf("V2_VOL_FLOOR_LOW_RECLAIM", 0.3)
    # Prior-high reclaim (PDH/PWH/PMH) — 2026-06-01. Continuation setup:
    # gap above the high, retest, reclaim. Volume usually solid on these
    # because the gap-up days already have heat, so the floor is tighter
    # than the low-side reclaim. Tunable.
    if name in ("staged_pdh_reclaim", "staged_pwh_reclaim", "staged_pmh_reclaim"):
        return _envf("V2_VOL_FLOOR_HIGH_RECLAIM", 1.0)
    # Unknown / NOTICE — don't gate.
    return 0.0


# Slope thresholds — per trade thesis. Continuation = positive; reversal
# (low-side defense) = non-freefall floor. Master tuning knob.
def _slope_min(alert_type_full: str) -> Optional[float]:
    name = alert_type_full.replace("tv_", "", 1)
    # Continuation rules — slope must be positive.
    if name == "pullback_long" or name.startswith("ma_bounce_long_v3"):
        return _envf("V2_SLOPE_MIN_CONTINUATION", 0.05)
    if name.startswith("staged_") and "_break" in name:
        return _envf("V2_SLOPE_MIN_BREAK", 0.05)
    if name == "gap_up_continuation_long":
        return _envf("V2_SLOPE_MIN_GAP", 0.05)
    if "_avwap_held" in name:
        return _envf("V2_SLOPE_MIN_AVWAP", 0.05)
    if name in ("staged_pdh_held", "staged_pwh_held", "staged_pmh_held"):
        return _envf("V2_SLOPE_MIN_HIGH_HELD", 0.05)
    # Reversal — support defense. Inverted floor (slope can be negative,
    # just not freefall). (FR-018)
    if name in ("staged_pdl_held", "staged_pwl_held", "staged_pml_held"):
        return _envf("V2_SLOPE_MIN_LOW_HELD", -0.5)
    # Support recovery — LOOSENED 2026-06-01 per founder request. At
    # support, slope often weak even on legitimate bounces (buyers just
    # stepping in, momentum hasn't built yet). Previous -0.3 floor was
    # silently dropping reclaim alerts with mildly negative slope.
    # Env-overridable to re-tighten later if noise becomes an issue.
    if name in ("staged_pdl_reclaim", "staged_pwl_reclaim", "staged_pml_reclaim"):
        return _envf("V2_SLOPE_MIN_LOW_RECLAIM", -1.0)
    # Prior-high reclaim — continuation setup. After a gap-up retest,
    # slope is usually still positive going into the reclaim. Floor mirrors
    # the break family.
    if name in ("staged_pdh_reclaim", "staged_pwh_reclaim", "staged_pmh_reclaim"):
        return _envf("V2_SLOPE_MIN_HIGH_RECLAIM", 0.0)
    # Unknown — don't gate on slope.
    return None


def _v2_quality_suppress(sig, alert_type_full: str) -> bool:
    """Return True when the alert fails v2 quality gates and should be
    persisted-but-not-delivered. False if it passes (or if the rule type
    doesn't have v2 gates configured, or the necessary fields are absent
    in the payload — we fail OPEN so missing data doesn't kill legitimate
    fires while Pine catches up to emit new fields).

    Master kill switch: set V2_QUALITY_GATE_ENABLED=false to disable.
    """
    if os.environ.get("V2_QUALITY_GATE_ENABLED", "true").lower() in ("0", "false", "no"):
        return False

    # Volume gate
    vr = getattr(sig, "_tv_volume_ratio", None)
    floor_v = _volume_floor(alert_type_full)
    if vr is not None and floor_v > 0 and float(vr) < floor_v:
        return True

    # Slope gate — skip when the payload doesn't carry slope (e.g., today's
    # pullback_long is missing it until Pine update FR-005). Don't fail
    # closed in that case — let the volume floor do the work alone.
    slope = getattr(sig, "_tv_vwap_slope_pct", None)
    floor_s = _slope_min(alert_type_full)
    if slope is not None and floor_s is not None and float(slope) < floor_s:
        return True

    return False


# ---------------------------------------------------------------------------
# IP allowlist helper (off by default).
# ---------------------------------------------------------------------------


def _is_allowed_ip(client_ip: str) -> bool:
    """Return True when allowlist is empty (off) or client_ip is on it."""
    if not TV_WEBHOOK_ALLOWED_IPS:
        return True
    allowed = {ip.strip() for ip in TV_WEBHOOK_ALLOWED_IPS.split(",") if ip.strip()}
    return client_ip in allowed


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/webhook")
async def tv_webhook(
    payload: TVWebhookPayload,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Ingest a TradingView alert and route it through the alerting pipeline.

    FAST RESPONSE (2026-05-20): TradingView times the webhook out at ~3s.
    The heavy pipeline — fetch_prior_day (yfinance), dedup, DB persist,
    Telegram notify — used to run synchronously here and routinely blew past
    3s under alert bursts, so TV marked deliveries "failed — timed out" and
    the alert was lost before reaching the backend. Now the handler only does
    the fast bits (validate, IP check, adapter parse) and hands the rest to a
    background task that runs AFTER the 200 is sent.

    Returns 200 on accepted, 400 on bad payload, 403 on disallowed IP,
    503 when feature is disabled.
    """
    if not TV_WEBHOOK_ENABLED:
        # 503 because the route is wired but not active. Differentiates from
        # a missing route (404) for easier debugging.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TV webhook ingest is disabled (set TV_WEBHOOK_ENABLED=true)",
        )

    client_ip = request.client.host if request.client else "unknown"
    if not _is_allowed_ip(client_ip):
        logger.warning("TV webhook: denied IP %s (allowlist active)", client_ip)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="source IP not allowed",
        )

    try:
        sig = payload_to_alert_signal(payload.model_dump())
    except TVAdapterError as e:
        logger.warning("TV webhook: bad payload from %s — %s", client_ip, e)
        raise HTTPException(status_code=400, detail=str(e)) from e

    logger.info(
        "TV webhook accepted: symbol=%s rule=%s direction=%s price=%.4f from=%s",
        sig.symbol, getattr(sig, "_tv_rule", "?"),
        sig.direction, float(sig.price), client_ip,
    )

    # Heavy pipeline runs AFTER the response is sent — keeps the webhook fast
    # so TradingView never times out. See _dispatch_background.
    background_tasks.add_task(_dispatch_background, sig)
    return {"accepted": True, "queued": True}


async def _dispatch_background(sig) -> None:
    """Background wrapper around _dispatch_signal. The HTTP 200 is already
    sent by the time this runs, so any error is logged, never raised — there
    is no response left to attach it to."""
    try:
        await _dispatch_signal(sig)
    except Exception:
        logger.exception(
            "TV webhook: background dispatch failed for %s",
            getattr(sig, "symbol", "?"),
        )


async def _dispatch_signal(sig) -> dict[str, Any]:
    """Apply HTF gate + structural targets + level dedup, then persist + notify.

    Pipeline mirrors api/app/background/monitor.py epilogue (Phase 1–4) but
    operates on a single signal from a single source rather than the full
    poll loop. Same DB tables, same notifier, same dedup semantics.
    """
    from app.database import async_session_factory  # local import to avoid cycle
    from app.models.alert import Alert
    from app.models.user import User
    from analytics.htf_bias import (
        HTFBias,
        compute_htf_bias,
        confluence_score,
    )
    from analytics.intraday_data import (
        fetch_intraday,
        fetch_intraday_crypto,
        fetch_prior_day,
    )
    from analytics.intraday_rules import _targets_for_long, _targets_for_short
    from config import is_crypto_alert_symbol

    is_crypto = is_crypto_alert_symbol(sig.symbol)

    # 1. Pull prior_day for structural target computation.
    # fetch_prior_day is a synchronous yfinance call (1-5s). Run it in a
    # worker thread so it doesn't block the event loop — otherwise one
    # background dispatch would stall every other webhook's response during
    # a burst and re-trip TradingView's timeout.
    try:
        prior_day = await asyncio.to_thread(
            fetch_prior_day, sig.symbol, is_crypto=is_crypto
        )
    except Exception:
        logger.exception("TV webhook: fetch_prior_day failed for %s", sig.symbol)
        prior_day = None

    # 2. HTF bias / confluence — RULE-ENGINE concept. Skipped for TV alerts:
    # the user is moving away from rule-engine logic. TV signals are driven
    # purely by what the Pine script emits (stage, VWAP slope). Adding HTF
    # confluence here would mix paradigms.
    bias = HTFBias()  # neutral default — passed through but not surfaced in Telegram

    direction = (sig.direction or "").upper()

    # 2b. Routing gate — A1 (SPY 8/21 long-bias suppresses non-SPY shorts) +
    # A2 (SPY shorts only ACTION on whitelist; others → NOTICE). LONG and
    # NOTICE alerts pass through unchanged.
    deliver, downgrade = await _route_alert(sig)
    if not deliver:
        logger.info(
            "TV routing: SUPPRESSED %s/%s rule=%s (long-bias mode, non-SPY short)",
            sig.symbol, sig.direction, getattr(sig, "_tv_rule", "?"),
        )
        return {"dispatched": False, "reason": "routing_suppressed_long_bias"}
    if downgrade:
        logger.info(
            "TV routing: DOWNGRADED %s/%s rule=%s → %s",
            sig.symbol, sig.direction, getattr(sig, "_tv_rule", "?"), downgrade,
        )
        sig.direction = downgrade
        direction = downgrade  # keep local var in sync for downstream branches

    # 3. Phase 4a structural targets if Pine Script didn't supply them.
    # Staged Pine always supplies entry/stop/T1/T2, so this only fills gaps
    # for older Pine scripts or non-staged rules.
    if direction in ("BUY", "LONG") and sig.entry and not (sig.target_1 and sig.target_2):
        stop = sig.stop if sig.stop else round(sig.entry * 0.995, 2)
        sig.stop = stop
        t1, t2 = _targets_for_long(sig.entry, stop, prior_day)
        sig.target_1, sig.target_2 = t1, t2
    elif direction == "SHORT" and sig.entry and not (sig.target_1 and sig.target_2):
        stop = sig.stop if sig.stop else round(sig.entry * 1.005, 2)
        sig.stop = stop
        t1, t2 = _targets_for_short(sig.entry, stop, prior_day)
        sig.target_1, sig.target_2 = t1, t2

    # 4. Stamp confluence score (Phase 2) — kept for non-TV consumers, but
    # the Telegram formatter ignores it on TV alerts (see _format_tv_body).
    sig._confluence_score = confluence_score(direction, bias)

    # 5. Persist + notify per user. Mirrors api/app/background/monitor.py:857
    # — each user gets their own Alert row AND their own Telegram delivery
    # via user.telegram_chat_id. The broadcast `notify()` doesn't work
    # because TELEGRAM_CHAT_ID env var isn't set on Railway in favor of
    # per-user IDs in the DB.
    persisted = 0
    notified = 0
    session_date = date.today().isoformat()
    # Identity dedup keys on (user, symbol, direction, alert_type) where
    # alert_type carries the MA tag. Default window 60 min (was 4hrs).
    #
    # Pine v3 state machine was stripped 2026-05-04 — all qualifying bars
    # now fire alert(). Backend dedup is the sole rate-limiter, so the
    # window has to balance "catch genuine multi-cross events" against
    # "don't spam on chop". 60 min lets a long bounce + short rejection
    # an hour apart both fire, while a same-direction repeat 30 min later
    # gets suppressed. Tune here without redeploying Pine.
    #
    # Per-alert-type overrides:
    #   tv_open_reclaimed → 90 min. Pine re-arms after fire so a true
    #   second lose-reclaim cycle later in the session can fire — 90-min
    #   window collapses chop while letting distinct legs through.

    # Build alert_type with MA-tag suffix so each MA is its own dedup key.
    # ma_tag "100E" -> "_ema100", "8E21E" -> "_ema8_ema21", "" -> "".
    # Computed once per signal — same across all subscribed users.
    rule_name = getattr(sig, "_tv_rule", "webhook")
    alert_type_full = f"tv_{rule_name}{_ma_tag_to_suffix(getattr(sig, '_tv_ma_tag', ''))}"[:100]

    # ---------------------------------------------------------------
    # Per-type enablement (2026-05-21) — the alert_type_config table.
    # ---------------------------------------------------------------
    # The Pine scripts fire every alert they can; this table decides what
    # is actually delivered, so each type is enabled/tested independently
    # from Settings > Alert Types. A DB-read failure falls back to the
    # static allow-list so delivery never goes fully dark.
    try:
        from app.models.alert_type_config import AlertTypeConfig
        async with async_session_factory() as _cfg_db:
            _cfg_rows = (await _cfg_db.execute(
                select(AlertTypeConfig.alert_type, AlertTypeConfig.enabled)
            )).all()
        enabled_types: Optional[set[str]] = {at for at, en in _cfg_rows if en}
        known_types: Optional[set[str]] = {at for at, _ in _cfg_rows}
    except Exception:
        logger.exception("TV webhook: alert_type_config read failed — static fallback")
        enabled_types = None
        known_types = None

    if not _is_allowed_alert_type(alert_type_full, enabled_types):
        # Known type, just toggled OFF → record it (deduped) for EOD review:
        # no Telegram, hidden from the live feed, and NOT run through the
        # twin/level dedup so the routed pipeline's state stays clean.
        # Unknown type (stale chart, typo) → drop entirely.
        if _is_allowed_alert_type(alert_type_full, known_types):
            logger.info(
                "TV webhook: type %s not routed — recording for review (%s)",
                alert_type_full, sig.symbol,
            )
            return await _persist_unrouted(sig, alert_type_full, session_date)
        logger.info(
            "TV webhook: unknown type %s dropped for %s",
            alert_type_full, sig.symbol,
        )
        return {"dispatched": False, "reason": "unknown_type"}

    # ──────────────────────────────────────────────────────────────────
    # Spec 58 — uptrend gate enforcement (FR-001 / FR-003, refined 2026-05-23)
    # ──────────────────────────────────────────────────────────────────
    # The uptrend gate applies ONLY to MA-based entries (`tv_ma_*` family).
    # Level-based entries (PDH/PDL/PWH/PWL/PMH/PML reclaim / held) MAY fire
    # regardless of MA stack — in downtrend regimes the trader plays the
    # levels with the overhead MAs as targets / resistance, not as entry
    # blockers (FR-003 refined). SWMR / PLTR case from 2026-05-22 — they
    # have overhead MA stacks but valid level plays the user wants to take.
    #
    # Pine already gates MA-bounce on uptrend_pass=true; this is belt-and-
    # suspenders against a Pine-side regression. Backward-compat: legacy
    # alerts with no `uptrend_pass` field treated as None → let through.
    _uptrend_pass = getattr(sig, "_tv_uptrend_pass", None)
    if is_uptrend_gate_rejected(alert_type_full, sig.direction, _uptrend_pass):
        _overhead = getattr(sig, "_tv_overhead_mas", []) or []
        logger.info(
            "TV webhook: uptrend gate rejected %s for %s — overhead MAs: %s",
            alert_type_full, sig.symbol,
            ", ".join(_overhead) or "(none reported)",
        )
        return await _persist_unrouted(
            sig, alert_type_full, session_date,
            suppressed_reason="uptrend_gate_failed",
        )

    # ──────────────────────────────────────────────────────────────────
    # Spec 58 — basing-chop filter (2026-05-24, refined drop inside_day)
    # ──────────────────────────────────────────────────────────────────
    # Suppress staged_* level entries when BOTH signals agree the regime
    # is pure chop: stage='BASING' AND |vwap_slope_pct| < 0.3.
    # The alert still records (suppressed_reason='basing_chop') so the
    # 'Not routed' filter surfaces it for EOD review — just no Telegram.
    # Scoped to staged_* (level + AVWAP) BUY alerts; MA bounces have their
    # own uptrend gate and can still be valid in slow grinds.
    if (
        (sig.direction or "").upper() == "BUY"
        and alert_type_full.startswith("tv_staged_")
        and is_basing_chop(
            getattr(sig, "_tv_stage", ""),
            getattr(sig, "_tv_vwap_slope_pct", None),
        )
    ):
        logger.info(
            "TV webhook: basing-chop suppressed %s for %s (stage=%s, vwap_slope=%.2f)",
            alert_type_full, sig.symbol,
            getattr(sig, "_tv_stage", "")[:40],
            getattr(sig, "_tv_vwap_slope_pct", 0) or 0,
        )
        return await _persist_unrouted(
            sig, alert_type_full, session_date,
            suppressed_reason="basing_chop",
        )

    # ──────────────────────────────────────────────────────────────────
    # Alert Quality v2 — asymmetric volume + slope gates (spec 60)
    # ──────────────────────────────────────────────────────────────────
    # Pipeline-side filters based on today's 679-alert data analysis.
    # Each rule family has its own threshold reflecting its trade thesis:
    #   • Continuation rules need positive slope + volume floor
    #   • Reversal rules (PDL/PWL/PML *_held / *_reclaim) need
    #     non-freefall slope (≥ −0.5%) + lower volume floor
    # Every threshold is an env var so we tune from data without redeploys.
    # 2026-06-01 — v2 quality gate DISABLED per founder request. The gate
    # was blocking too much legitimate data while we're still in the
    # validation phase. Re-enable later once we've tuned thresholds from
    # observed data. The helper _v2_quality_suppress + _volume_floor +
    # _slope_min remain defined so re-enabling is one-line uncomment.
    # if _v2_quality_suppress(sig, alert_type_full):
    #     return await _persist_unrouted(
    #         sig, alert_type_full, session_date,
    #         suppressed_reason="v2_quality_gate",
    #     )

    # ──────────────────────────────────────────────────────────────────
    # Futures session-window filter (2026-05-24)
    # ──────────────────────────────────────────────────────────────────
    # /ES /NQ and their micros trade 23 hr/day. Suppress alerts outside
    # 04:00–16:00 ET Mon-Fri so overnight Asian/Sunday-night chop doesn't
    # blow up Telegram. Suppressed alerts still persist (unrouted), visible
    # in the 'Not routed' feed for review.
    if is_outside_session_window(sig.symbol):
        logger.info(
            "TV webhook: outside session suppressed %s for %s",
            alert_type_full, sig.symbol,
        )
        return await _persist_unrouted(
            sig, alert_type_full, session_date,
            suppressed_reason="outside_session",
        )

    # Alert types that bypass SYMBOL_SESSION_DEDUP. These are either
    # genuinely-fresh signals on the same symbol (Pine re-arms internally)
    # or structural-level events whose meaning is independent of any
    # open-line alert that fired earlier in the session.
    #   • tv_open_reclaimed   → Pine re-arms; multi-leg reclaim days
    #   • tv_open_wick_reclaim → distinct signal from open_held (wick
    #                            actually crossed below); user wants both
    #   • tv_staged_p{d,w,m}h_break → structural level vs prior day/week/month
    #   • tv_staged_p{d,w,m}l_reclaim → same logic, structural reclaim
    #   • tv_p{w,m}{h,l}_held / wick_reclaim → HTF support holds (once per
    #                            SESSION per level; daily-reset cadence so
    #                            a level tested Mon + Wed both fire)
    SESSION_DEDUP_EXEMPT_TYPES = {
        "tv_open_reclaimed",
        "tv_open_wick_reclaim",
        "tv_staged_pdh_break",
        "tv_staged_pdl_reclaim",
        "tv_staged_pwh_break",
        "tv_staged_pwl_reclaim",
        "tv_staged_pmh_break",
        "tv_staged_pml_reclaim",
        "tv_pwh_held", "tv_pwh_wick_reclaim",
        "tv_pwl_held", "tv_pwl_wick_reclaim",
        "tv_pmh_held", "tv_pmh_wick_reclaim",
        "tv_pml_held", "tv_pml_wick_reclaim",
        # SPY SHORT structural rules — exempted so each type can fire once
        # per session independently (otherwise PDH rejection at 10:00 would
        # block PDL break at 14:00 via the symbol-direction-session check).
        # Identity dedup with a 16h window (see DEDUP_WINDOW_OVERRIDES) still
        # caps each individual type at once-per-session.
        # `tv_vwap_reject_short` removed 2026-05-19 — not in the PDH/PDL
        # allow-list, so it never reaches this code path.
        "tv_staged_pdh_rejection",
        "tv_staged_pdh_failed_short",
        "tv_staged_pdl_break",
        # Weekly + Monthly SHORT structural rules (S1 item 2, 2026-05-20).
        "tv_staged_pwh_rejection",
        "tv_staged_pwh_failed_short",
        "tv_staged_pwl_break",
        "tv_staged_pmh_rejection",
        "tv_staged_pmh_failed_short",
        "tv_staged_pml_break",
    }

    # Per-alert-type dedup windows. Defaults to 60 min.
    #   open_reclaimed: 90 min (Pine re-arms, multi-leg days)
    #   htf_proximity_*: 120 min (heads-up, less spammy)
    #   SPY SHORT structural rules: 16h (full session) — at most one alert
    #     per type per day, no matter how many times Pine re-triggers on chop.
    #
    # The open_* and htf_* / pwh-pml entries below are now dead code (the
    # allow-list drops them upstream) but kept here for clarity in case the
    # allow-list is widened later.
    DEDUP_WINDOW_OVERRIDES = {
        "tv_open_reclaimed":      timedelta(minutes=90),
        "tv_htf_proximity_pwh":   timedelta(minutes=120),
        "tv_htf_proximity_pwl":   timedelta(minutes=120),
        "tv_htf_proximity_pmh":   timedelta(minutes=120),
        "tv_htf_proximity_pml":   timedelta(minutes=120),
        "tv_staged_pdh_rejection":    timedelta(hours=16),
        "tv_staged_pdh_failed_short": timedelta(hours=16),
        "tv_staged_pdl_break":        timedelta(hours=16),
        "tv_staged_pwh_rejection":    timedelta(hours=16),
        "tv_staged_pwh_failed_short": timedelta(hours=16),
        "tv_staged_pwl_break":        timedelta(hours=16),
        "tv_staged_pmh_rejection":    timedelta(hours=16),
        "tv_staged_pmh_failed_short": timedelta(hours=16),
        "tv_staged_pml_break":        timedelta(hours=16),
    }
    dedup_window = DEDUP_WINDOW_OVERRIDES.get(alert_type_full, timedelta(minutes=90))

    # Daily fire cap per (symbol, alert_type) — user request 2026-05-26:
    # "2 fires max per symbol per day per alert type". Captures the legit
    # morning-test + afternoon-retest pattern; kills 3rd+ fires as chop.
    # pullback_long capped at 1 because user finds it too noisy already.
    DAILY_FIRE_CAP = 1 if alert_type_full == "tv_pullback_long" else 2

    # Confluence twin suppression — see _check_confluence_twin docstring.
    # Open-line + level alerts firing for the same setup get collapsed to one.
    near_pdh = bool(getattr(sig, "_tv_near_pdh", False))
    near_pdl = bool(getattr(sig, "_tv_near_pdl", False))
    twin = _check_confluence_twin(
        sig.symbol, session_date, alert_type_full, near_pdh, near_pdl
    )
    if twin:
        logger.info(
            "TV confluence twin suppressed: %s for %s — twin %s already fired in window",
            alert_type_full, sig.symbol, twin,
        )
        return {
            "dispatched": False,
            "reason": "confluence_twin_suppressed",
            "twin_type": twin,
        }
    _record_confluence_fire(
        sig.symbol, session_date, alert_type_full, near_pdh, near_pdl,
    )

    # Cross-level confluence dedup — see _check_level_confluence docstring.
    # If staged_pdl_reclaim fired and 30 min later staged_pwl_reclaim arrives
    # within 1% of the prior entry, suppress the second. First-fires-wins.
    side = _level_side(alert_type_full)
    if side is not None:
        level_conf = _check_level_confluence(
            sig.symbol, side, sig.entry, alert_type_full,
        )
        if level_conf:
            logger.info(
                "TV level-confluence suppressed: %s for %s @ %.4f — "
                "%s already fired @ %.4f (%.2f%% spread, %.1fmin ago)",
                alert_type_full, sig.symbol, sig.entry,
                level_conf["winner_type"], level_conf["winner_entry"],
                level_conf["spread_pct"],
                (datetime.utcnow() - level_conf["winner_time"]).total_seconds() / 60.0,
            )
            return {
                "dispatched": False,
                "reason": "level_confluence_suppressed",
                "winner_type": level_conf["winner_type"],
                "winner_entry": level_conf["winner_entry"],
                "spread_pct": round(level_conf["spread_pct"], 3),
            }
        _record_level_fire(sig.symbol, side, sig.entry, alert_type_full)

    # Spec 60 — generic same-bar collapser. Catches residual cross-family
    # confluence (e.g., staged_pdh_break + ma_bounce + pullback_long all
    # firing within 10 min on the same breakout candle). First-fires-wins.
    same_bar = _check_same_bar_collapse(sig.symbol, alert_type_full)
    if same_bar:
        logger.info(
            "TV same-bar collapse: %s for %s — %s fired %.1f min ago",
            alert_type_full, sig.symbol,
            same_bar["prior_type"], same_bar["minutes_ago"],
        )
        return await _persist_unrouted(
            sig, alert_type_full, session_date,
            suppressed_reason=f"confluence_collapsed:{same_bar['prior_type']}",
        )
    _record_same_bar_fire(sig.symbol, alert_type_full)

    # When this alert IS the confluence anchor (open_reclaimed/open_lost with
    # near flag set), prefix the message with a tag so the Telegram template
    # surfaces the confluence context.
    if alert_type_full == "tv_open_reclaimed" and near_pdh:
        sig.message = "✨ OPEN+PDH CONFLUENCE — " + (sig.message or "")
    elif alert_type_full == "tv_open_lost" and near_pdl:
        sig.message = "✨ OPEN+PDL CONFLUENCE — " + (sig.message or "")

    # Gap-down recovery context — staged_pdl_reclaim firing on a gap-down
    # day (opened below PDL) means price climbed back above. Tag so the
    # Telegram header reads "PDL reclaim — gap-down recovery ↑".
    gap_context = bool(getattr(sig, "_tv_gap_context", False))
    if alert_type_full == "tv_staged_pdl_reclaim" and gap_context:
        sig.message = "🔄 GAP-DOWN RECOVERY — " + (sig.message or "")

    # ──────────────────────────────────────────────────────────────────
    # Spec 58 — confluence annotation (FR-013)
    # ──────────────────────────────────────────────────────────────────
    # When the entry's support level clusters within 1% of another known
    # level (a second MA / a prior high or low / the monthly AVWAP), append
    # a "Confluence:" line to the message. Single alert covers both setups
    # — never fire a second alert for a confluent twin.
    _nearby_levels = getattr(sig, "_tv_nearby_levels", []) or []
    _entry_for_confluence = sig.entry if sig.entry not in (None, 0) else None
    if _nearby_levels and _entry_for_confluence:
        _confluences = find_confluences(float(_entry_for_confluence), _nearby_levels)
        _confluence_str = format_confluence_annotation(_confluences)
        if _confluence_str:
            sig.message = (sig.message or "").rstrip() + "\n" + _confluence_str

    pairs: list[tuple[Any, Alert]] = []

    async with async_session_factory() as db:
        # Fetch users whose watchlist contains this symbol.
        users = await _users_watching(db, sig.symbol)
        if not users:
            logger.info("TV webhook: no users watching %s", sig.symbol)
            return {"dispatched": False, "reason": "no_subscribers"}

        # Persist all alerts in one transaction; collect (user, alert) pairs
        # for the notification fan-out which happens AFTER commit so we don't
        # hold the DB connection during network I/O to Telegram.
        for user in users:
            # ──────────────────────────────────────────────────────────
            # Time-based dedup (2026-05-26 redesign — user request)
            # ──────────────────────────────────────────────────────────
            # Replaces the old symbol-session dedup which was too coarse
            # (any BUY alert blocked ALL subsequent BUYs on same symbol
            # regardless of type — ma_bounce got collateral-damaged when
            # staged_pdl_held fired earlier in the day).
            #
            # Two simple rules now control noise:
            #   1. Identity dedup with 90-min window (was 60) — same
            #      (user, symbol, direction, alert_type) inside the window
            #      = chop, drop.
            #   2. Daily fire cap per (symbol, alert_type) — default 2,
            #      pullback_long capped at 1. Captures legit morning-test
            #      + afternoon-retest pattern; kills chop spam.
            #
            # Cross-type alerts on same symbol now fire independently:
            #   - staged_pdl_held @ 08:35 doesn't block ma_bounce @ 08:45
            #   - staged_mtd_avwap_held doesn't block staged_pdh_held
            # That's the design choice — each setup type is its own signal.
            if await _alert_already_fired(
                db, user.id, sig.symbol, sig.direction,
                alert_type_full, dedup_window,
                new_entry=sig.entry, new_stop=sig.stop,
            ):
                logger.info(
                    "TV webhook: identity dedup suppressed %s/%s for user %d "
                    "(within %d-min window)",
                    sig.symbol, alert_type_full, user.id,
                    int(dedup_window.total_seconds() / 60),
                )
                continue

            # Daily fire cap — drop if this type has already fired N times
            # on this symbol today (regardless of time gap).
            if await _daily_fire_cap_exceeded(
                db, user.id, sig.symbol, alert_type_full, session_date, DAILY_FIRE_CAP,
            ):
                logger.info(
                    "TV webhook: daily fire cap (%d) hit for %s/%s/%s user %d",
                    DAILY_FIRE_CAP, sig.symbol, sig.direction, alert_type_full, user.id,
                )
                continue

            _vol_ratio = getattr(sig, "_tv_volume_ratio", None)
            _slope_pct = getattr(sig, "_tv_vwap_slope_pct", None)
            from analytics.alert_grade import compute_grade as _grade
            _alert_grade = _grade(_vol_ratio, _slope_pct)

            alert = Alert(
                user_id=user.id,
                symbol=sig.symbol,
                alert_type=alert_type_full,
                direction=sig.direction or "NOTICE",
                price=float(sig.price),
                entry=sig.entry,
                stop=sig.stop,
                target_1=sig.target_1,
                target_2=sig.target_2,
                confidence=sig.confidence,
                message=sig.message,
                score=int(sig.score) if sig.score else 0,
                confluence_score=int(getattr(sig, "_confluence_score", 0)) or 0,
                session_date=session_date,
                volume_ratio=_vol_ratio,
                cvd_delta=getattr(sig, "_tv_cvd_delta", None),
                cvd_diverging=1 if getattr(sig, "_tv_cvd_diverging", False) else 0,
                stage=getattr(sig, "_tv_stage", None) or None,
                vwap_slope_pct=_slope_pct,
                inside_day=1 if getattr(sig, "_tv_inside_day", False) else 0,
                grade=_alert_grade,
            )
            db.add(alert)
            pairs.append((user, alert))
            persisted += 1

        await db.commit()

    # 6. Per-user Telegram + email delivery via notify_user (mirrors
    # monitor.py:857). Each user with telegram_enabled + telegram_chat_id
    # gets a dedicated Telegram message on their own chat.
    if pairs:
        try:
            from alerting.notifier import notify_user
            for user, alert in pairs:
                if not getattr(user, "telegram_chat_id", None):
                    logger.info("TV NOTIFY SKIP: user=%d — telegram_chat_id empty", user.id)
                    continue
                if not getattr(user, "telegram_enabled", True):
                    logger.info("TV NOTIFY SKIP: user=%d — telegram_enabled=False", user.id)
                    continue
                # Free tier → A-grade alerts only (the B/C firehose is a Pro perk).
                if _tier_grade_blocked(user, getattr(alert, "grade", None)):
                    logger.info(
                        "TV NOTIFY SKIP: user=%d — grade %s below free A-floor",
                        user.id, getattr(alert, "grade", None),
                    )
                    continue
                prefs = {
                    "telegram_enabled": True,
                    "telegram_chat_id": user.telegram_chat_id,
                    "email_enabled": getattr(user, "email_enabled", False),
                    "notification_email": getattr(user, "email", None),
                }
                try:
                    email_ok, tg_ok = notify_user(sig, prefs, alert_id=alert.id)
                    if tg_ok:
                        notified += 1
                    logger.info(
                        "TV NOTIFY: user=%d %s tg=%s email=%s",
                        user.id, sig.symbol, tg_ok, email_ok,
                    )
                except Exception:
                    logger.warning("TV notify_user FAILED for user=%d %s",
                                   user.id, sig.symbol, exc_info=True)

                # iOS APNs push (Capacitor app) — graceful no-op until env
                # vars are set. Sent alongside Telegram, not as a replacement.
                if getattr(user, "apns_enabled", False) and getattr(user, "apns_token", None):
                    try:
                        from app.services.apns import send_apns_push, build_alert_push
                        title, body = build_alert_push(
                            sig.symbol, alert_type_full, sig.direction or "BUY", sig.entry
                        )
                        apns_ok = await send_apns_push(
                            user.apns_token, title, body,
                            payload={"alert_id": alert.id, "symbol": sig.symbol},
                        )
                        if apns_ok:
                            logger.info("APNs NOTIFY: user=%d %s ok=True", user.id, sig.symbol)
                    except Exception:
                        logger.warning("APNs send failed user=%d", user.id, exc_info=True)
        except Exception:
            logger.exception("TV webhook: notify fan-out failed for %s", sig.symbol)

    logger.info(
        "TV webhook done: symbol=%s persisted=%d notified=%d "
        "direction=%s htf_4h=%s htf_1h=%s",
        sig.symbol, persisted, notified, sig.direction, bias.htf_4h, bias.htf_1h,
    )
    return {
        "dispatched": True,
        "persisted": persisted,
        "notified": notified,
        "htf_4h": bias.htf_4h,
        "htf_1h": bias.htf_1h,
        "confluence_score": getattr(sig, "_confluence_score", 0),
    }


async def _persist_unrouted(
    sig,
    alert_type_full: str,
    session_date: str,
    suppressed_reason: str = "type_not_enabled",
) -> dict[str, Any]:
    """Record-only path for alerts that are suppressed before delivery.

    The alert is persisted (one row per user/symbol/type/direction/session)
    with `suppressed_reason` set, so it can be reviewed at EOD — but it gets
    no Telegram, is hidden from the live Signals feed, and never touches the
    twin/level dedup state of the routed pipeline.

    `suppressed_reason` defaults to `type_not_enabled` (the original use case —
    a toggled-OFF alert type). Spec 58 (2026-05-22) also uses this for
    `uptrend_gate_failed` (an entry on a downtrend stock) so the user can see
    in the EOD scorecard which alerts were correctly filtered.
    """
    from app.database import async_session_factory
    from app.models.alert import Alert

    direction = sig.direction or "NOTICE"
    recorded = 0
    async with async_session_factory() as db:
        users = await _users_watching(db, sig.symbol)
        for user in users:
            already = (await db.execute(
                select(Alert.id).where(
                    Alert.user_id == user.id,
                    Alert.symbol == sig.symbol,
                    Alert.alert_type == alert_type_full,
                    Alert.direction == direction,
                    Alert.session_date == session_date,
                ).limit(1)
            )).first()
            if already:
                continue
            db.add(Alert(
                user_id=user.id,
                symbol=sig.symbol,
                alert_type=alert_type_full,
                direction=direction,
                price=float(sig.price),
                entry=sig.entry,
                stop=sig.stop,
                target_1=sig.target_1,
                target_2=sig.target_2,
                confidence=sig.confidence,
                message=sig.message,
                session_date=session_date,
                suppressed_reason=suppressed_reason,
                # Carry stage + slope + inside_day through to the unrouted
                # audit row so the 'Not routed' feed shows WHY each basing_chop
                # / uptrend_gate suppression fired — not just the reason code.
                stage=getattr(sig, "_tv_stage", None) or None,
                vwap_slope_pct=getattr(sig, "_tv_vwap_slope_pct", None),
                inside_day=1 if getattr(sig, "_tv_inside_day", False) else 0,
                volume_ratio=getattr(sig, "_tv_volume_ratio", None),
            ))
            recorded += 1
        await db.commit()
    logger.info(
        "TV webhook: recorded %d %s/%s rows for %s (review only)",
        recorded, alert_type_full, suppressed_reason, sig.symbol,
    )
    return {"dispatched": False, "reason": suppressed_reason, "recorded": recorded}


async def _users_watching(db, symbol: str):
    """Return list of users whose watchlist contains the symbol.

    Watchlist is a separate table (`watchlist` → WatchlistItem) joined to
    users via user_id. This mirrors the rule-engine poll loop in
    api/app/background/monitor.py which also joins through WatchlistItem.

    Scoped to SCAN_USER_EMAIL (default vbolofinde@gmail.com) — the whole
    alert system serves a single user while alert quality is evaluated, the
    same gate the swing/day scanners and db.py already apply. One inbound TV
    alert then writes one Alert row, not one per subscribed account.
    """
    import os
    from sqlalchemy.orm import selectinload
    from app.models.user import User
    from app.models.watchlist import WatchlistItem

    stmt = (
        select(User)
        .join(WatchlistItem, WatchlistItem.user_id == User.id)
        .where(WatchlistItem.symbol == symbol)
        .options(selectinload(User.subscription))  # eager tier for grade-floor gate
        .distinct()
    )
    scan_email = (os.environ.get("SCAN_USER_EMAIL") or "vbolofinde@gmail.com").strip().lower()
    if scan_email:
        stmt = stmt.where(User.email == scan_email)
    result = await db.execute(stmt)
    return result.scalars().all()


def _tier_grade_blocked(user, grade) -> bool:
    """Tier-floor gate — TEMPORARILY DISABLED 2026-05-31 per founder request.

    The intent: Free tier delivers Grade A alerts only; B/C are a Pro perk
    (alerts_min_grade floor in app/tier.py). Admins/paid tiers were never
    blocked. The gate was correct for monetization but obscured debugging
    when the founder was wondering why an alert didn't reach Telegram —
    not the cause that night (AGENT_OWNS_TELEGRAM was), but a possible
    future false-positive.

    Re-enable by deleting this early-return and restoring the original
    body (see git blame). When you do, also surface the floor in the
    Settings page so Free users understand why B/C don't reach them.

    Impact while disabled: Free users receive ALL grades in Telegram +
    push. Pro/Admin/Premium behavior is unchanged.
    """
    return False
    # --- Original implementation (kept for easy revert) ---------------
    # try:
    #     from app.dependencies import get_user_tier, is_admin_user
    #     if is_admin_user(user):
    #         return False
    #     from app.tier import get_limits
    #     floor = get_limits(get_user_tier(user)).get("alerts_min_grade")
    #     return floor == "A" and (grade or "C").upper() != "A"
    # except Exception:
    #     logger.debug("tier grade gate lookup failed — delivering", exc_info=True)
    #     return False


_MA_TAG_SUFFIX_RE = __import__("re").compile(r"(\d+)([ES])")


def _ma_tag_to_suffix(raw_ma_tag: str) -> str:
    """Convert raw Pine ma_tag to an alert_type suffix.

    Examples:
        "100E"   -> "_ema100"
        "8E"     -> "_ema8"
        "8E21E"  -> "_ema8_ema21"   (confluence: multiple MAs same bar)
        "50S"    -> "_sma50"
        ""       -> ""              (rules without MAs — VWAP reclaim etc.)

    Suffix lets identity dedup distinguish EMA50 rejection from EMA100
    rejection without a price-band check (each MA is its own setup).
    """
    if not raw_ma_tag:
        return ""
    matches = _MA_TAG_SUFFIX_RE.findall(raw_ma_tag)
    if not matches:
        return ""
    parts = [f"{'ema' if kind == 'E' else 'sma'}{num}" for num, kind in matches]
    return "_" + "_".join(parts)


# ---------------------------------------------------------------------------
# Routing logic — SPY-only SHORT gate.
# User direction 2026-05-18: equity SHORTs are pure noise on chop days
# regardless of SPY regime. Hard-drop all non-SPY shorts. On SPY, only
# the 4 structural rules below fire (max 4 SPY SHORTs/day, one per type).
# ---------------------------------------------------------------------------


# Alert allow-list (2026-05-19) — only PDH/PDL exact types AND MA/EMA
# bounce/rejection prefix matches are delivered. Everything else (VWAP,
# open-line, weekly/monthly HTF, proximity NOTICEs, etc.) is dropped
# server-side regardless of what Pine fires.
#
# User directives:
#   • 2026-05-19a: "disable all alerts except pdh, pdl, that's it."
#   • 2026-05-19b: "also allow mas/ema alerts" — added MA prefixes below.
#
# Combined with the SHORT gate, the effective delivery matrix is:
#   • BUY  on any symbol  → tv_staged_pdh_break, tv_staged_pdl_reclaim,
#                           tv_ma_bounce_long_v3_<MA suffix>
#   • SHORT on SPY only   → tv_staged_pdh_rejection, tv_staged_pdh_failed_short,
#                           tv_staged_pdl_break
#                           (MA rejection SHORT NOT in SPY whitelist per
#                           prior "leave ema for nw could be noisy" guidance)
#   • SHORT on non-SPY    → all dropped
#   • Anything else       → dropped
_ALLOWED_ALERT_TYPES = {
    # Daily PDH/PDL staged events.
    "tv_staged_pdh_break",
    "tv_staged_pdh_rejection",
    "tv_staged_pdh_failed_short",
    "tv_staged_pdl_break",
    "tv_staged_pdl_reclaim",
    # Weekly + Monthly staged events (S1 item 2, 2026-05-20) — re-enabled
    # now that S0 position-relative direction is correct. W/M crossings are
    # low-frequency structural events, not noise.
    "tv_staged_pwh_break",
    "tv_staged_pwh_rejection",
    "tv_staged_pwh_failed_short",
    "tv_staged_pwl_break",
    "tv_staged_pwl_reclaim",
    "tv_staged_pmh_break",
    "tv_staged_pmh_rejection",
    "tv_staged_pmh_failed_short",
    "tv_staged_pml_break",
    "tv_staged_pml_reclaim",
    # S1 (2026-05-20) — collapsed HTF level alerts. The 8 per-level
    # hold/wick alerts fire as one tv_htf_support_held (BUY); the 4
    # per-level proximity NOTICEs fire as one tv_htf_proximity (NOTICE).
    "tv_htf_support_held",
    "tv_htf_proximity",
    # Uptrend pullback continuation (2026-05-20) — BUY, from ma-ema-daily.
    "tv_pullback_long",
    # Open-line alerts (2026-05-21) — re-enabled, gated per-type by the
    # alert_type_config table. Listed here only as the static fallback.
    "tv_open_reclaimed",
    "tv_open_held",
    "tv_open_wick_reclaim",
    "tv_open_lost",
}

# Prefix matches for the allow-list. Alert types with these prefixes
# (regardless of MA-tag suffix like `_ema50` or `_ema8_ema21`) are allowed.
# Proximity variants (2026-05-20) deliver as NOTICE — informational
# "price holding near an MA" heads-ups, no trade box.
_ALLOWED_ALERT_TYPE_PREFIXES = (
    "tv_ma_bounce_long_v3",
    "tv_ma_rejection_short_v3",
    "tv_ma_proximity_long_v3",
    "tv_ma_proximity_short_v3",
)

# Prefix families as base keys (no tv_ prefix) — mirrors PREFIX_FAMILIES in
# app/models/alert_type_config.py. Kept local so this module has no
# top-level app.* import (preserves test-import isolation).
_PREFIX_FAMILIES = (
    "ma_bounce_long_v3",
    "ma_rejection_short_v3",
    "ma_proximity_long_v3",
    "ma_proximity_short_v3",
)

# MA families split per moving average — each EMA has its own toggle, all SMAs
# share one. Mirrors MA_SPLIT_FAMILIES in app/models/alert_type_config.py.
_MA_SPLIT_FAMILIES = (
    "ma_bounce_long_v3",
    "ma_proximity_long_v3",
    "ma_rejection_short_v3",
)


def _ma_config_keys(base: str) -> Optional[list[str]]:
    """Map an MA-split-family alert base (no `tv_` prefix) to its
    alert_type_config keys — one per MA. Confluence alerts (e.g.
    `..._ema8_ema21`) carry several; each EMA maps to its own key, every SMA
    to the shared `<family>_sma` key. Returns None if `base` is not a
    split-family alert.
    """
    for fam in _MA_SPLIT_FAMILIES:
        if base == fam or base.startswith(fam + "_"):
            suffix = base[len(fam):].lstrip("_")  # "ema8" / "ema8_ema21" / "sma50"
            keys: list[str] = []
            for tok in (t for t in suffix.split("_") if t):
                if tok.startswith("sma"):
                    keys.append(fam + "_sma")
                elif tok.startswith("ema"):
                    keys.append(fam + "_" + tok)
            return keys or [fam]
    return None


def _is_allowed_alert_type(alert_type: str, enabled: set[str] | None = None) -> bool:
    """True if the alert_type should be delivered.

    When `enabled` is given (the set of enabled base keys from the
    alert_type_config table) it is authoritative — per-type toggles. MA
    families are matched per moving average; a confluence alert routes if
    ANY of its MAs is enabled. When `enabled` is None (a DB read failed)
    fall back to the static allow-list so delivery never goes fully dark.
    """
    if enabled is None:
        if alert_type in _ALLOWED_ALERT_TYPES:
            return True
        return any(alert_type.startswith(p) for p in _ALLOWED_ALERT_TYPE_PREFIXES)
    base = alert_type[3:] if alert_type.startswith("tv_") else alert_type
    ma_keys = _ma_config_keys(base)
    if ma_keys is not None:
        return any(k in enabled for k in ma_keys)
    if base in enabled:
        return True
    return any(base.startswith(p) and p in enabled for p in _PREFIX_FAMILIES)


# SPY SHORT structural whitelist — subset of _ALLOWED_ALERT_TYPES that are
# valid SHORT entries. Non-whitelisted SPY shorts are dropped (no NOTICE
# downgrade). VWAP reject was removed 2026-05-19 alongside the PDH/PDL-only
# allow-list switch.
# Weekly + Monthly SHORT structural rules added 2026-05-20 (S1 item 2) —
# "SPY shorts at any structural level" applies to W/M levels too, not just
# daily. Each fires once per session (16h dedup window, see below).
_SPY_SHORT_ACTION_RULES = {
    "tv_staged_pdh_rejection",
    "tv_staged_pdh_failed_short",
    "tv_staged_pdl_break",
    "tv_staged_pwh_rejection",
    "tv_staged_pwh_failed_short",
    "tv_staged_pwl_break",
    "tv_staged_pmh_rejection",
    "tv_staged_pmh_failed_short",
    "tv_staged_pml_break",
}


async def _route_alert(sig) -> tuple[bool, Optional[str]]:
    """Decide whether to deliver an alert and whether to downgrade direction.

    Returns:
        (deliver, downgrade)
        - (True, None)   → deliver as-is (ACTION)
        - (False, None)  → suppress entirely (no DB row, no Telegram)

    Rules:
        - BUY / LONG / NOTICE              → ACTION
        - SHORT, symbol != SPY             → DROP
        - SHORT, symbol == SPY, whitelist  → ACTION
        - SHORT, symbol == SPY, other      → DROP
    """
    direction = (sig.direction or "").upper()

    if direction not in ("SHORT", "SELL"):
        return True, None

    if sig.symbol != "SPY":
        return False, None

    rule = (getattr(sig, "_tv_rule", "") or "").strip()
    rule_full = f"tv_{rule}" if rule and not rule.startswith("tv_") else rule
    if rule_full in _SPY_SHORT_ACTION_RULES:
        return True, None
    return False, None


async def _symbol_session_already_fired(
    db,
    user_id: int,
    symbol: str,
    direction: str,
    session_date: str,
) -> bool:
    """True if ANY alert for (user, symbol, direction) already fired this
    session. Broader than _alert_already_fired — doesn't care about
    alert_type, so an MA bounce gets suppressed if a PDH break already
    fired (and vice versa) on the same symbol+direction same session.

    This is the primary chop-day noise reducer: ETH-USD bouncing off
    EMA5/EMA10/EMA21/EMA50/SMA50 across the day fires ONE alert, not 5–11.

    Opposite-direction alerts (BUY → SHORT) pass through — those represent
    a regime change worth signaling.
    """
    from app.models.alert import Alert

    stmt = select(Alert.id).where(
        Alert.user_id == user_id,
        Alert.symbol == symbol,
        Alert.direction == direction,
        Alert.session_date == session_date,
    ).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


# Level alert types that get the R-distance price-band check on identity dedup.
# When one of these re-fires within the time window, we ALSO check whether the
# new entry is more than 1R away from the prior entry (R = prior |entry-stop|).
# Inside 1R = same chop, suppress. Outside 1R = price genuinely moved, allow.
# Rationale (2026-05-18): NFLX PDH break fired 14:50 @ 89.68 and 20:00 @ 89.68
# (0% spread, 5h apart) — pure time dedup was too permissive. R-scaling means
# a $0.50 spread is huge on NFLX (R≈$0.32) but tiny on SPY (R≈$1.60).
_LEVEL_ALERT_TYPES_FOR_PRICE_BAND = {
    "tv_staged_pdh_break",
    "tv_staged_pdh_reclaim",
    "tv_staged_pdh_rejection",
    "tv_staged_pdh_failed_short",
    "tv_staged_pdl_break",
    "tv_staged_pdl_reclaim",
    "tv_staged_pwh_break",
    "tv_staged_pwh_reclaim",
    "tv_staged_pwl_reclaim",
    "tv_staged_pmh_break",
    "tv_staged_pmh_reclaim",
    "tv_staged_pml_reclaim",
}


def _is_chop_refire(
    alert_type: str,
    new_entry: Optional[float],
    prior_entry: Optional[float],
    prior_stop: Optional[float],
) -> bool:
    """Pure R-distance band check. Returns True if a re-fire should be
    suppressed as chop (within 1R of prior entry).

    Decision tree:
      • alert_type not in level scope → True  (defer to time dedup)
      • can't compute prior R (missing data or zero distance) → True
      • |new_entry - prior_entry| < prior_R → True  (chop, suppress)
      • >= prior_R → False  (price moved beyond 1R, allow re-fire)
    """
    if (
        alert_type not in _LEVEL_ALERT_TYPES_FOR_PRICE_BAND
        or new_entry is None
        or prior_entry is None
        or prior_stop is None
        or prior_entry == prior_stop
    ):
        return True
    prior_r = abs(prior_entry - prior_stop)
    return abs(new_entry - prior_entry) < prior_r


async def _daily_fire_cap_exceeded(
    db, user_id: int, symbol: str, alert_type: str, session_date: str, cap: int,
) -> bool:
    """True if this (symbol, alert_type) has already fired `cap` times today.

    Counts only delivered rows (suppressed_reason IS NULL) so cap = 2 means
    "at most 2 actual Telegram alerts per symbol per day per type". The 3rd+
    fires are treated as chop and dropped.
    """
    from app.models.alert import Alert
    from sqlalchemy import func as sa_func
    stmt = select(sa_func.count(Alert.id)).where(
        Alert.user_id == user_id,
        Alert.symbol == symbol,
        Alert.alert_type == alert_type,
        Alert.session_date == session_date,
        Alert.suppressed_reason.is_(None),
    )
    result = await db.execute(stmt)
    count = result.scalar_one() or 0
    return count >= cap


async def _alert_already_fired(
    db,
    user_id: int,
    symbol: str,
    direction: str,
    alert_type: str,
    window: timedelta,
    new_entry: Optional[float] = None,
    new_stop: Optional[float] = None,
) -> bool:
    """True if this exact (user, symbol, direction, alert_type) fired recently.

    Identity-based dedup with optional R-distance price-band check for
    level alerts (see _is_chop_refire): a re-fire within 1R of the prior
    entry is suppressed as chop; >= 1R away is treated as a fresh re-test
    and passes through.

    The alert_type carries the MA tag (e.g.,
    tv_ma_rejection_short_v3_ema100), so same MA + same direction = same
    setup. Different MAs (ema50 vs ema100) and opposite directions get
    different alert_types and fire independently.
    """
    from app.models.alert import Alert

    cutoff = datetime.utcnow() - window
    stmt = select(Alert.entry, Alert.stop).where(
        Alert.user_id == user_id,
        Alert.symbol == symbol,
        Alert.direction == direction,
        Alert.alert_type == alert_type,
        Alert.created_at >= cutoff,
    ).order_by(Alert.created_at.desc()).limit(1)
    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        return False

    prior_entry, prior_stop = row
    return _is_chop_refire(alert_type, new_entry, prior_entry, prior_stop)


# Public exports for tests
__all__ = [
    "router",
    "TVWebhookPayload",
    "_is_allowed_ip",
    "_ma_tag_to_suffix",
    "_alert_already_fired",
    "_symbol_session_already_fired",
    "_route_alert",
    "_SPY_SHORT_ACTION_RULES",
    "_is_chop_refire",
    "_LEVEL_ALERT_TYPES_FOR_PRICE_BAND",
    "_ALLOWED_ALERT_TYPES",
    "_ALLOWED_ALERT_TYPE_PREFIXES",
    "_is_allowed_alert_type",
]
