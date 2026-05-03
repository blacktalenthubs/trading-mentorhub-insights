"""Alert, active entry, and cooldown models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(100), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    entry: Mapped[Optional[float]] = mapped_column(Float)
    stop: Mapped[Optional[float]] = mapped_column(Float)
    target_1: Mapped[Optional[float]] = mapped_column(Float)
    target_2: Mapped[Optional[float]] = mapped_column(Float)
    confidence: Mapped[Optional[str]] = mapped_column(String(10))
    message: Mapped[Optional[str]] = mapped_column(Text)
    narrative: Mapped[Optional[str]] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    score_v2: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    confluence_score: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    confluence_label: Mapped[Optional[str]] = mapped_column(String(50))
    entry_guidance: Mapped[Optional[str]] = mapped_column(Text)
    notified_email: Mapped[int] = mapped_column(Integer, server_default="0")
    notified_sms: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    session_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    user_action: Mapped[Optional[str]] = mapped_column(String(20))
    suppressed_reason: Mapped[Optional[str]] = mapped_column(String(200))
    t1_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    t2_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    stop_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    volume_ratio: Mapped[Optional[float]] = mapped_column(Float)
    cvd_delta: Mapped[Optional[float]] = mapped_column(Float)
    cvd_diverging: Mapped[int] = mapped_column(Integer, server_default="0", default=0)


class ActiveEntry(Base):
    __tablename__ = "active_entries"
    __table_args__ = (
        UniqueConstraint("user_id", "symbol", "session_date", "alert_type",
                         name="uq_active_entry_user_symbol_session_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    entry_price: Mapped[Optional[float]] = mapped_column(Float)
    stop_price: Mapped[Optional[float]] = mapped_column(Float)
    target_1: Mapped[Optional[float]] = mapped_column(Float)
    target_2: Mapped[Optional[float]] = mapped_column(Float)
    alert_type: Mapped[Optional[str]] = mapped_column(String(100))
    session_date: Mapped[Optional[str]] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Cooldown(Base):
    __tablename__ = "cooldowns"
    __table_args__ = (
        UniqueConstraint("user_id", "symbol", "session_date",
                         name="uq_cooldown_user_symbol_session"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    cooldown_until: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    session_date: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
