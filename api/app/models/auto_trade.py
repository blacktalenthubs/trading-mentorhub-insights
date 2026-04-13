"""AI Auto-Pilot paper trades — system-level simulated account (Spec 35).

Every actionable AI signal (LONG / SHORT) auto-opens a simulated trade here.
The AI's stop/target manages the exit. Public equity curve + track record
are computed from this table.

NOT user-scoped — this is ONE system account. Users' own paper/real trades
live in PaperTrade / RealTrade.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AIAutoTrade(Base):
    __tablename__ = "ai_auto_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Source signal
    alert_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("alerts.id"), nullable=True, index=True,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    # "BUY" (long) or "SHORT"

    setup_type: Mapped[Optional[str]] = mapped_column(String(500))
    # AI sometimes returns long descriptions — bumped from 100. Code also truncates defensively.
    conviction: Mapped[Optional[str]] = mapped_column(String(20))
    # HIGH / MEDIUM / LOW

    # Entry
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    session_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    # Risk plan (from AI)
    stop_price: Mapped[Optional[float]] = mapped_column(Float)
    target_1_price: Mapped[Optional[float]] = mapped_column(Float)
    target_2_price: Mapped[Optional[float]] = mapped_column(Float)

    # Position sizing (fixed $10k notional for transparency)
    shares: Mapped[float] = mapped_column(Float, nullable=False)
    notional_at_entry: Mapped[float] = mapped_column(Float, nullable=False)

    # Exit state
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="open", index=True)
    # open | closed_t1 | closed_t2 | closed_stop | closed_eod | closed_manual
    exit_price: Mapped[Optional[float]] = mapped_column(Float)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(50))

    # P&L (populated on close)
    pnl_dollars: Mapped[Optional[float]] = mapped_column(Float)
    pnl_percent: Mapped[Optional[float]] = mapped_column(Float)
    r_multiple: Mapped[Optional[float]] = mapped_column(Float)
    # (exit_price - entry_price) / (entry_price - stop_price). Negative if stopped.

    # Meta
    market: Mapped[Optional[str]] = mapped_column(String(20))
    # 'equity' or 'crypto' — drives EOD handling
    notes: Mapped[Optional[str]] = mapped_column(String(500))
