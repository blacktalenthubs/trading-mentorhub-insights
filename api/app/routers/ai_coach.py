"""AI Coach endpoints — Spec 40: Best Setups of the Day."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
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

    # Convert dataclass to plain dict for JSON serialization
    return {
        "generated_at": result.generated_at,
        "watchlist_size": result.watchlist_size,
        "setups_found": result.setups_found,
        "picks": result.picks,
        "skipped": result.skipped,
        "error": result.error,
    }
