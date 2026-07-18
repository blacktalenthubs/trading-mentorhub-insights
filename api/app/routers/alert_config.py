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


# TWO-control Settings (user 2026-07-18): one switch per style, nothing else.
# Swing Trade = the levels that create the potential to HOLD for multiple days
# into weeks — 30-week MA reclaim, prior-quarter (PQ) reclaim, 200-MA bounce,
# and the 5/20 EMA cross. EVERY other type is Day Trade. (Feed panels still use
# style_for(); this mapping only drives the Settings buckets + bulk toggles.)
SWING_TRADE_TYPES: frozenset[str] = frozenset({
    "weekly_30w_held",         # wicked below & reclaimed the 30-week MA — long-hold trend support
    "pq_reclaim",              # prior-quarter Low bounce / Close reclaim / High break
    "ma200_bounce",            # daily close reclaimed the 200 EMA/SMA
    "ema_5_20_cross",          # Steve Burns 5/20 daily bullish cross
    "monthly_box",             # MoBO — monthly flat-base ceiling breakout (user 2026-07-18: breakout → swing)
    "mobo_rch",                # MoBO RC-H — prior monthly high that capped price, broken
    "ma_bounce_long_v3_sma200",  # the 200 SMA is swing support, not a day-trade bounce (user 2026-07-18)
})
TRADE_GROUP_ORDER = ["Day Trade", "Swing Trade"]


def _group_for(alert_type: str, category: str) -> str:
    """The Settings bucket for a type — exactly two: Day Trade or Swing Trade."""
    return "Swing Trade" if alert_type in SWING_TRADE_TYPES else "Day Trade"


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
            "trade_group": _group_for(r.alert_type, r.category),
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
    if body.category:
        types = (await db.execute(select(AlertTypeConfig.alert_type).where(AlertTypeConfig.category == body.category))).scalars().all()
    elif body.trade_group:
        allrows = (await db.execute(select(AlertTypeConfig.alert_type, AlertTypeConfig.category))).all()
        types = [r.alert_type for r in allrows if _group_for(r.alert_type, r.category) == body.trade_group]
    else:
        types = (await db.execute(select(AlertTypeConfig.alert_type))).scalars().all()
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
