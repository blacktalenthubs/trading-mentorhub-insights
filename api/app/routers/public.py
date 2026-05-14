"""Public (unauthenticated) endpoints for the shareable EOD report.

These routes expose the admin user's alerts so anyone with a link can view
the day's signals without logging in. Used for marketing + sharing.

All endpoints under `/api/v1/public/` skip authentication. Only the admin
user's data is exposed — other users' alerts stay private.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import ADMIN_EMAILS
from app.models.alert import Alert
from app.models.user import User
from app.schemas.alert import AlertResponse

logger = logging.getLogger("public")
router = APIRouter()


async def _public_user_id(db: AsyncSession) -> int:
    """Resolve the admin user_id whose alerts are exposed publicly.

    Picks the first admin user (by email match against ADMIN_EMAILS).
    Cached implicitly per request — small overhead, no auth surface.
    """
    stmt = select(User.id).where(User.email.in_(ADMIN_EMAILS)).order_by(User.id).limit(1)
    result = await db.execute(stmt)
    uid = result.scalar_one_or_none()
    if uid is None:
        raise HTTPException(
            status_code=503,
            detail="No public user configured (admin account not found)",
        )
    return uid


@router.get("/eod-report/session-dates")
async def public_session_dates(db: AsyncSession = Depends(get_db)):
    """Return distinct session dates with alerts, newest first. Public."""
    uid = await _public_user_id(db)
    result = await db.execute(
        select(distinct(Alert.session_date))
        .where(Alert.user_id == uid)
        .order_by(Alert.session_date.desc())
        .limit(90)
    )
    return [row[0] for row in result.all()]


@router.get("/eod-report/alerts", response_model=List[AlertResponse])
async def public_alerts_for_date(
    date: Optional[str] = Query(default=None, description="YYYY-MM-DD; defaults to most recent session"),
    symbol: Optional[str] = Query(default=None, description="Optional symbol filter (e.g., NVDA)"),
    db: AsyncSession = Depends(get_db),
):
    """Return all alerts for a session date (admin user's stream). Public.

    If `date` is omitted, returns the most recent session with alerts. If
    `symbol` is provided, restricts to just that symbol for the per-stock
    review view.
    """
    uid = await _public_user_id(db)

    if not date:
        latest = await db.execute(
            select(Alert.session_date)
            .where(Alert.user_id == uid)
            .order_by(Alert.session_date.desc())
            .limit(1)
        )
        date = latest.scalar_one_or_none() or _today_str()

    stmt = select(Alert).where(
        Alert.user_id == uid,
        Alert.session_date == date,
    )
    if symbol:
        stmt = stmt.where(Alert.symbol == symbol.upper())
    stmt = stmt.order_by(Alert.created_at.desc()).limit(2000)

    result = await db.execute(stmt)
    return [AlertResponse.from_orm_alert(a) for a in result.scalars().all()]


@router.get("/alert/{alert_id}", response_model=AlertResponse)
async def public_alert_by_id(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Return a single alert by id (admin user's stream only). Public.

    Used by the public replay/chart view when linking from the EOD report.
    Returns 404 if the alert belongs to a non-admin user.
    """
    uid = await _public_user_id(db)
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.user_id == uid)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertResponse.from_orm_alert(alert)


def _today_str() -> str:
    return date.today().isoformat()
