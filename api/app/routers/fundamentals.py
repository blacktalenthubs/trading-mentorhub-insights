"""Fundamentals endpoints — Watchlist > Details tab.

GET  /watchlist  → cached fundamentals + analyst ratings + AI views for the
                   user's watchlist symbols (null fields for un-fetched symbols).
POST /refresh    → on-demand fetch + AI-generate + upsert for one symbol, or
                   the whole watchlist ({"all": true}).

The refresh path is synchronous + slow (Finnhub throttle + yfinance + Anthropic),
so it runs in a thread-pool executor against the sync session factory wired into
app.state.sync_session_factory (same pattern as the routers/intel.py data calls).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user, require_ai_access
from app.models.fundamentals import SymbolFundamentals
from app.models.user import User
from app.models.watchlist import WatchlistItem

logger = logging.getLogger(__name__)

router = APIRouter()


def _sync_session_factory():
    """Build a standalone sync engine + session factory from DATABASE_URL —
    independent of app.state, so the on-demand refresh works regardless of
    lifespan startup order (app.state.sync_session_factory is unset if the
    scheduler startup block raised). Same pattern as the social-buzz refresh."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    url = get_settings().DATABASE_URL
    if url.startswith("sqlite"):
        url = url.replace("+aiosqlite", "")
    else:
        for suffix in ("+asyncpg", "+psycopg2", "+psycopg"):
            url = url.replace(suffix, "")
    engine = create_engine(url, pool_pre_ping=True)
    return engine, sessionmaker(bind=engine)


class FundamentalsItem(BaseModel):
    symbol: str
    company_name: Optional[str] = None
    description: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[float] = None
    trailing_eps: Optional[float] = None
    forward_eps: Optional[float] = None
    eps_growth_pct: Optional[float] = None
    pe_ratio: Optional[float] = None
    rec_strong_buy: Optional[int] = None
    rec_buy: Optional[int] = None
    rec_hold: Optional[int] = None
    rec_sell: Optional[int] = None
    rec_strong_sell: Optional[int] = None
    consensus: Optional[str] = None
    rec_period: Optional[str] = None
    short_term_view: Optional[str] = None
    long_term_view: Optional[str] = None
    # Structured AI brief (dict of sections + model) + extra decision metrics.
    ai_brief: Optional[dict] = None
    ai_generated_at: Optional[str] = None
    metrics: Optional[dict] = None
    fetched_at: Optional[str] = None  # ISO timestamp; None = never fetched


class FundamentalsResponse(BaseModel):
    items: List[FundamentalsItem]
    last_refreshed_at: Optional[str]


class RefreshRequest(BaseModel):
    symbol: Optional[str] = None
    all: bool = False


def _loads(raw: Optional[str]) -> Optional[Any]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _to_item(sym: str, row: Optional[SymbolFundamentals]) -> FundamentalsItem:
    if row is None:
        return FundamentalsItem(symbol=sym)
    return FundamentalsItem(
        symbol=sym,
        company_name=row.company_name,
        description=row.description,
        sector=row.sector,
        industry=row.industry,
        market_cap=row.market_cap,
        trailing_eps=row.trailing_eps,
        forward_eps=row.forward_eps,
        eps_growth_pct=row.eps_growth_pct,
        pe_ratio=row.pe_ratio,
        rec_strong_buy=row.rec_strong_buy,
        rec_buy=row.rec_buy,
        rec_hold=row.rec_hold,
        rec_sell=row.rec_sell,
        rec_strong_sell=row.rec_strong_sell,
        consensus=row.consensus,
        rec_period=row.rec_period,
        short_term_view=row.short_term_view,
        long_term_view=row.long_term_view,
        ai_brief=_loads(getattr(row, "ai_brief", None)),
        ai_generated_at=row.ai_generated_at.isoformat() if getattr(row, "ai_generated_at", None) else None,
        metrics=_loads(getattr(row, "metrics_json", None)),
        fetched_at=row.fetched_at.isoformat() if row.fetched_at else None,
    )


@router.get("/watchlist", response_model=FundamentalsResponse)
async def watchlist_fundamentals(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cached fundamentals for the user's watchlist. Un-fetched symbols appear
    with null fields + fetched_at=None so the UI can prompt a Refresh.
    """
    sym_rows = (await db.execute(
        select(WatchlistItem.symbol)
        .where(WatchlistItem.user_id == user.id)
        .distinct()
    )).all()
    symbols = sorted({r[0].upper() for r in sym_rows if r[0]})
    if not symbols:
        return FundamentalsResponse(items=[], last_refreshed_at=None)

    rows = (await db.execute(
        select(SymbolFundamentals).where(SymbolFundamentals.symbol.in_(symbols))
    )).scalars().all()
    by_sym = {r.symbol: r for r in rows}

    most_recent: Optional[str] = None
    items: list[FundamentalsItem] = []
    for sym in symbols:
        row = by_sym.get(sym)
        if row and row.fetched_at:
            iso = row.fetched_at.isoformat()
            if most_recent is None or iso > most_recent:
                most_recent = iso
        items.append(_to_item(sym, row))

    return FundamentalsResponse(items=items, last_refreshed_at=most_recent)


class SectorGroup(BaseModel):
    sector: str
    strength: float          # median momentum across the sector's names (higher = hotter) — for ranking
    count: int
    items: List[FundamentalsItem]


class UniverseResponse(BaseModel):
    sectors: List[SectorGroup]
    last_refreshed_at: Optional[str]


def _momentum(item: FundamentalsItem) -> Optional[float]:
    """Strength proxy from cached metrics: blend of distance above the 200-DMA and position in the
    52-week range. Higher = stronger leader. None if not computable."""
    m = item.metrics or {}
    lp = m.get("last_price"); ma200 = m.get("ma200")
    hi = m.get("week52_high"); lo = m.get("week52_low")
    parts = []
    if lp and ma200:
        parts.append(lp / ma200 - 1.0)
    if hi and lo and hi > lo and lp is not None:
        parts.append((lp - lo) / (hi - lo) - 0.5)
    return sum(parts) / len(parts) if parts else None


def _median(xs) -> float:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return 0.0
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


@router.get("/universe", response_model=UniverseResponse)
async def universe_fundamentals(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The whole cached leaders universe grouped by SECTOR, strongest sector first — for ANY signed-in
    user (not gated to the caller's watchlist). Sort within a sector is client-side. Names not yet
    fetched aren't here; the per-symbol endpoint fetches on-demand when a user opens one."""
    rows = (await db.execute(select(SymbolFundamentals))).scalars().all()
    groups: dict[str, List[FundamentalsItem]] = {}
    most_recent: Optional[str] = None
    for row in rows:
        item = _to_item(row.symbol, row)
        sec = (item.sector or "Other").strip() or "Other"
        groups.setdefault(sec, []).append(item)
        if row.fetched_at:
            iso = row.fetched_at.isoformat()
            if most_recent is None or iso > most_recent:
                most_recent = iso
    sectors = [
        SectorGroup(sector=sec, strength=round(_median([_momentum(it) for it in items]), 4),
                    count=len(items), items=items)
        for sec, items in groups.items()
    ]
    sectors.sort(key=lambda g: g.strength, reverse=True)
    return UniverseResponse(sectors=sectors, last_refreshed_at=most_recent)


# ───────────────────────────────────────────────────────────────────────────
# Fundamentals ENGINE (EDGAR-sourced deep fundamentals) — distinct from the
# Finnhub/AI Details snapshot above. Reads the cached fund_* tables written by
# the nightly analytics/fundamentals_engine_refresh job, so responses are fast
# (no live API calls). Declared BEFORE /{symbol} so these literal paths win.
# ───────────────────────────────────────────────────────────────────────────
class EngineFlag(BaseModel):
    code: str
    severity: str
    label: str
    detail: Optional[str] = None
    metric: Optional[str] = None


class EngineRankItem(BaseModel):
    symbol: str
    quality_score: Optional[float] = None
    risk_score: Optional[float] = None
    profitable: Optional[bool] = None
    quality_coverage: Optional[float] = None
    risk_coverage: Optional[float] = None
    as_of_date: Optional[str] = None
    latest_period_end: Optional[str] = None
    top_flags: List[EngineFlag] = []


class EngineRankResponse(BaseModel):
    items: List[EngineRankItem]
    # Symbols on the watchlist with no EDGAR fundamentals yet (ETFs/ADRs/IPOs).
    uncovered: List[str] = []


class EnginePeriod(BaseModel):
    period_end: str
    form: str
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None
    filed_date: Optional[str] = None
    source_url: Optional[str] = None
    line_items: dict


class EngineMetric(BaseModel):
    name: str
    value: Optional[float] = None
    unit: Optional[str] = None
    source_url: Optional[str] = None


class EngineReport(BaseModel):
    symbol: str
    quality_score: Optional[float] = None
    risk_score: Optional[float] = None
    profitable: Optional[bool] = None
    as_of_date: Optional[str] = None
    flags: List[EngineFlag] = []
    metrics: List[EngineMetric] = []
    periods: List[EnginePeriod] = []


_SEVERITY_RANK = {"critical": 0, "warn": 1, "info": 2}
_LINE_ITEM_COLS = (
    "revenue", "cost_of_revenue", "gross_profit", "operating_income", "net_income",
    "interest_expense", "operating_cash_flow", "capex", "inventory", "receivables",
    "total_current_assets", "total_current_liabilities", "total_assets",
    "total_liabilities", "cash", "short_term_debt", "long_term_debt",
    "stockholders_equity", "shares_diluted",
)


def _iso(d) -> Optional[str]:
    return d.isoformat() if d else None


@router.get("/engine/config")
async def engine_config(_user: User = Depends(get_current_user)):
    """The active tunable thresholds & weights (provenance + admin tuning surface).

    Mirrors the Pine/webhook tunable-gate pattern: every number the engine uses
    is here and env-overridable, so the methodology can be tuned without a code
    change. Read-only for now; an admin editor can POST these in a later pass.
    """
    from fundamentals_config import get_config
    return get_config().as_dict()


@router.get("/engine/watchlist", response_model=EngineRankResponse)
async def engine_watchlist(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The caller's watchlist ranked by the engine — quality & risk score plus
    the top red/value flags per name. Answers 'is this profitable / real value
    or hype?' at a glance. Served entirely from cache (fast)."""
    from app.models.fundamentals_engine import FundCompany, FundFlag, FundScore

    sym_rows = (await db.execute(
        select(WatchlistItem.symbol).where(WatchlistItem.user_id == user.id).distinct()
    )).all()
    symbols = sorted({r[0].upper() for r in sym_rows if r[0]})
    if not symbols:
        return EngineRankResponse(items=[], uncovered=[])

    # Latest score row per symbol (max as_of_date).
    score_rows = (await db.execute(
        select(FundScore).where(FundScore.symbol.in_(symbols))
    )).scalars().all()
    latest: dict[str, FundScore] = {}
    for r in score_rows:
        cur = latest.get(r.symbol)
        if cur is None or r.as_of_date > cur.as_of_date:
            latest[r.symbol] = r

    # Flags for each symbol's latest as_of_date.
    flag_rows = (await db.execute(
        select(FundFlag).where(FundFlag.symbol.in_(symbols))
    )).scalars().all()
    flags_by_sym: dict[str, list] = {}
    for f in flag_rows:
        sc = latest.get(f.symbol)
        if sc and f.as_of_date == sc.as_of_date:
            flags_by_sym.setdefault(f.symbol, []).append(f)

    # Symbols known to lack EDGAR data.
    comp_rows = (await db.execute(
        select(FundCompany).where(FundCompany.symbol.in_(symbols))
    )).scalars().all()
    no_data = {c.symbol for c in comp_rows if c.no_edgar_data}

    items: list[EngineRankItem] = []
    uncovered: list[str] = []
    for sym in symbols:
        sc = latest.get(sym)
        if sc is None:
            if sym in no_data:
                uncovered.append(sym)
            continue
        raw_flags = sorted(
            flags_by_sym.get(sym, []),
            key=lambda f: _SEVERITY_RANK.get(f.severity, 3),
        )
        items.append(EngineRankItem(
            symbol=sym,
            quality_score=sc.quality_score,
            risk_score=sc.risk_score,
            profitable=sc.profitable,
            quality_coverage=sc.quality_coverage,
            risk_coverage=sc.risk_coverage,
            as_of_date=_iso(sc.as_of_date),
            latest_period_end=_iso(sc.latest_period_end),
            top_flags=[EngineFlag(code=f.code, severity=f.severity, label=f.label,
                                  detail=f.detail, metric=f.metric)
                       for f in raw_flags[:5]],
        ))

    # Highest risk first, then lowest quality — the names that need a look.
    items.sort(key=lambda i: (-(i.risk_score or 0.0), i.quality_score or 0.0))
    return EngineRankResponse(items=items, uncovered=uncovered)


@router.get("/engine/report/{symbol}", response_model=EngineReport)
async def engine_report(
    symbol: str,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Per-stock fundamental report: latest score, flags, computed metrics, and
    the normalised financial time series (each period carrying its source
    filing URL for audit). Served from cache."""
    from app.models.fundamentals_engine import (
        FundFinancials, FundFlag, FundMetric, FundScore,
    )

    sym = symbol.upper().strip()
    score = (await db.execute(
        select(FundScore).where(FundScore.symbol == sym).order_by(FundScore.as_of_date.desc()).limit(1)
    )).scalars().first()

    report = EngineReport(symbol=sym)
    if score is None:
        return report
    report.quality_score = score.quality_score
    report.risk_score = score.risk_score
    report.profitable = score.profitable
    report.as_of_date = _iso(score.as_of_date)

    flag_rows = (await db.execute(
        select(FundFlag).where(FundFlag.symbol == sym, FundFlag.as_of_date == score.as_of_date)
    )).scalars().all()
    report.flags = sorted(
        [EngineFlag(code=f.code, severity=f.severity, label=f.label, detail=f.detail, metric=f.metric)
         for f in flag_rows],
        key=lambda f: _SEVERITY_RANK.get(f.severity, 3),
    )

    # Latest-period metrics (the newest period_end present).
    metric_rows = (await db.execute(
        select(FundMetric).where(FundMetric.symbol == sym)
    )).scalars().all()
    if metric_rows:
        newest = max(m.period_end for m in metric_rows)
        report.metrics = [
            EngineMetric(name=m.name, value=m.value, unit=m.unit, source_url=m.source_url)
            for m in metric_rows if m.period_end == newest
        ]

    fin_rows = (await db.execute(
        select(FundFinancials).where(FundFinancials.symbol == sym).order_by(FundFinancials.period_end)
    )).scalars().all()
    report.periods = [
        EnginePeriod(
            period_end=_iso(p.period_end), form=p.form, fiscal_year=p.fiscal_year,
            fiscal_period=p.fiscal_period, filed_date=_iso(p.filed_date), source_url=p.source_url,
            line_items={c: getattr(p, c) for c in _LINE_ITEM_COLS},
        )
        for p in fin_rows
    ]
    return report


@router.get("/{symbol}", response_model=FundamentalsItem)
async def symbol_fundamentals(
    symbol: str,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Full fundamentals + AI brief for ANY symbol (not just the caller's watchlist) —
    feeds the 'Top Ideas' dossier in Research. Null fields + fetched_at=None when never
    fetched, so the UI prompts a Refresh / Generate. (Declared after /watchlist so that
    exact path still wins.)"""
    sym = symbol.upper().strip()
    row = (await db.execute(
        select(SymbolFundamentals).where(SymbolFundamentals.symbol == sym).limit(1)
    )).scalars().first()
    return _to_item(sym, row)


def _refresh_in_thread(symbol: Optional[str], do_all: bool, with_ai: bool) -> dict:
    engine, factory = _sync_session_factory()
    try:
        if do_all:
            from analytics.fundamentals_refresh import refresh_all
            return refresh_all(factory, with_ai=with_ai)
        from analytics.fundamentals_refresh import refresh_one
        return refresh_one(factory, symbol, with_ai=with_ai)
    finally:
        engine.dispose()


@router.post("/refresh")
async def refresh_fundamentals(
    body: RefreshRequest,
    user: User = Depends(get_current_user),
):
    """Refresh the NUMBERS only (Finnhub fundamentals + analyst ratings + metrics)
    for a symbol or the whole watchlist. No LLM cost — the AI brief is generated
    separately by admins via /ai-refresh (and auto on newly-added symbols).

    Uses its OWN sync session factory (not app.state.sync_session_factory,
    which is unset when the scheduler startup block raised — that previously
    500'd this endpoint and left the Details tab perpetually un-fetched).
    """
    do_all = body.all or not body.symbol
    try:
        return await asyncio.to_thread(_refresh_in_thread, body.symbol, do_all, False)
    except Exception as e:  # surface the real cause instead of an opaque 500
        logger.exception("Fundamentals refresh endpoint failed")
        raise HTTPException(status_code=500, detail=f"refresh failed: {e}")


@router.post("/ai-refresh")
async def ai_refresh_fundamentals(
    body: RefreshRequest,
    user: User = Depends(require_ai_access),
):
    """Admin-only: (re)generate the structured AI investment brief (Sonnet) for a
    symbol or the whole watchlist, and refresh its numbers. The brief is stored
    per-symbol and read by every user, so this is run sparingly (admin / on-add)."""
    do_all = body.all or not body.symbol
    try:
        return await asyncio.to_thread(_refresh_in_thread, body.symbol, do_all, True)
    except Exception as e:
        logger.exception("Fundamentals AI-refresh endpoint failed")
        raise HTTPException(status_code=500, detail=f"ai-refresh failed: {e}")
