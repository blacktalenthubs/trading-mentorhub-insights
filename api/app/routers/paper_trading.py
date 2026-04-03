"""Paper trading endpoints (Alpaca integration)."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_pro
from app.models.paper_trade import PaperTrade
from app.models.user import User
from app.schemas.paper_trade import PaperTradeResponse

router = APIRouter()


@router.get("/positions", response_model=List[PaperTradeResponse])
async def get_positions(
    user: User = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
):
    """Get open paper trading positions."""
    result = await db.execute(
        select(PaperTrade)
        .where(PaperTrade.user_id == user.id, PaperTrade.status == "open")
        .order_by(PaperTrade.opened_at.desc())
    )
    return result.scalars().all()


@router.get("/history", response_model=List[PaperTradeResponse])
async def get_history(
    limit: int = 50,
    user: User = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
):
    """Get closed paper trades."""
    result = await db.execute(
        select(PaperTrade)
        .where(PaperTrade.user_id == user.id, PaperTrade.status == "closed")
        .order_by(PaperTrade.closed_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/account")
async def get_account_summary(
    user: User = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
):
    """Get paper trading account summary."""
    # Open positions
    open_result = await db.execute(
        select(func.count()).where(
            PaperTrade.user_id == user.id, PaperTrade.status == "open"
        )
    )
    open_count = open_result.scalar() or 0

    # Closed stats
    closed_result = await db.execute(
        select(PaperTrade).where(
            PaperTrade.user_id == user.id, PaperTrade.status == "closed"
        )
    )
    closed_trades = closed_result.scalars().all()

    total_pnl = sum(t.pnl or 0 for t in closed_trades)
    wins = sum(1 for t in closed_trades if t.pnl and t.pnl > 0)
    total_closed = len(closed_trades)
    win_rate = round(wins / total_closed * 100, 1) if total_closed else 0

    return {
        "open_positions": open_count,
        "total_closed": total_closed,
        "total_pnl": round(total_pnl, 2),
        "win_rate": win_rate,
    }


@router.get("/equity-curve")
async def equity_curve(
    user: User = Depends(require_pro),
    db: AsyncSession = Depends(get_db),
):
    """Cumulative P&L from closed paper trades."""
    result = await db.execute(
        select(PaperTrade)
        .where(PaperTrade.user_id == user.id, PaperTrade.status == "closed")
        .order_by(PaperTrade.closed_at.asc())
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
