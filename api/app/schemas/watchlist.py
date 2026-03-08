"""Watchlist schemas."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel


class WatchlistItemResponse(BaseModel):
    id: int
    symbol: str

    model_config = {"from_attributes": True}


class AddSymbolRequest(BaseModel):
    symbol: str


class BulkSetRequest(BaseModel):
    symbols: List[str]
