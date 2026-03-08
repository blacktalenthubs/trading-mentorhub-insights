"""Scanner schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SignalResultResponse(BaseModel):
    symbol: str
    score: int
    grade: str
    action_label: str
    entry: Optional[float] = None
    stop: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    rr_ratio: Optional[float] = None
    support_status: str = ""
    pattern: str = ""
    direction: str = ""
    near_support: bool = False
    close: Optional[float] = None
    prior_day_low: Optional[float] = None
    ma20: Optional[float] = None
    ma50: Optional[float] = None
    # New fields for expanded detail cards
    prior_high: Optional[float] = None
    prior_low: Optional[float] = None
    nearest_support: Optional[float] = None
    support_label: str = ""
    distance_to_support: Optional[float] = None
    distance_pct: Optional[float] = None
    reentry_stop: Optional[float] = None
    risk_per_share: Optional[float] = None
    bias: str = ""
    day_range: Optional[float] = None
    volume_ratio: Optional[float] = None


class ActiveEntryResponse(BaseModel):
    id: int
    symbol: str
    entry_price: Optional[float]
    stop_price: Optional[float]
    target_1: Optional[float]
    target_2: Optional[float]
    alert_type: Optional[str]
    session_date: Optional[str]
    status: str

    model_config = {"from_attributes": True}
