"""Premarket Gap Board snapshot — one row per premarket scan.

Latest row is served by GET /market/premarket-gaps. Populated by the premarket
cron (analytics/premarket_gaps.refresh_premarket_gaps). Mirrors SocialBuzzSnapshot.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PremarketGapSnapshot(Base):
    __tablename__ = "premarket_gap_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    # Ranked list of gapper dicts — see refresh_premarket_gaps() for shape:
    #   { symbol, bucket(clean|momentum), on_watchlist, gap_pct, gap_type,
    #     pm_last, pm_high, pm_low, pm_change_pct, pm_volume, pm_dollar_vol,
    #     prior_close, pdh, pdl, pwh, pwl, flags[], catalyst }
    entries: Mapped[list] = mapped_column(JSON, default=list)
