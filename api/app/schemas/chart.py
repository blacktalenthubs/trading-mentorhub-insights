"""Chart level schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ChartLevelRequest(BaseModel):
    symbol: str
    price: float
    label: str = ""
    color: str = "#3498db"


class ChartLevelUpdate(BaseModel):
    """Patch an existing level — reprice and/or retype (label + color)."""
    price: Optional[float] = None
    label: Optional[str] = None
    color: Optional[str] = None


class ChartLevelResponse(BaseModel):
    id: int
    symbol: str
    price: float
    label: str
    color: str

    model_config = {"from_attributes": True}
