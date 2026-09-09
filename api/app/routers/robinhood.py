"""Robinhood — admin-only, UI-triggered import + read-only options analytics.

  POST /robinhood/import    run the fill import on demand for any date,
                            attributed to the logged-in admin (force=True so it
                            works even if the scheduled 16:45 ET job is disabled).
  GET  /robinhood/options   read-only options chain + greeks for a symbol/expiration.

Live order placement is intentionally absent — see robinhood_integration_spec.html §8
(execution deferred: real money, unofficial API, regulatory exposure).
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool

from app.dependencies import get_current_user, is_admin_user
from app.models.user import User
from app.rate_limit import limiter

router = APIRouter()


def _require_admin(user: User) -> None:
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Admin only")


@router.post("/import")
@limiter.limit("6/minute")
async def run_import(
    request: Request,
    date_param: str | None = Query(None, alias="date", description="session date YYYY-MM-DD (default: today)"),
    lookback: int = Query(3, ge=0, le=90, description="days before `date` to also include"),
    user: User = Depends(get_current_user),
):
    """Run the Robinhood fill import now. Attributed to the logged-in admin's
    user id (resolves the actor-vs-target question for UI runs). Blocking
    network I/O is offloaded so the event loop stays free."""
    _require_admin(user)
    try:
        session_date = (
            datetime.strptime(date_param, "%Y-%m-%d").date() if date_param else date.today()
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")

    from brokers.robinhood_sync import sync_robinhood_fills

    r = await run_in_threadpool(
        sync_robinhood_fills,
        session_date=session_date,
        lookback_days=lookback,
        user_id=user.id,
        force=True,
    )
    return {
        "session_date": r.session_date.isoformat(),
        "fills_seen": r.fills_seen,
        "fills_imported": r.fills_imported,
        "matched_trades": r.matched_trades,
        "daily_target_rows": r.daily_target_rows,
        "realized_pnl": r.realized_pnl,
        "skipped": r.skipped,
        "error": r.error,
    }


@router.get("/options")
@limiter.limit("20/minute")
async def options_chain(
    request: Request,
    symbol: str = Query(..., min_length=1, max_length=10),
    exp: str = Query(..., description="expiration date YYYY-MM-DD"),
    kind: str = Query("both", alias="type", pattern="^(call|put|both)$"),
    user: User = Depends(get_current_user),
):
    """Read-only options chain + greeks. No order is ever placed."""
    _require_admin(user)
    try:
        datetime.strptime(exp, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="exp must be YYYY-MM-DD")

    from brokers.robinhood import RobinhoodError
    from brokers.robinhood_options import fetch_option_greeks

    try:
        rows = await run_in_threadpool(fetch_option_greeks, symbol.upper(), exp, kind)
    except RobinhoodError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"symbol": symbol.upper(), "expiration": exp, "type": kind, "rows": rows}
