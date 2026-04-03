"""Settings endpoints: profile, password, notification preferences, alert preferences."""

from __future__ import annotations

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.settings import (
    AlertCategoryItem,
    AlertPrefsResponse,
    ChangePasswordRequest,
    NotificationPrefsResponse,
    UpdateAlertPrefsRequest,
    UpdateNotificationPrefsRequest,
    UpdateProfileRequest,
)

router = APIRouter()


@router.put("/profile")
async def update_profile(
    body: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not body.display_name.strip():
        raise HTTPException(status_code=422, detail="Display name cannot be empty")

    user.display_name = body.display_name.strip()
    await db.flush()
    return {"display_name": user.display_name}


@router.put("/password")
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not bcrypt.checkpw(
        body.current_password.encode("utf-8"),
        user.password_hash.encode("utf-8"),
    ):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if len(body.new_password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters")

    user.password_hash = bcrypt.hashpw(
        body.new_password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")
    await db.flush()
    return {"message": "Password updated"}


@router.get("/notifications", response_model=NotificationPrefsResponse)
async def get_notification_prefs(
    user: User = Depends(get_current_user),
):
    return NotificationPrefsResponse(
        telegram_enabled=user.telegram_enabled,
        email_enabled=user.email_enabled,
        push_enabled=user.push_enabled,
        quiet_hours_start=user.quiet_hours_start,
        quiet_hours_end=user.quiet_hours_end,
    )


@router.put("/notifications", response_model=NotificationPrefsResponse)
async def update_notification_prefs(
    body: UpdateNotificationPrefsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.telegram_enabled = body.telegram_enabled
    user.email_enabled = body.email_enabled
    user.push_enabled = body.push_enabled
    user.quiet_hours_start = body.quiet_hours_start
    user.quiet_hours_end = body.quiet_hours_end
    await db.flush()
    return NotificationPrefsResponse(
        telegram_enabled=user.telegram_enabled,
        email_enabled=user.email_enabled,
        push_enabled=user.push_enabled,
        quiet_hours_start=user.quiet_hours_start,
        quiet_hours_end=user.quiet_hours_end,
    )


# --- Alert Category Preferences ---


@router.get("/alert-preferences", response_model=AlertPrefsResponse)
async def get_alert_preferences(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get alert category toggles and min score filter."""
    from alert_config import ALERT_CATEGORIES
    from app.models.alert_prefs import UserAlertCategoryPref

    rows = (await db.execute(
        select(UserAlertCategoryPref).where(UserAlertCategoryPref.user_id == user.id)
    )).scalars().all()
    saved = {r.category_id: bool(r.enabled) for r in rows}

    categories = []
    for cat_id, cat in ALERT_CATEGORIES.items():
        categories.append(AlertCategoryItem(
            category_id=cat_id,
            name=cat["name"],
            description=cat["description"],
            enabled=saved.get(cat_id, True),
        ))

    return AlertPrefsResponse(categories=categories, min_score=user.min_alert_score)


@router.put("/alert-preferences", response_model=AlertPrefsResponse)
async def update_alert_preferences(
    body: UpdateAlertPrefsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update alert category toggles and min score filter."""
    from alert_config import ALERT_CATEGORIES
    from app.models.alert_prefs import UserAlertCategoryPref

    user.min_alert_score = max(0, min(100, body.min_score))

    for cat_id, enabled in body.categories.items():
        if cat_id not in ALERT_CATEGORIES:
            continue
        existing = (await db.execute(
            select(UserAlertCategoryPref).where(
                UserAlertCategoryPref.user_id == user.id,
                UserAlertCategoryPref.category_id == cat_id,
            )
        )).scalar_one_or_none()
        if existing:
            existing.enabled = int(enabled)
        else:
            db.add(UserAlertCategoryPref(
                user_id=user.id,
                category_id=cat_id,
                enabled=int(enabled),
            ))

    await db.flush()

    categories = []
    for cat_id, cat in ALERT_CATEGORIES.items():
        categories.append(AlertCategoryItem(
            category_id=cat_id,
            name=cat["name"],
            description=cat["description"],
            enabled=body.categories.get(cat_id, True),
        ))

    return AlertPrefsResponse(categories=categories, min_score=user.min_alert_score)
