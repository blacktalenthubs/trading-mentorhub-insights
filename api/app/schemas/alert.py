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
    score: int = 0
    confluence_score: int = 0
    confluence_label: Optional[str] = None
    entry_guidance: Optional[str] = None
    message: Optional[str] = None
    created_at: str
    session_date: str
    user_action: Optional[str] = None
    outcome: Optional[str] = None
    volume_ratio: Optional[float] = None
    cvd_delta: Optional[float] = None
    cvd_diverging: Optional[int] = None
    suppressed_reason: Optional[str] = None

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
            score=alert.score or 0,
            confluence_score=getattr(alert, "confluence_score", 0) or 0,
            confluence_label=getattr(alert, "confluence_label", None),
            entry_guidance=getattr(alert, "entry_guidance", None),
            message=alert.message,
            # ISO 8601 with explicit Z = UTC marker. Without it, the frontend's
            # `new Date(string)` parses as LOCAL time → display in CT looks ~5hr
            # off (alert fired at 10:45 CT shows as 15:45 CT). User-reported
            # 2026-05-26.
            created_at=alert.created_at.isoformat() + "Z" if alert.created_at else "",
            session_date=alert.session_date or "",
            user_action=alert.user_action,
            outcome=getattr(alert, "outcome", None),
            volume_ratio=getattr(alert, "volume_ratio", None),
            cvd_delta=getattr(alert, "cvd_delta", None),
            cvd_diverging=getattr(alert, "cvd_diverging", None),
            suppressed_reason=getattr(alert, "suppressed_reason", None),
        )


class SessionSummaryResponse(BaseModel):
    total_alerts: int
    buy_alerts: int
    sell_alerts: int
    target_1_hits: int
    target_2_hits: int
    stopped_out: int
    active_entries: int
