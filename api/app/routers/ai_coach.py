"""AI Coach endpoints — Best Setups of the Day + user-pinned Telegram alerts."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_user_tier
from app.models.user import User
from app.tier import get_limits

logger = logging.getLogger(__name__)
router = APIRouter()

# Shared usage-limits feature key (persisted in usage_limits table)
_FEATURE_BEST_SETUPS = "best_setups"


async def _get_usage(db: AsyncSession, user_id: int, session_date: str) -> int:
    from sqlalchemy import text
    row = (await db.execute(
        text(
            "SELECT usage_count FROM usage_limits "
            "WHERE user_id = :uid AND feature = :f AND usage_date = :d"
        ),
        {"uid": user_id, "f": _FEATURE_BEST_SETUPS, "d": session_date},
    )).fetchone()
    return int(row[0]) if row else 0


async def _increment_usage(db: AsyncSession, user_id: int, session_date: str) -> None:
    from sqlalchemy import text
    try:
        await db.execute(
            text(
                "INSERT INTO usage_limits (user_id, feature, usage_date, usage_count) "
                "VALUES (:uid, :f, :d, 1) "
                "ON CONFLICT (user_id, feature, usage_date) "
                "DO UPDATE SET usage_count = usage_limits.usage_count + 1"
            ),
            {"uid": user_id, "f": _FEATURE_BEST_SETUPS, "d": session_date},
        )
        await db.commit()
    except Exception:
        logger.exception("best_setups: usage increment failed")


@router.get("/best-setups")
async def best_setups(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ranked best setups across the user's watchlist for today.

    Cached 15 min per (user, watchlist_hash). Tier-gated:
    free=1/day, pro=20/day, premium unlimited.
    """
    if os.environ.get("BEST_SETUPS_ENABLED", "true").lower() in ("false", "0", "no"):
        raise HTTPException(503, detail="Feature disabled")

    tier = get_user_tier(user)
    cap = get_limits(tier).get("best_setups_per_day")
    session_date = date.today().isoformat()

    if cap is not None:
        used = await _get_usage(db, user.id, session_date)
        if used >= cap:
            raise HTTPException(
                429,
                detail={
                    "error": "daily_limit_reached",
                    "tier": tier,
                    "cap": cap,
                    "message": f"Daily best-setups limit reached ({cap}). "
                               f"Upgrade for more.",
                },
            )

    # Build sync session factory for the threaded scanner
    from analytics.ai_best_setups import generate_best_setups
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.config import get_settings

    settings = get_settings()
    sync_url = settings.DATABASE_URL
    for suffix in ("+asyncpg", "+psycopg2", "+psycopg"):
        sync_url = sync_url.replace(suffix, "")
    sync_engine = create_engine(sync_url, pool_pre_ping=True)
    sync_factory = sessionmaker(bind=sync_engine)

    result = await asyncio.to_thread(generate_best_setups, user.id, sync_factory)

    # Count usage only when we actually ran AI (not on cache hit — but result
    # doesn't distinguish yet; accept slight over-count on 2nd same-watchlist
    # call within 15 min. Non-critical.)
    if cap is not None and not result.error:
        await _increment_usage(db, user.id, session_date)

    return {
        "generated_at": result.generated_at,
        "watchlist_size": result.watchlist_size,
        "day_trade_picks": result.day_trade_picks,
        "swing_trade_picks": result.swing_trade_picks,
        "skipped": result.skipped,
        "error": result.error,
    }


class PinAlertRequest(BaseModel):
    symbol: str
    timeframe: str = Field(..., pattern="^(day|swing)$")
    direction: str = Field(..., pattern="^(LONG|SHORT)$")
    setup_type: str = ""
    entry: float
    stop: Optional[float] = None
    t1: Optional[float] = None
    t2: Optional[float] = None
    conviction: str = "MEDIUM"
    why_now: str = ""
    current_price: float


def _fire_pinned_alert(user_id: int, payload: PinAlertRequest) -> dict:
    """Sync: record alert + send Telegram with Took/Skip/Exit buttons."""
    from analytics.intraday_rules import AlertSignal, AlertType
    from alerting.alert_store import record_alert
    from alerting.notifier import notify_user
    from db import get_db as get_sync_db

    alert_type = (
        AlertType.BEST_SETUP_DAY if payload.timeframe == "day"
        else AlertType.BEST_SETUP_SWING
    )
    direction = "BUY" if payload.direction == "LONG" else "SHORT"
    message = payload.setup_type
    if payload.why_now:
        message = f"{message} — {payload.why_now}" if message else payload.why_now

    signal = AlertSignal(
        symbol=payload.symbol.upper(),
        alert_type=alert_type,
        direction=direction,
        price=payload.current_price,
        entry=payload.entry,
        stop=payload.stop,
        target_1=payload.t1,
        target_2=payload.t2,
        confidence=payload.conviction,
        message=message[:500],
    )

    alert_id = record_alert(signal, user_id=user_id)

    # Load user prefs for notify_user
    with get_sync_db() as conn:
        row = conn.execute(
            "SELECT telegram_enabled, telegram_chat_id, email_enabled, "
            "notification_email FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    if not row:
        return {"ok": False, "alert_id": alert_id, "reason": "user not found"}

    prefs = {
        "telegram_enabled": bool(row["telegram_enabled"]),
        "telegram_chat_id": row["telegram_chat_id"] or "",
        "email_enabled": bool(row["email_enabled"]),
        "notification_email": row["notification_email"] or "",
    }

    email_sent, telegram_sent = notify_user(signal, prefs, alert_id=alert_id)
    return {
        "ok": True,
        "alert_id": alert_id,
        "telegram_sent": telegram_sent,
        "email_sent": email_sent,
    }


@router.post("/best-setups/alert")
async def pin_best_setup_alert(
    payload: PinAlertRequest,
    user: User = Depends(get_current_user),
):
    """Fire a user-pinned Best Setup as an alert (Telegram with Took/Skip/Exit buttons).

    Reuses the existing alert pipeline — same delivery, same callback handling.
    Alert is distinguished from scanner alerts by alert_type=best_setup_day/swing
    and a "BEST SETUP (you pinned)" Telegram header.
    """
    if os.environ.get("BEST_SETUPS_ENABLED", "true").lower() in ("false", "0", "no"):
        raise HTTPException(503, detail="Feature disabled")

    try:
        result = await asyncio.to_thread(_fire_pinned_alert, user.id, payload)
    except Exception as e:
        logger.exception("pin_best_setup_alert: failed")
        raise HTTPException(500, detail=f"Failed to send alert: {str(e)[:80]}")

    if not result.get("ok"):
        raise HTTPException(400, detail=result.get("reason") or "alert failed")

    return result
