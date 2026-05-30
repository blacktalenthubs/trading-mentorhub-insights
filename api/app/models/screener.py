"""In-Play Volume Screener models (spec 62).

`screener_universe` caches the Layer-1 liquid universe (weekly rebuild);
`screener_snapshot` stores each Layer-2 in-play refresh as a JSON entry list.
Both work on SQLite (local) and Postgres (prod) via SQLAlchemy.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ScreenerUniverse(Base):
    """One row per eligible symbol in the cached, capped universe (FR-1, FR-7)."""

    __tablename__ = "screener_universe"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    market_cap: Mapped[float] = mapped_column(Float, nullable=False)
    last_price: Mapped[float] = mapped_column(Float, nullable=False)
    avg_dollar_vol: Mapped[float] = mapped_column(Float, nullable=False)
    sector: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    rebuilt_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ScreenerSnapshot(Base):
    """One row per in-play refresh; latest row is what the endpoint serves (FR-2, FR-3, FR-8)."""

    __tablename__ = "screener_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    market_open: Mapped[bool] = mapped_column(Boolean, default=False)
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    top_n: Mapped[int] = mapped_column(Integer, default=30)
    # Ordered list of InPlayEntry dicts (see analytics/screener.py::InPlayEntry.to_dict)
    entries: Mapped[list] = mapped_column(JSON, default=list)


class ScreenerUserSettings(Base):
    """Per-user view overrides (FR-6) over the global snapshot — thresholds only."""

    __tablename__ = "screener_user_settings"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_cap_floor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    top_n: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
