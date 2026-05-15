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
import time
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from alert_config import (
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
) -> dict[str, Any]:
    """Ingest a TradingView alert and route it through the alerting pipeline.

    Returns 200 on accepted alerts, 400 on bad payload, 403 on disallowed IP,
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

    # Defer to a small dispatcher function so the request handler stays thin.
    # Any exception during dispatch is swallowed + logged to keep TV happy
    # (TV retries 5xx; we don't want spurious retries on transient issues).
    try:
        result = await _dispatch_signal(sig, request)
    except Exception:
        logger.exception("TV webhook: dispatch failed for %s", sig.symbol)
        # Return 200 so TV doesn't retry; we'll have logged the failure.
        return {"accepted": True, "dispatched": False, "reason": "dispatch_error"}

    return {"accepted": True, **result}


async def _dispatch_signal(sig, request: Request) -> dict[str, Any]:
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
    try:
        prior_day = fetch_prior_day(sig.symbol, is_crypto=is_crypto)
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

    dedup_window = timedelta(minutes=90) if alert_type_full == "tv_open_reclaimed" else timedelta(minutes=60)

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

    # When this alert IS the confluence anchor (open_reclaimed/open_lost with
    # near flag set), prefix the message with a tag so the Telegram template
    # surfaces the confluence context.
    if alert_type_full == "tv_open_reclaimed" and near_pdh:
        sig.message = "✨ OPEN+PDH CONFLUENCE — " + (sig.message or "")
    elif alert_type_full == "tv_open_lost" and near_pdl:
        sig.message = "✨ OPEN+PDL CONFLUENCE — " + (sig.message or "")

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
            # 1. Symbol-session dedup (primary noise reducer for chop days).
            # If ANY alert for (user, symbol, direction) already fired this
            # session, drop subsequent ones regardless of alert_type. This
            # collapses cases like ETH-USD firing 11 MA bounces across
            # EMA5/10/21/50/SMA50 within hours — only the first fires.
            # Opposite-direction alerts still pass (regime change is news).
            #
            # EXEMPTION (2026-05-15): tv_open_reclaimed bypasses session
            # dedup. Pine re-arms after fire so a fresh lose-and-reclaim
            # cycle later in the session is a genuinely new signal — but
            # we don't want it spammed, so a 90-min identity dedup window
            # (set above) catches rapid chop. Net result: distinct legs
            # of a multi-cycle day each get their own alert.
            session_dedup_exempt = alert_type_full == "tv_open_reclaimed"
            if SYMBOL_SESSION_DEDUP and sig.direction in ("BUY", "SHORT") and not session_dedup_exempt:
                if await _symbol_session_already_fired(
                    db, user.id, sig.symbol, sig.direction, session_date,
                ):
                    logger.info(
                        "TV webhook: symbol-session dedup suppressed %s/%s/%s "
                        "for user %d (alert_type=%s)",
                        sig.symbol, sig.direction, session_date,
                        user.id, alert_type_full,
                    )
                    continue

            # 2. Per-user identity dedup against alerts table.
            # Key = (user_id, symbol, direction, alert_type) where alert_type
            # carries the MA tag (tv_ma_rejection_short_v3_ema100). Same MA +
            # same direction within the window = same setup, suppressed.
            # Different MAs (ema50 vs ema100) and opposite directions still
            # fire — they're genuinely different events.
            if await _alert_already_fired(
                db, user.id, sig.symbol, sig.direction,
                alert_type_full, dedup_window,
            ):
                logger.info(
                    "TV webhook: identity dedup suppressed %s/%s for user %d",
                    sig.symbol, alert_type_full, user.id,
                )
                continue

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
                volume_ratio=getattr(sig, "_tv_volume_ratio", None),
                cvd_delta=getattr(sig, "_tv_cvd_delta", None),
                cvd_diverging=1 if getattr(sig, "_tv_cvd_diverging", False) else 0,
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


async def _users_watching(db, symbol: str):
    """Return list of users whose watchlist contains the symbol.

    Watchlist is a separate table (`watchlist` → WatchlistItem) joined to
    users via user_id. This mirrors the rule-engine poll loop in
    api/app/background/monitor.py which also joins through WatchlistItem.

    Production note: not gating by tier/subscription here; the poll loop
    does that filtering. For TV ingest in v1 we deliver to anyone watching
    the symbol — fits the "TV is additive" philosophy. Add tier gating if
    we see TV alerts going to free users we want to exclude.
    """
    from app.models.user import User
    from app.models.watchlist import WatchlistItem

    stmt = (
        select(User)
        .join(WatchlistItem, WatchlistItem.user_id == User.id)
        .where(WatchlistItem.symbol == symbol)
        .distinct()
    )
    result = await db.execute(stmt)
    return result.scalars().all()


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
# Routing logic — A1 (SPY 8/21 long-bias gate) + A2 (SPY short whitelist)
# Spec: specs/41-tv-trading-system/v2-routing-notices-patterns.md
# ---------------------------------------------------------------------------


# SPY-state cache. yfinance is slow + flaky — refresh at most once per
# 5 minutes during a webhook burst. In-process; resets on container start.
_SPY_STATE_TTL_SEC = 300
_spy_state_cache: dict[str, Any] = {"value": None, "expires_at": 0.0}


# SPY SHORT whitelist (A2). Rules NOT in this set drop to NOTICE when
# SPY is in long-bias regime.
#
# Note: `vwap_lose_short` was added briefly 2026-05-05 and removed the
# same day — single bar-close VWAP cross was too noisy on charts where
# candles hug VWAP (AAPL 1h showed 7 false triggers in a session). The
# actionable VWAP-from-above case is already covered by vwap_reject_short
# (which requires `vwap_setup_bars` confirmation).
_SPY_SHORT_ACTION_RULES = {
    "tv_staged_pdh_rejection",
    "tv_staged_pdh_failed_short",  # added 2026-05-07 — failed-breakout reversal
    "tv_staged_pdl_break",
    "tv_vwap_reject_short",
}


def _fetch_spy_state_sync() -> bool:
    """Sync helper: SPY's last close > both daily 8 EMA and 21 EMA.

    Returns True (long-bias=permissive) on insufficient data.
    Called from a thread pool so it doesn't block the event loop.
    """
    import yfinance as yf

    spy = yf.Ticker("SPY")
    hist = spy.history(period="60d", interval="1d")
    if len(hist) < 22:
        return True  # not enough data — fail-open
    closes = hist["Close"]
    ema8 = closes.ewm(span=8, adjust=False).mean().iloc[-1]
    ema21 = closes.ewm(span=21, adjust=False).mean().iloc[-1]
    last = closes.iloc[-1]
    return bool(last > ema8 and last > ema21)


async def _spy_above_8_21() -> bool:
    """True if SPY closed above both daily 8 EMA and 21 EMA.

    Cached for 5 min. Fails open (returns True = long-bias permissive)
    on any error so a yfinance hiccup doesn't silently block alerts.
    """
    now = time.time()
    if _spy_state_cache["expires_at"] > now and _spy_state_cache["value"] is not None:
        return _spy_state_cache["value"]
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _fetch_spy_state_sync)
    except Exception:
        logger.exception(
            "SPY 8/21 fetch failed — failing open (long-bias=True permissive)"
        )
        return True
    _spy_state_cache["value"] = result
    _spy_state_cache["expires_at"] = now + _SPY_STATE_TTL_SEC
    return result


async def _route_alert(sig) -> tuple[bool, Optional[str]]:
    """Decide whether to deliver an alert and whether to downgrade direction.

    Returns:
        (deliver, downgrade)
        - (True, None)        → deliver as-is (ACTION)
        - (True, "NOTICE")    → deliver but override sig.direction to NOTICE
        - (False, None)       → suppress entirely (no DB row, no Telegram)

    Rules implemented:
        A1. When SPY > daily 8 AND 21 EMAs (long-bias regime):
            - non-SPY SHORTs → suppress
        A2. When SPY > 8/21 AND symbol == SPY AND direction == SHORT:
            - whitelisted rule → ACTION
            - other SPY short rules → NOTICE
        Otherwise (LONGs, NOTICEs, shorts with weak SPY) → ACTION as-is.
    """
    direction = (sig.direction or "").upper()

    # LONG / BUY / NOTICE pass through unchanged in v1.
    if direction not in ("SHORT", "SELL"):
        return True, None

    spy_long_bias = await _spy_above_8_21()
    if not spy_long_bias:
        # SPY weak — all shorts (including single-name) restored to ACTION.
        return True, None

    rule = (getattr(sig, "_tv_rule", "") or "").strip()

    if sig.symbol != "SPY":
        # A1: non-SPY shorts in long-bias regime are noise. Suppress.
        return False, None

    # A2: SPY shorts. Whitelisted rules pass through; others NOTICE-downgrade.
    if rule in _SPY_SHORT_ACTION_RULES:
        return True, None
    return True, "NOTICE"


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


async def _alert_already_fired(
    db,
    user_id: int,
    symbol: str,
    direction: str,
    alert_type: str,
    window: timedelta,
) -> bool:
    """True if this exact (user, symbol, direction, alert_type) fired recently.

    Identity-based dedup. The alert_type carries the MA tag (e.g.,
    tv_ma_rejection_short_v3_ema100), so same MA + same direction = same
    setup. Different MAs (ema50 vs ema100) and opposite directions get
    different alert_types and fire independently.

    Replaces the old price-band approach — same setup at slightly different
    prices (e.g., ETH EMA100 short at $2338 then $2322) was the noise we
    actually wanted to suppress, and identity captures it cleanly.
    """
    from app.models.alert import Alert

    cutoff = datetime.utcnow() - window
    stmt = select(Alert.id).where(
        Alert.user_id == user_id,
        Alert.symbol == symbol,
        Alert.direction == direction,
        Alert.alert_type == alert_type,
        Alert.created_at >= cutoff,
    ).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


# Public exports for tests
__all__ = [
    "router",
    "TVWebhookPayload",
    "_is_allowed_ip",
    "_ma_tag_to_suffix",
    "_alert_already_fired",
    "_symbol_session_already_fired",
    "_route_alert",
    "_spy_above_8_21",
    "_fetch_spy_state_sync",
    "_SPY_SHORT_ACTION_RULES",
]
