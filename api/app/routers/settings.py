"""Settings endpoints: profile, password, notification preferences."""

from __future__ import annotations

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.settings import (
    ChangePasswordRequest,
    NotificationPrefsResponse,
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
