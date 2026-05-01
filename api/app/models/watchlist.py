"""Watchlist + WatchlistGroup models.

Groups are pure presentation — they let users organize their watchlist by
category (Mega Tech, Chips, etc.). Alert routing (`_users_watching` in
tv_webhook.py) only joins WatchlistItem.symbol → users; group_id is not
consulted, so grouping never affects which alerts a user receives.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WatchlistGroup(Base):
    __tablename__ = "watchlist_group"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_watchlist_group_user_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class WatchlistItem(Base):
    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("user_id", "symbol", name="uq_watchlist_user_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    group_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("watchlist_group.id", ondelete="SET NULL"), nullable=True, index=True
    )
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
