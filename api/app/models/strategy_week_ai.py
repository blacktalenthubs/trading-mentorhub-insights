"""Per-week cache for the AI strategy-analysis verdicts.

The Daily/Weekly redesign keys the AI verdicts by ISO week (the Monday of the
week), unlike the legacy strategy_analysis_cache which is keyed by lookback_days.
One row per week; regenerated on demand via POST /strategy-analysis/refresh.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StrategyWeekAICache(Base):
    __tablename__ = "strategy_week_ai_cache"

    week_start: Mapped[str] = mapped_column(String(10), primary_key=True)  # Monday ISO date
    narrative: Mapped[str] = mapped_column(Text, nullable=False)           # AI prose summary
    verdicts_json: Mapped[str] = mapped_column(Text, nullable=True)        # {alert_type: {recommendation, classification}}
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
