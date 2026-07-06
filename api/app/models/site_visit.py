from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SiteVisit(Base):
    """A lightweight page-view record for admin traffic analytics.

    Logged by the frontend on every route change via the public POST /track
    endpoint. Holds no PII beyond a client-generated anonymous `visitor_id`
    (persisted in localStorage) plus an optional `user_id` when the visitor is
    logged in. Used only for aggregate admin traffic stats.
    """

    __tablename__ = "site_visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Anonymous, client-generated id (localStorage) — lets us count unique
    # visitors without cookies or PII.
    visitor_id: Mapped[str] = mapped_column(String(64), index=True)
    # Set when the visit comes from a logged-in session (best-effort).
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    path: Mapped[str] = mapped_column(String(300))
    referrer: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    # First-touch attribution — the utm_* from the link the visitor arrived on
    # (Twitter/TikTok posts, campaigns). Persisted client-side + sent on every
    # ping so the whole session carries the source, not just the landing hit.
    utm_source: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    utm_medium: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    utm_campaign: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
