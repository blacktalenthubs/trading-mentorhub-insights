"""Market data endpoints with Redis/memory caching."""

from __future__ import annotations

import asyncio
import sys
from functools import partial
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Request

from app.cache import cache_get, cache_set
from app.dependencies import get_current_user
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.market import MarketStatusResponse, OHLCBar, PriorDayResponse

# Add project root so analytics is importable
_root = str(Path(__file__).resolve().parents[3])
if _root not in sys.path:
    sys.path.insert(0, _root)

from analytics.market_hours import is_market_hours, is_premarket, get_session_phase  # noqa: E402
from analytics.intraday_data import fetch_intraday, fetch_prior_day  # noqa: E402

router = APIRouter()

# Cache TTLs (seconds)
_INTRADAY_TTL = 180  # 3 min — matches monitor interval
_PRIOR_DAY_TTL = 3600  # 1 hour — stale after close


@router.get("/status", response_model=MarketStatusResponse)
async def market_status(user: User = Depends(get_current_user)):
    return MarketStatusResponse(
        is_open=is_market_hours(),
        is_premarket=is_premarket(),
        session_phase=get_session_phase(),
    )


def _fetch_and_serialize_intraday(symbol: str) -> List[dict]:
    df = fetch_intraday(symbol)
    if df.empty:
        return []
    return [
        {
            "timestamp": str(ts),
            "open": round(row["Open"], 2),
            "high": round(row["High"], 2),
            "low": round(row["Low"], 2),
            "close": round(row["Close"], 2),
            "volume": round(row["Volume"], 0),
        }
        for ts, row in df.iterrows()
    ]


@router.get("/intraday/{symbol}", response_model=List[OHLCBar])
@limiter.limit("20/minute")
async def intraday(
    request: Request,
    symbol: str,
    user: User = Depends(get_current_user),
):
    """Get today's 5-min intraday bars for a symbol (cached)."""
    key = f"intraday:{symbol.upper()}"
    cached = cache_get(key)
    if cached is not None:
        return cached

    loop = asyncio.get_event_loop()
    bars = await loop.run_in_executor(
        None, partial(_fetch_and_serialize_intraday, symbol.upper())
    )
    if bars:
        cache_set(key, bars, _INTRADAY_TTL)
    return bars


@router.get("/prior-day/{symbol}", response_model=Optional[PriorDayResponse])
@limiter.limit("20/minute")
async def prior_day(
    request: Request,
    symbol: str,
    user: User = Depends(get_current_user),
):
    """Get prior completed day's data for a symbol (cached)."""
    key = f"prior_day:{symbol.upper()}"
    cached = cache_get(key)
    if cached is not None:
        return PriorDayResponse(**cached) if cached else None

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, partial(fetch_prior_day, symbol.upper()))
    if not data:
        cache_set(key, {}, _PRIOR_DAY_TTL)
        return None
    cache_set(key, data, _PRIOR_DAY_TTL)
    return PriorDayResponse(**data)
