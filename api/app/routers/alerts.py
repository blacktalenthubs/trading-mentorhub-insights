"""Alert endpoints: today, history, session summary, SSE stream."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.dependencies import get_current_user, require_pro
from app.models.alert import ActiveEntry, Alert
from app.models.user import User
from app.schemas.alert import AlertResponse, SessionSummaryResponse

router = APIRouter()


def _today() -> str:
    return date.today().isoformat()


@router.get("/today", response_model=List[AlertResponse])
async def alerts_today(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Alert)
        .where(Alert.user_id == user.id, Alert.session_date == _today())
        .order_by(Alert.created_at.desc())
    )
    return result.scalars().all()


@router.get("/history", response_model=List[AlertResponse])
async def alerts_history(
    days: int = Query(default=7, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Alert)
        .where(Alert.user_id == user.id)
        .order_by(Alert.created_at.desc())
        .limit(days * 50)
    )
    return result.scalars().all()


@router.get("/session-summary", response_model=SessionSummaryResponse)
async def session_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = _today()

    # Total alerts
    total_result = await db.execute(
        select(func.count()).where(Alert.user_id == user.id, Alert.session_date == today)
    )
    total = total_result.scalar() or 0

    # Buy alerts
    buy_result = await db.execute(
        select(func.count()).where(
            Alert.user_id == user.id,
            Alert.session_date == today,
            Alert.direction == "BUY",
        )
    )
    buys = buy_result.scalar() or 0

    # Sell alerts
    sell_result = await db.execute(
        select(func.count()).where(
            Alert.user_id == user.id,
            Alert.session_date == today,
            Alert.direction.in_(["SELL", "SHORT"]),
        )
    )
    sells = sell_result.scalar() or 0

    # Target hits
    t1_result = await db.execute(
        select(func.count()).where(
            Alert.user_id == user.id,
            Alert.session_date == today,
            Alert.alert_type == "target_1_hit",
        )
    )
    t1 = t1_result.scalar() or 0

    t2_result = await db.execute(
        select(func.count()).where(
            Alert.user_id == user.id,
            Alert.session_date == today,
            Alert.alert_type == "target_2_hit",
        )
    )
    t2 = t2_result.scalar() or 0

    # Stops
    stop_result = await db.execute(
        select(func.count()).where(
            Alert.user_id == user.id,
            Alert.session_date == today,
            Alert.alert_type == "stop_loss_hit",
        )
    )
    stops = stop_result.scalar() or 0

    # Active entries
    active_result = await db.execute(
        select(func.count()).where(
            ActiveEntry.user_id == user.id,
            ActiveEntry.status == "active",
        )
    )
    active = active_result.scalar() or 0

    return SessionSummaryResponse(
        total_alerts=total,
        buy_alerts=buys,
        sell_alerts=sells,
        target_1_hits=t1,
        target_2_hits=t2,
        stopped_out=stops,
        active_entries=active,
    )


@router.get("/stream")
async def alert_stream(user: User = Depends(require_pro)):
    """SSE endpoint — pushes new alerts in real time (Pro only).

    Monitor publishes to per-user asyncio.Queue via alert_bus.
    Keepalive pings every 30s to keep the connection alive.
    """
    from app.background.alert_bus import subscribe, unsubscribe

    queue = subscribe(user.id)

    async def event_generator():
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {"event": "alert", "data": data}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "keepalive"}
        finally:
            unsubscribe(user.id, queue)

    return EventSourceResponse(event_generator())
