"""Chart level schemas."""

from __future__ import annotations

from pydantic import BaseModel


class ChartLevelRequest(BaseModel):
    symbol: str
    price: float
    label: str = ""
    color: str = "#3498db"


class ChartLevelResponse(BaseModel):
    id: int
    symbol: str
    price: float
    label: str
    color: str

    model_config = {"from_attributes": True}
