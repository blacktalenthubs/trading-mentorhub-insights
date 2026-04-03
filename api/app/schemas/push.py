"""Push notification schemas."""

from __future__ import annotations

from pydantic import BaseModel


class RegisterTokenRequest(BaseModel):
    token: str
    platform: str  # "ios" or "android"


class RegisterTokenResponse(BaseModel):
    id: int
    platform: str

    model_config = {"from_attributes": True}
