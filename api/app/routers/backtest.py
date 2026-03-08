"""Backtest endpoint (Pro only)."""

from __future__ import annotations

import asyncio
import sys
from functools import partial
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, Request

from app.dependencies import require_pro
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.paper_trade import BacktestRequest, BacktestResult

_root = str(Path(__file__).resolve().parents[3])
if _root not in sys.path:
    sys.path.insert(0, _root)

from analytics.market_data import fetch_ohlc  # noqa: E402
from analytics.signal_engine import analyze_symbol  # noqa: E402

router = APIRouter()


def _run_backtest(symbols: List[str], start_date: str, end_date: str) -> List[dict]:
    """Run backtest on historical data for given symbols."""
    results = []
    for symbol in symbols:
        hist = fetch_ohlc(symbol.upper(), period="1y")
        if hist.empty or len(hist) < 10:
            continue

        # Filter to date range
        hist = hist.loc[start_date:end_date]
        if hist.empty or len(hist) < 5:
            continue

        wins = 0
        losses = 0
        total_pnl = 0.0
        rr_sum = 0.0
        signals = 0

        # Walk through each day and evaluate the signal
        for i in range(2, len(hist)):
            window = hist.iloc[:i + 1]
            result = analyze_symbol(window, symbol)
            if result is None or result.support_status == "BROKEN":
                continue

            signals += 1
            rr_sum += result.rr_ratio

            # Simple backtest: check if next day hit target or stop
            if i + 1 < len(hist):
                next_day = hist.iloc[i + 1]
                if result.target_1 > 0 and next_day["High"] >= result.target_1:
                    wins += 1
                    total_pnl += result.risk_per_share * result.rr_ratio
                elif result.stop > 0 and next_day["Low"] <= result.stop:
                    losses += 1
                    total_pnl -= result.risk_per_share

        if signals == 0:
            continue

        results.append({
            "symbol": symbol,
            "total_signals": signals,
            "win_count": wins,
            "loss_count": losses,
            "win_rate": round(wins / (wins + losses) * 100, 1) if (wins + losses) else 0,
            "total_pnl": round(total_pnl, 2),
            "avg_rr": round(rr_sum / signals, 2) if signals else 0,
        })

    return results


@router.post("/run", response_model=List[BacktestResult])
@limiter.limit("3/minute")
async def run_backtest(
    request: Request,
    body: BacktestRequest,
    user: User = Depends(require_pro),
):
    """Run backtest on historical data (Pro only)."""
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(
        None, partial(_run_backtest, body.symbols, body.start_date, body.end_date)
    )
    return [BacktestResult(**r) for r in results]
