"""Alert endpoints: today, history, session summary, ack, PDF export, SSE stream."""

from __future__ import annotations

import asyncio
from datetime import date
from functools import partial
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response as RawResponse
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.dependencies import get_current_user, get_user_tier, require_pro
from app.tier import get_limits
from app.models.alert import ActiveEntry, Alert
from app.models.user import User
from app.schemas.alert import AlertResponse, SessionSummaryResponse

router = APIRouter()


def _run_sync(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(None, partial(fn, *args, **kwargs))


def _today() -> str:
    return date.today().isoformat()


async def _history_user_id(user: User, db: AsyncSession) -> int:
    """Return the user_id to scope read-only history queries to.

    2026-06-01 public-access launch: when a user has zero rows in the
    `alerts` table (brand-new accounts that only just started receiving
    fan-out), fall back to the first admin's user_id. Lets them see the
    historical patterns + past session reports immediately — the alerts
    are read-only by definition (their own user_action / exit_price stays
    NULL because they didn't act on them). Once they have at least one
    row of their own, they switch to their own history.
    """
    exists = await db.execute(
        select(Alert.id).where(Alert.user_id == user.id).limit(1)
    )
    if exists.scalar_one_or_none() is not None:
        return user.id
    from app.dependencies import ADMIN_EMAILS
    admin_id = (await db.execute(
        select(User.id).where(User.email.in_(ADMIN_EMAILS)).order_by(User.id).limit(1)
    )).scalar_one_or_none()
    return admin_id if admin_id is not None else user.id


def _grade_filter_clause(user: User):
    """Returns a SQLAlchemy WHERE fragment for the user's min_alert_grade
    setting. 'A' = A only; 'B' = A + B; 'C' or anything else = no filter.
    Applied on /alerts/today and /alerts/history. Performance / Weekly
    intentionally don't filter — those are for analysis, not feed noise
    control.

    Free tier is clamped to A-grade regardless of the user's own setting —
    the alert firehose (B/C grades) is a Pro perk (alerts_min_grade limit).
    """
    mg = (user.min_alert_grade or "C").upper()
    from app.dependencies import get_user_tier
    from app.tier import get_limits
    floor = get_limits(get_user_tier(user)).get("alerts_min_grade")
    if floor == "A":
        mg = "A"  # free: force A-only, ignore any wider personal setting
    if mg == "A":
        return Alert.grade == "A"
    if mg == "B":
        return Alert.grade.in_(["A", "B"])
    return None  # no filter


@router.get("/today", response_model=List[AlertResponse])
async def alerts_today(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    grade_clause = _grade_filter_clause(user)

    # Try today first
    base = select(Alert).where(Alert.user_id == user.id, Alert.session_date == _today())
    if grade_clause is not None:
        base = base.where(grade_clause)
    result = await db.execute(base.order_by(Alert.created_at.desc()))
    alerts = result.scalars().all()

    # If no alerts today, show the most recent session (weekend/after-hours)
    if not alerts:
        latest = await db.execute(
            select(Alert.session_date)
            .where(Alert.user_id == user.id)
            .order_by(Alert.session_date.desc())
            .limit(1)
        )
        last_date = latest.scalar_one_or_none()
        if last_date:
            q2 = select(Alert).where(Alert.user_id == user.id, Alert.session_date == last_date)
            if grade_clause is not None:
                q2 = q2.where(grade_clause)
            result2 = await db.execute(q2.order_by(Alert.created_at.desc()))
            alerts = result2.scalars().all()

    # Include tier limits in response for frontend gating
    tier = get_user_tier(user)
    limits = get_limits(tier)
    visible = limits.get("visible_alerts")
    all_alerts = [AlertResponse.from_orm_alert(a) for a in alerts]

    # Return all alerts but include meta for frontend blurring
    return all_alerts


@router.get("/history", response_model=List[AlertResponse])
async def alerts_history(
    days: int = Query(default=7, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Enforce tier-based history depth. Admin users bypass all caps.
    from app.dependencies import is_admin_user
    if not is_admin_user(user):
        tier = get_user_tier(user)
        limits = get_limits(tier)
        max_days = limits.get("alert_history_days")
        if max_days is not None:
            days = min(days, max(max_days, 1))

    # Row cap was previously `days * 50` (4500 for 90 days). With high
    # alert volume (~70+ per day for active users), older sessions were
    # getting cut off entirely. Bumped to 200/day so even very busy
    # symbols stay in scope. Admin users get a higher ceiling.
    rows_per_day = 500 if is_admin_user(user) else 200

    grade_clause = _grade_filter_clause(user)
    scope_uid = await _history_user_id(user, db)
    q = select(Alert).where(Alert.user_id == scope_uid)
    if grade_clause is not None:
        q = q.where(grade_clause)
    result = await db.execute(
        q.order_by(Alert.created_at.desc()).limit(days * rows_per_day)
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


@router.post("/{alert_id}/exit")
async def set_alert_exit_price(
    alert_id: int,
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record the actual exit price for a Took alert.

    Body: `{"exit_price": 142.50}` — pass null/0 to clear.
    Returns the saved exit_price plus computed r_multiple when entry+stop exist.
    """
    raw = body.get("exit_price")
    new_exit: Optional[float] = None
    if raw is not None and raw != "":
        try:
            v = float(raw)
            new_exit = v if v > 0 else None
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="exit_price must be a number")

    result = await db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.user_id == user.id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.exit_price = new_exit

    r_mult: Optional[float] = None
    if new_exit is not None and alert.entry and alert.stop and alert.entry != alert.stop:
        risk = alert.entry - alert.stop  # positive for longs (entry > stop)
        if risk != 0:
            r_mult = round((new_exit - alert.entry) / risk, 2)
    return {"id": alert_id, "exit_price": new_exit, "r_multiple": r_mult}


@router.post("/{alert_id}/outcome")
async def set_alert_outcome(
    alert_id: int,
    outcome: str = Query(..., regex="^(worked|failed|clear)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually grade an alert's outcome — worked / failed / clear (un-mark)."""
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.user_id == user.id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.outcome = None if outcome == "clear" else outcome
    return {"id": alert_id, "outcome": alert.outcome}


@router.get("/by-alert-type-performance")
async def by_alert_type_performance(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Per-alert-type performance roll-up for the Trades page.

    Source of truth: user's Took alerts that have a recorded exit_price.
    Filters to the live spec-58 catalog only (no retired ai_*, no
    open_*, no breakouts, no shorts). Returns R-based stats — no
    fictional dollar P&L. R = (exit - entry) / (entry - stop).
    """
    from app.models.alert_type_config import ALERT_TYPE_CATALOG, describe_alert_type

    live_types = {row[0] for row in ALERT_TYPE_CATALOG}
    label_map = {row[0]: row[1] for row in ALERT_TYPE_CATALOG}

    rows = (await db.execute(
        select(
            Alert.alert_type, Alert.entry, Alert.stop, Alert.exit_price,
            Alert.user_action,
        ).where(
            Alert.user_id == user.id,
            Alert.user_action == "took",
        )
    )).all()

    agg: dict[str, dict] = {}
    for at, entry, stop, exit_price, _action in rows:
        if at not in live_types:
            continue  # ignore retired alert types
        d = agg.setdefault(at, {
            "took": 0, "with_exit": 0, "wins": 0,
            "r_sum": 0.0, "r_best": None, "r_worst": None,
        })
        d["took"] += 1
        if exit_price is None or entry is None or stop is None or entry == stop:
            continue
        risk = entry - stop
        if risk == 0:
            continue
        r = (exit_price - entry) / risk
        d["with_exit"] += 1
        d["r_sum"] += r
        if r > 0:
            d["wins"] += 1
        d["r_best"] = r if d["r_best"] is None else max(d["r_best"], r)
        d["r_worst"] = r if d["r_worst"] is None else min(d["r_worst"], r)

    items = []
    for at, d in agg.items():
        items.append({
            "alert_type": at,
            "label": label_map.get(at, at),
            "description": describe_alert_type(at),
            "took": d["took"],
            "with_exit": d["with_exit"],
            "wins": d["wins"],
            "win_rate": round(d["wins"] / d["with_exit"] * 100, 1) if d["with_exit"] else None,
            "avg_r": round(d["r_sum"] / d["with_exit"], 2) if d["with_exit"] else None,
            "best_r": round(d["r_best"], 2) if d["r_best"] is not None else None,
            "worst_r": round(d["r_worst"], 2) if d["r_worst"] is not None else None,
        })
    items.sort(key=lambda x: (-(x["with_exit"] or 0), -(x["took"] or 0), x["alert_type"]))
    return {"items": items}


@router.get("/scorecard")
async def alert_scorecard(
    session_date: str = Query(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Win rate by alert_type from the manual outcome marks, for one session.

    Falls back to admin's outcomes when the caller has no rows yet — the
    scorecard then shows the founder's historical wins as a reference
    track-record (read-only).
    """
    sd = session_date or _today()
    scope_uid = await _history_user_id(user, db)
    rows = (await db.execute(
        select(Alert.alert_type, Alert.outcome).where(
            Alert.user_id == scope_uid,
            Alert.session_date == sd,
            Alert.outcome.isnot(None),
        )
    )).all()
    agg: dict[str, dict] = {}
    for at, oc in rows:
        d = agg.setdefault(at, {"worked": 0, "failed": 0})
        if oc == "worked":
            d["worked"] += 1
        elif oc == "failed":
            d["failed"] += 1
    items = []
    for at, d in agg.items():
        graded = d["worked"] + d["failed"]
        items.append({
            "alert_type": at,
            "worked": d["worked"],
            "failed": d["failed"],
            "graded": graded,
            "win_rate": round(d["worked"] / graded * 100, 1) if graded else 0.0,
            "group": "swing" if at.startswith("swing_") else "day",
        })
    items.sort(key=lambda x: (-x["graded"], x["alert_type"]))
    return {"session_date": sd, "items": items}


@router.get("/session-dates")
async def session_dates(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return distinct session dates with alerts, newest first.

    Falls back to admin's session list when the caller has no rows yet
    (brand-new public-access users — see _history_user_id).
    """
    scope_uid = await _history_user_id(user, db)
    result = await db.execute(
        select(distinct(Alert.session_date))
        .where(Alert.user_id == scope_uid)
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
    """Session summary for a specific date.

    Falls back to admin's data when the caller has no alert rows yet.
    """
    scope_uid = await _history_user_id(user, db)
    total_result = await db.execute(
        select(func.count()).where(Alert.user_id == scope_uid, Alert.session_date == session_date)
    )
    total = total_result.scalar() or 0

    buy_result = await db.execute(
        select(func.count()).where(
            Alert.user_id == scope_uid, Alert.session_date == session_date, Alert.direction == "BUY"
        )
    )
    buys = buy_result.scalar() or 0

    sell_result = await db.execute(
        select(func.count()).where(
            Alert.user_id == scope_uid,
            Alert.session_date == session_date,
            Alert.direction.in_(["SELL", "SHORT"]),
        )
    )
    sells = sell_result.scalar() or 0

    t1_result = await db.execute(
        select(func.count()).where(
            Alert.user_id == scope_uid, Alert.session_date == session_date, Alert.alert_type == "target_1_hit"
        )
    )
    t1 = t1_result.scalar() or 0

    t2_result = await db.execute(
        select(func.count()).where(
            Alert.user_id == scope_uid, Alert.session_date == session_date, Alert.alert_type == "target_2_hit"
        )
    )
    t2 = t2_result.scalar() or 0

    stop_result = await db.execute(
        select(func.count()).where(
            Alert.user_id == scope_uid, Alert.session_date == session_date, Alert.alert_type == "stop_loss_hit"
        )
    )
    stops = stop_result.scalar() or 0

    active_result = await db.execute(
        select(func.count()).where(ActiveEntry.user_id == scope_uid, ActiveEntry.status == "active")
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
            "created_at": a.created_at.isoformat() + "Z" if a.created_at else None,
            "session_date": a.session_date,
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
