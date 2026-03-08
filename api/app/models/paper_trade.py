"""Paper trading and real trade models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False, server_default="BUY")
    shares: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_price: Mapped[Optional[float]] = mapped_column(Float)
    exit_price: Mapped[Optional[float]] = mapped_column(Float)
    stop_price: Mapped[Optional[float]] = mapped_column(Float)
    target_price: Mapped[Optional[float]] = mapped_column(Float)
    pnl: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="open",
                                        index=True)
    alert_type: Mapped[Optional[str]] = mapped_column(String(100))
    alert_id: Mapped[Optional[int]] = mapped_column(Integer)
    alpaca_order_id: Mapped[Optional[str]] = mapped_column(String(100))
    alpaca_close_order_id: Mapped[Optional[str]] = mapped_column(String(100))
    session_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class RealTrade(Base):
    __tablename__ = "real_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False, server_default="BUY")
    shares: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[Optional[float]] = mapped_column(Float)
    stop_price: Mapped[Optional[float]] = mapped_column(Float)
    target_price: Mapped[Optional[float]] = mapped_column(Float)
    target_2_price: Mapped[Optional[float]] = mapped_column(Float)
    pnl: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="open",
                                        index=True)
    alert_type: Mapped[Optional[str]] = mapped_column(String(100))
    alert_id: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text, server_default="")
    session_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
