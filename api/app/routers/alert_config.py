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
from app.models.alert_type_pref import UserAlertTypePref
from app.models.user import User

router = APIRouter()


async def _set_pref(db: AsyncSession, user_id: int, alert_type: str, enabled: bool) -> None:
    """Upsert one user's on/off choice for one alert type (per-user, not global)."""
    row = (await db.execute(
        select(UserAlertTypePref).where(
            UserAlertTypePref.user_id == user_id,
            UserAlertTypePref.alert_type == alert_type,
        )
    )).scalar_one_or_none()
    if row is not None:
        row.enabled = enabled
    else:
        db.add(UserAlertTypePref(user_id=user_id, alert_type=alert_type, enabled=enabled))


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
    """Every alert type with THIS user's on/off state (per-user, default OFF).

    The catalog (labels/categories) comes from alert_type_config; the enabled flag
    is the user's own choice from user_alert_type_prefs. No row = OFF.
    """
    rows = (await db.execute(
        select(AlertTypeConfig).order_by(
            AlertTypeConfig.category, AlertTypeConfig.alert_type
        )
    )).scalars().all()
    prefs = (await db.execute(
        select(UserAlertTypePref).where(UserAlertTypePref.user_id == user.id)
    )).scalars().all()
    enabled_by_type = {p.alert_type: bool(p.enabled) for p in prefs}
    return [
        {
            "alert_type": r.alert_type,
            "label": r.label,
            "category": r.category,
            "trade_group": CATEGORY_TO_GROUP.get(r.category, "Other"),
            "enabled": enabled_by_type.get(r.alert_type, False),
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
    q = select(AlertTypeConfig.alert_type)
    if body.category:
        q = q.where(AlertTypeConfig.category == body.category)
    elif body.trade_group:
        cats = [c for c, g in CATEGORY_TO_GROUP.items() if g == body.trade_group]
        q = q.where(AlertTypeConfig.category.in_(cats))
    types = (await db.execute(q)).scalars().all()
    for at in types:
        await _set_pref(db, user.id, at, body.enabled)
    return {"updated": len(types), "enabled": body.enabled, "category": body.category, "trade_group": body.trade_group}


@router.put("/{alert_type}")
async def set_alert_config(
    alert_type: str,
    body: AlertConfigUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enable or disable one alert type FOR THIS USER. Next fired alert respects it."""
    exists = (await db.execute(
        select(AlertTypeConfig.alert_type).where(AlertTypeConfig.alert_type == alert_type)
    )).scalar_one_or_none()
    if exists is None:
        raise HTTPException(404, detail="Unknown alert type")
    await _set_pref(db, user.id, alert_type, body.enabled)
    return {"alert_type": alert_type, "enabled": body.enabled}
