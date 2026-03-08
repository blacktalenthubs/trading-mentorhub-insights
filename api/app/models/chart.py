"""Chart level and monitor status models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ChartLevel(Base):
    __tablename__ = "chart_levels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str] = mapped_column(String(100), server_default="")
    color: Mapped[str] = mapped_column(String(20), server_default="#3498db")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MonitorStatus(Base):
    __tablename__ = "monitor_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    last_poll_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    symbols_checked: Mapped[int] = mapped_column(Integer, server_default="0")
    alerts_fired: Mapped[int] = mapped_column(Integer, server_default="0")
    status: Mapped[str] = mapped_column(String(20), server_default="idle")
