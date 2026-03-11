"""Real trade tracking endpoints."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
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


@router.post("/{trade_id}/close", response_model=RealTradeResponse)
async def close_trade(
    trade_id: int,
    body: CloseRealTradeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
    trade.closed_at = datetime.now(timezone.utc)
    trade.notes = body.notes or trade.notes

    # Calculate P&L
    if trade.direction == "BUY":
        trade.pnl = round((body.exit_price - trade.entry_price) * trade.shares, 2)
    else:
        trade.pnl = round((trade.entry_price - body.exit_price) * trade.shares, 2)

    await db.flush()
    return trade


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
