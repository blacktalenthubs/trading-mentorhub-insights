"""Real trade tracking endpoints (stocks + options)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date, datetime, timezone
from functools import partial
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.paper_trade import RealTrade
from app.models.user import User
from app.schemas.paper_trade import (
    CloseRealTradeRequest,
    OpenRealTradeRequest,
    RealTradeResponse,
    RealTradeStatsResponse,
)

router = APIRouter()

# Default position sizing
_DEFAULT_CAP = 50_000
_SPY_SHARES = 200


def _calculate_shares(symbol: str, entry_price: float) -> int:
    if symbol.upper() == "SPY":
        return _SPY_SHARES
    return int(_DEFAULT_CAP // entry_price) if entry_price > 0 else 0


@router.post("/open", response_model=RealTradeResponse, status_code=201)
async def open_trade(
    body: OpenRealTradeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    symbol = body.symbol.upper()
    shares = body.shares or _calculate_shares(symbol, body.entry_price)

    trade = RealTrade(
        user_id=user.id,
        symbol=symbol,
        direction=body.direction.upper(),
        shares=shares,
        entry_price=body.entry_price,
        stop_price=body.stop_price,
        target_price=body.target_price,
        target_2_price=body.target_2_price,
        alert_type=body.alert_type,
        notes=body.notes,
        session_date=date.today().isoformat(),
    )
    db.add(trade)
    await db.flush()
    return trade


@router.post("/{trade_id}/close")
async def close_trade(
    trade_id: int,
    body: CloseRealTradeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import logging
    _log = logging.getLogger("real_trades")
    try:
        result = await db.execute(
            select(RealTrade).where(RealTrade.id == trade_id, RealTrade.user_id == user.id)
        )
        trade = result.scalar_one_or_none()
        if not trade:
            raise HTTPException(status_code=404, detail="Trade not found")
        if trade.status != "open":
            raise HTTPException(status_code=409, detail="Trade already closed")

        trade.exit_price = body.exit_price
        trade.status = "closed"
        trade.closed_at = datetime.utcnow()
        trade.notes = body.notes or trade.notes

        # Calculate P&L
        if trade.direction == "BUY":
            trade.pnl = round((body.exit_price - trade.entry_price) * trade.shares, 2)
        else:
            trade.pnl = round((trade.entry_price - body.exit_price) * trade.shares, 2)

        await db.flush()
        return {
            "id": trade.id,
            "symbol": trade.symbol,
            "direction": trade.direction,
            "pnl": trade.pnl,
            "status": trade.status,
            "exit_price": trade.exit_price,
        }
    except HTTPException:
        raise
    except Exception as e:
        _log.exception("Close trade %d failed", trade_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/open", response_model=List[RealTradeResponse])
async def get_open_trades(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RealTrade)
        .where(RealTrade.user_id == user.id, RealTrade.status == "open")
        .order_by(RealTrade.opened_at.desc())
    )
    return result.scalars().all()


@router.get("/closed", response_model=List[RealTradeResponse])
async def get_closed_trades(
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RealTrade)
        .where(RealTrade.user_id == user.id, RealTrade.status == "closed")
        .order_by(RealTrade.closed_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/stats", response_model=RealTradeStatsResponse)
async def trade_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RealTrade).where(
            RealTrade.user_id == user.id, RealTrade.status == "closed"
        )
    )
    trades = result.scalars().all()

    if not trades:
        return RealTradeStatsResponse(
            total_pnl=0, total_trades=0, win_count=0, loss_count=0,
            win_rate=0, avg_win=0, avg_loss=0, expectancy=0,
        )

    wins = [t for t in trades if t.pnl and t.pnl > 0]
    losses = [t for t in trades if t.pnl and t.pnl <= 0]
    total_pnl = sum(t.pnl or 0 for t in trades)
    avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0
    total = len(trades)
    win_rate = len(wins) / total * 100 if total else 0

    # Expectancy = (win_rate * avg_win) + (loss_rate * avg_loss)
    loss_rate = len(losses) / total if total else 0
    expectancy = (win_rate / 100 * avg_win) + (loss_rate * avg_loss)

    return RealTradeStatsResponse(
        total_pnl=round(total_pnl, 2),
        total_trades=total,
        win_count=len(wins),
        loss_count=len(losses),
        win_rate=round(win_rate, 1),
        avg_win=round(avg_win, 2),
        avg_loss=round(avg_loss, 2),
        expectancy=round(expectancy, 2),
    )


# --- Performance Breakdown ---

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_HOUR_LABELS = {
    9: "9AM", 10: "10AM", 11: "11AM", 12: "12PM",
    13: "1PM", 14: "2PM", 15: "3PM", 16: "4PM",
}


def _format_alert_type(raw: str) -> str:
    """Convert 'ma_bounce_20' → 'MA Bounce 20'."""
    return raw.replace("_", " ").title()


@router.get("/performance-breakdown")
async def performance_breakdown(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Breakdown of closed trade performance by pattern, time, symbol, and day."""
    result = await db.execute(
        select(RealTrade).where(
            RealTrade.user_id == user.id, RealTrade.status == "closed"
        )
    )
    trades = result.scalars().all()

    if not trades:
        return {
            "by_pattern": [],
            "by_hour": [],
            "by_symbol": [],
            "by_day": [],
        }

    # ── By Pattern (alert_type) ──
    pattern_map: dict[str, dict] = defaultdict(lambda: {"trades": 0, "wins": 0, "total_pnl": 0.0})
    for t in trades:
        key = t.alert_type or "unknown"
        bucket = pattern_map[key]
        bucket["trades"] += 1
        bucket["total_pnl"] += t.pnl or 0
        if t.pnl and t.pnl > 0:
            bucket["wins"] += 1

    by_pattern = []
    for pattern, d in pattern_map.items():
        cnt = d["trades"]
        by_pattern.append({
            "pattern": pattern,
            "label": _format_alert_type(pattern),
            "trades": cnt,
            "wins": d["wins"],
            "win_rate": round(d["wins"] / cnt * 100, 1) if cnt else 0,
            "avg_pnl": round(d["total_pnl"] / cnt, 2) if cnt else 0,
            "total_pnl": round(d["total_pnl"], 2),
        })
    by_pattern.sort(key=lambda x: x["trades"], reverse=True)

    # ── By Hour of Day ──
    hour_map: dict[int, dict] = defaultdict(lambda: {"trades": 0, "wins": 0, "total_pnl": 0.0})
    for t in trades:
        if t.opened_at:
            h = t.opened_at.hour
            bucket = hour_map[h]
            bucket["trades"] += 1
            bucket["total_pnl"] += t.pnl or 0
            if t.pnl and t.pnl > 0:
                bucket["wins"] += 1

    by_hour = []
    for hour, d in hour_map.items():
        cnt = d["trades"]
        by_hour.append({
            "hour": f"{hour}:00",
            "label": _HOUR_LABELS.get(hour, f"{hour}:00"),
            "trades": cnt,
            "wins": d["wins"],
            "win_rate": round(d["wins"] / cnt * 100, 1) if cnt else 0,
            "avg_pnl": round(d["total_pnl"] / cnt, 2) if cnt else 0,
        })
    by_hour.sort(key=lambda x: x["trades"], reverse=True)

    # ── By Symbol ──
    symbol_map: dict[str, dict] = defaultdict(lambda: {"trades": 0, "wins": 0, "total_pnl": 0.0})
    for t in trades:
        bucket = symbol_map[t.symbol]
        bucket["trades"] += 1
        bucket["total_pnl"] += t.pnl or 0
        if t.pnl and t.pnl > 0:
            bucket["wins"] += 1

    by_symbol = []
    for sym, d in symbol_map.items():
        cnt = d["trades"]
        by_symbol.append({
            "symbol": sym,
            "trades": cnt,
            "wins": d["wins"],
            "win_rate": round(d["wins"] / cnt * 100, 1) if cnt else 0,
            "total_pnl": round(d["total_pnl"], 2),
        })
    by_symbol.sort(key=lambda x: x["trades"], reverse=True)

    # ── By Day of Week ──
    day_map: dict[int, dict] = defaultdict(lambda: {"trades": 0, "wins": 0})
    for t in trades:
        if t.opened_at:
            dow = t.opened_at.weekday()  # 0=Monday
            bucket = day_map[dow]
            bucket["trades"] += 1
            if t.pnl and t.pnl > 0:
                bucket["wins"] += 1

    by_day = []
    for dow, d in day_map.items():
        cnt = d["trades"]
        by_day.append({
            "day": _DAY_NAMES[dow],
            "trades": cnt,
            "wins": d["wins"],
            "win_rate": round(d["wins"] / cnt * 100, 1) if cnt else 0,
        })
    by_day.sort(key=lambda x: x["trades"], reverse=True)

    return {
        "by_pattern": by_pattern,
        "by_hour": by_hour,
        "by_symbol": by_symbol,
        "by_day": by_day,
    }


# --- Notes ---

class UpdateNotesRequest(BaseModel):
    notes: str


@router.put("/{trade_id}/notes")
async def update_notes(
    trade_id: int,
    body: UpdateNotesRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RealTrade).where(RealTrade.id == trade_id, RealTrade.user_id == user.id)
    )
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    trade.notes = body.notes
    await db.flush()
    return {"id": trade_id, "notes": trade.notes}


# --- Equity Curve ---

@router.get("/equity-curve")
async def equity_curve(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cumulative P&L series from closed trades, sorted by close date."""
    result = await db.execute(
        select(RealTrade)
        .where(RealTrade.user_id == user.id, RealTrade.status == "closed")
        .order_by(RealTrade.closed_at.asc())
    )
    trades = result.scalars().all()
    cumulative = 0.0
    curve = []
    for t in trades:
        cumulative += t.pnl or 0
        curve.append({
            "date": t.session_date,
            "pnl": round(cumulative, 2),
        })
    return curve


# --- Options Trades (wraps alerting/options_trade_store.py) ---

def _run_sync(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(None, partial(fn, *args, **kwargs))


class OpenOptionsRequest(BaseModel):
    symbol: str
    option_type: str  # "call" or "put"
    strike: float
    expiration: str
    contracts: int = 1
    premium_per_contract: float
    alert_type: Optional[str] = None
    alert_id: Optional[int] = None


class CloseOptionsRequest(BaseModel):
    exit_premium: float
    notes: str = ""


@router.post("/options/open", status_code=201)
async def open_options_trade(
    body: OpenOptionsRequest,
    user: User = Depends(get_current_user),
):
    from alerting.options_trade_store import open_options_trade as _open

    trade_id = await _run_sync(
        _open,
        body.symbol.upper(),
        body.option_type,
        body.strike,
        body.expiration,
        body.contracts,
        body.premium_per_contract,
        body.alert_type,
        body.alert_id,
        date.today().isoformat(),
    )
    return {"id": trade_id}


@router.post("/options/{trade_id}/close")
async def close_options_trade(
    trade_id: int,
    body: CloseOptionsRequest,
    user: User = Depends(get_current_user),
):
    from alerting.options_trade_store import close_options_trade as _close

    pnl = await _run_sync(_close, trade_id, body.exit_premium, body.notes)
    return {"id": trade_id, "pnl": pnl}


@router.post("/options/{trade_id}/expire")
async def expire_options_trade(
    trade_id: int,
    user: User = Depends(get_current_user),
):
    from alerting.options_trade_store import expire_options_trade as _expire

    pnl = await _run_sync(_expire, trade_id)
    return {"id": trade_id, "pnl": pnl}


@router.get("/options/open")
async def get_open_options(user: User = Depends(get_current_user)):
    from alerting.options_trade_store import get_open_options_trades

    return await _run_sync(get_open_options_trades)


@router.get("/options/closed")
async def get_closed_options(
    limit: int = Query(default=200, le=500),
    user: User = Depends(get_current_user),
):
    from alerting.options_trade_store import get_closed_options_trades

    return await _run_sync(get_closed_options_trades, limit)


@router.get("/options/stats")
async def get_options_stats(user: User = Depends(get_current_user)):
    from alerting.options_trade_store import get_options_trade_stats

    return await _run_sync(get_options_trade_stats)
