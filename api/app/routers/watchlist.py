"""Watchlist CRUD endpoints."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user, get_user_tier
from app.models.user import User
from app.models.watchlist import WatchlistItem
from app.schemas.watchlist import AddSymbolRequest, BulkSetRequest, WatchlistItemResponse

router = APIRouter()
settings = get_settings()


@router.get("", response_model=List[WatchlistItemResponse])
async def get_watchlist(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WatchlistItem)
        .where(WatchlistItem.user_id == user.id)
        .order_by(WatchlistItem.id)
    )
    return result.scalars().all()


@router.post("", response_model=WatchlistItemResponse, status_code=status.HTTP_201_CREATED)
async def add_symbol(
    body: AddSymbolRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tier = get_user_tier(user)
    symbol = body.symbol.upper().strip()

    # Check limit for free tier
    if tier == "free":
        count_result = await db.execute(
            select(WatchlistItem).where(WatchlistItem.user_id == user.id)
        )
        if len(count_result.scalars().all()) >= settings.FREE_WATCHLIST_MAX:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Free tier limited to {settings.FREE_WATCHLIST_MAX} symbols",
            )

    # Check duplicate
    existing = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.user_id == user.id,
            WatchlistItem.symbol == symbol,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Symbol already in watchlist")

    item = WatchlistItem(user_id=user.id, symbol=symbol)
    db.add(item)
    await db.flush()
    return item


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_symbol(
    symbol: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        delete(WatchlistItem).where(
            WatchlistItem.user_id == user.id,
            WatchlistItem.symbol == symbol.upper(),
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Symbol not in watchlist")


@router.put("", response_model=List[WatchlistItemResponse])
async def bulk_set(
    body: BulkSetRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tier = get_user_tier(user)
    symbols = [s.upper().strip() for s in body.symbols]

    if tier == "free" and len(symbols) > settings.FREE_WATCHLIST_MAX:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Free tier limited to {settings.FREE_WATCHLIST_MAX} symbols",
        )

    # Replace all
    await db.execute(delete(WatchlistItem).where(WatchlistItem.user_id == user.id))
    items = [WatchlistItem(user_id=user.id, symbol=s) for s in symbols]
    db.add_all(items)
    await db.flush()
    return items
