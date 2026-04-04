"""Alert endpoints: today, history, session summary, ack, PDF export, SSE stream."""

from __future__ import annotations

import asyncio
from datetime import date
from functools import partial
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response as RawResponse
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.dependencies import get_current_user, require_pro
from app.models.alert import ActiveEntry, Alert
from app.models.user import User
from app.schemas.alert import AlertResponse, SessionSummaryResponse

router = APIRouter()


def _run_sync(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(None, partial(fn, *args, **kwargs))


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
    return [AlertResponse.from_orm_alert(a) for a in result.scalars().all()]


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
    return [AlertResponse.from_orm_alert(a) for a in result.scalars().all()]


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


@router.post("/{alert_id}/ack")
async def ack_alert(
    alert_id: int,
    action: str = Query(..., regex="^(took|skipped)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark alert as 'took' or 'skipped'. If 'took', also open a real trade."""
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.user_id == user.id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.user_action = action

    # Auto-create a real trade when user takes the alert
    trade_id = None
    if action == "took" and alert.entry and alert.direction in ("BUY", "SHORT"):
        from app.models.paper_trade import RealTrade

        # Position sizing: $50k cap, SPY fixed at 200 shares
        entry = alert.entry
        if alert.symbol == "SPY":
            shares = 200
        else:
            shares = int(50_000 // entry) if entry > 0 else 0

        trade = RealTrade(
            user_id=user.id,
            symbol=alert.symbol,
            direction=alert.direction,
            shares=shares,
            entry_price=entry,
            stop_price=alert.stop,
            target_price=alert.target_1,
            target_2_price=alert.target_2,
            status="open",
            alert_type=alert.alert_type,
            alert_id=alert.id,
            session_date=alert.session_date,
        )
        db.add(trade)
        await db.flush()
        trade_id = trade.id

    return {"id": alert_id, "user_action": action, "trade_id": trade_id}


@router.get("/session-dates")
async def session_dates(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return distinct session dates with alerts, newest first."""
    result = await db.execute(
        select(distinct(Alert.session_date))
        .where(Alert.user_id == user.id)
        .order_by(Alert.session_date.desc())
        .limit(90)
    )
    return [row[0] for row in result.all()]


@router.get("/session/{session_date}", response_model=SessionSummaryResponse)
async def session_by_date(
    session_date: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Session summary for a specific date."""
    total_result = await db.execute(
        select(func.count()).where(Alert.user_id == user.id, Alert.session_date == session_date)
    )
    total = total_result.scalar() or 0

    buy_result = await db.execute(
        select(func.count()).where(
            Alert.user_id == user.id, Alert.session_date == session_date, Alert.direction == "BUY"
        )
    )
    buys = buy_result.scalar() or 0

    sell_result = await db.execute(
        select(func.count()).where(
            Alert.user_id == user.id,
            Alert.session_date == session_date,
            Alert.direction.in_(["SELL", "SHORT"]),
        )
    )
    sells = sell_result.scalar() or 0

    t1_result = await db.execute(
        select(func.count()).where(
            Alert.user_id == user.id, Alert.session_date == session_date, Alert.alert_type == "target_1_hit"
        )
    )
    t1 = t1_result.scalar() or 0

    t2_result = await db.execute(
        select(func.count()).where(
            Alert.user_id == user.id, Alert.session_date == session_date, Alert.alert_type == "target_2_hit"
        )
    )
    t2 = t2_result.scalar() or 0

    stop_result = await db.execute(
        select(func.count()).where(
            Alert.user_id == user.id, Alert.session_date == session_date, Alert.alert_type == "stop_loss_hit"
        )
    )
    stops = stop_result.scalar() or 0

    active_result = await db.execute(
        select(func.count()).where(ActiveEntry.user_id == user.id, ActiveEntry.status == "active")
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


@router.get("/pdf")
async def alerts_pdf(
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate PDF report of alerts. Returns binary PDF."""
    from alerts_pdf import generate_alerts_pdf

    today = _today()
    sd = start_date or today
    ed = end_date or today

    result = await db.execute(
        select(Alert)
        .where(
            Alert.user_id == user.id,
            Alert.session_date >= sd,
            Alert.session_date <= ed,
        )
        .order_by(Alert.session_date.desc(), Alert.created_at.desc())
    )
    alerts = result.scalars().all()

    # Convert ORM to dicts for PDF generator
    alert_dicts = []
    for a in alerts:
        alert_dicts.append({
            "id": a.id, "symbol": a.symbol, "alert_type": a.alert_type,
            "direction": a.direction, "price": a.price, "entry": a.entry,
            "stop": a.stop, "target_1": a.target_1, "target_2": a.target_2,
            "confidence": a.confidence, "message": a.message,
            "created_at": str(a.created_at), "session_date": a.session_date,
        })

    # Group by date for summaries
    dates = sorted(set(a["session_date"] for a in alert_dicts), reverse=True)
    summaries: dict = {}
    for d in dates:
        day_alerts = [a for a in alert_dicts if a["session_date"] == d]
        summaries[d] = {
            "total": len(day_alerts),
            "buy_count": sum(1 for a in day_alerts if a["direction"] == "BUY"),
            "sell_count": sum(1 for a in day_alerts if a["direction"] in ("SELL", "SHORT")),
        }

    pdf_bytes = await _run_sync(generate_alerts_pdf, alert_dicts, summaries, dates)
    return RawResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="alerts_{sd}_{ed}.pdf"'},
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
