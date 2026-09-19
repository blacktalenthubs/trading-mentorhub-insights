"""Daily Target — self-reporting page endpoints.

Log the day's trades, sum realized P/L against a target, and close the day once the number is
hit. A discipline tool against overtrading/give-back: "make my number, then stop." Gated to a
single account for now (everyone else gets 403). All state is user-scoped so it generalizes later.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
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
    target: Optional[str] = None       # structural target (50 SMA, PWH, ...)
    stop: Optional[str] = None         # structural stop (200 SMA, PDL, ...)
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
        "target": t.target,
        "stop": t.stop,
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
        target=body.target,
        stop=body.stop,
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
    t.target = body.target
    t.stop = body.stop
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


# ─────────────────────────────────────────────────────────────────────────────
# P&L Calendar — realized P&L by close date across the FULL account history.
#
# Reads matched_trades (broker/monthly FIFO round-trips) ∪ trades_1099 (tax),
# NOT daily_trades — so the calendar spans everything, not just Daily-Target rows.
# Options in matched_trades are per-unit priced (contracts, no ×100); we scale
# asset_type='option' rows by 100 here so option days aren't ~100× under-counted.
# trades_1099.gain_loss is already in dollars. Read-only; owner-gated like the rest.
# ─────────────────────────────────────────────────────────────────────────────

_OPTION_MULTIPLIER = 100

# Per-trade (date, pnl) rows, options scaled to dollars, unioned across both
# realized-P&L sources. Callers append their own WHERE date-range on the alias `d`.
_REALIZED_ROWS = f"""
    SELECT sell_date AS d,
           (CASE WHEN asset_type = 'option'
                 THEN realized_pnl * {_OPTION_MULTIPLIER}
                 ELSE realized_pnl END) AS pnl
    FROM matched_trades
    WHERE user_id = :uid {{mt_range}}
    UNION ALL
    SELECT date_sold AS d, gain_loss AS pnl
    FROM trades_1099
    WHERE user_id = :uid {{t99_range}}
"""


def _valid_month(month: Optional[str]) -> str:
    """Return YYYY-MM, defaulting to the current ET month; 422 on garbage."""
    if not month:
        return datetime.now(_ET).strftime("%Y-%m")
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise HTTPException(status_code=422, detail="month must be YYYY-MM")
    return month


def _month_bounds(month: str) -> tuple[str, str]:
    """[start, end) ISO date strings for a YYYY-MM month."""
    start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
    end = (start.replace(day=28) + timedelta(days=7)).replace(day=1)
    return start.isoformat(), end.isoformat()


@router.get("/calendar")
async def calendar(
    month: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Per-day realized P&L for one month: [{date, pnl, trades, wins, losses, hit}]."""
    _require_owner(user)
    m = _valid_month(month)
    start, end = _month_bounds(m)
    rows_sql = _REALIZED_ROWS.format(
        mt_range="AND sell_date >= :start AND sell_date < :end",
        t99_range="AND date_sold >= :start AND date_sold < :end",
    )
    sql = text(f"""
        SELECT d,
               SUM(pnl) AS pnl,
               COUNT(*) AS trades,
               SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) AS losses
        FROM ({rows_sql}) x
        GROUP BY d
        ORDER BY d
    """)
    res = await db.execute(sql, {"uid": user.id, "start": start, "end": end})

    # Target/hit markers come from the Daily-Target session rows when present.
    sres = await db.execute(
        select(DailySession).where(
            DailySession.user_id == user.id,
            DailySession.session_date >= start,
            DailySession.session_date < end,
        )
    )
    sessions = {s.session_date: s for s in sres.scalars().all()}
    default_target = _user_default_target(user)

    days = []
    for r in res.fetchall():
        d = r.d if isinstance(r.d, str) else str(r.d)[:10]
        pnl = round(float(r.pnl or 0.0), 2)
        sess = sessions.get(d)
        target = sess.target if sess else default_target
        days.append({
            "date": d,
            "pnl": pnl,
            "trades": int(r.trades or 0),
            "wins": int(r.wins or 0),
            "losses": int(r.losses or 0),
            "hit": target is not None and pnl >= target,
        })
    return {"month": m, "days": days}


@router.get("/day")
async def day_detail(
    date: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Every realized trade that closed on a given day (the calendar drill-down)."""
    _require_owner(user)
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD")

    mt = await db.execute(
        text(f"""
            SELECT symbol, underlying_symbol, quantity, buy_price, sell_price,
                   buy_date, holding_days, asset_type, holding_period_type,
                   (CASE WHEN asset_type = 'option'
                         THEN realized_pnl * {_OPTION_MULTIPLIER}
                         ELSE realized_pnl END) AS pnl
            FROM matched_trades
            WHERE user_id = :uid AND sell_date = :d
            ORDER BY symbol
        """),
        {"uid": user.id, "d": date},
    )
    trades = []
    for r in mt.fetchall():
        is_opt = (r.asset_type or "").lower() == "option"
        trades.append({
            "source": "matched",
            "symbol": r.underlying_symbol or r.symbol,
            "contract": r.symbol if is_opt else None,
            "asset_type": r.asset_type or "stock",
            "trade_type": r.holding_period_type,   # day_trade | swing | position
            "direction": "long",                   # FIFO buy→sell round-trips are long
            "quantity": r.quantity,
            "entry_price": r.buy_price,
            "exit_price": r.sell_price,
            "opened": r.buy_date,
            "holding_days": r.holding_days,
            "pnl": round(float(r.pnl or 0.0), 2),
        })

    t99 = await db.execute(
        text("""
            SELECT symbol, proceeds, cost_basis, gain_loss, date_acquired, term
            FROM trades_1099
            WHERE user_id = :uid AND date_sold = :d
            ORDER BY symbol
        """),
        {"uid": user.id, "d": date},
    )
    for r in t99.fetchall():
        trades.append({
            "source": "1099",
            "symbol": r.symbol,
            "contract": None,
            "asset_type": "stock",
            "trade_type": (r.term or "").lower() or None,
            "direction": "long",
            "quantity": None,
            "entry_price": r.cost_basis,
            "exit_price": r.proceeds,
            "opened": r.date_acquired,
            "holding_days": None,
            "pnl": round(float(r.gain_loss or 0.0), 2),
        })

    total = round(sum(t["pnl"] for t in trades), 2)
    return {
        "date": date,
        "total": total,
        "trade_count": len(trades),
        "wins": sum(1 for t in trades if t["pnl"] > 0),
        "losses": sum(1 for t in trades if t["pnl"] < 0),
        "trades": trades,
    }


def _range_start(range_key: str) -> Optional[str]:
    """Lower-bound ISO date for a stats range, or None for 'all'."""
    today = datetime.now(_ET).date()
    if range_key == "month":
        return today.replace(day=1).isoformat()
    if range_key == "quarter":
        q_first_month = ((today.month - 1) // 3) * 3 + 1
        return date(today.year, q_first_month, 1).isoformat()
    if range_key == "year":
        return date(today.year, 1, 1).isoformat()
    return None  # all


@router.get("/stats")
async def stats(
    range: str = "all",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Summary metrics over a range: realized, win rate, avg win/loss, profit factor, best/worst, streak."""
    _require_owner(user)
    range_key = range if range in {"month", "quarter", "year", "all"} else "all"
    start = _range_start(range_key)

    if start is None:
        rows_sql = _REALIZED_ROWS.format(mt_range="", t99_range="")
        params = {"uid": user.id}
    else:
        rows_sql = _REALIZED_ROWS.format(
            mt_range="AND sell_date >= :start",
            t99_range="AND date_sold >= :start",
        )
        params = {"uid": user.id, "start": start}

    res = await db.execute(text(f"SELECT d, pnl FROM ({rows_sql}) x"), params)
    rows = res.fetchall()

    pnls = [float(r.pnl or 0.0) for r in rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_win = round(sum(wins), 2)
    gross_loss = round(sum(losses), 2)  # negative
    n = len(pnls)

    # Per-day totals for best/worst/streak.
    by_day: dict[str, float] = {}
    for r in rows:
        d = r.d if isinstance(r.d, str) else str(r.d)[:10]
        by_day[d] = by_day.get(d, 0.0) + float(r.pnl or 0.0)
    day_items = sorted(by_day.items())  # ascending by date
    best_day = max(by_day.items(), key=lambda kv: kv[1], default=(None, 0.0))
    worst_day = min(by_day.items(), key=lambda kv: kv[1], default=(None, 0.0))

    # Current streak: consecutive most-recent days of the same result sign.
    streak_type, streak_count = "flat", 0
    for _, tot in reversed(day_items):
        sign = "win" if tot > 0 else "loss" if tot < 0 else "flat"
        if sign == "flat":
            break
        if streak_count == 0:
            streak_type, streak_count = sign, 1
        elif sign == streak_type:
            streak_count += 1
        else:
            break

    return {
        "range": range_key,
        "realized": round(sum(pnls), 2),
        "trade_count": n,
        "trading_days": len(by_day),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / n, 4) if n else 0.0,
        "avg_win": round(gross_win / len(wins), 2) if wins else 0.0,
        "avg_loss": round(gross_loss / len(losses), 2) if losses else 0.0,
        "gross_profit": gross_win,
        "gross_loss": gross_loss,
        "profit_factor": round(gross_win / abs(gross_loss), 2) if gross_loss else None,
        "best_day": {"date": best_day[0], "pnl": round(best_day[1], 2)} if best_day[0] else None,
        "worst_day": {"date": worst_day[0], "pnl": round(worst_day[1], 2)} if worst_day[0] else None,
        "streak": {"type": streak_type, "count": streak_count},
    }
