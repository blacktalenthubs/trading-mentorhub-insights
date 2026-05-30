"""In-Play Volume Screener endpoints (spec 62).

Reads are fast: they serve the latest cached snapshot and apply optional refine
filters over the ≤N rows in-process. Refresh happens out-of-band (scheduler).
Gated to Pro+ (FR-10).
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from analytics import screener as scr
from app.config import get_settings
from app.dependencies import require_pro
from app.models.user import User
from app.schemas.screener import SettingsOut, SnapshotOut
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


@router.get("/in-play", response_model=SnapshotOut)
async def get_in_play(
    preset: str = Query("any"),
    direction: str = Query("any"),
    has_setup: bool = Query(False),
    user: User = Depends(require_pro),
):
    """Latest in-play snapshot, optionally narrowed by a refine preset (FR-2/FR-9)."""
    snap = await svc.get_latest_snapshot()
    if snap is None:
        return SnapshotOut(captured_at=None, market_open=svc.is_market_open(), stale=False, top_n=get_settings().SCREENER_TOP_N, entries=[])

    entries = [_entry_from_dict(d) for d in (snap.entries or [])]
    if preset != "any" or direction != "any" or has_setup:
        entries = scr.apply_refine_filters(entries, preset=preset, direction=direction, has_setup=has_setup)

    return SnapshotOut(
        captured_at=snap.captured_at,
        market_open=bool(snap.market_open),
        stale=bool(snap.stale),
        top_n=snap.top_n,
        entries=[e.to_dict() for e in entries],
    )


@router.get("/settings", response_model=SettingsOut)
async def get_screener_settings(user: User = Depends(require_pro)):
    """Effective thresholds (global defaults in v1) + last universe rebuild time."""
    s = get_settings()
    return SettingsOut(
        market_cap_floor=s.SCREENER_MARKET_CAP_FLOOR,
        price_floor=s.SCREENER_PRICE_FLOOR,
        dollar_vol_floor=s.SCREENER_DOLLAR_VOL_FLOOR,
        top_n=s.SCREENER_TOP_N,
        refresh_minutes=s.SCREENER_REFRESH_MINUTES,
        universe_rebuilt_at=await svc.universe_rebuilt_at(),
    )


@router.post("/universe/rebuild", status_code=202)
async def rebuild_universe(background: BackgroundTasks, user: User = Depends(require_pro)):
    """Trigger an on-demand universe rebuild (FR-7). Runs in the background.

    TODO(T029): tighten to admin-only.
    """
    background.add_task(svc.rebuild_universe)
    return {"status": "rebuild started"}
