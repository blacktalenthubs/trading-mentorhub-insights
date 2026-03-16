"""User and subscription models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Notification preferences (stored directly on user for simplicity)
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, server_default="1", default=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, server_default="0", default=False)
    push_enabled: Mapped[bool] = mapped_column(Boolean, server_default="0", default=False)
    quiet_hours_start: Mapped[Optional[str]] = mapped_column(String(10))
    quiet_hours_end: Mapped[Optional[str]] = mapped_column(String(10))

    subscription: Mapped[Optional[Subscription]] = relationship(back_populates="user")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    tier: Mapped[str] = mapped_column(
        Enum("free", "pro", name="tier_enum"), nullable=False, server_default="free",
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), server_default="active")
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="subscription")
