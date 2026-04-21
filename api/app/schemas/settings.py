"""Settings schemas."""

from __future__ import annotations

from typing import Dict, Optional

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
    # Spec 36 — AI alert filters
    min_conviction: str = "medium"             # low | medium | high
    wait_alerts_enabled: bool = True           # ON by default — users opt out in Settings
    alert_directions: str = "LONG,SHORT,RESISTANCE,EXIT"
    # Spec 36 — position sizing
    default_portfolio_size: float = 50000.0
    default_risk_pct: float = 1.0


class UpdateNotificationPrefsRequest(BaseModel):
    telegram_enabled: bool = True
    email_enabled: bool = False
    push_enabled: bool = False
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    # Spec 36 — AI alert filters (all optional on update)
    min_conviction: Optional[str] = None
    wait_alerts_enabled: Optional[bool] = None
    alert_directions: Optional[str] = None
    default_portfolio_size: Optional[float] = None
    default_risk_pct: Optional[float] = None


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


# --- Per-alert-type channel routing ---


class NotificationRoutingResponse(BaseModel):
    """Returned by GET /settings/notification-routing.

    Values per alert type: "telegram" | "email" | "both" | "off".
    Defaults apply when the user has never set a preference.
    """
    ai_update: str = "telegram"
    ai_resistance: str = "telegram"
    ai_long: str = "telegram"
    ai_short: str = "telegram"
    ai_exit: str = "telegram"


class UpdateNotificationRoutingRequest(BaseModel):
    routing: Dict[str, str]  # {alert_type: channel}
