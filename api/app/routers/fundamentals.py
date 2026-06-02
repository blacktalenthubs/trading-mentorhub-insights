"""Fundamentals endpoints — Watchlist > Details tab.

GET  /watchlist  → cached fundamentals + analyst ratings + AI views for the
                   user's watchlist symbols (null fields for un-fetched symbols).
POST /refresh    → on-demand fetch + AI-generate + upsert for one symbol, or
                   the whole watchlist ({"all": true}).

The refresh path is synchronous + slow (Finnhub throttle + yfinance + Anthropic),
so it runs in a thread-pool executor against the sync session factory wired into
app.state.sync_session_factory (same pattern as the routers/intel.py data calls).
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from functools import partial
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.fundamentals import SymbolFundamentals
from app.models.user import User
from app.models.watchlist import WatchlistItem

router = APIRouter()


def _run_sync(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(None, partial(fn, *args, **kwargs))


class FundamentalsItem(BaseModel):
    symbol: str
    company_name: Optional[str] = None
    description: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[float] = None
    trailing_eps: Optional[float] = None
    forward_eps: Optional[float] = None
    eps_growth_pct: Optional[float] = None
    pe_ratio: Optional[float] = None
    rec_strong_buy: Optional[int] = None
    rec_buy: Optional[int] = None
    rec_hold: Optional[int] = None
    rec_sell: Optional[int] = None
    rec_strong_sell: Optional[int] = None
    consensus: Optional[str] = None
    rec_period: Optional[str] = None
    short_term_view: Optional[str] = None
    long_term_view: Optional[str] = None
    fetched_at: Optional[str] = None  # ISO timestamp; None = never fetched


class FundamentalsResponse(BaseModel):
    items: List[FundamentalsItem]
    last_refreshed_at: Optional[str]


class RefreshRequest(BaseModel):
    symbol: Optional[str] = None
    all: bool = False


def _to_item(sym: str, row: Optional[SymbolFundamentals]) -> FundamentalsItem:
    if row is None:
        return FundamentalsItem(symbol=sym)
    return FundamentalsItem(
        symbol=sym,
        company_name=row.company_name,
        description=row.description,
        sector=row.sector,
        industry=row.industry,
        market_cap=row.market_cap,
        trailing_eps=row.trailing_eps,
        forward_eps=row.forward_eps,
        eps_growth_pct=row.eps_growth_pct,
        pe_ratio=row.pe_ratio,
        rec_strong_buy=row.rec_strong_buy,
        rec_buy=row.rec_buy,
        rec_hold=row.rec_hold,
        rec_sell=row.rec_sell,
        rec_strong_sell=row.rec_strong_sell,
        consensus=row.consensus,
        rec_period=row.rec_period,
        short_term_view=row.short_term_view,
        long_term_view=row.long_term_view,
        fetched_at=row.fetched_at.isoformat() if row.fetched_at else None,
    )


@router.get("/watchlist", response_model=FundamentalsResponse)
async def watchlist_fundamentals(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cached fundamentals for the user's watchlist. Un-fetched symbols appear
    with null fields + fetched_at=None so the UI can prompt a Refresh.
    """
    sym_rows = (await db.execute(
        select(WatchlistItem.symbol)
        .where(WatchlistItem.user_id == user.id)
        .distinct()
    )).all()
    symbols = sorted({r[0].upper() for r in sym_rows if r[0]})
    if not symbols:
        return FundamentalsResponse(items=[], last_refreshed_at=None)

    rows = (await db.execute(
        select(SymbolFundamentals).where(SymbolFundamentals.symbol.in_(symbols))
    )).scalars().all()
    by_sym = {r.symbol: r for r in rows}

    most_recent: Optional[str] = None
    items: list[FundamentalsItem] = []
    for sym in symbols:
        row = by_sym.get(sym)
        if row and row.fetched_at:
            iso = row.fetched_at.isoformat()
            if most_recent is None or iso > most_recent:
                most_recent = iso
        items.append(_to_item(sym, row))

    return FundamentalsResponse(items=items, last_refreshed_at=most_recent)


@router.post("/refresh")
async def refresh_fundamentals(
    body: RefreshRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Fetch + AI-generate + upsert. Single symbol (`symbol`) or whole
    watchlist (`all: true`). Runs off the event loop — the AI + network calls
    are blocking and can take several seconds.
    """
    session_factory = request.app.state.sync_session_factory

    if body.all or not body.symbol:
        from analytics.fundamentals_refresh import refresh_all
        return await _run_sync(refresh_all, session_factory)

    from analytics.fundamentals_refresh import refresh_one
    return await _run_sync(refresh_one, session_factory, body.symbol)
