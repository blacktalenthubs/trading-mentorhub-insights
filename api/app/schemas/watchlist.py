"""Watchlist schemas."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class WatchlistItemResponse(BaseModel):
    id: int
    symbol: str
    group_id: Optional[int] = None

    model_config = {"from_attributes": True}


class AddSymbolRequest(BaseModel):
    symbol: str
    group_id: Optional[int] = None


class BulkSetRequest(BaseModel):
    symbols: List[str]


class MoveItemRequest(BaseModel):
    """Move a watchlist item to a different group (or ungroup with null)."""

    group_id: Optional[int] = None


class WatchlistGroupResponse(BaseModel):
    id: int
    name: str
    sort_order: int
    color: str

    model_config = {"from_attributes": True}


class CreateGroupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    sort_order: int = 0
    color: str = ""


class UpdateGroupRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    sort_order: Optional[int] = None
    color: Optional[str] = None
