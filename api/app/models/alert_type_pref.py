"""Per-user alert-type enablement.

Replaces the GLOBAL alert_type_config switch for delivery so one user's toggles
never affect another (multi-tenancy fix, 2026-06-20). alert_type_config stays as
the *catalog* (which types exist + labels/categories); this table holds each
user's own on/off choice. Absence of a row = OFF (opt-in by default).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserAlertTypePref(Base):
    __tablename__ = "user_alert_type_prefs"
    __table_args__ = (
        UniqueConstraint("user_id", "alert_type", name="uq_alert_type_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(80), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
