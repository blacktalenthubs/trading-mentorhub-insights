"""Focus List endpoints — persist and review AI Best Setups scans.

Wraps the existing Best Setups engine (analytics/ai_best_setups.py) with
persistence: every completed scan is saved as a FocusList snapshot, retrievable
without re-invoking the AI.

  POST /ai/focus-lists/run     run the scan + persist (consumes quota)
  GET  /ai/focus-lists/latest  the current saved focus list (no AI, no quota)
  GET  /ai/focus-lists         browsable history (no AI)
  GET  /ai/focus-lists/{id}    one full saved focus list (no AI, no quota)
"""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_user_tier
from app.models.focus_list import FocusList
from app.models.user import User
from app.services.focus_list_service import (
    build_recommendations,
    classify_market_window,
    et_today,
    save_focus_list,
    utcnow,
)
from app.tier import get_limits

logger = logging.getLogger(__name__)
router = APIRouter()

_FEATURE_BEST_SETUPS = "best_setups"
# Soft twice-daily cadence — the 3rd+ run of the day prompts a confirmation.
_CADENCE_SOFT_LIMIT = 2


def _sync_factory():
    """Build a sync session factory for the threaded Best Setups scanner."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.config import get_settings

    sync_url = get_settings().DATABASE_URL
    for suffix in ("+asyncpg", "+psycopg2", "+psycopg"):
        sync_url = sync_url.replace(suffix, "")
    return sessionmaker(bind=create_engine(sync_url, pool_pre_ping=True))


async def _get_usage(db: AsyncSession, user_id: int, session_date: str) -> int:
    row = (await db.execute(
        text(
            "SELECT usage_count FROM usage_limits "
            "WHERE user_id = :uid AND feature = :f AND usage_date = :d"
        ),
        {"uid": user_id, "f": _FEATURE_BEST_SETUPS, "d": session_date},
    )).fetchone()
    return int(row[0]) if row else 0


async def _increment_usage(db: AsyncSession, user_id: int, session_date: str) -> None:
    """Increment the daily best_setups counter — committed with the request txn."""
    await db.execute(
        text(
            "INSERT INTO usage_limits (user_id, feature, usage_date, usage_count) "
            "VALUES (:uid, :f, :d, 1) "
            "ON CONFLICT (user_id, feature, usage_date) "
            "DO UPDATE SET usage_count = usage_limits.usage_count + 1"
        ),
        {"uid": user_id, "f": _FEATURE_BEST_SETUPS, "d": session_date},
    )


def _serialize(row: FocusList, *, include_recs: bool = True) -> dict:
    data = {
        "id": row.id,
        "generated_at": row.generated_at.isoformat() if row.generated_at else None,
        "session_date": row.session_date,
        "market_window": row.market_window,
        "status": row.status,
        "watchlist_size": row.watchlist_size,
        "skipped": row.skipped or [],
        "message": row.message,
    }
    if include_recs:
        data["recommendations"] = row.recommendations or []
    return data


@router.post("/focus-lists/run")
async def run_focus_list(
    force: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run the AI Best Setups scan and persist the result as a focus list.

    Consumes one daily best_setups run on success or no-setups. A failed scan
    saves a `failed` row but consumes no quota and never replaces the prior list.
    """
    if os.environ.get("BEST_SETUPS_ENABLED", "true").lower() in ("false", "0", "no"):
        raise HTTPException(503, detail="Feature disabled")

    tier = get_user_tier(user)
    cap = get_limits(tier).get("best_setups_per_day")
    session_date = et_today()
    used = await _get_usage(db, user.id, session_date)

    # Hard cap — tier daily limit. Saved lists stay readable via the GET routes.
    if cap is not None and used >= cap:
        raise HTTPException(
            429,
            detail={
                "error": "daily_limit_reached",
                "tier": tier,
                "cap": cap,
                "message": (
                    f"Daily best-setups limit reached ({cap}). Your saved focus "
                    f"lists are still available — upgrade for more scans."
                ),
            },
        )

    # Soft twice-daily cadence — pause before the 3rd+ run so we don't spend an
    # AI run to discover the cadence is exceeded. The client re-calls with force.
    if used >= _CADENCE_SOFT_LIMIT and not force:
        return {
            "cadence_check": True,
            "runs_today": used,
            "cadence_exceeded": True,
            "message": (
                f"You've already run {used} scans today. Your saved focus lists "
                f"are still available without spending another AI run."
            ),
        }

    # Run the scan in a thread — yfinance + Anthropic calls are blocking.
    from analytics.ai_best_setups import generate_best_setups

    result = await asyncio.to_thread(generate_best_setups, user.id, _sync_factory())

    generated_at = utcnow()
    market_window = classify_market_window(generated_at)

    if result.error:
        row = await save_focus_list(
            db,
            user_id=user.id,
            generated_at=generated_at,
            session_date=session_date,
            market_window=market_window,
            status="failed",
            watchlist_size=result.watchlist_size,
            recommendations=[],
            skipped=result.skipped or [],
            message=result.error,
        )
        runs_today = used  # failed run consumes no quota
    else:
        recs = build_recommendations(result.day_trade_picks, result.swing_trade_picks)
        if recs:
            status_val, message = "has_setups", None
        elif result.watchlist_size == 0:
            status_val = "no_setups"
            message = "Add symbols to your watchlist to get setups."
        else:
            status_val = "no_setups"
            message = "No qualifying setups right now — check back at the next window."
        row = await save_focus_list(
            db,
            user_id=user.id,
            generated_at=generated_at,
            session_date=session_date,
            market_window=market_window,
            status=status_val,
            watchlist_size=result.watchlist_size,
            recommendations=recs,
            skipped=result.skipped or [],
            message=message,
        )
        await _increment_usage(db, user.id, session_date)
        runs_today = used + 1

    payload = _serialize(row)
    payload["cadence_check"] = False
    payload["runs_today"] = runs_today
    payload["cadence_exceeded"] = runs_today >= _CADENCE_SOFT_LIMIT
    return payload


@router.get("/focus-lists/latest")
async def latest_focus_list(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current focus list — the newest has_setups/no_setups row.

    Never consumes an AI run. Returns an empty 204 when the user has no list.
    """
    row = (await db.execute(
        select(FocusList)
        .where(
            FocusList.user_id == user.id,
            FocusList.status.in_(("has_setups", "no_setups")),
        )
        .order_by(FocusList.generated_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    if row is None:
        return Response(status_code=204)

    data = _serialize(row)
    data["is_stale"] = row.session_date < et_today()
    return data


@router.get("/focus-lists")
async def focus_list_history(
    limit: int = 30,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's focus-list history (metadata only), newest first."""
    limit = max(1, min(limit, 60))
    offset = max(0, offset)

    total = (await db.execute(
        select(func.count()).select_from(FocusList).where(FocusList.user_id == user.id)
    )).scalar_one()

    rows = (await db.execute(
        select(FocusList)
        .where(FocusList.user_id == user.id)
        .order_by(FocusList.generated_at.desc())
        .limit(limit)
        .offset(offset)
    )).scalars().all()

    items = []
    for row in rows:
        meta = _serialize(row, include_recs=False)
        meta["recommendation_count"] = len(row.recommendations or [])
        items.append(meta)
    return {"items": items, "total": total}


@router.get("/focus-lists/{list_id}")
async def focus_list_detail(
    list_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return one full saved focus list. Never consumes an AI run."""
    row = (await db.execute(
        select(FocusList).where(
            FocusList.id == list_id,
            FocusList.user_id == user.id,
        )
    )).scalar_one_or_none()

    if row is None:
        raise HTTPException(404, detail="Focus list not found")

    data = _serialize(row)
    data["is_stale"] = row.session_date < et_today()
    return data
