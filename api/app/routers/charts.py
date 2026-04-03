"""Chart levels + OHLCV endpoints with caching."""

from __future__ import annotations

import asyncio
import sys
from functools import partial
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_get, cache_set
from app.database import get_db
from app.dependencies import get_current_user
from app.models.chart import ChartLevel
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.chart import ChartLevelRequest, ChartLevelResponse
from app.schemas.market import OHLCBar

_root = str(Path(__file__).resolve().parents[3])
if _root not in sys.path:
    sys.path.insert(0, _root)

from analytics.market_data import fetch_ohlc  # noqa: E402

router = APIRouter()

_OHLCV_TTL = 900  # 15 min for daily bars


# --- Chart Levels ---

@router.get("/levels", response_model=List[ChartLevelResponse])
async def get_levels(
    symbol: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChartLevel)
        .where(ChartLevel.user_id == user.id, ChartLevel.symbol == symbol.upper())
        .order_by(ChartLevel.price)
    )
    return result.scalars().all()


@router.post("/levels", response_model=ChartLevelResponse, status_code=201)
async def add_level(
    body: ChartLevelRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    level = ChartLevel(
        user_id=user.id,
        symbol=body.symbol.upper(),
        price=body.price,
        label=body.label,
        color=body.color,
    )
    db.add(level)
    await db.flush()
    return level


@router.delete("/levels/{level_id}", status_code=204)
async def delete_level(
    level_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        delete(ChartLevel).where(ChartLevel.id == level_id, ChartLevel.user_id == user.id)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Level not found")


# --- OHLCV ---

def _fetch_and_serialize_ohlcv(symbol: str, period: str, interval: str = "1d") -> List[dict]:
    df = fetch_ohlc(symbol, period, interval=interval)
    if df.empty:
        return []
    # Drop duplicate timestamps (yfinance can return dupes on intraday intervals)
    df = df[~df.index.duplicated(keep="last")]
    df = df.sort_index()
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


@router.get("/ohlcv/{symbol}", response_model=List[OHLCBar])
@limiter.limit("15/minute")
async def ohlcv(
    request: Request,
    symbol: str,
    period: str = "3mo",
    interval: str = "1d",
    user: User = Depends(get_current_user),
):
    """Get OHLCV bars for charting (cached). Supports any yfinance period/interval."""
    key = f"ohlcv:{symbol.upper()}:{period}:{interval}"
    cached = cache_get(key)
    if cached is not None:
        return cached

    loop = asyncio.get_event_loop()
    bars = await loop.run_in_executor(
        None, partial(_fetch_and_serialize_ohlcv, symbol.upper(), period, interval)
    )
    if bars:
        cache_set(key, bars, _OHLCV_TTL)
    return bars
