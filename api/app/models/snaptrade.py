"""SnapTrade connection model — one row per user.

Holds the per-user SnapTrade identity (userId + userSecret) plus the current
brokerage connection status. A single SnapTrade user can hold multiple
brokerage authorizations (e.g. Robinhood + Schwab); this row tracks the
registration and the last-synced state, while individual synced fills land in
`trades_monthly` (provenance stamped via the `account` column, e.g. "ROBINHOOD").

Security note: `user_secret` is a bearer credential for the SnapTrade API and
must never be returned to the client. Responses expose only `status`,
`broker_slug`, and sync metadata — never the secret.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Status lifecycle for a SnapTrade connection.
STATUS_REGISTERED = "registered"  # SnapTrade user created, no broker linked yet
STATUS_CONNECTED = "connected"    # at least one brokerage authorization is live
STATUS_DISABLED = "disabled"      # user disconnected / authorization removed


class SnapTradeConnection(Base):
    __tablename__ = "snaptrade_connections"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_snaptrade_conn_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    # The user_id we register with SnapTrade (namespaced, e.g. "btd_42").
    snaptrade_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Bearer secret returned by SnapTrade at registration. NEVER expose.
    user_secret: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=STATUS_REGISTERED
    )
    # Brokerage slug of the most recently connected authorization, e.g.
    # "ROBINHOOD". Informational — sync pulls activities across all accounts.
    broker_slug: Mapped[Optional[str]] = mapped_column(String(50))
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_sync_count: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
