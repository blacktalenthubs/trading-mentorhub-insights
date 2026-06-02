"""Alert, active entry, and cooldown models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text as sa_text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Alert(Base):
    __tablename__ = "alerts"
    # Composite indexes added 2026-06-01 after public-access fan-out: the
    # alerts table now grows ~N× faster (one row per user × signal) and
    # the dominant query patterns are (user_id + session_date) for today /
    # session views, (user_id + created_at desc) for /alerts/history, and
    # (user_id + user_action) for the Took/Skipped performance views.
    __table_args__ = (
        Index("idx_alerts_user_session", "user_id", "session_date"),
        Index("idx_alerts_user_created", "user_id", "created_at"),
        Index(
            "idx_alerts_user_action",
            "user_id",
            "user_action",
            postgresql_where=sa_text("user_action IS NOT NULL"),
        ),
    )

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
    outcome: Mapped[Optional[str]] = mapped_column(String(20))
    # User-supplied actual exit price when they closed the trade. Used to
    # compute real R-multiple per alert for the Trades-page rollup. Null
    # until user enters it via the inline input on the Trades page.
    exit_price: Mapped[Optional[float]] = mapped_column(Float)
    suppressed_reason: Mapped[Optional[str]] = mapped_column(String(200))
    t1_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    t2_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    stop_notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    volume_ratio: Mapped[Optional[float]] = mapped_column(Float)
    cvd_delta: Mapped[Optional[float]] = mapped_column(Float)
    cvd_diverging: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    # Spec 58 — Pine's day-type stage classifier + VWAP slope, surfaced to Telegram
    stage: Mapped[Optional[str]] = mapped_column(String)
    vwap_slope_pct: Mapped[Optional[float]] = mapped_column(Float)
    inside_day: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    # Setup grade — A/B/C computed at write time from vol_ratio + vwap_slope_pct.
    # See analytics/alert_grade.py. Defaults to 'C' so legacy rows don't break filters.
    grade: Mapped[Optional[str]] = mapped_column(String(1), server_default="C")
    # Spec 61 follow-up — real outcome computed after EOD from actual price action.
    # Populated by analytics/alert_outcomes.py nightly job, NOT from fixed-% T1/T2.
    # real_outcome: 'worked' (hit +1R MFE before -1R MAE), 'failed' (hit -1R first),
    # 'inconclusive' (neither within session). NULL = not yet computed.
    real_outcome: Mapped[Optional[str]] = mapped_column(String(20))
    mfe_r: Mapped[Optional[float]] = mapped_column(Float)   # max favorable excursion in R
    mae_r: Mapped[Optional[float]] = mapped_column(Float)   # max adverse excursion in R
    outcome_computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # Strategy Analysis — REAL forward % return from the alert price to a later
    # close. Populated by analytics/forward_returns.py. Baseline is `price` (the
    # fire price), NOT entry. Measures whether the move actually held:
    #   ret_eod_pct: % from price to the close on session_date (same day).
    #   ret_eow_pct: % from price to the close on that week's last trading day.
    # NULL = not yet computed / horizon not yet matured (week still open).
    ret_eod_pct: Mapped[Optional[float]] = mapped_column(Float)
    ret_eow_pct: Mapped[Optional[float]] = mapped_column(Float)
    fwd_returns_computed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


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
