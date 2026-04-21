"""User and subscription models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
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
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(50))
    email_enabled: Mapped[bool] = mapped_column(Boolean, server_default="0", default=False)
    push_enabled: Mapped[bool] = mapped_column(Boolean, server_default="0", default=False)
    quiet_hours_start: Mapped[Optional[str]] = mapped_column(String(10))
    quiet_hours_end: Mapped[Optional[str]] = mapped_column(String(10))
    min_alert_score: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    referral_code: Mapped[Optional[str]] = mapped_column(String(20), unique=True, nullable=True)
    auto_analysis_enabled: Mapped[bool] = mapped_column(Boolean, server_default="0", default=False)

    # Attribution — captured at signup from UTM params
    attribution_source: Mapped[Optional[str]] = mapped_column(String(100))    # twitter, tiktok, friend, ...
    attribution_medium: Mapped[Optional[str]] = mapped_column(String(100))    # social, dm, cpc, organic, ...
    attribution_campaign: Mapped[Optional[str]] = mapped_column(String(200))  # launch, eth_replay, ...
    attribution_referrer: Mapped[Optional[str]] = mapped_column(String(500))  # document.referrer

    # AI Alert Filters (Spec 36) — user-controlled alert volume
    min_conviction: Mapped[str] = mapped_column(String(10), server_default="medium", default="medium")
    # Values: "low" | "medium" | "high"  — filters Telegram delivery by signal conviction
    wait_alerts_enabled: Mapped[bool] = mapped_column(Boolean, server_default="1", default=True)
    # Default ON — don't silently hide AI from users; let free tier turn it off if noisy
    alert_directions: Mapped[str] = mapped_column(
        String(100), server_default="LONG,SHORT,RESISTANCE,EXIT",
        default="LONG,SHORT,RESISTANCE,EXIT",
    )
    # Comma-separated: any subset of {LONG, SHORT, RESISTANCE, EXIT}

    # Spec 38 — swing alerts (daily/weekly key levels)
    swing_alerts_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default="1", default=True,
    )

    # Per-alert-type channel routing — JSON dict, e.g.
    # {"ai_update": "email", "ai_long": "telegram", "ai_exit": "both"}
    # Values: "telegram" | "email" | "both" | "off".
    # NULL / missing key → fall back to legacy telegram_enabled behavior.
    notification_routing: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Position sizing (Spec 36 Option A) — used by Telegram Took It flow
    default_portfolio_size: Mapped[float] = mapped_column(
        Float, server_default="50000", default=50000.0,
    )
    default_risk_pct: Mapped[float] = mapped_column(
        Float, server_default="1.0", default=1.0,
    )

    subscription: Mapped[Optional[Subscription]] = relationship(back_populates="user")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    tier: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="free",
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), server_default="active")
    current_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime)
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="subscription")
