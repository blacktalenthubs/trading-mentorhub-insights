"""Push notification endpoints — register/unregister device tokens."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.device_token import DeviceToken
from app.models.user import User
from app.schemas.push import RegisterTokenRequest, RegisterTokenResponse

router = APIRouter()


@router.post("/register", response_model=RegisterTokenResponse, status_code=status.HTTP_201_CREATED)
async def register_device_token(
    body: RegisterTokenRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Store a device push token. Upserts if same user+token already exists."""
    if body.platform not in ("ios", "android"):
        raise HTTPException(status_code=422, detail="platform must be 'ios' or 'android'")

    # Check if already registered
    result = await db.execute(
        select(DeviceToken).where(
            DeviceToken.user_id == user.id,
            DeviceToken.token == body.token,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    device = DeviceToken(user_id=user.id, token=body.token, platform=body.platform)
    db.add(device)
    await db.flush()
    return device


@router.delete("/unregister", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_device_token(
    body: RegisterTokenRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a device push token (e.g. on logout)."""
    result = await db.execute(
        delete(DeviceToken).where(
            DeviceToken.user_id == user.id,
            DeviceToken.token == body.token,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Token not found")
