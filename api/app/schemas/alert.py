"""Alert schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


def _compute_r(alert) -> Optional[float]:
    """R-multiple = (exit - entry) / (entry - stop). Longs only for now."""
    exit_price = getattr(alert, "exit_price", None)
    entry = getattr(alert, "entry", None)
    stop = getattr(alert, "stop", None)
    if exit_price is None or entry is None or stop is None:
        return None
    risk = entry - stop
    if risk == 0:
        return None
    return round((exit_price - entry) / risk, 2)


class AlertResponse(BaseModel):
    id: int
    symbol: str
    alert_type: str
    description: Optional[str] = None  # plain-English pattern explanation (spec 61 follow-up)
    direction: str
    price: float
    entry: Optional[float] = None
    stop: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    # Sub-spec A/L — single-target kind + day/swing tag.
    target_kind: Optional[str] = None        # level | rsi | eod
    trade_type: Optional[str] = None         # day | swing
    swing_eligible: Optional[bool] = None
    confidence: Optional[str] = None
    score: int = 0
    confluence_score: int = 0
    confluence_label: Optional[str] = None
    entry_guidance: Optional[str] = None
    message: Optional[str] = None
    narrative: Optional[str] = None          # the AI agent's read — sent to Telegram, now surfaced in the app's Today > Briefing
    created_at: str
    session_date: str
    user_action: Optional[str] = None
    outcome: Optional[str] = None
    volume_ratio: Optional[float] = None
    vwap_slope_pct: Optional[float] = None
    grade: Optional[str] = None              # A / B / C per analytics/alert_grade.py
    real_outcome: Optional[str] = None       # worked | failed | inconclusive (post-fire compute)
    mfe_r: Optional[float] = None
    mae_r: Optional[float] = None
    cvd_delta: Optional[float] = None
    cvd_diverging: Optional[int] = None
    suppressed_reason: Optional[str] = None
    # Feed split (2026-06-29): every alert is filed in a STYLE panel regardless of
    # delivery. style = day_trade | swing | long_term; delivered = was it pushed
    # (Telegram/in-app) vs recorded-only (suppressed_reason set → not delivered).
    style: str = "day_trade"
    delivered: bool = True
    # Trades-page additions (2026-05-28): user records actual exit price; R is derived.
    exit_price: Optional[float] = None
    r_multiple: Optional[float] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_alert(cls, alert) -> "AlertResponse":
        # Import inside the method to avoid a circular import — the
        # alert_type_config module imports from various app/* modules.
        from app.models.alert_type_config import describe_alert_type, style_for
        _sr = getattr(alert, "suppressed_reason", None)
        return cls(
            id=alert.id,
            symbol=alert.symbol,
            alert_type=alert.alert_type,
            description=describe_alert_type(alert.alert_type) or None,
            style=style_for(alert.alert_type),
            delivered=_sr is None,
            direction=alert.direction,
            price=alert.price,
            entry=alert.entry,
            stop=alert.stop,
            target_1=alert.target_1,
            target_2=alert.target_2,
            target_kind=getattr(alert, "target_kind", None),
            trade_type=getattr(alert, "trade_type", None),
            swing_eligible=bool(getattr(alert, "swing_eligible", 0)) if getattr(alert, "swing_eligible", None) is not None else None,
            confidence=alert.confidence,
            score=alert.score or 0,
            confluence_score=getattr(alert, "confluence_score", 0) or 0,
            confluence_label=getattr(alert, "confluence_label", None),
            entry_guidance=getattr(alert, "entry_guidance", None),
            message=alert.message,
            narrative=getattr(alert, "narrative", None),
            # ISO 8601 with explicit Z = UTC marker. Without it, the frontend's
            # `new Date(string)` parses as LOCAL time → display in CT looks ~5hr
            # off (alert fired at 10:45 CT shows as 15:45 CT). User-reported
            # 2026-05-26.
            created_at=alert.created_at.isoformat() + "Z" if alert.created_at else "",
            session_date=alert.session_date or "",
            user_action=alert.user_action,
            outcome=getattr(alert, "outcome", None),
            volume_ratio=getattr(alert, "volume_ratio", None),
            vwap_slope_pct=getattr(alert, "vwap_slope_pct", None),
            grade=getattr(alert, "grade", None),
            real_outcome=getattr(alert, "real_outcome", None),
            mfe_r=getattr(alert, "mfe_r", None),
            mae_r=getattr(alert, "mae_r", None),
            cvd_delta=getattr(alert, "cvd_delta", None),
            cvd_diverging=getattr(alert, "cvd_diverging", None),
            suppressed_reason=getattr(alert, "suppressed_reason", None),
            exit_price=getattr(alert, "exit_price", None),
            r_multiple=_compute_r(alert),
        )


class SessionSummaryResponse(BaseModel):
    total_alerts: int
    buy_alerts: int
    sell_alerts: int
    target_1_hits: int
    target_2_hits: int
    stopped_out: int
    active_entries: int
