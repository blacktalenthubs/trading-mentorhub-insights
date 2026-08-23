"""Daily Target — self-reporting page endpoints.

Log the day's trades, sum realized P/L against a target, and close the day once the number is
hit. A discipline tool against overtrading/give-back: "make my number, then stop." Gated to a
single account for now (everyone else gets 403). All state is user-scoped so it generalizes later.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.daily_target import DailySession, DailyTrade
from app.models.user import User

router = APIRouter()

# Gate: only this account may use the Daily Target page for now (founder self-reporting).
_ALLOWED_EMAIL = "vbolofinde@gmail.com"
_ET = ZoneInfo("America/New_York")
_DEFAULT_TARGET = 4000.0


def _require_owner(user: User) -> None:
    if (user.email or "").lower() != _ALLOWED_EMAIL:
        raise HTTPException(status_code=403, detail="Daily Target is not enabled for this account")


def _today() -> str:
    return datetime.now(_ET).date().isoformat()


def _user_default_target(user: User) -> float:
    return user.daily_target if user.daily_target is not None else _DEFAULT_TARGET


class TradeIn(BaseModel):
    symbol: str
    instrument: str = "stock"          # stock | option
    trade_type: str = "day"            # day | swing
    setup: Optional[str] = None        # entry mechanism (PDH break, PDL held, SMA reclaim, level, ...)
    direction: Optional[str] = None    # long | short
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    quantity: Optional[float] = None       # shares (stock) or contracts (option)
    position_size: Optional[float] = None  # $ deployed
    pnl: float = 0.0                   # realized P/L in $ (0 while a position is still open)
    is_open: bool = False              # still holding — no exit / not realized yet
    exit_reason: Optional[str] = None  # target | stop | into resistance | time | other
    note: Optional[str] = None
    chart_image: Optional[str] = None  # data: URL of a chart screenshot


class TargetIn(BaseModel):
    target: float


def _trade_dict(t: DailyTrade) -> dict:
    return {
        "id": t.id,
        "symbol": t.symbol,
        "instrument": t.instrument,
        "trade_type": t.trade_type,
        "setup": t.setup,
        "direction": t.direction,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "quantity": t.quantity,
        "position_size": t.position_size,
        "pnl": t.pnl,
        "exit_reason": t.exit_reason,
        "note": t.note,
        "has_image": t.chart_image is not None,
        "is_open": bool(t.is_open),
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


async def _get_session_row(db: AsyncSession, user_id: int, date: str) -> Optional[DailySession]:
    res = await db.execute(
        select(DailySession).where(
            DailySession.user_id == user_id, DailySession.session_date == date
        )
    )
    return res.scalar_one_or_none()


@router.get("/summary")
async def summary(
    date: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(user)
    d = date or _today()
    res = await db.execute(
        select(DailyTrade)
        .where(DailyTrade.user_id == user.id, DailyTrade.session_date == d)
        .order_by(DailyTrade.created_at)
    )
    trades = list(res.scalars().all())
    realized = [t for t in trades if not t.is_open]  # open positions are NOT realized — excluded from the number
    total = round(sum(t.pnl for t in realized), 2)
    sess = await _get_session_row(db, user.id, d)
    target = sess.target if sess else _user_default_target(user)
    closed = bool(sess.closed) if sess else False
    wins = sum(1 for t in realized if t.pnl > 0)
    losses = sum(1 for t in realized if t.pnl < 0)
    return {
        "date": d,
        "target": target,
        "total_pnl": total,
        "hit": total >= target,
        "closed": closed,
        "trade_count": len(realized),
        "wins": wins,
        "losses": losses,
        "open_count": len(trades) - len(realized),
        "trades": [_trade_dict(t) for t in trades],
    }


@router.get("/history")
async def history(
    limit: int = 60,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(user)
    res = await db.execute(
        select(DailyTrade)
        .where(DailyTrade.user_id == user.id)
        .order_by(DailyTrade.session_date.desc(), DailyTrade.created_at)
    )
    trades = list(res.scalars().all())
    sres = await db.execute(select(DailySession).where(DailySession.user_id == user.id))
    sessions = {s.session_date: s for s in sres.scalars().all()}
    by_date: dict[str, list] = {}
    for t in trades:
        by_date.setdefault(t.session_date, []).append(t)
    for d in sessions:
        by_date.setdefault(d, [])
    days = []
    for d in sorted(by_date.keys(), reverse=True)[:limit]:
        ts = by_date[d]
        realized = [t for t in ts if not t.is_open]
        total = round(sum(t.pnl for t in realized), 2)
        sess = sessions.get(d)
        target = sess.target if sess else _user_default_target(user)
        days.append({
            "date": d,
            "target": target,
            "total_pnl": total,
            "hit": total >= target,
            "closed": bool(sess.closed) if sess else False,
            "trade_count": len(realized),
            "wins": sum(1 for t in realized if t.pnl > 0),
            "losses": sum(1 for t in realized if t.pnl < 0),
            "open_count": len(ts) - len(realized),
            "trades": [_trade_dict(t) for t in ts],
        })
    return {"days": days}


@router.put("/target")
async def set_target(
    body: TargetIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(user)
    tgt = max(0.0, float(body.target))
    user.daily_target = tgt   # standing default for future days
    d = _today()
    sess = await _get_session_row(db, user.id, d)
    if sess is None:
        db.add(DailySession(user_id=user.id, session_date=d, target=tgt, closed=False))
    else:
        sess.target = tgt
    await db.flush()
    return {"target": tgt}


@router.post("/trade")
async def add_trade(
    body: TradeIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(user)
    sym = (body.symbol or "").strip().upper()
    if not sym:
        raise HTTPException(status_code=422, detail="Symbol required")
    t = DailyTrade(
        user_id=user.id,
        session_date=_today(),
        symbol=sym,
        instrument=(body.instrument or "stock").strip().lower(),
        trade_type=(body.trade_type or "day").strip().lower(),
        setup=body.setup,
        direction=body.direction,
        entry_price=body.entry_price,
        exit_price=body.exit_price,
        quantity=body.quantity,
        position_size=body.position_size,
        pnl=float(body.pnl or 0.0),
        exit_reason=body.exit_reason,
        note=body.note,
        chart_image=body.chart_image,
        is_open=bool(body.is_open),
    )
    db.add(t)
    await db.flush()
    return _trade_dict(t)


@router.get("/trade/{trade_id}/image")
async def trade_image(
    trade_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(user)
    res = await db.execute(
        select(DailyTrade).where(DailyTrade.id == trade_id, DailyTrade.user_id == user.id)
    )
    t = res.scalar_one_or_none()
    if t is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    return {"chart_image": t.chart_image}


@router.put("/trade/{trade_id}")
async def update_trade(
    trade_id: int,
    body: TradeIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(user)
    res = await db.execute(
        select(DailyTrade).where(DailyTrade.id == trade_id, DailyTrade.user_id == user.id)
    )
    t = res.scalar_one_or_none()
    if t is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    sym = (body.symbol or "").strip().upper()
    if sym:
        t.symbol = sym
    t.instrument = (body.instrument or "stock").strip().lower()
    t.trade_type = (body.trade_type or "day").strip().lower()
    t.setup = body.setup
    t.direction = body.direction
    t.entry_price = body.entry_price
    t.exit_price = body.exit_price
    t.quantity = body.quantity
    t.position_size = body.position_size
    t.pnl = float(body.pnl or 0.0)
    t.exit_reason = body.exit_reason
    t.note = body.note
    t.chart_image = body.chart_image
    t.is_open = bool(body.is_open)
    await db.flush()
    return _trade_dict(t)


@router.delete("/trade/{trade_id}")
async def delete_trade(
    trade_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(user)
    res = await db.execute(
        select(DailyTrade).where(DailyTrade.id == trade_id, DailyTrade.user_id == user.id)
    )
    t = res.scalar_one_or_none()
    if t is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    await db.delete(t)
    await db.flush()
    return {"deleted": trade_id}


async def _set_closed(db: AsyncSession, user: User, date: Optional[str], closed: bool) -> dict:
    d = date or _today()
    sess = await _get_session_row(db, user.id, d)
    if sess is None:
        db.add(
            DailySession(
                user_id=user.id, session_date=d, target=_user_default_target(user), closed=closed
            )
        )
    else:
        sess.closed = closed
    await db.flush()
    return {"date": d, "closed": closed}


@router.post("/close")
async def close_day(
    date: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(user)
    return await _set_closed(db, user, date, True)


@router.post("/reopen")
async def reopen_day(
    date: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(user)
    return await _set_closed(db, user, date, False)
