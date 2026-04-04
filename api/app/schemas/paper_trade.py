"""Paper trading and real trade schemas."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel


# --- Real Trades ---

class OpenRealTradeRequest(BaseModel):
    symbol: str
    direction: str = "BUY"
    entry_price: float
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    target_2_price: Optional[float] = None
    alert_type: Optional[str] = None
    shares: Optional[int] = None
    notes: str = ""


class CloseRealTradeRequest(BaseModel):
    exit_price: float
    notes: str = ""


class RealTradeResponse(BaseModel):
    id: int
    symbol: str
    direction: str
    shares: int
    entry_price: float
    exit_price: Optional[float]
    stop_price: Optional[float]
    target_price: Optional[float]
    target_2_price: Optional[float]
    pnl: Optional[float]
    status: str
    alert_type: Optional[str]
    notes: Optional[str]
    session_date: str
    opened_at: Any = None
    closed_at: Any = None

    model_config = {"from_attributes": True}


class RealTradeStatsResponse(BaseModel):
    total_pnl: float
    total_trades: int
    win_count: int
    loss_count: int
    win_rate: float
    avg_win: float
    avg_loss: float
    expectancy: float


# --- Paper Trades ---

class PaperTradeResponse(BaseModel):
    id: int
    symbol: str
    direction: str
    shares: int
    entry_price: Optional[float]
    exit_price: Optional[float]
    stop_price: Optional[float]
    target_price: Optional[float]
    pnl: Optional[float]
    status: str
    session_date: str

    model_config = {"from_attributes": True}


# --- Backtest ---

class BacktestRequest(BaseModel):
    symbols: List[str]
    start_date: str
    end_date: str
    rules: Optional[List[str]] = None


class BacktestResult(BaseModel):
    symbol: str
    total_signals: int
    win_count: int
    loss_count: int
    win_rate: float
    total_pnl: float
    avg_rr: float
