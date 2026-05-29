"""Swing trade endpoints — spec 56.

Reads the deterministic swing scanner's output from the alerts table. An open
swing is a routed swing entry (swing_bounce_* / swing_rsi_30) with no later
swing_exit; history pairs each swing_exit with the entry it closed.
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import List

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_pro
from app.models.alert import Alert
from app.models.user import User
from app.schemas.swing import (
    SpyRegimeResponse,
    SwingScanResponse,
    SwingTradeResponse,
)

router = APIRouter()

_SETUP_LABELS = {
    "swing_bounce_ema21": "EMA 21 bounce",
    "swing_bounce_ema50": "EMA 50 bounce",
    "swing_bounce_sma50": "SMA 50 bounce",
    "swing_bounce_ema100": "EMA 100 bounce",
    "swing_bounce_sma100": "SMA 100 bounce",
    "swing_bounce_ema200": "EMA 200 bounce",
    "swing_bounce_sma200": "SMA 200 bounce",
    "swing_rsi_30": "RSI-30 recovery",
}
_ENTRY_TYPES = list(_SETUP_LABELS.keys())


def _to_resp(a: Alert, status: str) -> SwingTradeResponse:
    return SwingTradeResponse(
        id=a.id,
        symbol=a.symbol,
        alert_type=a.alert_type,
        setup=_SETUP_LABELS.get(a.alert_type, a.alert_type),
        entry=a.entry,
        stop=a.stop,
        target_1=a.target_1,
        target_2=a.target_2,
        conviction=a.confidence,
        opened_date=a.session_date,
        status=status,
    )


@router.get("/regime", response_model=SpyRegimeResponse)
async def swing_regime(user: User = Depends(get_current_user)):
    """SPY regime — bounce (SPY at/above its 21 EMA) vs RSI (SPY below it)."""
    import yfinance as yf
    from analytics.swing_quality import REGIME_BOUNCE, spy_regime

    loop = asyncio.get_running_loop()
    hist = await loop.run_in_executor(
        None, lambda: yf.Ticker("SPY").history(period="6mo", interval="1d")
    )
    if hist is None or hist.empty:
        return SpyRegimeResponse(regime=REGIME_BOUNCE, bounce_mode=True)

    regime = spy_regime(hist)
    close = hist["Close"].astype(float)
    return SpyRegimeResponse(
        regime=regime,
        bounce_mode=(regime == REGIME_BOUNCE),
        spy_close=round(float(close.iloc[-1]), 2),
        spy_ema21=round(float(close.ewm(span=21, adjust=False).mean().iloc[-1]), 2),
    )


@router.get("/trades/active", response_model=List[SwingTradeResponse])
async def active_swing_trades(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Open swings — the latest routed entry per symbol with no later exit."""
    entries = (await db.execute(
        select(Alert)
        .where(
            Alert.user_id == user.id,
            Alert.alert_type.in_(_ENTRY_TYPES),
            Alert.suppressed_reason.is_(None),
        )
        .order_by(desc(Alert.id))
    )).scalars().all()

    exit_rows = (await db.execute(
        select(Alert.symbol, Alert.id)
        .where(Alert.user_id == user.id, Alert.alert_type == "swing_exit")
        .order_by(desc(Alert.id))
    )).all()
    latest_exit: dict[str, int] = {}
    for sym, aid in exit_rows:
        latest_exit.setdefault(sym, aid)   # desc order — first seen is newest

    out: List[SwingTradeResponse] = []
    seen: set[str] = set()
    for a in entries:                      # newest entry first
        if a.symbol in seen:
            continue                       # one open swing per symbol
        seen.add(a.symbol)
        if latest_exit.get(a.symbol, 0) > a.id:
            continue                       # an exit closed this entry
        out.append(_to_resp(a, status="active"))
    return out


@router.get("/trades/history", response_model=List[SwingTradeResponse])
async def swing_trades_history(
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Closed swings — each swing_exit paired with the entry it closed."""
    exits = (await db.execute(
        select(Alert)
        .where(Alert.user_id == user.id, Alert.alert_type == "swing_exit")
        .order_by(desc(Alert.id))
        .limit(limit)
    )).scalars().all()

    out: List[SwingTradeResponse] = []
    for ex in exits:
        entry = (await db.execute(
            select(Alert)
            .where(
                Alert.user_id == user.id,
                Alert.symbol == ex.symbol,
                Alert.alert_type.in_(_ENTRY_TYPES),
                Alert.id < ex.id,
            )
            .order_by(desc(Alert.id))
            .limit(1)
        )).scalars().first()
        if entry is None:
            continue
        r = _to_resp(entry, status="closed")
        r.exit_price = ex.price
        r.closed_date = ex.session_date
        if entry.entry:
            r.pnl_pct = round((ex.price - entry.entry) / entry.entry * 100, 2)
        out.append(r)
    return out


@router.post("/scan", response_model=SwingScanResponse)
async def trigger_swing_scan(request: Request, user: User = Depends(require_pro)):
    """Manually run one swing scan cycle (the scheduler also runs it)."""
    from analytics.swing_scanner import swing_scan_cycle

    factory = getattr(request.app.state, "sync_session_factory", None)
    if factory is None:
        return SwingScanResponse(alerts_fired=0)
    loop = asyncio.get_running_loop()
    # Manual button press = explicit ad-hoc request. Bypass the in-cycle
    # market-hours gate so the scan actually runs outside RTH (the most
    # common time a user taps the button — pre-market / after-hours review).
    # Pass the authenticated user's email so the watchlist filter targets
    # THEIR symbols rather than the SCAN_USER_EMAIL env default (which
    # exists for scheduler-cost-control and may be set to a different user).
    user_email = (user.email or "").strip().lower()
    count = await loop.run_in_executor(
        None, partial(swing_scan_cycle, factory, True, user_email or None)
    )
    return SwingScanResponse(alerts_fired=count)
