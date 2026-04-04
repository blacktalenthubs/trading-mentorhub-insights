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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days for dev
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

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
        "https://worker-production-f56f.up.railway.app",
        "capacitor://localhost",       # iOS Capacitor
        "https://localhost",           # iOS WKWebView
    ]

    # Feature limits
    FREE_WATCHLIST_MAX: int = 5

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

    # App
    APP_NAME: str = "TradeCoPilot API"
    DEBUG: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
