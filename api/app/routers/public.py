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

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from jose import jwt
from pydantic import BaseModel
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import ADMIN_EMAILS
from app.models.alert import Alert
from app.models.site_visit import SiteVisit
from app.models.user import User
from app.schemas.alert import AlertResponse

logger = logging.getLogger("public")
router = APIRouter()


class TrackVisitIn(BaseModel):
    path: str
    visitor_id: str
    referrer: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


@router.post("/track", status_code=204)
async def track_visit(
    payload: TrackVisitIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public page-view logger — the frontend pings this on every route change.

    No auth required; if a valid bearer token is present we best-effort attach
    the user_id (so we can split logged-in vs anonymous traffic). Never raises
    to the client — analytics must not break navigation.
    """
    settings = get_settings()
    user_id: Optional[int] = None
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            data = jwt.decode(
                auth.split(" ", 1)[1],
                settings.JWT_SECRET,
                algorithms=[settings.JWT_ALGORITHM],
            )
            user_id = int(data.get("sub", 0)) or None
        except Exception:
            user_id = None

    ua = request.headers.get("User-Agent")
    ref = payload.referrer
    try:
        db.add(
            SiteVisit(
                visitor_id=(payload.visitor_id or "anon")[:64],
                user_id=user_id,
                path=(payload.path or "/")[:300],
                referrer=ref[:500] if ref else None,
                user_agent=ua[:400] if ua else None,
                utm_source=(payload.utm_source or None) and payload.utm_source[:80],
                utm_medium=(payload.utm_medium or None) and payload.utm_medium[:80],
                utm_campaign=(payload.utm_campaign or None) and payload.utm_campaign[:120],
            )
        )
        await db.commit()
    except Exception:  # pragma: no cover - analytics is best-effort
        await db.rollback()
    return None


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
    """Return distinct session dates that have DELIVERED signals, newest first.
    Public. Dates with only muted/unrouted alerts (no delivered signal) are
    excluded so the report's date picker matches the Signals feed."""
    uid = await _public_user_id(db)
    result = await db.execute(
        select(distinct(Alert.session_date))
        .where(Alert.user_id == uid, Alert.suppressed_reason.is_(None))
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
    """Return the DELIVERED signals for a session date (admin user's stream). Public.

    Only delivered alerts (suppressed_reason IS NULL) — the same set as the live
    Signals feed. Muted (type_not_enabled) and unrouted (gated / confluence-
    collapsed) rows are EXCLUDED, so the EOD report and its stats reflect what
    actually fired, not what was held back. If `date` is omitted, returns the
    most recent session with delivered signals. `symbol` restricts to one stock.
    """
    uid = await _public_user_id(db)

    if not date:
        latest = await db.execute(
            select(Alert.session_date)
            .where(Alert.user_id == uid, Alert.suppressed_reason.is_(None))
            .order_by(Alert.session_date.desc())
            .limit(1)
        )
        date = latest.scalar_one_or_none() or _today_str()

    stmt = select(Alert).where(
        Alert.user_id == uid,
        Alert.session_date == date,
        Alert.suppressed_reason.is_(None),
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


@router.get("/performance/{token}")
async def public_performance(token: str, db: AsyncSession = Depends(get_db)):
    """Read-only shared performance snapshot (unauthenticated) — created via
    POST /api/v1/performance/share. 404 if the token is unknown."""
    from sqlalchemy import text as _text
    import json as _json
    try:
        row = (await db.execute(_text(
            "SELECT payload, created_at FROM share_links "
            "WHERE token = :t AND kind = 'performance' LIMIT 1"
        ), {"t": token})).first()
    except Exception:
        row = None
    if not row:
        raise HTTPException(status_code=404, detail="Shared report not found")
    data = _json.loads(row.payload) if isinstance(row.payload, str) else row.payload
    data["shared_at"] = str(row.created_at) if row.created_at else None
    return data
