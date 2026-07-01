"""Pydantic schemas for the SnapTrade broker-connect + sync endpoints.

None of these ever carry the SnapTrade `user_secret` — it stays server-side.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ConnectionStatusResponse(BaseModel):
    """Current SnapTrade connection state for the authenticated user."""

    connected: bool
    status: str  # "registered" | "connected" | "disabled" | "none"
    broker_slug: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    last_sync_count: int = 0


class ConnectPortalResponse(BaseModel):
    """A one-time SnapTrade Connection Portal URL to link a brokerage."""

    redirect_uri: str


class SyncResultResponse(BaseModel):
    """Outcome of a fill-sync run."""

    fills_fetched: int
    fills_imported: int
    fills_skipped: int
    patterns_matched: int
    start_date: str
    end_date: str


class BrokerAccountResponse(BaseModel):
    """A connected brokerage account (institution + masked number)."""

    account_id: str
    institution_name: Optional[str] = None
    name: Optional[str] = None
    number: Optional[str] = None


class ConnectionsListResponse(BaseModel):
    status: str
    accounts: List[BrokerAccountResponse] = []
