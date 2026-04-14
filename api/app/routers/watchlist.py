"""Watchlist CRUD endpoints."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_user_tier
from app.tier import get_limits
from app.models.user import User
from app.models.watchlist import WatchlistItem
from app.schemas.watchlist import AddSymbolRequest, BulkSetRequest, WatchlistItemResponse
from app.services.symbol_resolver import resolve_symbol

router = APIRouter()


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
    limits = get_limits(tier)
    max_symbols = limits["watchlist_max"]
    raw_symbol = body.symbol.upper().strip()

    # Check limit per tier
    count_result = await db.execute(
        select(WatchlistItem).where(WatchlistItem.user_id == user.id)
    )
    if len(count_result.scalars().all()) >= max_symbols:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "upgrade_required",
                "current_tier": tier,
                "limit": max_symbols,
                "message": f"{tier.title()} tier limited to {max_symbols} symbols. Upgrade for more.",
            },
        )

    # Resolve user input → canonical symbol via Alpaca probe
    resolved = resolve_symbol(raw_symbol)

    if resolved.kind == "unknown":
        raise HTTPException(
            status_code=404,
            detail={
                "error": "symbol_not_found",
                "input": raw_symbol,
                "message": f"No data found for '{raw_symbol}'. Check spelling or try the full form (e.g. BCH-USD for crypto).",
            },
        )

    if resolved.kind == "ambiguous":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "ambiguous_symbol",
                "input": raw_symbol,
                "message": f"'{raw_symbol}' matches both an equity and a crypto. Pick one.",
                "options": [
                    {
                        "symbol": opt.symbol,
                        "kind": opt.kind,
                        "display_name": opt.display_name,
                        "last_price": opt.last_price,
                    }
                    for opt in resolved.options
                ],
            },
        )

    # Single match — use canonical form (may differ from user input, e.g. BCH → BCH-USD)
    symbol = resolved.canonical or raw_symbol

    # Check duplicate against canonical form
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
    await db.execute(
        delete(WatchlistItem).where(
            WatchlistItem.user_id == user.id,
            WatchlistItem.symbol == symbol.upper(),
        )
    )


@router.put("", response_model=List[WatchlistItemResponse])
async def bulk_set(
    body: BulkSetRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tier = get_user_tier(user)
    symbols = [s.upper().strip() for s in body.symbols]

    limits = get_limits(tier)
    max_symbols = limits["watchlist_max"]
    if len(symbols) > max_symbols:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "upgrade_required",
                "current_tier": tier,
                "limit": max_symbols,
                "message": f"{tier.title()} tier limited to {max_symbols} symbols. Upgrade for more.",
            },
        )

    # Replace all
    await db.execute(delete(WatchlistItem).where(WatchlistItem.user_id == user.id))
    items = [WatchlistItem(user_id=user.id, symbol=s) for s in symbols]
    db.add_all(items)
    await db.flush()
    return items
