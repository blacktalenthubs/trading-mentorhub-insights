"""Earnings endpoints — spec 61.

Returns the user's watchlist symbols joined with their next earnings event
and the most recent historical surprise %. Powers the Watchlist > Earnings
tab.
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.earnings import Earnings, EarningsHistory
from app.models.user import User
from app.models.watchlist import WatchlistItem


router = APIRouter()


class UpcomingEarningsItem(BaseModel):
    symbol: str
    next_earnings_date: Optional[date]
    days_until: Optional[int]
    time_of_day: Optional[str]      # BMO / AMC / DMH / null
    eps_estimate: Optional[float]
    revenue_estimate: Optional[float]
    confirmed: bool
    last_surprise_pct: Optional[float]
    last_quarter_label: Optional[str]
    last_reported_at: Optional[date]
    fetched_at: Optional[str]       # ISO timestamp


class UpcomingEarningsResponse(BaseModel):
    items: List[UpcomingEarningsItem]
    last_refreshed_at: Optional[str]   # most recent fetched_at across user's symbols


@router.get("/upcoming", response_model=UpcomingEarningsResponse)
async def upcoming_earnings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """User's watchlist symbols sorted by next earnings date ASC, with
    last-quarter surprise attached. Symbols with no Finnhub data return
    a row with nulls so the user knows we tried.
    """
    today = date.today()

    # 1. The user's watchlist symbols.
    sym_rows = (await db.execute(
        select(WatchlistItem.symbol)
        .where(WatchlistItem.user_id == user.id)
        .distinct()
    )).all()
    symbols = sorted({r[0].upper() for r in sym_rows if r[0]})
    if not symbols:
        return UpcomingEarningsResponse(items=[], last_refreshed_at=None)

    # 2. Upcoming earnings rows for those symbols.
    earnings_rows = (await db.execute(
        select(Earnings).where(Earnings.symbol.in_(symbols))
    )).scalars().all()
    earnings_by_sym = {e.symbol: e for e in earnings_rows}

    # 3. Most recent historical surprise per symbol (one DB round-trip).
    # Subquery would be cleaner but SQLAlchemy distinct-on across dialects
    # is fiddly — fetch all 4 quarters and pick the latest in Python.
    history_rows = (await db.execute(
        select(EarningsHistory)
        .where(EarningsHistory.symbol.in_(symbols))
        .order_by(EarningsHistory.symbol, desc(EarningsHistory.reported_at))
    )).scalars().all()
    last_hist_by_sym: dict[str, EarningsHistory] = {}
    for h in history_rows:
        if h.symbol not in last_hist_by_sym:
            last_hist_by_sym[h.symbol] = h

    # 4. Assemble items. Symbols with no earnings row still appear so the
    # tab doesn't hide them — user knows we tried and Finnhub had nothing.
    items: list[UpcomingEarningsItem] = []
    most_recent_fetch: Optional[str] = None

    for sym in symbols:
        e = earnings_by_sym.get(sym)
        h = last_hist_by_sym.get(sym)
        days_until = None
        if e and e.next_earnings_date:
            days_until = (e.next_earnings_date - today).days
        fetched_iso = e.fetched_at.isoformat() if (e and e.fetched_at) else None
        if fetched_iso and (most_recent_fetch is None or fetched_iso > most_recent_fetch):
            most_recent_fetch = fetched_iso

        items.append(UpcomingEarningsItem(
            symbol=sym,
            next_earnings_date=e.next_earnings_date if e else None,
            days_until=days_until,
            time_of_day=e.time_of_day if e else None,
            eps_estimate=e.eps_estimate if e else None,
            revenue_estimate=e.revenue_estimate if e else None,
            confirmed=bool(e.confirmed) if e else False,
            last_surprise_pct=h.surprise_pct if h else None,
            last_quarter_label=h.quarter_label if h else None,
            last_reported_at=h.reported_at if h else None,
            fetched_at=fetched_iso,
        ))

    # Sort: rows with a date first (sorted asc), rows without a date last.
    items.sort(key=lambda i: (
        0 if i.next_earnings_date is not None else 1,
        i.next_earnings_date or date.max,
        i.symbol,
    ))

    return UpcomingEarningsResponse(
        items=items,
        last_refreshed_at=most_recent_fetch,
    )
