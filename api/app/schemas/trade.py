"""Trade history, import, and annotation schemas."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


# --- Trade History ---

class TradeHistoryItem(BaseModel):
    symbol: str
    trade_date: str
    proceeds: float
    cost_basis: float
    realized_pnl: float
    wash_sale_disallowed: float
    asset_type: Optional[str] = None
    category: Optional[str] = None
    holding_days: Optional[int] = None
    holding_period_type: Optional[str] = None
    account: Optional[str] = None
    source: str  # "1099" or "monthly"


class MonthlyStats(BaseModel):
    month: str
    total_trades: int
    total_pnl: float
    win_count: int
    loss_count: int
    win_rate: float


# --- Annotations ---

class AnnotationRequest(BaseModel):
    source: str
    symbol: str
    trade_date: str
    quantity: Optional[float] = None
    strategy_tag: Optional[str] = None
    notes: Optional[str] = None


class AnnotationResponse(BaseModel):
    id: int
    source: str
    symbol: str
    trade_date: str
    quantity: Optional[float]
    strategy_tag: Optional[str]
    notes: Optional[str]

    model_config = {"from_attributes": True}


# --- Import ---

class ImportParseResponse(BaseModel):
    """Preview of parsed trades before confirmation."""
    file_type: str  # "1099" or "monthly"
    period: str
    trade_count: int
    preview: List[dict]  # first 10 trades as dicts
    parse_id: str  # temp ID to confirm


class ImportConfirmRequest(BaseModel):
    parse_id: str


class ImportConfirmResponse(BaseModel):
    import_id: int
    records_imported: int


class ImportRecordResponse(BaseModel):
    id: int
    filename: str
    file_type: str
    period: str
    records_imported: int
    imported_at: str

    model_config = {"from_attributes": True}
