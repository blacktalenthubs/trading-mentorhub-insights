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


class AlertConfigUpdate(BaseModel):
    enabled: bool


class AlertConfigBulkUpdate(BaseModel):
    enabled: bool
    category: str | None = None  # if set, toggle ONLY this category's types (#281)


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
    rows = (await db.execute(q)).scalars().all()
    for r in rows:
        r.enabled = body.enabled
    return {"updated": len(rows), "enabled": body.enabled, "category": body.category}


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
