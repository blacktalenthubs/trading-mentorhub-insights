"""Intel hub & AI coach schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class WinRateResponse(BaseModel):
    overall: Dict[str, Any] = {}
    by_symbol: Dict[str, Any] = {}
    by_type: Dict[str, Any] = {}
    by_hour: Dict[Any, Any] = {}


class FundamentalsResponse(BaseModel):
    symbol: str
    data: Dict[str, Any] = {}


class SetupAnalysisResponse(BaseModel):
    symbol: str
    timeframe: str
    analysis: Dict[str, Any] = {}


class MTFContextResponse(BaseModel):
    symbol: str
    daily: Dict[str, Any] = {}
    weekly: Dict[str, Any] = {}
    intraday: Dict[str, Any] = {}


class JournalEntry(BaseModel):
    date: str
    entries: List[Dict[str, Any]] = []


class DecisionQualityResponse(BaseModel):
    metrics: Dict[str, Any] = {}


class ScannerContextResponse(BaseModel):
    context: Dict[str, Any] = {}


class OHLCVBar(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class CoachRequest(BaseModel):
    messages: List[Dict[str, str]]
    symbols: Optional[List[str]] = None
    ohlcv_bars: Optional[List[OHLCVBar]] = None
    timeframe: Optional[str] = None


class PositionCheckRequest(BaseModel):
    pass


class ClassifyPatternRequest(BaseModel):
    pass
