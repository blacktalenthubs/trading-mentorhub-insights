"""Intel hub & AI coach endpoints — wraps analytics/intel_hub.py, trade_coach.py, position_advisor.py."""

from __future__ import annotations

import asyncio
import json
from functools import partial
from typing import List

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.database import get_db as get_db_dep
from app.dependencies import get_current_user, require_pro, require_premium, require_ai_access, check_usage_limit, get_user_tier
from app.models.user import User

from fastapi import HTTPException
from sqlalchemy import select
from app.schemas.intel import (
    AnalyzeChartRequest,
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
    from analytics.intel_hub import get_mtf_analysis

    ctx = await _run_sync(get_mtf_analysis, symbol.upper())
    return MTFContextResponse(
        symbol=symbol.upper(),
        daily=ctx.get("daily", {}),
        weekly=ctx.get("weekly", {}),
        intraday={},
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


@router.post("/coach", dependencies=[Depends(require_ai_access)])
async def coach_stream(
    body: CoachRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_dep),
):
    """SSE stream — AI trade coach chat. Usage-limited per tier."""
    remaining = await check_usage_limit(user, "ai_queries", db)
    from analytics.trade_coach import ask_coach, assemble_context, format_system_prompt

    import re as _re

    # Resolve the actual symbol — extract from user message first, fallback to body.symbols
    _msg_symbol = None
    if body.messages:
        _last_content = body.messages[-1].get("content", "")
        _sym_match = _re.search(r"\[Looking at ([^\]]+)\]", _last_content)
        if _sym_match:
            _msg_symbol = _sym_match.group(1).upper()
    hub_symbol = _msg_symbol or (body.symbols[0] if body.symbols else None)

    # Detect requested timeframe from user message
    _tf = body.timeframe
    if not _tf and body.messages:
        _last_msg = body.messages[-1].get("content", "").lower()
        _tf_keywords = [
            ("1m ", "1m"), ("1-min", "1m"), ("5m ", "5m"), ("5-min", "5m"),
            ("15m", "15m"), ("15-min", "15m"), ("30m", "30m"), ("30-min", "30m"),
            ("hour", "1H"), ("1h", "1H"), ("4h", "4H"), ("4-hour", "4H"),
            ("daily", "D"), ("week", "W"),
        ]
        for keyword, tf_val in _tf_keywords:
            if keyword in _last_msg:
                _tf = tf_val
                break
    if not _tf:
        _tf = "1H"

    # Assemble trading context
    context = await _run_sync(assemble_context, hub_symbol)

    # Always fetch chart bars for the hub symbol — server-side is the reliable path
    # Frontend bars are a bonus optimization, but server-side fetch guarantees data
    _has_matching_bars = False
    if body.ohlcv_bars and len(body.ohlcv_bars) >= 5:
        # Only use frontend bars if they match the requested symbol
        # (frontend might send bars for a different symbol than what's in the message)
        context["user_chart_bars"] = [
            {
                "time": b.timestamp,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": int(b.volume),
            }
            for b in body.ohlcv_bars
        ]
        context["user_chart_timeframe"] = body.timeframe or _tf
        _has_matching_bars = True

    if hub_symbol and not _has_matching_bars:
        # Fetch bars server-side — guaranteed to match the requested symbol + timeframe
        _tf_map = {
            "1m": ("1d", "1m"), "5m": ("5d", "5m"), "15m": ("5d", "15m"),
            "30m": ("5d", "30m"), "1H": ("5d", "60m"), "4H": ("1mo", "60m"),
            "D": ("1y", "1d"), "W": ("1y", "1wk"), "M": ("5y", "1mo"),
        }
        _period, _interval = _tf_map.get(_tf, ("5d", "60m"))
        try:
            from analytics.market_data import fetch_ohlc
            _df = await _run_sync(fetch_ohlc, hub_symbol, _period, _interval)
            if _df is not None and not _df.empty:
                _bars = []
                for ts, row in _df.tail(30).iterrows():
                    _bars.append({
                        "time": str(ts),
                        "open": round(float(row["Open"]), 2),
                        "high": round(float(row["High"]), 2),
                        "low": round(float(row["Low"]), 2),
                        "close": round(float(row["Close"]), 2),
                        "volume": int(row["Volume"]),
                    })
                context["user_chart_bars"] = _bars
                context["user_chart_timeframe"] = _tf
        except Exception:
            pass

    # Compute VWAP from chart bars so Coach doesn't hallucinate it
    user_bars = context.get("user_chart_bars")
    if user_bars and len(user_bars) >= 2:
        try:
            import pandas as pd
            _df = pd.DataFrame(user_bars)
            # Rename to match compute_vwap expectations
            _col_map = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
            _df.rename(columns={k: v for k, v in _col_map.items() if k in _df.columns}, inplace=True)
            if "High" in _df.columns and "Low" in _df.columns and "Close" in _df.columns and "Volume" in _df.columns:
                _typical = (_df["High"] + _df["Low"] + _df["Close"]) / 3
                _cum_vol = _df["Volume"].cumsum()
                _cum_tp_vol = (_typical * _df["Volume"]).cumsum()
                _vwap_series = _cum_tp_vol / _cum_vol
                _current_vwap = round(float(_vwap_series.iloc[-1]), 2)
                context["computed_vwap"] = _current_vwap
        except Exception:
            pass

    # Fetch LIVE price server-side (not stale last-bar close) so Coach uses real current price
    if hub_symbol:
        def _fetch_live_price(sym: str) -> float | None:
            try:
                import yfinance as yf
                t = yf.Ticker(sym)
                fi = t.fast_info
                return round(float(fi.last_price), 2)
            except Exception:
                return None

        _live = await _run_sync(_fetch_live_price, hub_symbol)
        if _live:
            context["live_price"] = {"symbol": hub_symbol, "price": _live}
        elif user_bars and len(user_bars) >= 1:
            # Fallback to last bar close only if live fetch fails
            _last_bar = user_bars[-1]
            _last_close = _last_bar.get("close") or _last_bar.get("Close")
            if _last_close:
                context["live_price"] = {"symbol": hub_symbol, "price": round(float(_last_close), 2)}

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
        # Include remaining usage in done event
        yield {"event": "done", "data": json.dumps({"remaining": remaining})}

    return EventSourceResponse(event_generator())


# --- Chart Analysis endpoint ---


@router.post("/analyze-chart", dependencies=[Depends(require_ai_access)])
async def analyze_chart(
    body: AnalyzeChartRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_dep),
):
    """SSE stream — AI chart analysis with structured trade plan. Usage-limited."""
    remaining = await check_usage_limit(user, "ai_queries", db)

    from analytics.chart_analyzer import (
        assemble_analysis_context,
        build_analysis_prompt,
        parse_trade_plan,
        get_cached_analysis,
        set_cached_analysis,
        stream_chart_analysis,
    )
    from analytics.trade_coach import ask_coach

    symbol = body.symbol.upper()
    tf = body.timeframe

    # Check cache
    cached = get_cached_analysis(user.id, symbol, tf)
    if cached:
        async def cached_generator():
            yield {"event": "plan", "data": json.dumps(cached.get("plan", {}))}
            yield {"event": "reasoning", "data": json.dumps({"text": cached.get("reasoning", "")})}
            yield {"event": "higher_tf", "data": json.dumps({"text": cached.get("higher_tf_summary", "")})}
            yield {"event": "done", "data": json.dumps({"analysis_id": cached.get("id"), "remaining": remaining})}
        return EventSourceResponse(cached_generator())

    # Prepare bars from request if provided
    bars = None
    if body.ohlcv_bars:
        bars = [
            {
                "timestamp": b.timestamp,
                "Open": b.open, "High": b.high,
                "Low": b.low, "Close": b.close,
                "Volume": int(b.volume),
            }
            for b in body.ohlcv_bars
        ]

    async def event_generator():
        full_text = []
        analysis_id = None
        try:
            # Assemble context and build prompt (blocking I/O — run in executor)
            context = await _run_sync(assemble_analysis_context, symbol, tf, bars)
            prompt = build_analysis_prompt(context)

            # Stream from Claude
            messages = [{"role": "user", "content": f"Analyze the {tf} chart for {symbol} and provide a structured trade plan."}]

            def _stream():
                chunks = []
                for chunk in ask_coach(system_prompt=prompt, messages=messages, max_tokens=512):
                    chunks.append(chunk)
                return chunks

            chunks = await _run_sync(_stream)
            for chunk in chunks:
                full_text.append(chunk)
                yield {"event": "chunk", "data": json.dumps({"text": chunk})}

            # Parse structured plan from full response
            response_text = "".join(full_text)
            plan = parse_trade_plan(response_text)

            # Save to DB
            analysis_id = None
            try:
                from app.models.chart_analysis import ChartAnalysis
                record = ChartAnalysis(
                    user_id=user.id,
                    symbol=symbol,
                    timeframe=tf,
                    direction=plan.get("direction"),
                    entry_price=plan.get("entry"),
                    stop_price=plan.get("stop"),
                    target_1=plan.get("target_1"),
                    target_2=plan.get("target_2"),
                    rr_ratio=plan.get("rr_ratio"),
                    confidence=plan.get("confidence"),
                    confluence_score=plan.get("confluence_score"),
                    reasoning=plan.get("reasoning"),
                    higher_tf_summary=plan.get("higher_tf_summary"),
                    historical_ref=plan.get("historical_ref") if isinstance(plan.get("historical_ref"), str) else None,
                )
                db.add(record)
                await db.flush()
                analysis_id = record.id
            except Exception:
                logging.getLogger("intel").exception("Failed to save chart analysis")

            # Cache the result
            cache_data = {**plan, "id": analysis_id, "reasoning": plan.get("reasoning", ""), "higher_tf_summary": plan.get("higher_tf_summary", "")}
            set_cached_analysis(user.id, symbol, tf, cache_data)

            # Emit structured events
            yield {"event": "plan", "data": json.dumps({
                "setup": plan.get("setup"),
                "direction": plan.get("direction"),
                "entry": plan.get("entry"),
                "stop": plan.get("stop"),
                "target_1": plan.get("target_1"),
                "target_2": plan.get("target_2"),
                "rr_ratio": plan.get("rr_ratio"),
                "confidence": plan.get("confidence"),
                "confluence_score": plan.get("confluence_score"),
                "timeframe_fit": plan.get("timeframe_fit"),
                "key_levels": plan.get("key_levels", []),
                "historical_ref": plan.get("historical_ref") if isinstance(plan.get("historical_ref"), str) else None,
            })}
            yield {"event": "reasoning", "data": json.dumps({"text": plan.get("reasoning", "")})}
            yield {"event": "higher_tf", "data": json.dumps({"text": plan.get("higher_tf_summary", "")})}

        except Exception as exc:
            yield {"event": "error", "data": json.dumps({"error": str(exc)})}

        yield {"event": "done", "data": json.dumps({"analysis_id": analysis_id if 'analysis_id' in dir() else None, "remaining": remaining})}

    return EventSourceResponse(event_generator())


# --- Analysis History & Outcome endpoints ---


@router.get("/analysis-history")
async def analysis_history(
    symbol: str = Query(default=None),
    days: int = Query(default=30, le=90),
    limit: int = Query(default=20, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_dep),
):
    """Get user's saved chart analyses."""
    from datetime import datetime, timedelta
    from sqlalchemy import select
    from app.models.chart_analysis import ChartAnalysis

    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = (
        select(ChartAnalysis)
        .where(ChartAnalysis.user_id == user.id)
        .where(ChartAnalysis.created_at >= cutoff)
    )
    if symbol:
        stmt = stmt.where(ChartAnalysis.symbol == symbol.upper())
    stmt = stmt.order_by(ChartAnalysis.created_at.desc()).limit(limit)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return {
        "analyses": [
            {
                "id": r.id,
                "symbol": r.symbol,
                "timeframe": r.timeframe,
                "direction": r.direction,
                "entry": r.entry_price,
                "stop": r.stop_price,
                "target_1": r.target_1,
                "target_2": r.target_2,
                "rr_ratio": r.rr_ratio,
                "confidence": r.confidence,
                "confluence_score": r.confluence_score,
                "reasoning": r.reasoning,
                "actual_outcome": r.actual_outcome,
                "outcome_pnl": r.outcome_pnl,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@router.put("/analysis/{analysis_id}/outcome")
async def record_analysis_outcome(
    analysis_id: int,
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_dep),
):
    """Record actual outcome of a saved analysis."""
    from sqlalchemy import select
    from app.models.chart_analysis import ChartAnalysis

    result = await db.execute(
        select(ChartAnalysis).where(
            ChartAnalysis.id == analysis_id,
            ChartAnalysis.user_id == user.id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Analysis not found")

    outcome = body.get("outcome", "").upper()
    if outcome not in ("WIN", "LOSS", "SCRATCH"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="outcome must be WIN, LOSS, or SCRATCH")

    record.actual_outcome = outcome
    record.outcome_pnl = body.get("pnl")
    await db.flush()

    return {"id": record.id, "actual_outcome": record.actual_outcome, "outcome_pnl": record.outcome_pnl}


class PreTradeCheckRequest(BaseModel):
    symbol: str
    direction: str  # BUY or SHORT
    entry: float
    stop: float
    target: float


@router.post("/pre-trade-check")
async def pre_trade_check(
    body: PreTradeCheckRequest,
    user: User = Depends(require_pro),
):
    """Run pre-trade checklist — structure, volume, regime, R:R, timing, daily budget."""
    from analytics.pretrade_check import run_pretrade_check

    result = await _run_sync(
        run_pretrade_check,
        body.symbol.upper(), body.direction.upper(),
        body.entry, body.stop, body.target,
    )
    return result


@router.post("/position-check", dependencies=[Depends(require_ai_access)])
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


@router.post("/classify-pattern/{symbol}", dependencies=[Depends(require_ai_access)])
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


@router.get("/premarket", dependencies=[Depends(require_ai_access)])
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


@router.get("/eod-recap", dependencies=[Depends(require_ai_access)])
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


# --- Trade Replay Analyst ---


@router.get("/trade-replay/{alert_id}", dependencies=[Depends(require_ai_access)])
async def trade_replay_analysis(
    alert_id: int,
    user: User = Depends(require_pro),
    db: AsyncSession = Depends(get_db_dep),
):
    """Generate AI narration for a completed trade replay.

    Combines the alert data, chart bars, and outcome into an educational
    analysis that teaches the user what happened and why.
    """
    from app.models.alert import Alert
    from app.models.paper_trade import RealTrade

    # Fetch alert
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.user_id == user.id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Check for associated trade outcome
    trade_result = await db.execute(
        select(RealTrade).where(RealTrade.alert_id == alert_id, RealTrade.user_id == user.id)
    )
    trade = trade_result.scalar_one_or_none()

    # Fetch chart data for the alert
    chart_bars = []
    try:
        from analytics.market_data import fetch_ohlc
        df = await _run_sync(fetch_ohlc, alert.symbol, "5d", "5m")
        if df is not None and not df.empty:
            for ts, row in df.tail(60).iterrows():
                chart_bars.append({
                    "time": str(ts),
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row["Volume"]),
                })
    except Exception:
        pass

    # Build AI analysis context
    context = {
        "symbol": alert.symbol,
        "direction": alert.direction,
        "alert_type": alert.alert_type,
        "entry": alert.entry,
        "stop": alert.stop,
        "target_1": alert.target_1,
        "target_2": alert.target_2,
        "price_at_alert": alert.price,
        "confidence": alert.confidence,
        "message": alert.message,
        "created_at": str(alert.created_at),
        "user_action": alert.user_action,
    }
    if trade:
        context["trade"] = {
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "pnl": trade.pnl,
            "status": trade.status,
            "shares": trade.shares,
        }

    # Generate AI narration
    analysis = None
    try:
        analysis = await _run_sync(_generate_replay_analysis, context, chart_bars)
    except Exception:
        pass

    return {
        "alert": context,
        "trade": context.get("trade"),
        "bars": chart_bars[-30:] if chart_bars else [],
        "analysis": analysis or "Replay analysis not available.",
    }


def _generate_replay_analysis(context: dict, bars: list) -> str | None:
    """Generate AI narration for a trade replay."""
    from alert_config import ANTHROPIC_API_KEY
    import anthropic

    api_key = ANTHROPIC_API_KEY
    if not api_key:
        return None

    symbol = context["symbol"]
    direction = context["direction"]
    alert_type = context.get("alert_type", "").replace("_", " ").title()
    entry = context.get("entry", 0)
    stop = context.get("stop", 0)
    t1 = context.get("target_1", 0)
    trade = context.get("trade", {})
    outcome = "UNKNOWN"
    if trade:
        if trade.get("pnl") and trade["pnl"] > 0:
            outcome = f"WIN (+${trade['pnl']:.2f})"
        elif trade.get("pnl") and trade["pnl"] < 0:
            outcome = f"LOSS (${trade['pnl']:.2f})"
        elif trade.get("status") == "open":
            outcome = "STILL OPEN"

    # Last few bars for price action context
    bar_summary = ""
    if bars:
        recent = bars[-10:]
        bar_summary = "\n".join([
            f"  {b['time']}: O={b['open']} H={b['high']} L={b['low']} C={b['close']}"
            for b in recent
        ])

    prompt = f"""Analyze this trade replay for a learning trader:

TRADE: {direction} {symbol} — {alert_type}
Entry: ${entry:.2f}, Stop: ${stop:.2f}, T1: ${t1:.2f}
Outcome: {outcome}
Alert message: {context.get('message', 'N/A')}

Recent price action:
{bar_summary}

Write a brief trade replay analysis (120 words max). Use this EXACT format:

ENTRY: [1-2 sentences — why this was valid/invalid, reference specific price]
WHAT HAPPENED: [2-3 sentences — key price action, use dollar amounts]
OUTCOME: [1-2 sentences — what the result teaches]
LESSON: [1 sentence — one specific takeaway]

CRITICAL: No markdown, no bold, no asterisks, no headers. Just plain text with the section labels above. Be concise and specific with dollar amounts."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
            timeout=20.0,
        )
        return response.content[0].text.strip()
    except Exception:
        return None


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

    overall = data.get("overall", {})
    return {
        "period_days": days,
        "total_signals": overall.get("total", 0),
        "wins": overall.get("wins", 0),
        "losses": overall.get("losses", 0),
        "win_rate": overall.get("win_rate", 0),
        "by_alert_type": data.get("by_alert_type", {}),
    }


@router.get("/game-plan")
async def game_plan(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_dep),
):
    """Get today's top 3 setups ranked by confluence + score."""
    from app.models.watchlist import WatchlistItem

    result = await db.execute(
        select(WatchlistItem.symbol).where(WatchlistItem.user_id == user.id)
    )
    symbols = [row[0] for row in result.all()]
    if not symbols:
        return []

    loop = asyncio.get_event_loop()
    from analytics.game_plan import generate_game_plan
    setups = await loop.run_in_executor(None, partial(generate_game_plan, symbols))
    return setups


@router.get("/trade-journal")
async def trade_journal(
    request: Request,
    date: str = Query(None, description="YYYY-MM-DD, defaults to today"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_dep),
):
    """Get trade journal entries for a date."""
    from sqlalchemy import text as sql_text
    from datetime import date as _date

    target_date = date or _date.today().isoformat()
    result = await db.execute(
        sql_text("""
            SELECT id, symbol, alert_type, direction, entry_price, exit_price,
                   stop_price, target_1, target_2, outcome, pnl_r, replay_text,
                   session_date, created_at
            FROM trade_journal
            WHERE user_id = :uid AND session_date = :d
            ORDER BY created_at DESC
        """),
        {"uid": user.id, "d": target_date},
    )
    rows = result.fetchall()

    return [
        {
            "id": r[0], "symbol": r[1], "alert_type": r[2], "direction": r[3],
            "entry_price": r[4], "exit_price": r[5], "stop_price": r[6],
            "target_1": r[7], "target_2": r[8], "outcome": r[9],
            "pnl_r": r[10], "replay_text": r[11],
            "session_date": r[12], "created_at": str(r[13]) if r[13] else "",
        }
        for r in rows
    ]
