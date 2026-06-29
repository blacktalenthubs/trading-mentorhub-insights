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
    # Nullable so OAuth-only accounts (Google / Apple) can exist without a password.
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    # OAuth identity — auto-linked by verified email when present.
    oauth_provider: Mapped[Optional[str]] = mapped_column(String(16))   # 'google' | 'apple' | NULL
    oauth_sub: Mapped[Optional[str]] = mapped_column(String(255), index=True)  # provider subject id
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # Bumped on /auth/me — drives the activation funnel and DAU/WAU metrics.
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Notification preferences (stored directly on user for simplicity)
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, server_default="1", default=True)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(50))
    email_enabled: Mapped[bool] = mapped_column(Boolean, server_default="0", default=False)
    push_enabled: Mapped[bool] = mapped_column(Boolean, server_default="0", default=False)
    # iOS APNs push (Capacitor native app) — device token + opt-in flag
    apns_token: Mapped[Optional[str]] = mapped_column(String(200))
    apns_enabled: Mapped[bool] = mapped_column(Boolean, server_default="0", default=False)
    quiet_hours_start: Mapped[Optional[str]] = mapped_column(String(10))
    quiet_hours_end: Mapped[Optional[str]] = mapped_column(String(10))
    min_alert_score: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    # Minimum setup grade — A/B/C. 'A' = high-conviction only, 'B' = A+B,
    # 'C' = no filter. See analytics/alert_grade.py. Applied at
    # /alerts/today, push delivery, and Telegram routing.
    min_alert_grade: Mapped[str] = mapped_column(String(1), server_default="C", default="C")
    referral_code: Mapped[Optional[str]] = mapped_column(String(20), unique=True, nullable=True)
    auto_analysis_enabled: Mapped[bool] = mapped_column(Boolean, server_default="0", default=False)

    # SPY 8/21 market gate. We manage it: protection is ON by default for everyone,
    # and it only bites when SPY is weak (below its 8 or 21 EMA) — then this user's
    # DAY-TRADE LONG alerts are suppressed, except symbols on their exempt list (and
    # the always-flow bypass setups). The flag is now an OVERRIDE: a user sets it
    # False to opt out and keep receiving longs in a weak tape. (Was opt-in/default
    # OFF before 2026-06-25; flipped to default ON + backfilled existing users.)
    market_gate_enabled: Mapped[bool] = mapped_column(Boolean, server_default="1", default=True)
    market_gate_exempt: Mapped[str] = mapped_column(String(2000), server_default="", default="")

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
    # Opt-in (default OFF): only PUSH day-trade alerts for the user's FOCUS symbols.
    # Off = whole watchlist (no change for existing users). Swing/long-term are never
    # focus-scoped. Non-focus day-trade alerts are still recorded (NOT SENT marker).
    daytrade_focus_only: Mapped[bool] = mapped_column(
        Boolean, server_default="0", default=False,
    )

    # Per-alert-type channel routing — JSON dict, e.g.
    # {"ai_update": "email", "ai_long": "telegram", "ai_exit": "both"}
    # Values: "telegram" | "email" | "both" | "off".
    # NULL / missing key → fall back to legacy telegram_enabled behavior.
    notification_routing: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Per-symbol Telegram override for AI Updates — comma-separated symbols
    # whose AI Updates always go to Telegram regardless of general routing.
    # Default "SPY" — market barometer. Set to "" to disable override.
    telegram_update_symbols: Mapped[Optional[str]] = mapped_column(
        String(500), server_default="SPY", default="SPY",
    )

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
