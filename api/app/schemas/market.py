"""Market data schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class MarketStatusResponse(BaseModel):
    is_open: bool
    is_premarket: bool
    session_phase: str


class OHLCBar(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class PriorDayResponse(BaseModel):
    open: float
    high: float
    low: float
    close: float
    volume: float
    ma20: Optional[float] = None
    ma50: Optional[float] = None
    ma100: Optional[float] = None
    ma200: Optional[float] = None
    pattern: str
    direction: str
    is_inside: bool
    parent_high: float
    parent_low: float
    rsi14: Optional[float] = None
