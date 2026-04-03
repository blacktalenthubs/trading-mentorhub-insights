"""Swing trade schemas."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class SpyRegimeResponse(BaseModel):
    regime_bullish: bool
    spy_close: Optional[float] = None
    spy_ema20: Optional[float] = None
    spy_rsi: Optional[float] = None


class SwingCategoryItem(BaseModel):
    symbol: str
    category: str
    rsi: Optional[float] = None
    session_date: str


class SwingTradeResponse(BaseModel):
    id: int
    symbol: str
    direction: str
    entry_price: float
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    current_price: Optional[float] = None
    current_rsi: Optional[float] = None
    status: str
    opened_date: str
    closed_date: Optional[str] = None
    exit_price: Optional[float] = None
    pnl: Optional[float] = None


class SwingScanResponse(BaseModel):
    alerts_fired: int
