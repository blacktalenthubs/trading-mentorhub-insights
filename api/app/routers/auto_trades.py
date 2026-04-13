"""Public AI Auto-Pilot API — Spec 35 Phase 3.

All endpoints are public (no auth). This is the marketing asset —
anyone can audit the AI's live paper trading record.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.database import get_db
from app.models.auto_trade import AIAutoTrade

router = APIRouter()


# ── Response schemas ─────────────────────────────────────────────────


class AutoTradeSummary(BaseModel):
    id: int
    symbol: str
    direction: str
    setup_type: Optional[str] = None
    conviction: Optional[str] = None
    entry_price: float
    stop_price: Optional[float] = None
    target_1_price: Optional[float] = None
    target_2_price: Optional[float] = None
    shares: float
    status: str
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl_dollars: Optional[float] = None
    pnl_percent: Optional[float] = None
    r_multiple: Optional[float] = None
    opened_at: datetime
    closed_at: Optional[datetime] = None
    session_date: str
    market: Optional[str] = None
    alert_id: Optional[int] = None


class Stats(BaseModel):
    total_trades: int
    open_trades: int
    closed_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl_dollars: float
    total_pnl_percent: float   # sum of per-trade P&L % — comparable since notional is fixed
    avg_win_pct: float
    avg_loss_pct: float
    best_trade_pct: Optional[float] = None
    worst_trade_pct: Optional[float] = None
    total_notional_invested: float


class PatternRow(BaseModel):
    setup_type: Optional[str]
    trades: int
    wins: int
    win_rate: float
    avg_pnl_pct: float


class SymbolRow(BaseModel):
    symbol: str
    trades: int
    wins: int
    win_rate: float
    avg_pnl_pct: float


class EquityPoint(BaseModel):
    date: str
    cumulative_pnl_pct: float
    cumulative_pnl_dollars: float
    trades_closed: int


# ── Helpers ──────────────────────────────────────────────────────────


def _is_win(t: AIAutoTrade) -> bool:
    return (t.pnl_dollars or 0) > 0


def _to_summary(t: AIAutoTrade) -> AutoTradeSummary:
    return AutoTradeSummary(
        id=t.id,
        symbol=t.symbol,
        direction=t.direction,
        setup_type=t.setup_type,
        conviction=t.conviction,
        entry_price=t.entry_price,
        stop_price=t.stop_price,
        target_1_price=t.target_1_price,
        target_2_price=t.target_2_price,
        shares=t.shares,
        status=t.status,
        exit_price=t.exit_price,
        exit_reason=t.exit_reason,
        pnl_dollars=t.pnl_dollars,
        pnl_percent=t.pnl_percent,
        r_multiple=t.r_multiple,
        opened_at=t.opened_at,
        closed_at=t.closed_at,
        session_date=t.session_date,
        market=t.market,
        alert_id=t.alert_id,
    )


# ── Endpoints (all public) ───────────────────────────────────────────


@router.get("/stats", response_model=Stats)
async def stats(
    days: int = Query(default=30, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate stats for the last N days (default 30)."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = await db.execute(
        select(AIAutoTrade).where(AIAutoTrade.session_date >= cutoff)
    )
    trades = list(result.scalars().all())

    closed = [t for t in trades if t.status != "open"]
    opens = [t for t in trades if t.status == "open"]
    wins = [t for t in closed if _is_win(t)]
    losses = [t for t in closed if not _is_win(t)]

    win_pcts = [t.pnl_percent or 0 for t in wins]
    loss_pcts = [t.pnl_percent or 0 for t in losses]
    closed_pcts = [t.pnl_percent or 0 for t in closed]

    return Stats(
        total_trades=len(trades),
        open_trades=len(opens),
        closed_trades=len(closed),
        wins=len(wins),
        losses=len(losses),
        win_rate=round((len(wins) / len(closed) * 100) if closed else 0.0, 2),
        total_pnl_dollars=round(sum(t.pnl_dollars or 0 for t in closed), 2),
        total_pnl_percent=round(sum(closed_pcts), 4),
        avg_win_pct=round(sum(win_pcts) / len(win_pcts), 4) if win_pcts else 0.0,
        avg_loss_pct=round(sum(loss_pcts) / len(loss_pcts), 4) if loss_pcts else 0.0,
        best_trade_pct=max(closed_pcts) if closed_pcts else None,
        worst_trade_pct=min(closed_pcts) if closed_pcts else None,
        total_notional_invested=round(sum(t.notional_at_entry or 0 for t in trades), 2),
    )


@router.get("/recent", response_model=list[AutoTradeSummary])
async def recent_closed(
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Most recent closed trades — used for the public trade table."""
    result = await db.execute(
        select(AIAutoTrade)
        .where(AIAutoTrade.status != "open")
        .order_by(AIAutoTrade.closed_at.desc())
        .limit(limit)
    )
    return [_to_summary(t) for t in result.scalars().all()]


@router.get("/open", response_model=list[AutoTradeSummary])
async def open_positions(db: AsyncSession = Depends(get_db)):
    """Currently open AI Auto-Pilot positions — live transparency."""
    result = await db.execute(
        select(AIAutoTrade)
        .where(AIAutoTrade.status == "open")
        .order_by(AIAutoTrade.opened_at.desc())
    )
    return [_to_summary(t) for t in result.scalars().all()]


@router.get("/equity-curve", response_model=list[EquityPoint])
async def equity_curve(
    days: int = Query(default=90, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Daily cumulative P&L (percent + dollars) for chart rendering."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = await db.execute(
        select(AIAutoTrade)
        .where(AIAutoTrade.session_date >= cutoff)
        .where(AIAutoTrade.status != "open")
        .order_by(AIAutoTrade.closed_at.asc())
    )
    closed = list(result.scalars().all())

    # Group by session_date (day of close)
    by_day: dict[str, list] = {}
    for t in closed:
        day = (t.closed_at.date().isoformat() if t.closed_at else t.session_date)
        by_day.setdefault(day, []).append(t)

    points: list[EquityPoint] = []
    cum_pct = 0.0
    cum_dollars = 0.0
    for day in sorted(by_day.keys()):
        day_trades = by_day[day]
        cum_pct += sum(t.pnl_percent or 0 for t in day_trades)
        cum_dollars += sum(t.pnl_dollars or 0 for t in day_trades)
        points.append(EquityPoint(
            date=day,
            cumulative_pnl_pct=round(cum_pct, 4),
            cumulative_pnl_dollars=round(cum_dollars, 2),
            trades_closed=len(day_trades),
        ))
    return points


@router.get("/by-pattern", response_model=list[PatternRow])
async def by_pattern(
    days: int = Query(default=90, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Win rate + avg P&L grouped by AI setup type."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = await db.execute(
        select(AIAutoTrade)
        .where(AIAutoTrade.session_date >= cutoff)
        .where(AIAutoTrade.status != "open")
    )
    closed = list(result.scalars().all())

    buckets: dict[Optional[str], list] = {}
    for t in closed:
        buckets.setdefault(t.setup_type, []).append(t)

    rows: list[PatternRow] = []
    for setup, trades in buckets.items():
        wins = sum(1 for t in trades if _is_win(t))
        pcts = [t.pnl_percent or 0 for t in trades]
        rows.append(PatternRow(
            setup_type=setup,
            trades=len(trades),
            wins=wins,
            win_rate=round((wins / len(trades) * 100) if trades else 0.0, 2),
            avg_pnl_pct=round(sum(pcts) / len(pcts), 4) if pcts else 0.0,
        ))
    rows.sort(key=lambda r: r.trades, reverse=True)
    return rows


@router.get("/by-symbol", response_model=list[SymbolRow])
async def by_symbol(
    days: int = Query(default=90, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Win rate + avg P&L grouped by symbol."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = await db.execute(
        select(AIAutoTrade)
        .where(AIAutoTrade.session_date >= cutoff)
        .where(AIAutoTrade.status != "open")
    )
    closed = list(result.scalars().all())

    buckets: dict[str, list] = {}
    for t in closed:
        buckets.setdefault(t.symbol, []).append(t)

    rows: list[SymbolRow] = []
    for sym, trades in buckets.items():
        wins = sum(1 for t in trades if _is_win(t))
        pcts = [t.pnl_percent or 0 for t in trades]
        rows.append(SymbolRow(
            symbol=sym,
            trades=len(trades),
            wins=wins,
            win_rate=round((wins / len(trades) * 100) if trades else 0.0, 2),
            avg_pnl_pct=round(sum(pcts) / len(pcts), 4) if pcts else 0.0,
        ))
    rows.sort(key=lambda r: r.trades, reverse=True)
    return rows


@router.get("/{trade_id}", response_model=AutoTradeSummary)
async def get_trade(
    trade_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Single trade detail — used by shareable permalinks."""
    result = await db.execute(
        select(AIAutoTrade).where(AIAutoTrade.id == trade_id)
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Trade not found")
    return _to_summary(t)
