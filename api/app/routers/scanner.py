"""Scanner endpoints: scan watchlist, premarket, active entries."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import List

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.alert import ActiveEntry
from app.models.user import User
from app.models.watchlist import WatchlistItem
from app.rate_limit import limiter
from app.schemas.scanner import ActiveEntryResponse, SignalResultResponse
from app.services.scanner import run_scan

router = APIRouter()


async def _get_user_symbols(user: User, db: AsyncSession) -> List[str]:
    result = await db.execute(
        select(WatchlistItem.symbol)
        .where(WatchlistItem.user_id == user.id)
        .order_by(WatchlistItem.id)
    )
    return [row[0] for row in result.all()]


@router.get("/scan", response_model=List[SignalResultResponse])
@limiter.limit("5/minute")
async def scan(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run daily scanner on user's watchlist."""
    symbols = await _get_user_symbols(user, db)
    if not symbols:
        return []
    # Run CPU-bound scanner in thread pool
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, partial(run_scan, symbols))
    return results


@router.get("/active-entries", response_model=List[ActiveEntryResponse])
async def active_entries(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get active entries for the user's current session."""
    result = await db.execute(
        select(ActiveEntry)
        .where(ActiveEntry.user_id == user.id, ActiveEntry.status == "active")
        .order_by(ActiveEntry.created_at.desc())
    )
    return result.scalars().all()
