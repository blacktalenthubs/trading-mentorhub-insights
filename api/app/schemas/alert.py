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
    user_action: Optional[str] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_alert(cls, alert) -> "AlertResponse":
        return cls(
            id=alert.id,
            symbol=alert.symbol,
            alert_type=alert.alert_type,
            direction=alert.direction,
            price=alert.price,
            entry=alert.entry,
            stop=alert.stop,
            target_1=alert.target_1,
            target_2=alert.target_2,
            confidence=alert.confidence,
            message=alert.message,
            created_at=str(alert.created_at) if alert.created_at else "",
            session_date=alert.session_date or "",
            user_action=alert.user_action,
        )


class SessionSummaryResponse(BaseModel):
    total_alerts: int
    buy_alerts: int
    sell_alerts: int
    target_1_hits: int
    target_2_hits: int
    stopped_out: int
    active_entries: int
