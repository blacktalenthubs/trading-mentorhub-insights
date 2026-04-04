"""Signal Library — public educational endpoints (no auth required)."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

# Ensure project root is importable
_root = str(Path(__file__).resolve().parents[3])
if _root not in sys.path:
    sys.path.insert(0, _root)

from app.data.learn_content import CATEGORIES, CATEGORY_ORDER

router = APIRouter()


# ── Response schemas ──────────────────────────────────────────────────

class AlertTypeInfo(BaseModel):
    type: str
    name: str
    desc: str


class CategoryStats(BaseModel):
    signal_count: int = 0
    win_rate: Optional[float] = None
    loss_count: int = 0
    win_count: int = 0


class CategorySummary(BaseModel):
    id: str
    name: str
    tagline: str
    difficulty: str
    pattern_count: int
    stats: CategoryStats


class CategoryDetail(BaseModel):
    id: str
    name: str
    tagline: str
    difficulty: str
    overview: str
    why_it_works: str
    when_it_fails: str
    how_to_read: List[str]
    pro_tips: List[str]
    key_alert_types: List[AlertTypeInfo]
    stats: CategoryStats


# ── Stats helper ──────────────────────────────────────────────────────

def _compute_category_stats(category_id: str, days: int = 90) -> CategoryStats:
    """Compute win/loss stats for a category from the alerts DB."""
    try:
        from alert_config import ALERT_TYPE_TO_CATEGORY
        from db import get_db

        session_cutoff = (date.today() - timedelta(days=days)).isoformat()

        # Get alert types belonging to this category
        cat_types = {
            at for at, cat in ALERT_TYPE_TO_CATEGORY.items()
            if cat == category_id
        }
        if not cat_types:
            return CategoryStats()

        with get_db() as conn:
            # Count total signals for this category
            placeholders = ",".join("?" for _ in cat_types)
            row = conn.execute(
                f"SELECT COUNT(*) FROM alerts WHERE alert_type IN ({placeholders}) "
                f"AND session_date >= ?",
                (*cat_types, session_cutoff),
            ).fetchone()
            signal_count = row[0] if row else 0

            # Compute win/loss by matching entry alerts to outcome alerts
            # within same (symbol, session_date) group
            outcome_wins = {"target_1_hit", "target_2_hit"}
            outcome_losses = {"stop_loss_hit", "auto_stop_out"}

            # Get all sessions with entry signals from this category
            entry_sessions = conn.execute(
                f"SELECT DISTINCT symbol, session_date FROM alerts "
                f"WHERE alert_type IN ({placeholders}) AND session_date >= ? "
                f"AND direction IN ('BUY', 'SHORT')",
                (*cat_types, session_cutoff),
            ).fetchall()

            win_count = 0
            loss_count = 0
            for symbol, session_date in entry_sessions:
                # Check if this session had a win or loss outcome
                outcomes = conn.execute(
                    "SELECT alert_type FROM alerts "
                    "WHERE symbol = ? AND session_date = ? AND alert_type IN (?, ?, ?, ?)",
                    (symbol, session_date, "target_1_hit", "target_2_hit",
                     "stop_loss_hit", "auto_stop_out"),
                ).fetchall()
                outcome_types = {r[0] for r in outcomes}
                if outcome_types & outcome_wins:
                    win_count += 1
                elif outcome_types & outcome_losses:
                    loss_count += 1

            total_decided = win_count + loss_count
            win_rate = round(win_count / total_decided * 100, 1) if total_decided > 0 else None

            return CategoryStats(
                signal_count=signal_count,
                win_rate=win_rate,
                win_count=win_count,
                loss_count=loss_count,
            )
    except Exception:
        return CategoryStats()


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/categories", response_model=List[CategorySummary])
async def list_categories():
    """List all 8 pattern categories with live stats. Public — no auth."""
    results = []
    for cat_id in CATEGORY_ORDER:
        cat = CATEGORIES.get(cat_id)
        if not cat:
            continue
        stats = _compute_category_stats(cat_id)
        results.append(CategorySummary(
            id=cat_id,
            name=cat["name"],
            tagline=cat["tagline"],
            difficulty=cat["difficulty"],
            pattern_count=len(cat.get("key_alert_types", [])),
            stats=stats,
        ))
    return results


@router.get("/{category_id}", response_model=CategoryDetail)
async def get_category(category_id: str):
    """Get detailed educational content for a category. Public — no auth."""
    cat = CATEGORIES.get(category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    stats = _compute_category_stats(category_id)

    return CategoryDetail(
        id=category_id,
        name=cat["name"],
        tagline=cat["tagline"],
        difficulty=cat["difficulty"],
        overview=cat["overview"],
        why_it_works=cat["why_it_works"],
        when_it_fails=cat["when_it_fails"],
        how_to_read=cat["how_to_read"],
        pro_tips=cat["pro_tips"],
        key_alert_types=[AlertTypeInfo(**at) for at in cat["key_alert_types"]],
        stats=stats,
    )
