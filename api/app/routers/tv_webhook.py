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

import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from alert_config import (
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
    dedup_window = timedelta(minutes=30)
    dedup_tolerance_pct = 0.005  # 0.5% — same as Phase 1 level dedup

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
            # Per-user level dedup against alerts table.
            if await _level_already_alerted(
                db, user.id, sig.symbol, sig.entry or sig.price,
                dedup_tolerance_pct, dedup_window,
            ):
                logger.info(
                    "TV webhook: level dedup suppressed %s for user %d",
                    sig.symbol, user.id,
                )
                continue

            alert = Alert(
                user_id=user.id,
                symbol=sig.symbol,
                alert_type=f"tv_{getattr(sig, '_tv_rule', 'webhook')}"[:100],
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


async def _level_already_alerted(
    db,
    user_id: int,
    symbol: str,
    level: float,
    tolerance_pct: float,
    window: timedelta,
) -> bool:
    """True if an alert at a similar level fired for this user recently."""
    from app.models.alert import Alert

    if not level or level <= 0:
        return False
    cutoff = datetime.utcnow() - window
    stmt = select(Alert).where(
        Alert.user_id == user_id,
        Alert.symbol == symbol,
        Alert.created_at >= cutoff,
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    band = level * tolerance_pct
    for row in rows:
        prev = row.entry or row.price or 0
        if prev <= 0:
            continue
        if abs(prev - level) <= band:
            return True
    return False


# Public exports for tests
__all__ = ["router", "TVWebhookPayload", "_is_allowed_ip"]
