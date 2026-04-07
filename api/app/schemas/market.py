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


class OptionsFlowItem(BaseModel):
    symbol: str
    type: str  # "CALL" or "PUT"
    strike: float
    expiry: str
    volume: int
    open_interest: int
    volume_oi_ratio: float
    last_price: Optional[float] = None
    implied_vol: Optional[float] = None
    sentiment: str  # "BULLISH" or "BEARISH"


class SectorRotationItem(BaseModel):
    symbol: str
    name: str
    price: float
    change_1d: float
    change_5d: float
    change_20d: float
    flow: str  # "INFLOW" | "OUTFLOW" | "NEUTRAL"


class CatalystItem(BaseModel):
    symbol: str
    event: str  # "EARNINGS" | "EX_DIVIDEND" | "DIVIDEND"
    date: str  # ISO date string
    days_away: int
    timing: Optional[str] = None  # "After Close" | "Before Open" | "Unknown"


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
