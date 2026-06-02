"""Cache for the AI strategy-analysis narrative.

The pattern leaderboard is recomputed live (cheap SQL), but the Claude
recommendation costs tokens, so we cache the latest narrative per lookback
window. Regenerated on demand via POST /performance/strategy-analysis/refresh.
One row per lookback_days.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StrategyAnalysisCache(Base):
    __tablename__ = "strategy_analysis_cache"

    lookback_days: Mapped[int] = mapped_column(Integer, primary_key=True)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
