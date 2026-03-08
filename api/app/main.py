"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.rate_limit import limiter

logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle hook — creates tables + starts monitor."""
    settings = get_settings()

    # Auto-create tables in dev mode (SQLite or DEBUG)
    if settings.DEBUG or settings.DATABASE_URL.startswith("sqlite"):
        from app.database import Base, engine
        # Import all models so Base.metadata knows about them
        import app.models  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created/verified")

    # Background monitor (skip for SQLite — requires sync postgres driver)
    scheduler = None
    sync_engine = None
    if not settings.DATABASE_URL.startswith("sqlite"):
        from apscheduler.schedulers.background import BackgroundScheduler
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.background.monitor import poll_all_users

        sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2").replace(
            "postgresql+psycopg2", "postgresql"
        )
        sync_engine = create_engine(sync_url, pool_pre_ping=True)
        sync_session_factory = sessionmaker(bind=sync_engine)

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            poll_all_users,
            "interval",
            minutes=3,
            args=[sync_session_factory],
            id="alert_monitor",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("Background monitor started (3-min interval)")
    else:
        logger.info("SQLite mode — background monitor disabled")

    yield

    if scheduler:
        scheduler.shutdown(wait=False)
    if sync_engine:
        sync_engine.dispose()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        lifespan=lifespan,
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Health check ---
    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    # --- Router registration ---
    from app.routers import (
        auth, watchlist, scanner, market, alerts,
        trades, charts, real_trades, paper_trading, backtest,
    )
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(watchlist.router, prefix="/api/v1/watchlist", tags=["watchlist"])
    app.include_router(scanner.router, prefix="/api/v1/scanner", tags=["scanner"])
    app.include_router(market.router, prefix="/api/v1/market", tags=["market"])
    app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["alerts"])
    app.include_router(trades.router, prefix="/api/v1/trades", tags=["trades"])
    app.include_router(charts.router, prefix="/api/v1/charts", tags=["charts"])
    app.include_router(real_trades.router, prefix="/api/v1/real-trades", tags=["real-trades"])
    app.include_router(paper_trading.router, prefix="/api/v1/paper-trading", tags=["paper-trading"])
    app.include_router(backtest.router, prefix="/api/v1/backtest", tags=["backtest"])

    return app


app = create_app()
