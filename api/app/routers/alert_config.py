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
from app.models.alert_type_config import AlertTypeConfig
from app.models.user import User

router = APIRouter()


class AlertConfigUpdate(BaseModel):
    enabled: bool


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
        }
        for r in rows
    ]


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
