"""Focus List service — window classification, recommendation mapping,
persistence, and history retention for the AI Best Setups focus list.

The AI engine (analytics/ai_best_setups.py) is reused unchanged for generation;
this module only adds persistence + labelling around it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.focus_list import FocusList

_ET = ZoneInfo("America/New_York")

# Market window boundaries (ET minutes-of-day). Boundaries are a tuning detail.
_OPEN_MIN = 9 * 60 + 30   # 09:30
_CLOSE_MIN = 16 * 60      # 16:00
_PRE_CLOSE_MIN = 15 * 60  # 15:00 — last hour before the close

HISTORY_RETENTION_DAYS = 30


def utcnow() -> datetime:
    """Current UTC time as a naive datetime (matches the DB's TIMESTAMP columns)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def et_today() -> str:
    """Today's date in US/Eastern as an ISO string."""
    return datetime.now(_ET).date().isoformat()


def classify_market_window(now_utc: datetime) -> str:
    """Return the market window a timestamp falls in: pre_open | pre_close | other."""
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    et = now_utc.astimezone(_ET)
    minutes = et.hour * 60 + et.minute
    if minutes < _OPEN_MIN:
        return "pre_open"
    if _PRE_CLOSE_MIN <= minutes < _CLOSE_MIN:
        return "pre_close"
    return "other"


def entry_candidate_to_recommendation(pick: dict, horizon: str) -> dict:
    """Map one engine pick (an EntryCandidate dict) to a stored recommendation.

    `horizon` is day_trade | swing. No new AI work — qualifying_criteria is
    assembled from fields the engine already returns (FR-014).
    """
    confluence = list(pick.get("confluence") or [])
    setup_type = pick.get("setup_type") or ""
    return {
        "symbol": (pick.get("symbol") or "").upper(),
        "setup_type": setup_type,
        "direction": (pick.get("direction") or "").upper(),
        "trade_horizon": horizon,
        "conviction": (pick.get("conviction") or "MEDIUM").upper(),
        "entry": pick.get("entry"),
        "stop": pick.get("stop"),
        "t1": pick.get("t1"),
        "t2": pick.get("t2"),
        "current_price": pick.get("current_price"),
        "distance_to_entry_pct": pick.get("distance_to_entry_pct"),
        "confluence": confluence,
        "why_now": pick.get("why_now") or "",
        "qualifying_criteria": {
            "entry_trigger": setup_type,
            "conviction_drivers": confluence,
            "horizon_fit": horizon,
        },
    }


def build_recommendations(day_picks: list[dict], swing_picks: list[dict]) -> list[dict]:
    """Combine the engine's two pick arrays into one ordered recommendation list."""
    recs = [entry_candidate_to_recommendation(p, "day_trade") for p in (day_picks or [])]
    recs += [entry_candidate_to_recommendation(p, "swing") for p in (swing_picks or [])]
    return recs


async def save_focus_list(
    db: AsyncSession,
    *,
    user_id: int,
    generated_at: datetime,
    session_date: str,
    market_window: str,
    status: str,
    watchlist_size: int,
    recommendations: list[dict],
    skipped: list[dict],
    message: str | None,
) -> FocusList:
    """Persist a FocusList row and prune the user's lists older than 30 days."""
    row = FocusList(
        user_id=user_id,
        generated_at=generated_at,
        session_date=session_date,
        market_window=market_window,
        status=status,
        watchlist_size=watchlist_size,
        recommendations=recommendations,
        skipped=skipped,
        message=message,
    )
    db.add(row)
    await db.flush()

    cutoff = utcnow() - timedelta(days=HISTORY_RETENTION_DAYS)
    await db.execute(
        delete(FocusList).where(
            FocusList.user_id == user_id,
            FocusList.generated_at < cutoff,
        )
    )
    await db.flush()
    return row
