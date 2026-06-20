"""Alert-type enablement API — list every alert type and toggle it on/off.

Backs the Settings > Alert Types panel. The TradingView webhook reads the
same table to decide which alert types to deliver.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.alert_type_config import AlertTypeConfig, describe_alert_type
from app.models.user import User

router = APIRouter()


# Group the catalog's fine-grained categories into the 3 trade-style buckets
# users actually think in (2026-06-20). Powers the Settings grouping + the
# one-shot "enable all Day / Swing / Long-term" so beginners pick a style, not
# 45 toggles. Any category not listed falls under "Other".
CATEGORY_TO_GROUP: dict[str, str] = {
    "Daily PDH/PDL": "Day Trade",
    "Weekly": "Day Trade",            # prior-week H/L levels, traded intraday
    "Monthly": "Day Trade",           # prior-month H/L levels
    "Gap S/R": "Day Trade",
    "Gap-and-go": "Day Trade",
    "Multi-period S/R": "Day Trade",
    "Index shorts": "Day Trade",
    "Multi-touch levels": "Day Trade",
    "Market context": "Day Trade",
    "4h reversal": "Day Trade",       # rc_4h / RC-H — the cornerstone
    "Levels": "Day Trade",
    "Swing": "Swing Trade",
    "MA / EMA · Bounce Long": "Swing Trade",
    "MA / EMA · Rejection Short": "Swing Trade",
    "Weekly trend": "Long Term",      # weekly 10w/30w MA + weekly RC
}
TRADE_GROUP_ORDER = ["Day Trade", "Swing Trade", "Long Term", "Other"]


class AlertConfigUpdate(BaseModel):
    enabled: bool


class AlertConfigBulkUpdate(BaseModel):
    enabled: bool
    category: str | None = None       # toggle ONLY this fine-grained category (#281)
    trade_group: str | None = None    # toggle a whole Day/Swing/Long-term bucket (one-shot)


@router.get("")
async def list_alert_config(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Every alert type with its current on/off state, ordered by category."""
    rows = (await db.execute(
        select(AlertTypeConfig).order_by(
            AlertTypeConfig.category, AlertTypeConfig.alert_type
        )
    )).scalars().all()
    return [
        {
            "alert_type": r.alert_type,
            "label": r.label,
            "category": r.category,
            "trade_group": CATEGORY_TO_GROUP.get(r.category, "Other"),
            "enabled": r.enabled,
            "description": describe_alert_type(r.alert_type),
        }
        for r in rows
    ]


@router.put("")
async def set_all_alert_config(
    body: AlertConfigBulkUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk enable/disable alert types in one call — backs the 'All off' / 'All on'
    buttons AND the per-category Enable/Disable (#281: pass category to flip just one
    group, e.g. the MA/EMA bounce alerts when the tape gets choppy). No category =
    every type. Takes effect on the next fired alert."""
    q = select(AlertTypeConfig)
    if body.category:
        q = q.where(AlertTypeConfig.category == body.category)
    elif body.trade_group:
        cats = [c for c, g in CATEGORY_TO_GROUP.items() if g == body.trade_group]
        q = q.where(AlertTypeConfig.category.in_(cats))
    rows = (await db.execute(q)).scalars().all()
    for r in rows:
        r.enabled = body.enabled
    return {"updated": len(rows), "enabled": body.enabled, "category": body.category, "trade_group": body.trade_group}


@router.put("/{alert_type}")
async def set_alert_config(
    alert_type: str,
    body: AlertConfigUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enable or disable one alert type. Takes effect on the next fired alert."""
    row = (await db.execute(
        select(AlertTypeConfig).where(AlertTypeConfig.alert_type == alert_type)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, detail="Unknown alert type")
    row.enabled = body.enabled
    return {"alert_type": row.alert_type, "enabled": row.enabled}
