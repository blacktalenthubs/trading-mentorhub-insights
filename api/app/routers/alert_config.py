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
from app.models.alert_type_config import AlertTypeConfig, describe_alert_type, style_for
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
    "Gap S/R": "Notice",              # gap fill/reject/support — context, not a setup
    "Gap-and-go": "Day Trade",        # tradable (RSI 75 / morning-low stop)
    "Multi-period S/R": "Notice",     # HTF S/R bounce/reject — context
    "Index shorts": "Day Trade",
    "Multi-touch levels": "Notice",   # multi-touch cross — context
    "Market context": "Notice",       # index_open_strength removed
    "4h reversal": "Day Trade",       # rc_4h / RC-H — the cornerstone
    "Daily RC": "Day Trade",          # rc_daily_long/hrec — prior-day H/L reclaim (RC-model)
    # "ORB · 15m" mapping removed 2026-07-08 — the 15m family retired (→ OBSOLETE).
    "ORB · 1h": "Day Trade",           # orb_reclaim — 1h OR reclaim (the clean, low-noise one)
    "Index reclaim": "Day Trade",     # reclaim_long — the backtested SPY/QQQ/DRAM edge (#65)
    "Levels": "Notice",               # lost_support_reject — context
    "Swing": "Swing Trade",
    "MA / EMA · Bounce Long": "Swing Trade",
    "MA / EMA · Rejection Short": "Notice",   # shorts → context; we prefer the long side
    "Weekly trend": "Long Term",      # weekly 10w/30w MA + weekly RC
    "Monthly trend": "Long Term",     # monthly_rc — prior-month H/L reclaim (rare position)
}
# Notice = info-only context, NOT tradable setups. Default OFF; users opt in per item.
TRADE_GROUP_ORDER = ["Day Trade", "Swing Trade", "Long Term", "Notice", "Other"]

_STYLE_GROUP = {"day_trade": "Day Trade", "swing": "Swing Trade", "long_term": "Long Term"}


def _group_for(alert_type: str, category: str) -> str:
    """The Settings bucket for a type. Info/context keeps its category group; tradable types follow
    style_for() so a SHARED category (weekly_rc vs weekly_10w) splits correctly by hold-horizon
    (2026-07-07 — reclaims are day trades, MA bounces are day trades, trend-MA holds are swings)."""
    g = CATEGORY_TO_GROUP.get(category, "Other")
    if g in ("Notice", "Other"):
        return g
    return _STYLE_GROUP.get(style_for(alert_type), g)


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
