"""In-Play Volume Screener schemas (spec 62) — mirrors contracts/openapi.yaml."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SetupOut(BaseModel):
    pattern: str = ""
    entry: Optional[float] = None
    stop: Optional[float] = None
    target: Optional[float] = None
    conviction: str = ""
    score: int = 0
    bias: str = ""


class RefineOut(BaseModel):
    above_ema50: Optional[bool] = None
    above_vwap: Optional[bool] = None
    rsi: Optional[float] = None
    rs_vs_spy: Optional[float] = None
    atr_pct: Optional[float] = None
    near_20d_high: Optional[bool] = None


class EntryOut(BaseModel):
    rank: int
    symbol: str
    last_price: float
    pct_change: float
    rvol: float
    dollar_vol: float
    market_cap: float
    sector: Optional[str] = None
    direction: str = "neutral"
    setup: Optional[SetupOut] = None
    refine: RefineOut = Field(default_factory=RefineOut)


class SnapshotOut(BaseModel):
    captured_at: Optional[datetime] = None
    market_open: bool = False
    stale: bool = False
    top_n: int = 30
    entries: list[EntryOut] = Field(default_factory=list)


class SettingsOut(BaseModel):
    market_cap_floor: float
    price_floor: float
    dollar_vol_floor: float
    top_n: int
    refresh_minutes: int
    universe_rebuilt_at: Optional[datetime] = None


class SettingsUpdate(BaseModel):
    market_cap_floor: Optional[float] = Field(default=None, ge=50_000_000, le=1_000_000_000_000)
    top_n: Optional[int] = Field(default=None, ge=10, le=100)
