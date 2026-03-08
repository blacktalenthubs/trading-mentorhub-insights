"""Alert schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class AlertResponse(BaseModel):
    id: int
    symbol: str
    alert_type: str
    direction: str
    price: float
    entry: Optional[float] = None
    stop: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    confidence: Optional[str] = None
    message: Optional[str] = None
    created_at: str
    session_date: str

    model_config = {"from_attributes": True}


class SessionSummaryResponse(BaseModel):
    total_alerts: int
    buy_alerts: int
    sell_alerts: int
    target_1_hits: int
    target_2_hits: int
    stopped_out: int
    active_entries: int
