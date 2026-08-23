"""Daily Target self-reporting — per-user daily trade log + per-day session state.

Backs the founder's "make my number, then stop" discipline page. A DailyTrade is one
logged fill (symbol, instrument, entry mechanism, entry/exit, realized P/L). A DailySession
holds the per-day target snapshot + the closed flag ("day is over"). Gated to one account in
the router for now; the tables are user-scoped so they generalize later without a schema change.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DailyTrade(Base):
    __tablename__ = "daily_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    session_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # YYYY-MM-DD (ET)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    instrument: Mapped[str] = mapped_column(String(10), server_default="stock", default="stock")  # stock | option
    trade_type: Mapped[str] = mapped_column(String(10), server_default="day", default="day")     # day | swing
    setup: Mapped[Optional[str]] = mapped_column(String(60))          # entry mechanism (PDH break, SMA reclaim, ...)
    direction: Mapped[Optional[str]] = mapped_column(String(10))      # long | short
    entry_price: Mapped[Optional[float]] = mapped_column(Float)
    exit_price: Mapped[Optional[float]] = mapped_column(Float)
    quantity: Mapped[Optional[float]] = mapped_column(Float)        # shares (stock) or contracts (option)
    position_size: Mapped[Optional[float]] = mapped_column(Float)   # $ deployed (notional / capital in the trade)
    pnl: Mapped[float] = mapped_column(Float, nullable=False)         # realized P/L in $ (+ win / − loss)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(60))    # target | stop | into resistance | time | other
    note: Mapped[Optional[str]] = mapped_column(Text)                # thought process / review comment
    chart_image: Mapped[Optional[str]] = mapped_column(Text)         # a chart screenshot as a data: URL (base64)
    is_open: Mapped[bool] = mapped_column(Boolean, server_default="0", default=False)  # still holding — no exit / not realized yet
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DailySession(Base):
    __tablename__ = "daily_sessions"
    __table_args__ = (UniqueConstraint("user_id", "session_date", name="uq_daily_session_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    session_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    target: Mapped[float] = mapped_column(Float, server_default="4000", default=4000.0)  # $ target for the day
    closed: Mapped[bool] = mapped_column(Boolean, server_default="0", default=False)     # day is over — stop trading
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
