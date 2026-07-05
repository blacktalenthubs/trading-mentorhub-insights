"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All settings are read from env vars (or .env file)."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/tradecopilot"

    # JWT
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    # Long-lived tokens for mobile app — single-user trader use case where
    # frequent re-login on iOS is friction. Refresh still works inside the
    # window; the long TTL just avoids cold-start re-auth.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200  # 30 days
    REFRESH_TOKEN_EXPIRE_DAYS: int = 90

    # Redis (optional — falls back to in-memory cache if empty)
    REDIS_URL: str = ""

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3000",
        "https://aicopilottrader.com",
        "https://www.aicopilottrader.com",
        "https://tradesignalwithai.com",
        "https://www.tradesignalwithai.com",
        "https://tradingwithai.ai",
        "https://www.tradingwithai.ai",
        "https://busytradersdesk.com",
        "https://www.busytradersdesk.com",
        "https://worker-production-f56f.up.railway.app",
        "capacitor://localhost",       # iOS Capacitor
        "https://localhost",           # iOS WKWebView
    ]

    # Feature limits
    FREE_WATCHLIST_MAX: int = 5

    # In-Play Volume Screener (spec 62) — default thresholds (all adjustable)
    SCREENER_MARKET_CAP_FLOOR: float = 2_000_000_000  # $2B
    SCREENER_PRICE_FLOOR: float = 5.0
    SCREENER_DOLLAR_VOL_FLOOR: float = 20_000_000  # $20M avg daily $-volume
    SCREENER_TOP_N: int = 30
    SCREENER_REFRESH_MINUTES: int = 10

    # Square billing
    SQUARE_ACCESS_TOKEN: str = ""
    SQUARE_APP_ID: str = ""
    SQUARE_LOCATION_ID: str = ""
    SQUARE_ENVIRONMENT: str = "sandbox"  # "sandbox" or "production"
    SQUARE_WEBHOOK_SIGNATURE_KEY: str = ""
    SQUARE_PRO_PLAN_ID: str = ""       # Catalog plan_variation_id for Pro monthly
    SQUARE_PREMIUM_PLAN_ID: str = ""   # Catalog plan_variation_id for Premium monthly

    # AI
    ANTHROPIC_API_KEY: str = ""

    # Google Sign-In (OAuth) — the OAuth 2.0 Client ID from Google Cloud
    # Console. Used to verify ID tokens server-side at /auth/google. The
    # same value is exposed to the web client as VITE_GOOGLE_CLIENT_ID.
    GOOGLE_CLIENT_ID: str = ""

    # Sign in with Apple — Services ID (NOT the bundle ID) from the Apple
    # Developer console, e.g. "com.busytradersdesk.signin". Used as the
    # audience claim when verifying Apple ID tokens at /auth/apple. The
    # same value is exposed to the web client as VITE_APPLE_CLIENT_ID.
    # No private key needed for the ID-token-verify flow — Apple's public
    # JWKS at https://appleid.apple.com/auth/keys is enough.
    APPLE_CLIENT_ID: str = ""

    # App
    APP_NAME: str = "BusyTradersDesk API"
    DEBUG: bool = False

    # Canonical public web origin used to build shareable, logged-out links
    # (e.g. the Performance share link). MUST point at a host that serves the
    # SPA deep-links to anonymous visitors — NOT a legacy/apex domain that only
    # shows the marketing landing page. Kept in sync with the DomainRedirect
    # middleware's CANONICAL_DOMAIN. Override via env for other environments.
    PUBLIC_BASE_URL: str = "https://www.busytradersdesk.com"

    # TV alert lifecycle notifications (T1/T2/stop hits for took trades).
    # Disabled by default 2026-05-03 — exit-button-handler doesn't stamp
    # t1/t2/stop_notified_at, so T2 fires after a user manually exits a
    # trade (live miss: ETH ma_bounce_long entry $2309.26 pinged "T2 HIT
    # $2360.89 +3.00R" 30+ minutes after the user had already exited).
    # Re-enable by setting TV_LIFECYCLE_ALERTS_ENABLED=true once exit flow
    # stamps the lifecycle columns properly.
    TV_LIFECYCLE_ALERTS_ENABLED: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
