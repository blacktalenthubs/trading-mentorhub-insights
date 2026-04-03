"""Settings schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class UpdateProfileRequest(BaseModel):
    display_name: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class NotificationPrefsResponse(BaseModel):
    telegram_enabled: bool = True
    email_enabled: bool = False
    push_enabled: bool = False
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


class UpdateNotificationPrefsRequest(BaseModel):
    telegram_enabled: bool = True
    email_enabled: bool = False
    push_enabled: bool = False
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


# --- Alert Category Preferences ---


class AlertCategoryItem(BaseModel):
    category_id: str
    name: str
    description: str
    enabled: bool


class AlertPrefsResponse(BaseModel):
    categories: list[AlertCategoryItem]
    min_score: int = 0


class UpdateAlertPrefsRequest(BaseModel):
    categories: dict[str, bool]  # {category_id: enabled}
    min_score: int = 0
