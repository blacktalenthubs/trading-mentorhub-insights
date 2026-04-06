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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle hook — creates tables + starts monitor."""
    settings = get_settings()

    from app.database import Base, engine
    # Import all models so Base.metadata knows about them
    import app.models  # noqa: F401

    # Auto-create new tables (usage_limits etc.) and add missing columns
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migration: add trial_ends_at column if missing (idempotent)
        from sqlalchemy import text
        try:
            await conn.execute(text(
                "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMP"
            ))
            logger.info("Migration: trial_ends_at column ensured")
        except Exception as e:
            logger.warning("Migration ALTER TABLE trial_ends_at: %s", e)

        # Give existing free users a 3-day trial (one-time migration)
        try:
            result = await conn.execute(text(
                "UPDATE subscriptions SET trial_ends_at = NOW() + INTERVAL '3 days' "
                "WHERE tier = 'free' AND status = 'active' AND trial_ends_at IS NULL"
            ))
            if result.rowcount and result.rowcount > 0:
                logger.info("Migration: gave %d free users a 3-day trial", result.rowcount)
        except Exception:
            pass  # SQLite uses different syntax; fine for dev

        # Migration: add referral_code to users if missing
        try:
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_code VARCHAR(20)"
            ))
        except Exception:
            pass

        # Migration: add user_id to real_trades if missing (V1 table didn't have it)
        try:
            await conn.execute(text(
                "ALTER TABLE real_trades ADD COLUMN IF NOT EXISTS user_id INTEGER"
            ))
        except Exception:
            pass
    logger.info("Database tables created/verified")

    # Background monitor — runs for both SQLite (dev) and Postgres (prod)
    scheduler = None
    sync_engine = None
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.background.monitor import poll_all_users

        if settings.DATABASE_URL.startswith("sqlite"):
            # SQLite: use sync engine directly (strip async driver)
            sync_url = settings.DATABASE_URL.replace("+aiosqlite", "")
            sync_engine = create_engine(sync_url, pool_pre_ping=True)
        else:
            # Postgres: ensure plain postgresql:// for sync psycopg2
            sync_url = settings.DATABASE_URL
            for suffix in ("+asyncpg", "+psycopg2", "+psycopg"):
                sync_url = sync_url.replace(suffix, "")
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
        # Also run immediately on startup so we don't wait 3 min
        scheduler.add_job(
            poll_all_users,
            args=[sync_session_factory],
            id="alert_monitor_initial",
        )
        # EOD swing scan — runs once at 4:15 PM ET weekdays
        def _eod_swing_scan():
            try:
                from alerting.swing_scanner import swing_scan_eod
                swing_scan_eod()
                logger.info("EOD swing scan completed")
            except Exception:
                logger.exception("EOD swing scan failed")

        scheduler.add_job(
            _eod_swing_scan,
            "cron",
            hour=16, minute=15,
            timezone="America/New_York",
            day_of_week="mon-fri",
            id="eod_swing_scan",
            replace_existing=True,
        )

        # Pre-market brief — runs once at 9:15 AM ET weekdays
        def _premarket_brief():
            try:
                from analytics.premarket_brief import send_premarket_brief, send_ai_premarket_brief
                send_premarket_brief()
                send_ai_premarket_brief()
                logger.info("Pre-market brief sent (data + AI)")
            except Exception:
                logger.exception("Pre-market brief failed")

        scheduler.add_job(
            _premarket_brief,
            "cron",
            hour=9, minute=15,
            timezone="America/New_York",
            day_of_week="mon-fri",
            id="premarket_brief",
            replace_existing=True,
        )

        # EOD cleanup — close stale active entries at 4:30 PM ET
        def _eod_cleanup():
            try:
                from datetime import date as _date
                with sync_session_factory() as db:
                    from app.models.alert import ActiveEntry
                    today = _date.today().isoformat()
                    db.execute(
                        ActiveEntry.__table__.update()
                        .where(ActiveEntry.session_date == today, ActiveEntry.status == "active")
                        .values(status="closed")
                    )
                    db.commit()
                    logger.info("EOD cleanup: closed stale active entries")
            except Exception:
                logger.exception("EOD cleanup failed")

        scheduler.add_job(
            _eod_cleanup,
            "cron",
            hour=16, minute=30,
            timezone="America/New_York",
            day_of_week="mon-fri",
            id="eod_cleanup",
            replace_existing=True,
        )

        # Daily EOD review — 4:35 PM ET weekdays (after EOD cleanup)
        def _daily_review():
            try:
                from analytics.weekly_review import send_daily_reviews
                count = send_daily_reviews()
                logger.info("Daily EOD reviews sent: %d", count)
            except Exception:
                logger.exception("Daily EOD review failed")

        scheduler.add_job(
            _daily_review,
            "cron",
            hour=16, minute=35,
            timezone="America/New_York",
            day_of_week="mon-fri",
            id="daily_review",
            replace_existing=True,
        )

        # Weekly coaching review — Friday 5 PM ET
        def _weekly_review():
            try:
                from analytics.weekly_review import send_weekly_reviews
                count = send_weekly_reviews()
                logger.info("Weekly reviews sent: %d", count)
            except Exception:
                logger.exception("Weekly review failed")

        scheduler.add_job(
            _weekly_review,
            "cron",
            hour=17, minute=0,
            timezone="America/New_York",
            day_of_week="fri",
            id="weekly_review",
            replace_existing=True,
        )

        scheduler.start()
        logger.info("Background monitor started (3-min poll + EOD/premarket/weekly jobs)")
    except Exception:
        logger.exception("Failed to start background monitor")

    # Start Telegram bot — prefer webhook mode (no 409 conflicts),
    # fall back to polling for local dev.
    import os as _os
    _webhook_base = _os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    if _webhook_base:
        _webhook_base = f"https://{_webhook_base}"
    # Also accept explicit override
    if not _webhook_base:
        _webhook_base = _os.environ.get("WEBHOOK_BASE_URL")

    try:
        import sys
        from pathlib import Path
        _scripts = str(Path(__file__).resolve().parents[2] / "scripts")
        if _scripts not in sys.path:
            sys.path.insert(0, _scripts)

        if _webhook_base:
            # Production: use webhook — Telegram pushes updates to us
            from telegram_bot import setup_webhook, shutdown_webhook
            if await setup_webhook(_webhook_base):
                logger.info("Telegram bot started (webhook mode)")
            else:
                logger.warning("Telegram webhook setup failed")
        else:
            # Local dev: use polling (no public URL available)
            from telegram_bot import start_bot_thread
            if start_bot_thread():
                logger.info("Telegram bot started (polling mode)")
            else:
                logger.warning("Telegram bot not started (token missing or import error)")
    except Exception:
        logger.exception("Failed to start Telegram bot")

    yield

    # Shutdown
    if _webhook_base:
        try:
            from telegram_bot import shutdown_webhook
            await shutdown_webhook()
        except Exception:
            pass
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

    # Redirect old domain → new domain
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import RedirectResponse

    class DomainRedirectMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            host = request.headers.get("host", "")
            path = request.url.path
            # Only redirect non-API, non-health paths (don't break API calls)
            if "tradesignalwithai.com" in host and not path.startswith(("/api/", "/telegram/")) and path != "/healthz":
                new_url = f"https://www.tradingwithai.ai{path}"
                if request.url.query:
                    new_url += f"?{request.url.query}"
                return RedirectResponse(new_url, status_code=301)
            return await call_next(request)

    app.add_middleware(DomainRedirectMiddleware)

    # --- Health check ---
    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    # --- Router registration ---
    from app.routers import (
        auth, watchlist, scanner, market, alerts,
        trades, charts, real_trades, paper_trading, backtest,
        push, settings, swing, intel, learn, billing, admin, referral,
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
    app.include_router(push.router, prefix="/api/v1/push", tags=["push"])
    app.include_router(settings.router, prefix="/api/v1/settings", tags=["settings"])
    app.include_router(swing.router, prefix="/api/v1/swing", tags=["swing"])
    app.include_router(intel.router, prefix="/api/v1/intel", tags=["intel"])
    app.include_router(learn.router, prefix="/api/v1/learn", tags=["learn"])
    app.include_router(billing.router, prefix="/api/v1/billing", tags=["billing"])
    app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(referral.router, prefix="/api/v1/referral", tags=["referral"])

    # --- Telegram webhook route (must be before SPA catch-all) ---
    from fastapi import Request
    from fastapi.responses import JSONResponse as _JSONResponse

    try:
        import sys as _sys
        from pathlib import Path as _Path
        _scripts_path = str(_Path(__file__).resolve().parents[2] / "scripts")
        if _scripts_path not in _sys.path:
            _sys.path.insert(0, _scripts_path)
        from telegram_bot import get_webhook_path, process_webhook_update
        _tg_webhook_path = get_webhook_path()

        @app.post(_tg_webhook_path, include_in_schema=False)
        async def telegram_webhook(request: Request):
            data = await request.json()
            await process_webhook_update(data)
            return _JSONResponse({"ok": True})

        logger.info("Telegram webhook route registered: POST %s", _tg_webhook_path)
    except Exception:
        logger.warning("Could not register Telegram webhook route")

    # --- Serve React frontend (production) ---
    import os
    from pathlib import Path
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    dist_dir = Path(__file__).resolve().parents[2] / "web" / "dist"
    if dist_dir.exists():
        # Serve static assets (JS, CSS, images)
        app.mount("/assets", StaticFiles(directory=str(dist_dir / "assets")), name="static")

        # Catch-all: serve index.html for any non-API route (SPA client-side routing)
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            # Never intercept API routes — let FastAPI handle 404s
            if full_path.startswith("api/"):
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            # If it's a file that exists in dist, serve it
            file_path = dist_dir / full_path
            if file_path.is_file():
                # Assets have hashed filenames — cache forever
                headers = {"Cache-Control": "public, max-age=31536000, immutable"} if "assets/" in full_path else {}
                return FileResponse(str(file_path), headers=headers)
            # index.html — never cache (so users always get latest build)
            return FileResponse(str(dist_dir / "index.html"), headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

    return app


app = create_app()
