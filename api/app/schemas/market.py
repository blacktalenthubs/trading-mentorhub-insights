"""Market data schemas."""

from __future__ import annotations

from typing import List, Optional

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


class GroupSymbolQuote(BaseModel):
    """Per-symbol quote inside a sector group."""

    symbol: str
    last_price: Optional[float] = None
    prior_close: Optional[float] = None
    gap_pct: Optional[float] = None
    volume: Optional[float] = None


class GroupPremarketSummary(BaseModel):
    """Aggregated premarket movement for a single watchlist group."""

    group_id: int
    name: str
    color: str
    sort_order: int
    item_count: int
    avg_gap_pct: Optional[float] = None
    breadth_green: int = 0  # how many symbols with gap_pct > 0
    breadth_total: int = 0  # how many symbols had data
    top_mover: Optional[GroupSymbolQuote] = None
    bottom_mover: Optional[GroupSymbolQuote] = None
    items: List[GroupSymbolQuote] = []


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
