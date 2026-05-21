"""Focus List model — persisted AI Best Setups scan snapshots.

A focus list is an immutable snapshot of one Best Setups scan. Recommendations
are stored inline as JSON (always read as a set with their parent list).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FocusList(Base):
    __tablename__ = "focus_lists"
    __table_args__ = (
        Index("ix_focus_lists_user_generated", "user_id", "generated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    # When the scan completed (engine timestamp).
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # ET calendar date of the run (ISO string, consistent with alerts/usage tables).
    session_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    # pre_open | pre_close | other
    market_window: Mapped[str] = mapped_column(String(20), nullable=False)
    # has_setups | no_setups | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    watchlist_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # list[ Recommendation ] — empty unless status == has_setups
    recommendations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # list[ {symbol, reason} ]
    skipped: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # human-readable explanation for no_setups / failed
    message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
