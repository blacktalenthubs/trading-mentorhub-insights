"""Earnings calendar + history + per-user notifications-sent log.

Spec 61. Three models, all populated by analytics/earnings_refresh.py
running on the nightly APScheduler cron.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Earnings(Base):
    """The upcoming earnings event for one symbol. Replaced when a new
    quarter is announced — we never store more than one upcoming row per
    symbol. Historical actuals go to EarningsHistory.
    """

    __tablename__ = "earnings"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    next_earnings_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    time_of_day: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)  # BMO / AMC / DMH
    eps_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    revenue_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, server_default="0", default=False, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class EarningsHistory(Base):
    """Append-only quarterly history. Composite PK on (symbol, quarter_label)
    prevents duplicates when a re-run sees the same quarter again.
    """

    __tablename__ = "earnings_history"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    quarter_label: Mapped[str] = mapped_column(String(12), primary_key=True)  # e.g. "2026Q1"
    eps_actual: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    eps_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    surprise_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reported_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class EarningsNotificationSent(Base):
    """Marker rows so we never send the same earnings notification twice.
    Unique on (user_id, symbol, earnings_date, kind) — `kind` lets us
    layer T-14, T-1, post-earnings later without duplicating the T-7.
    """

    __tablename__ = "earnings_notifications_sent"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "symbol", "earnings_date", "kind",
            name="uq_earnings_notif_user_sym_date_kind",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    earnings_date: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="t7", default="t7")
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
