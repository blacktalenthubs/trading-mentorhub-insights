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
import json
import logging
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user, require_ai_access
from app.models.fundamentals import SymbolFundamentals
from app.models.user import User
from app.models.watchlist import WatchlistItem

logger = logging.getLogger(__name__)

router = APIRouter()


def _sync_session_factory():
    """Build a standalone sync engine + session factory from DATABASE_URL —
    independent of app.state, so the on-demand refresh works regardless of
    lifespan startup order (app.state.sync_session_factory is unset if the
    scheduler startup block raised). Same pattern as the social-buzz refresh."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    url = get_settings().DATABASE_URL
    if url.startswith("sqlite"):
        url = url.replace("+aiosqlite", "")
    else:
        for suffix in ("+asyncpg", "+psycopg2", "+psycopg"):
            url = url.replace(suffix, "")
    engine = create_engine(url, pool_pre_ping=True)
    return engine, sessionmaker(bind=engine)


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
    # Structured AI brief (dict of sections + model) + extra decision metrics.
    ai_brief: Optional[dict] = None
    ai_generated_at: Optional[str] = None
    metrics: Optional[dict] = None
    fetched_at: Optional[str] = None  # ISO timestamp; None = never fetched


class FundamentalsResponse(BaseModel):
    items: List[FundamentalsItem]
    last_refreshed_at: Optional[str]


class RefreshRequest(BaseModel):
    symbol: Optional[str] = None
    all: bool = False


def _loads(raw: Optional[str]) -> Optional[Any]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


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
        ai_brief=_loads(getattr(row, "ai_brief", None)),
        ai_generated_at=row.ai_generated_at.isoformat() if getattr(row, "ai_generated_at", None) else None,
        metrics=_loads(getattr(row, "metrics_json", None)),
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


@router.get("/{symbol}", response_model=FundamentalsItem)
async def symbol_fundamentals(
    symbol: str,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Full fundamentals + AI brief for ANY symbol (not just the caller's watchlist) —
    feeds the 'Top Ideas' dossier in Research. Null fields + fetched_at=None when never
    fetched, so the UI prompts a Refresh / Generate. (Declared after /watchlist so that
    exact path still wins.)"""
    sym = symbol.upper().strip()
    row = (await db.execute(
        select(SymbolFundamentals).where(SymbolFundamentals.symbol == sym).limit(1)
    )).scalars().first()
    return _to_item(sym, row)


def _refresh_in_thread(symbol: Optional[str], do_all: bool, with_ai: bool) -> dict:
    engine, factory = _sync_session_factory()
    try:
        if do_all:
            from analytics.fundamentals_refresh import refresh_all
            return refresh_all(factory, with_ai=with_ai)
        from analytics.fundamentals_refresh import refresh_one
        return refresh_one(factory, symbol, with_ai=with_ai)
    finally:
        engine.dispose()


@router.post("/refresh")
async def refresh_fundamentals(
    body: RefreshRequest,
    user: User = Depends(get_current_user),
):
    """Refresh the NUMBERS only (Finnhub fundamentals + analyst ratings + metrics)
    for a symbol or the whole watchlist. No LLM cost — the AI brief is generated
    separately by admins via /ai-refresh (and auto on newly-added symbols).

    Uses its OWN sync session factory (not app.state.sync_session_factory,
    which is unset when the scheduler startup block raised — that previously
    500'd this endpoint and left the Details tab perpetually un-fetched).
    """
    do_all = body.all or not body.symbol
    try:
        return await asyncio.to_thread(_refresh_in_thread, body.symbol, do_all, False)
    except Exception as e:  # surface the real cause instead of an opaque 500
        logger.exception("Fundamentals refresh endpoint failed")
        raise HTTPException(status_code=500, detail=f"refresh failed: {e}")


@router.post("/ai-refresh")
async def ai_refresh_fundamentals(
    body: RefreshRequest,
    user: User = Depends(require_ai_access),
):
    """Admin-only: (re)generate the structured AI investment brief (Sonnet) for a
    symbol or the whole watchlist, and refresh its numbers. The brief is stored
    per-symbol and read by every user, so this is run sparingly (admin / on-add)."""
    do_all = body.all or not body.symbol
    try:
        return await asyncio.to_thread(_refresh_in_thread, body.symbol, do_all, True)
    except Exception as e:
        logger.exception("Fundamentals AI-refresh endpoint failed")
        raise HTTPException(status_code=500, detail=f"ai-refresh failed: {e}")
