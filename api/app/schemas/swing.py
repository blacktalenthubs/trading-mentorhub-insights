"""Swing trade schemas — spec 56 deterministic swing scanner."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SpyRegimeResponse(BaseModel):
    regime: str                            # "bounce" | "rsi"
    bounce_mode: bool                      # True when SPY >= its 21 EMA
    spy_close: Optional[float] = None
    spy_ema21: Optional[float] = None


class SwingTradeResponse(BaseModel):
    id: int
    symbol: str
    alert_type: str                        # swing_bounce_ema50 / swing_rsi_30
    setup: str                             # human label, e.g. "EMA 50 bounce"
    entry: Optional[float] = None
    stop: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    conviction: Optional[str] = None
    opened_date: str
    status: str                            # "active" | "closed"
    closed_date: Optional[str] = None
    exit_price: Optional[float] = None
    pnl_pct: Optional[float] = None


class SwingScanResponse(BaseModel):
    alerts_fired: int
