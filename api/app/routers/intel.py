"""Intel hub & AI coach endpoints — wraps analytics/intel_hub.py, trade_coach.py, position_advisor.py."""

from __future__ import annotations

import asyncio
import json
from functools import partial
from typing import List

from fastapi import APIRouter, Depends, Query, Request
from sse_starlette.sse import EventSourceResponse

from app.dependencies import get_current_user, require_pro
from app.models.user import User
from app.schemas.intel import (
    CoachRequest,
    DecisionQualityResponse,
    FundamentalsResponse,
    JournalEntry,
    MTFContextResponse,
    ScannerContextResponse,
    SetupAnalysisResponse,
    WinRateResponse,
)

router = APIRouter()


def _run_sync(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(None, partial(fn, *args, **kwargs))


# --- Data endpoints ---


@router.get("/win-rates", response_model=WinRateResponse)
async def alert_win_rates(
    days: int = Query(default=90, le=365),
    user: User = Depends(get_current_user),
):
    from analytics.intel_hub import get_alert_win_rates

    data = await _run_sync(get_alert_win_rates, days, user.id)
    return WinRateResponse(**data) if isinstance(data, dict) else WinRateResponse()


@router.get("/acked-win-rates", response_model=WinRateResponse)
async def acked_win_rates(
    days: int = Query(default=90, le=365),
    user: User = Depends(get_current_user),
):
    from analytics.intel_hub import get_acked_trade_win_rates

    data = await _run_sync(get_acked_trade_win_rates, user.id, days)
    return WinRateResponse(**data) if isinstance(data, dict) else WinRateResponse()


@router.get("/fundamentals/{symbol}", response_model=FundamentalsResponse)
async def fundamentals(symbol: str, user: User = Depends(get_current_user)):
    from analytics.intel_hub import get_fundamentals

    data = await _run_sync(get_fundamentals, symbol.upper())
    return FundamentalsResponse(symbol=symbol.upper(), data=data or {})


@router.get("/daily/{symbol}", response_model=SetupAnalysisResponse)
async def daily_analysis(symbol: str, user: User = Depends(get_current_user)):
    from analytics.intel_hub import analyze_daily_setup
    from analytics.intraday_data import get_daily_bars

    bars = await _run_sync(get_daily_bars, symbol.upper(), period="6mo")
    analysis = await _run_sync(analyze_daily_setup, symbol.upper(), bars)
    return SetupAnalysisResponse(
        symbol=symbol.upper(),
        timeframe="daily",
        analysis=analysis or {},
    )


@router.get("/weekly/{symbol}", response_model=SetupAnalysisResponse)
async def weekly_analysis(symbol: str, user: User = Depends(get_current_user)):
    from analytics.intel_hub import analyze_weekly_setup, get_weekly_bars

    bars = await _run_sync(get_weekly_bars, symbol.upper())
    analysis = await _run_sync(analyze_weekly_setup, symbol.upper(), bars)
    return SetupAnalysisResponse(
        symbol=symbol.upper(),
        timeframe="weekly",
        analysis=analysis or {},
    )


@router.get("/mtf/{symbol}", response_model=MTFContextResponse)
async def mtf_context(symbol: str, user: User = Depends(get_current_user)):
    from analytics.intel_hub import build_mtf_context

    ctx = await _run_sync(build_mtf_context, symbol.upper())
    return MTFContextResponse(
        symbol=symbol.upper(),
        daily=ctx.get("daily", {}),
        weekly=ctx.get("weekly", {}),
        intraday=ctx.get("intraday", {}),
    )


@router.get("/journal", response_model=List[JournalEntry])
async def trading_journal(
    days: int = Query(default=30, le=90),
    user: User = Depends(get_current_user),
):
    from analytics.intel_hub import get_trading_journal

    entries = await _run_sync(get_trading_journal, user.id, days)
    return [
        JournalEntry(date=e.get("date", ""), entries=e.get("entries", []))
        for e in (entries or [])
    ]


@router.get("/decision-quality", response_model=DecisionQualityResponse)
async def decision_quality(
    days: int = Query(default=30, le=90),
    user: User = Depends(get_current_user),
):
    from analytics.intel_hub import get_decision_quality

    data = await _run_sync(get_decision_quality, user.id, days)
    return DecisionQualityResponse(metrics=data or {})


@router.get("/scanner-context", response_model=ScannerContextResponse)
async def scanner_context(
    symbols: str = Query(default=""),
    user: User = Depends(get_current_user),
):
    from analytics.intel_hub import assemble_scanner_context

    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    ctx = await _run_sync(assemble_scanner_context, sym_list, user.id)
    return ScannerContextResponse(context=ctx or {})


# --- AI Streaming endpoints (SSE) ---


@router.post("/coach")
async def coach_stream(
    body: CoachRequest,
    user: User = Depends(require_pro),
):
    """SSE stream — AI trade coach chat."""
    from analytics.trade_coach import ask_coach, assemble_context, format_system_prompt

    # Assemble trading context and build system prompt
    hub_symbol = body.symbols[0] if body.symbols else None
    context = await _run_sync(assemble_context, hub_symbol)
    system_prompt = format_system_prompt(context)

    async def event_generator():
        try:
            gen = await _run_sync(ask_coach, system_prompt, body.messages)
            if hasattr(gen, "__iter__"):
                for chunk in gen:
                    yield {"event": "chunk", "data": json.dumps({"text": chunk})}
            else:
                yield {"event": "chunk", "data": json.dumps({"text": str(gen)})}
        except Exception as exc:
            yield {"event": "error", "data": json.dumps({"error": str(exc)})}
        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())


@router.post("/position-check")
async def position_check_stream(
    user: User = Depends(require_pro),
):
    """SSE stream — AI position re-evaluation."""
    from analytics.position_advisor import check_positions_stream

    async def event_generator():
        try:
            gen = await _run_sync(check_positions_stream, user.id)
            if hasattr(gen, "__iter__"):
                for chunk in gen:
                    yield {"event": "chunk", "data": json.dumps({"text": chunk})}
            else:
                yield {"event": "chunk", "data": json.dumps({"text": str(gen)})}
        except Exception as exc:
            yield {"event": "error", "data": json.dumps({"error": str(exc)})}
        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())


@router.post("/classify-pattern/{symbol}")
async def classify_pattern_stream(
    symbol: str,
    user: User = Depends(require_pro),
):
    """SSE stream — AI pattern classification."""
    from analytics.intel_hub import classify_daily_pattern

    async def event_generator():
        try:
            gen = await _run_sync(classify_daily_pattern, symbol.upper())
            if hasattr(gen, "__iter__"):
                for chunk in gen:
                    yield {"event": "chunk", "data": json.dumps({"text": chunk})}
            else:
                yield {"event": "chunk", "data": json.dumps({"text": str(gen)})}
        except Exception as exc:
            yield {"event": "error", "data": json.dumps({"error": str(exc)})}
        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())


# --- Intelligence Briefings ---


@router.get("/premarket")
async def premarket_brief(
    user: User = Depends(require_pro),
):
    """Generate pre-market brief for user's watchlist."""
    from db import get_watchlist

    symbols = await _run_sync(get_watchlist, user.id)
    if not symbols:
        return {"brief": "No symbols on watchlist. Add symbols to get a pre-market brief."}

    try:
        from analytics.premarket_brief import generate_premarket_brief
        brief = await _run_sync(generate_premarket_brief, symbols, user.id)
        return {"brief": brief or "Pre-market analysis not available yet."}
    except Exception as exc:
        return {"brief": f"Brief generation failed: {exc}"}


@router.get("/eod-recap")
async def eod_recap(
    user: User = Depends(require_pro),
):
    """Generate end-of-day recap for user's alerts today."""
    try:
        from analytics.post_market_review import generate_post_market_review
        recap = await _run_sync(generate_post_market_review, user.id)
        return {"recap": recap or "No alerts to recap today."}
    except Exception as exc:
        return {"recap": f"Recap generation failed: {exc}"}


# --- Public Track Record (no auth required) ---


@router.get("/public-track-record")
async def public_track_record(days: int = Query(default=30, le=90)):
    """Public 30-day rolling alert performance — no authentication required.

    Returns overall and per-category win rates for marketing/landing page.
    """
    from analytics.intel_hub import get_alert_win_rates

    data = await _run_sync(get_alert_win_rates, days)
    if not isinstance(data, dict):
        return {
            "period_days": days,
            "total_alerts": 0,
            "win_rate": 0,
            "categories": [],
        }

    return {
        "period_days": days,
        "total_alerts": data.get("total", 0),
        "wins": data.get("wins", 0),
        "losses": data.get("losses", 0),
        "win_rate": data.get("win_rate", 0),
        "avg_rr": data.get("avg_rr", 0),
        "by_type": data.get("by_type", {}),
        "by_direction": data.get("by_direction", {}),
    }
