"""Diagnostic endpoints — post-session audit of AI scanner output."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.alert import Alert
from app.models.user import User
from app.schemas.alert import AlertResponse

router = APIRouter()

AI_UPDATE_TYPES = ("ai_scan_wait", "ai_resistance")


@router.get("/ai-updates", response_model=List[AlertResponse])
async def ai_updates(
    session_date: str = Query(..., description="YYYY-MM-DD"),
    symbols: Optional[str] = Query(None, description="Comma-separated symbols"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Alert)
        .where(
            Alert.user_id == user.id,
            Alert.session_date == session_date,
            Alert.alert_type.in_(AI_UPDATE_TYPES),
        )
        .order_by(Alert.symbol, Alert.created_at)
    )
    if symbols:
        wanted = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if wanted:
            stmt = stmt.where(Alert.symbol.in_(wanted))

    result = await db.execute(stmt)
    return [AlertResponse.from_orm_alert(a) for a in result.scalars().all()]
