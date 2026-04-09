"""Trade journal model — auto-generated AI replay entries."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TradeJournal(Base):
    __tablename__ = "trade_journal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    alert_id: Mapped[int] = mapped_column(Integer, nullable=False)
    alert_type: Mapped[str] = mapped_column(String(100), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    entry_price: Mapped[Optional[float]] = mapped_column(Float)
    exit_price: Mapped[Optional[float]] = mapped_column(Float)
    stop_price: Mapped[Optional[float]] = mapped_column(Float)
    target_1: Mapped[Optional[float]] = mapped_column(Float)
    target_2: Mapped[Optional[float]] = mapped_column(Float)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)  # "t1_hit", "t2_hit", "stopped", "open", "breakeven"
    pnl_r: Mapped[Optional[float]] = mapped_column(Float)  # P&L in R multiples
    replay_text: Mapped[Optional[str]] = mapped_column(Text)  # AI-generated replay
    session_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
