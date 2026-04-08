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


class AnalyzeChartRequest(BaseModel):
    symbol: str
    timeframe: str  # "1m", "5m", "15m", "30m", "1H", "4H", "D", "W"
    ohlcv_bars: Optional[List[OHLCVBar]] = None


class TradePlanResponse(BaseModel):
    direction: str  # "LONG", "SHORT", "NO_TRADE"
    entry: Optional[float] = None
    stop: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    rr_ratio: Optional[float] = None
    confidence: str  # "HIGH", "MEDIUM", "LOW"
    confluence_score: int  # 0-10
    timeframe_fit: str  # "2-4 hours", "1-3 days", etc.
    key_levels: List[str] = []
    historical_ref: Optional[str] = None


class ChartAnalysisResponse(BaseModel):
    id: int
    symbol: str
    timeframe: str
    direction: Optional[str] = None
    entry: Optional[float] = None
    stop: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    rr_ratio: Optional[float] = None
    confidence: Optional[str] = None
    confluence_score: Optional[int] = None
    reasoning: Optional[str] = None
    actual_outcome: Optional[str] = None
    outcome_pnl: Optional[float] = None
    created_at: Optional[str] = None
