"""In-Play Volume Screener endpoints (spec 62).

Reads are fast: they serve the latest cached snapshot and apply optional refine
filters over the ≤N rows in-process. Refresh happens out-of-band (scheduler).
Gated to Pro+ (FR-10).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from analytics import screener as scr
from app.config import get_settings
from app.dependencies import get_current_user, is_admin_user, require_pro
from app.models.user import User
from app.schemas.screener import SettingsOut, SettingsUpdate, SnapshotOut
from app.services import screener_service as svc

router = APIRouter()


def _entry_from_dict(d: dict) -> scr.InPlayEntry:
    return scr.InPlayEntry(
        symbol=d.get("symbol", ""), last_price=d.get("last_price", 0.0),
        pct_change=d.get("pct_change", 0.0), rvol=d.get("rvol", 0.0),
        dollar_vol=d.get("dollar_vol", 0.0), market_cap=d.get("market_cap", 0.0),
        sector=d.get("sector"), direction=d.get("direction", "neutral"),
        setup=d.get("setup"), refine=d.get("refine") or {}, rank=d.get("rank", 0),
    )


@router.post("/in-play/refresh", status_code=202)
async def refresh_in_play_now(background: BackgroundTasks, user: User = Depends(require_pro)):
    """On-demand in-play rescan ('Run scan'). Runs as a FastAPI background task on
    the main loop (works even when the scheduled interval job isn't firing)."""
    background.add_task(svc.refresh_in_play)
    return {"status": "in-play scan started"}


@router.get("/in-play", response_model=SnapshotOut)
async def get_in_play(
    preset: str = Query("any"),
    direction: str = Query("any"),
    has_setup: bool = Query(False),
    user: User = Depends(get_current_user),  # readable on Free (top-N preview)
):
    """Latest in-play snapshot, optionally narrowed by a refine preset (FR-2/FR-9)."""
    snap = await svc.get_latest_snapshot()
    if snap is None:
        return SnapshotOut(captured_at=None, market_open=svc.is_market_open(), stale=False, top_n=get_settings().SCREENER_TOP_N, entries=[])

    entries = [_entry_from_dict(d) for d in (snap.entries or [])]
    if preset != "any" or direction != "any" or has_setup:
        entries = scr.apply_refine_filters(entries, preset=preset, direction=direction, has_setup=has_setup)

    # Per-user view (FR-6): tighten cap / trim to the user's preferred N.
    overrides = await svc.get_user_settings(user.id)
    entries = scr.apply_user_view(
        entries,
        top_n=overrides.get("top_n"),
        market_cap_floor=overrides.get("market_cap_floor"),
    )

    return SnapshotOut(
        captured_at=snap.captured_at,
        market_open=bool(snap.market_open),
        stale=bool(snap.stale),
        top_n=snap.top_n,
        entries=[e.to_dict() for e in entries],
    )


@router.get("/settings", response_model=SettingsOut)
async def get_screener_settings(user: User = Depends(require_pro)):
    """Effective thresholds = global defaults overlaid with this user's overrides (FR-6)."""
    s = get_settings()
    defaults = {
        "market_cap_floor": s.SCREENER_MARKET_CAP_FLOOR,
        "price_floor": s.SCREENER_PRICE_FLOOR,
        "dollar_vol_floor": s.SCREENER_DOLLAR_VOL_FLOOR,
        "top_n": s.SCREENER_TOP_N,
        "refresh_minutes": s.SCREENER_REFRESH_MINUTES,
    }
    eff = scr.effective_settings(defaults, await svc.get_user_settings(user.id))
    return SettingsOut(**eff, universe_rebuilt_at=await svc.universe_rebuilt_at())


@router.put("/settings", response_model=SettingsOut)
async def update_screener_settings(body: SettingsUpdate, user: User = Depends(require_pro)):
    """Update this user's threshold overrides (market_cap_floor, top_n). Bounds via schema."""
    await svc.set_user_settings(user.id, market_cap_floor=body.market_cap_floor, top_n=body.top_n)
    return await get_screener_settings(user)


@router.get("/swing")
async def get_swing(
    cap: str = Query("mega"),
    run_id: Optional[int] = Query(None),
    user: User = Depends(get_current_user),  # readable on Free (top-N preview)
):
    """Swing setups (daily-bar MA hold). cap=mega|small. run_id selects a specific
    saved run (history); omit for the latest. Not market-gated."""
    if run_id is not None:
        snap = await svc.get_snapshot(run_id)
    else:
        kind = "swing_small" if cap == "small" else "swing"
        snap = await svc.get_latest_snapshot(kind)
    if snap is None:
        return {"id": None, "captured_at": None, "stale": False, "entries": []}
    return {"id": snap.id, "captured_at": snap.captured_at, "stale": bool(snap.stale), "entries": snap.entries or []}


@router.get("/swing/history")
async def swing_history(cap: str = Query("mega"), user: User = Depends(get_current_user)):
    """Recent saved swing runs (for the history selector)."""
    kind = "swing_small" if cap == "small" else "swing"
    return {"runs": await svc.list_snapshots(kind)}


@router.post("/swing/refresh", status_code=202)
async def refresh_swing(background: BackgroundTasks, cap: str = Query("mega"), user: User = Depends(require_pro)):
    """On-demand swing rescan (the 'Run scan' button), per cap segment."""
    background.add_task(svc.refresh_swing_small if cap == "small" else svc.refresh_swing)
    return {"status": "swing scan started"}


@router.post("/universe/rebuild", status_code=202)
async def rebuild_universe(background: BackgroundTasks, user: User = Depends(require_pro)):
    """Trigger an on-demand universe rebuild (FR-7). Admin-only (T029)."""
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Admin access required")
    background.add_task(svc.rebuild_universe)
    return {"status": "rebuild started"}


# ── Social Buzz (Apewisdom-fed) ──────────────────────────────────────
# Hourly cron writes the snapshot; this endpoint serves the latest. No
# tier gate v1 — universal feature so Free users can see what's being
# discussed too (and the cross-ref with Grade-A is a Pro-only signal
# that nudges upgrade).

from sqlalchemy import desc, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402
from app.database import get_db  # noqa: E402
from app.dependencies import get_current_user  # noqa: E402
from app.models.social_buzz import SocialBuzzSnapshot  # noqa: E402


def _sync_session_factory():
    """Build a standalone sync session factory from DATABASE_URL — independent of
    app.state, so the manual refresh works regardless of lifespan startup order."""
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


@router.post("/social-buzz/refresh", status_code=200)
async def refresh_social_buzz_now(user: User = Depends(get_current_user)):
    """Manual refresh — runs the same code path as the hourly cron, but with its
    OWN session factory (not app.state) and SYNCHRONOUSLY, returning the fetch
    summary. The summary lets the UI distinguish 'fetch blocked' (fetched=0) from
    'refreshed' (fetched>0) instead of silently no-op'ing on failure.
    """
    import asyncio
    import logging

    def _run() -> dict:
        from analytics.social_buzz import refresh_social_buzz
        engine, factory = _sync_session_factory()
        try:
            return refresh_social_buzz(factory)
        finally:
            engine.dispose()

    try:
        summary = await asyncio.to_thread(_run)
    except Exception:
        logging.getLogger(__name__).exception("Manual social buzz refresh failed")
        return {"status": "error", "fetched": 0, "snapshot_id": None}
    return {"status": "ok", **summary}


@router.get("/social-buzz/context")
async def social_buzz_context(
    symbol: str,
    user: User = Depends(get_current_user),
):
    """Recent StockTwits messages + sentiment summary for one symbol.

    Lazy — only called when the user expands a row in the Social tab.
    Server-side cache (5min per symbol) keeps StockTwits API usage well
    below the 200/hour anonymous limit.

    Returns:
      {symbol, messages: [...], bullish_count, bearish_count, neutral_count,
       total_count, bullish_pct, bearish_pct, neutral_pct, error?}
    """
    import asyncio as _aio
    from functools import partial as _partial
    from analytics.stocktwits import get_social_context

    loop = _aio.get_event_loop()
    ctx = await loop.run_in_executor(None, _partial(get_social_context, symbol))
    return ctx.to_dict()


@router.get("/social-buzz")
async def social_buzz(
    run_id: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Social Buzz snapshot — top tickers being discussed across retail social,
    ranked by mention growth %. ``run_id`` selects a specific saved run (history);
    omit for the latest.
    """
    if run_id is not None:
        row = await db.get(SocialBuzzSnapshot, run_id)
    else:
        row = (await db.execute(
            select(SocialBuzzSnapshot)
            .order_by(desc(SocialBuzzSnapshot.captured_at))
            .limit(1)
        )).scalar_one_or_none()

    if row is None:
        return {"id": None, "captured_at": None, "source": None, "entries": [], "stale": False}

    # Stale if older than 3 hours — typically hourly cron, so > 3h means
    # the job is broken or paused. A specific saved run is never "stale".
    from datetime import datetime, timedelta
    is_stale = run_id is None and (datetime.utcnow() - row.captured_at) > timedelta(hours=3)

    return {
        "id": row.id,
        "captured_at": row.captured_at.isoformat() + "Z",
        "source": row.source,
        "entries": row.entries or [],
        "stale": is_stale,
    }


@router.get("/social-buzz/history")
async def social_buzz_history(
    limit: int = Query(20, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recent saved Social Buzz runs (newest first) for the history selector."""
    rows = (await db.execute(
        select(SocialBuzzSnapshot.id, SocialBuzzSnapshot.captured_at, SocialBuzzSnapshot.entries)
        .order_by(desc(SocialBuzzSnapshot.captured_at))
        .limit(limit)
    )).all()
    return {
        "runs": [
            {"id": r.id, "captured_at": r.captured_at.isoformat() + "Z", "count": len(r.entries or [])}
            for r in rows
        ]
    }
