"""Swing trade endpoints — wraps alerting/swing_scanner.py + analytics/swing_rules.py."""

from __future__ import annotations

from functools import partial
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_pro
from app.models.user import User
from app.schemas.swing import (
    SpyRegimeResponse,
    SwingCategoryItem,
    SwingScanResponse,
    SwingTradeResponse,
)

router = APIRouter()


def _run_sync(fn, *args, **kwargs):
    """Run a synchronous function in the default executor."""
    import asyncio
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(None, partial(fn, *args, **kwargs))


@router.get("/regime", response_model=SpyRegimeResponse)
async def spy_regime(user: User = Depends(get_current_user)):
    """Return current SPY regime (close vs EMA20) and RSI."""
    from analytics.swing_rules import check_spy_regime
    import yfinance as yf

    bars = await _run_sync(lambda: yf.download("SPY", period="1mo", progress=False))
    if bars is None or bars.empty:
        return SpyRegimeResponse(regime_bullish=False)

    # yfinance may return MultiIndex columns — flatten if needed
    if hasattr(bars.columns, 'nlevels') and bars.columns.nlevels > 1:
        bars.columns = bars.columns.get_level_values(0)
    last = bars.iloc[-1]
    spy_ctx = {
        "spy_close": float(last["Close"]),
        "spy_ema20": float(bars["Close"].ewm(span=20).mean().iloc[-1]) if len(bars) >= 20 else None,
    }
    bullish = check_spy_regime(spy_ctx)

    # RSI
    rsi_val = None
    if len(bars) >= 14:
        delta = bars["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi_series = 100 - (100 / (1 + rs))
        rsi_val = round(float(rsi_series.iloc[-1]), 1)

    return SpyRegimeResponse(
        regime_bullish=bullish,
        spy_close=round(spy_ctx["spy_close"], 2),
        spy_ema20=round(spy_ctx["spy_ema20"], 2) if spy_ctx["spy_ema20"] else None,
        spy_rsi=rsi_val,
    )


@router.get("/categories", response_model=List[SwingCategoryItem])
async def swing_categories(
    session_date: str = Query(default=""),
    user: User = Depends(get_current_user),
):
    """Return categorized watchlist for swing analysis."""
    from datetime import date as dt_date
    from alerting.swing_scanner import get_swing_categories

    sd = session_date or dt_date.today().isoformat()
    rows = await _run_sync(get_swing_categories, sd)
    return [
        SwingCategoryItem(
            symbol=r.get("symbol", ""),
            category=r.get("category", ""),
            rsi=r.get("rsi"),
            session_date=r.get("session_date", sd),
        )
        for r in rows
    ]


@router.get("/trades/active", response_model=List[SwingTradeResponse])
async def active_swing_trades(user: User = Depends(get_current_user)):
    from alerting.swing_scanner import get_active_swing_trades

    rows = await _run_sync(get_active_swing_trades)
    return [_map_swing_trade(r) for r in rows]


@router.get("/trades/history", response_model=List[SwingTradeResponse])
async def swing_trades_history(
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
):
    from alerting.swing_scanner import get_swing_trades_history

    rows = await _run_sync(get_swing_trades_history, limit)
    return [_map_swing_trade(r) for r in rows]


@router.post("/scan", response_model=SwingScanResponse)
async def trigger_swing_scan(user: User = Depends(require_pro)):
    from alerting.swing_scanner import swing_scan_eod

    count = await _run_sync(swing_scan_eod)
    return SwingScanResponse(alerts_fired=count)


def _map_swing_trade(r: dict) -> SwingTradeResponse:
    return SwingTradeResponse(
        id=r.get("id", 0),
        symbol=r.get("symbol", ""),
        direction=r.get("direction", "BUY"),
        entry_price=r.get("entry_price", 0),
        stop_price=r.get("stop_price"),
        target_price=r.get("target_price"),
        current_price=r.get("current_price"),
        current_rsi=r.get("current_rsi"),
        status=r.get("status", "active"),
        opened_date=r.get("opened_date", ""),
        closed_date=r.get("closed_date"),
        exit_price=r.get("exit_price"),
        pnl=r.get("pnl"),
    )
