"""Usage tracking model — daily feature counters per user."""

from __future__ import annotations

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UsageLimit(Base):
    __tablename__ = "usage_limits"
    __table_args__ = (
        UniqueConstraint("user_id", "feature", "usage_date", name="uq_usage_per_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    feature: Mapped[str] = mapped_column(String(100), nullable=False)
    usage_date: Mapped[str] = mapped_column(String(10), nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
