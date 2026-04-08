"""Chart analysis ORM model."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Float, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ChartAnalysis(Base):
    __tablename__ = "chart_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    direction: Mapped[Optional[str]] = mapped_column(String(10))
    entry_price: Mapped[Optional[float]] = mapped_column(Float)
    stop_price: Mapped[Optional[float]] = mapped_column(Float)
    target_1: Mapped[Optional[float]] = mapped_column(Float)
    target_2: Mapped[Optional[float]] = mapped_column(Float)
    rr_ratio: Mapped[Optional[float]] = mapped_column(Float)
    confidence: Mapped[Optional[str]] = mapped_column(String(10))
    confluence_score: Mapped[Optional[int]] = mapped_column(Integer)
    reasoning: Mapped[Optional[str]] = mapped_column(Text)
    higher_tf_summary: Mapped[Optional[str]] = mapped_column(Text)
    historical_ref: Mapped[Optional[str]] = mapped_column(Text)
    actual_outcome: Mapped[Optional[str]] = mapped_column(String(20))
    outcome_pnl: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
