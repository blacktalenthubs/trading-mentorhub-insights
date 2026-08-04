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
from app.schemas.chart import ChartLevelRequest, ChartLevelResponse, ChartLevelUpdate
from app.schemas.market import OHLCBar

_root = str(Path(__file__).resolve().parents[3])
if _root not in sys.path:
    sys.path.insert(0, _root)

from analytics.market_data import fetch_ohlc  # noqa: E402
from config import is_crypto_alert_symbol  # noqa: E402
import pandas as pd  # noqa: E402

router = APIRouter()

_OHLCV_TTL = 900  # 15 min for daily bars
_OHLCV_NEG_TTL = 120  # cache empties 2 min so a data-less symbol doesn't re-hammer


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
    symbol = body.symbol.upper()
    # Server-side dedup — bulletproof against client races / repeat fires: if a
    # line already sits within ~0.15% of this price, return it instead of stacking.
    existing = (await db.execute(
        select(ChartLevel).where(ChartLevel.user_id == user.id, ChartLevel.symbol == symbol)
    )).scalars().all()
    for e in existing:
        if abs(e.price - body.price) / max(abs(body.price), 1e-9) < 0.0015:
            return e

    level = ChartLevel(
        user_id=user.id,
        symbol=symbol,
        price=body.price,
        label=body.label,
        color=body.color,
    )
    db.add(level)
    await db.flush()
    return level


@router.put("/levels/{level_id}", response_model=ChartLevelResponse)
async def update_level(
    level_id: int,
    body: ChartLevelUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reprice and/or retype (label + color) an existing line — owner only."""
    level = (await db.execute(
        select(ChartLevel).where(ChartLevel.id == level_id, ChartLevel.user_id == user.id)
    )).scalar_one_or_none()
    if level is None:
        raise HTTPException(status_code=404, detail="Level not found")
    if body.price is not None:
        level.price = body.price
    if body.label is not None:
        level.label = body.label
    if body.color is not None:
        level.color = body.color
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

def _resample_4h(df, is_crypto: bool):
    """1h -> session-aligned 4h. Equity: RTH 09:30-16:00, buckets anchored 09:30/13:30 ET (matches
    TV's "240"). Crypto: 4h blocks anchored 00:00 UTC. yfinance/Alpaca have no native 4h interval."""
    if df is None or df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return df
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    try:
        d = df.tz_localize("UTC") if df.index.tz is None else df
        if is_crypto:
            return d.tz_convert("UTC").resample("4h").agg(agg).dropna()
        et = d.tz_convert("America/New_York").between_time("09:30", "16:00")
        return et.resample("4h", offset="9h30min").agg(agg).dropna()
    except Exception:
        return df


def _fetch_and_serialize_ohlcv(symbol: str, period: str, interval: str = "1d") -> List[dict]:
    if interval == "4h":
        # no native 4h source -> fetch 1h and resample session-aligned
        df = _resample_4h(fetch_ohlc(symbol, period, interval="1h"), is_crypto_alert_symbol(symbol))
    else:
        df = fetch_ohlc(symbol, period, interval=interval)
    if df is None or df.empty:
        return []
    # Drop duplicate timestamps (yfinance can return dupes on intraday intervals)
    df = df[~df.index.duplicated(keep="last")]
    # Drop bars with any missing OHLC. A NaN survives round() and serializes to
    # JSON null, which makes lightweight-charts throw "Value is null" and takes
    # down the whole chart on a single bad bar.
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if df.empty:
        return []
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
@limiter.limit("120/minute")
async def ohlcv(
    request: Request,
    symbol: str,
    period: str = "3mo",
    interval: str = "1d",
    user: User = Depends(get_current_user),
):
    """Get OHLCV bars for charting (cached). Supports any yfinance period/interval.

    Rate limit is generous (120/min) because the chart PREFETCHES ~20 symbols on
    load plus auto-refetches the selected one — a tight cap (was 15/min) 429'd the
    prefetch burst, leaving clicked symbols with no data ("Loading chart…" forever).
    The result is cached (15 min), so most hits never touch the data source anyway.
    """
    key = f"ohlcv:{symbol.upper()}:{period}:{interval}"
    cached = cache_get(key)
    if cached is not None:
        return cached

    loop = asyncio.get_event_loop()
    bars = await loop.run_in_executor(
        None, partial(_fetch_and_serialize_ohlcv, symbol.upper(), period, interval)
    )
    # Cache success for 15 min; cache EMPTY briefly too (negative cache) so a symbol
    # the data source can't serve doesn't re-fetch + re-block on every single click.
    cache_set(key, bars, _OHLCV_TTL if bars else _OHLCV_NEG_TTL)
    return bars


_LVL_GREEN = "#22c55e"  # support (below price)
_LVL_RED = "#ef4444"    # resistance (above price)


def _fourh_level_list(symbol: str, days: int = 3) -> List[dict]:
    """The 4H structural stack for the chart overlay — last two SESSION-ALIGNED 4h candles' H/L +
    PDH/PDL + PWH/PWL + PMH/PML — computed server-side so it matches the platform's 4h chart and the
    4h pine. Colored by role vs the last price (green support / red resistance)."""
    is_crypto = is_crypto_alert_symbol(symbol)
    price = None
    pairs: List[tuple] = []
    try:
        a = _resample_4h(fetch_ohlc(symbol, "1mo", interval="1h"), is_crypto)
        if a is not None and len(a) >= 3:
            price = float(a["Close"].iloc[-1])
            pairs = [("4H-1 H", float(a["High"].iloc[-2])), ("4H-1 L", float(a["Low"].iloc[-2])),
                     ("4H-2 H", float(a["High"].iloc[-3])), ("4H-2 L", float(a["Low"].iloc[-3]))]
    except Exception:
        pairs = []
    try:
        dfd = fetch_ohlc(symbol, "1y", interval="1d")
        if dfd is not None and len(dfd) >= 2:
            if price is None:
                price = float(dfd["Close"].iloc[-1])
            # N days of prior-day H/L (PDH1=yesterday .. PDHn), like the pdh_pdl_5days pine
            for _d in range(1, days + 1):
                if len(dfd) >= _d + 1:
                    pairs += [(f"PDH{_d}", float(dfd["High"].iloc[-1 - _d])),
                              (f"PDL{_d}", float(dfd["Low"].iloc[-1 - _d]))]
            if len(dfd) >= 40 and isinstance(dfd.index, pd.DatetimeIndex):
                _d = pd.DataFrame({"h": dfd["High"].values, "l": dfd["Low"].values}, index=dfd.index)
                for rule, hl, ll in (("W", "PWH", "PWL"), ("M", "PMH", "PML")):
                    ag = _d.resample(rule).agg({"h": "max", "l": "min"}).dropna()
                    if len(ag) >= 2:
                        pairs += [(hl, float(ag["h"].iloc[-2])), (ll, float(ag["l"].iloc[-2]))]
    except Exception:
        pass
    out: List[dict] = []
    for i, (label, p) in enumerate(pairs):
        if p is None or p <= 0:
            continue
        color = _LVL_GREEN if (price is not None and p < price) else _LVL_RED
        out.append({"id": -(100 + i), "symbol": symbol.upper(), "price": round(p, 2), "label": label, "color": color})
    return out


@router.get("/fourh-levels/{symbol}", response_model=List[ChartLevelResponse])
@limiter.limit("120/minute")
async def fourh_levels(request: Request, symbol: str, days: int = 3, user: User = Depends(get_current_user)):
    """The 4H structural levels for the chart overlay (same key structure the 4h pine draws) +
    `days` prior-day H/L (PDH1..PDHn / PDL1..PDLn, default 3) like the pdh_pdl 5-day pine."""
    days = max(1, min(days, 5))
    key = f"fourh_levels:{symbol.upper()}:{days}"
    cached = cache_get(key)
    if cached is not None:
        return cached
    loop = asyncio.get_event_loop()
    lvls = await loop.run_in_executor(None, partial(_fourh_level_list, symbol.upper(), days))
    cache_set(key, lvls, 300)
    return lvls


@router.get("/replay/{alert_id}")
async def chart_replay(
    alert_id: int,
    request: Request,
):
    """Get chart replay data for an alert — OHLCV bars + outcome. Public for Signal Library."""
    from app.services.replay import get_replay_data

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, partial(get_replay_data, alert_id))
    if not data:
        raise HTTPException(404, "Alert not found")
    return data
