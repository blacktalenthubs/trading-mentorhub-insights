"""Auth request/response schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: Optional[str] = None
    # Attribution — captured from UTM / referrer on landing page
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    referrer: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    """One-shot request from the frontend after Google returns an ID token.

    `credential` is the JWT issued by Google Identity Services; we verify it
    server-side against Google's public keys before trusting any fields.
    Attribution is forwarded for new-account creation only (ignored on
    existing accounts so we don't overwrite the original signup source).
    """
    credential: str
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    referrer: Optional[str] = None


class AppleAuthRequest(BaseModel):
    """Request from the frontend after Apple returns an ID token.

    `id_token` is the JWT signed by Apple; we verify it against Apple's
    public keys at https://appleid.apple.com/auth/keys. `user_payload`
    carries the name fields that Apple only sends on the FIRST sign-in
    (subsequent sign-ins return only sub + email).
    """
    id_token: str
    user_first_name: Optional[str] = None
    user_last_name: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    referrer: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: str
    display_name: Optional[str]
    tier: str
    trial_active: bool = False
    trial_days_left: int = 0
    # Effective per-tier feature limits — the single source of truth the client
    # reads instead of hardcoding its own copy (kills frontend/backend drift).
    limits: dict = {}

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    # Refresh token returned in body too — needed for Capacitor mobile
    # where cookies don't survive across cross-origin WebView restarts.
    refresh_token: Optional[str] = None


class TokenRefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
