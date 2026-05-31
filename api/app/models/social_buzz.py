"""Social Buzz snapshot — one row per refresh of Apewisdom + filters.

Latest row is served by /screener/social-buzz. Older rows kept ~7 days
for future "buzz trend" charts; weekly cleanup job (see cron in
api/app/main.py + cleanup_old_snapshots in analytics/social_buzz.py).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SocialBuzzSnapshot(Base):
    __tablename__ = "social_buzz_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    # "apewisdom_stocks" today; future sources: "stocktwits", "wsb_reddit", etc.
    source: Mapped[str] = mapped_column(String(32), default="apewisdom_stocks", index=True)
    # Top-N list of SocialBuzzEntry dicts. See refresh_social_buzz() for shape:
    #   { symbol, name, mentions, mentions_prev_24h, growth_pct,
    #     sentiment, sentiment_score, rank, has_grade_a_today }
    entries: Mapped[list] = mapped_column(JSON, default=list)
