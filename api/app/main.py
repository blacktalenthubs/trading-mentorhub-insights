"""FastAPI application factory."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
    import app.models.journal  # noqa: F401

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

        # Migration: add auto_analysis_enabled to users
        try:
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_analysis_enabled INTEGER DEFAULT 0"
            ))
        except Exception:
            pass

        # Migration: swing alert refresh columns
        for col_def in [
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS setup_level REAL",
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS setup_condition TEXT",
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS refreshed_entry REAL",
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS refreshed_stop REAL",
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS refreshed_at TIMESTAMP",
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS gap_invalidated INTEGER DEFAULT 0",
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS gap_pct REAL",
            "ALTER TABLE swing_trades ADD COLUMN IF NOT EXISTS setup_level REAL",
            "ALTER TABLE swing_trades ADD COLUMN IF NOT EXISTS setup_condition TEXT",
            "ALTER TABLE swing_trades ADD COLUMN IF NOT EXISTS refreshed_entry REAL",
            # Premium features: confluence, entry guidance, trade journal
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS confluence_score INTEGER DEFAULT 0",
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS confluence_label TEXT",
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS entry_guidance TEXT",
            # P3: record suppressed_reason for tagged signals (noise, stale, overhead MA)
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS suppressed_reason VARCHAR(200)",
            # Coach message history persistence
            """CREATE TABLE IF NOT EXISTS coach_messages (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                symbol VARCHAR(20),
                role VARCHAR(10) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )""",
            # Attribution columns — track signup source
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS attribution_source VARCHAR(100)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS attribution_medium VARCHAR(100)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS attribution_campaign VARCHAR(200)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS attribution_referrer VARCHAR(500)",
            # AI Alert Filters (Spec 36)
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS min_conviction VARCHAR(10) DEFAULT 'medium'",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS wait_alerts_enabled BOOLEAN DEFAULT TRUE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS alert_directions VARCHAR(100) DEFAULT 'LONG,SHORT,RESISTANCE,EXIT'",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS default_portfolio_size REAL DEFAULT 50000",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS default_risk_pct REAL DEFAULT 1.0",
            # Spec 38 — swing alerts opt-in (default ON)
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS swing_alerts_enabled BOOLEAN DEFAULT TRUE",
            # Per-alert-type channel routing (JSON blob) — NULL = legacy telegram-only behavior
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS notification_routing VARCHAR(500)",
            # Per-symbol Telegram override for AI Updates (default SPY)
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_update_symbols VARCHAR(500) DEFAULT 'SPY'",
            # Table to track one-shot data migrations so they don't re-run
            """CREATE TABLE IF NOT EXISTS migration_flags (
                flag_name VARCHAR(200) PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT NOW()
            )""",
            # Spec 35 — bump auto-trade setup_type column (AI returns long descriptions)
            "ALTER TABLE ai_auto_trades ALTER COLUMN setup_type TYPE VARCHAR(500)",
        ]:
            try:
                await conn.execute(text(col_def))
            except Exception as _e:
                logger.warning("Migration step skipped: %s — %s", col_def[:80], _e)

        # Fix: auto_analysis_enabled may exist as INTEGER on prod from older schema.
        # Must drop default first, then alter type, then set new default.
        # Run separately with explicit logging so we know if it succeeded.
        try:
            # Check current type
            _type_check = await conn.execute(text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'users' AND column_name = 'auto_analysis_enabled'"
            ))
            _row = _type_check.fetchone()
            _current_type = _row[0] if _row else None
            logger.info("Migration: auto_analysis_enabled current type=%s", _current_type)
            if _current_type and _current_type.lower() in ("integer", "smallint", "bigint"):
                logger.info("Migration: converting auto_analysis_enabled INTEGER → BOOLEAN")
                await conn.execute(text(
                    "ALTER TABLE users ALTER COLUMN auto_analysis_enabled DROP DEFAULT"
                ))
                await conn.execute(text(
                    "ALTER TABLE users ALTER COLUMN auto_analysis_enabled TYPE BOOLEAN "
                    "USING (CASE WHEN auto_analysis_enabled = 0 THEN FALSE ELSE TRUE END)"
                ))
                await conn.execute(text(
                    "ALTER TABLE users ALTER COLUMN auto_analysis_enabled SET DEFAULT FALSE"
                ))
                logger.info("Migration: auto_analysis_enabled converted to BOOLEAN successfully")
        except Exception as _e:
            logger.error("Migration FAILED for auto_analysis_enabled type fix: %s", _e, exc_info=True)

        # Migration: sync V1 telegram_chat_id to V2 users table
        # Users who linked Telegram before the V2 sync fix have chat_id in
        # user_notification_prefs but not in users.telegram_chat_id
        try:
            result = await conn.execute(text(
                "UPDATE users SET telegram_chat_id = n.telegram_chat_id "
                "FROM user_notification_prefs n "
                "WHERE users.id = n.user_id "
                "AND n.telegram_chat_id IS NOT NULL "
                "AND n.telegram_chat_id != '' "
                "AND (users.telegram_chat_id IS NULL OR users.telegram_chat_id = '')"
            ))
            if result.rowcount and result.rowcount > 0:
                logger.info("Migration: synced %d telegram_chat_ids from V1 to V2", result.rowcount)
        except Exception:
            pass  # V1 table may not exist in fresh installs

        # One-shot backfill (Spec 36): the first rollout defaulted
        # wait_alerts_enabled=FALSE for everyone. That silently muted existing
        # users' AI Updates. Flip to TRUE — one time only — so existing users
        # aren't surprised. New users keep the TRUE default; anyone who has
        # explicitly set it (after this flag runs) won't be disturbed.
        try:
            flag = await conn.execute(text(
                "SELECT 1 FROM migration_flags WHERE flag_name = 'spec36_wait_default_true'"
            ))
            if not flag.fetchone():
                upd = await conn.execute(text(
                    "UPDATE users SET wait_alerts_enabled = TRUE WHERE wait_alerts_enabled = FALSE"
                ))
                await conn.execute(text(
                    "INSERT INTO migration_flags (flag_name) VALUES ('spec36_wait_default_true') "
                    "ON CONFLICT (flag_name) DO NOTHING"
                ))
                if upd.rowcount:
                    logger.info("Migration: flipped wait_alerts_enabled=TRUE for %d users", upd.rowcount)
        except Exception:
            logger.debug("Spec 36 backfill skipped", exc_info=True)

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

        # Feature flag: RULE_ENGINE_ENABLED (default True). Set to "false"/"0" on Railway
        # to disable rule-based alerting and run AI-scan-only. No redeploy needed.
        import os as _os
        _rule_env = _os.environ.get("RULE_ENGINE_ENABLED", "true").strip().lower()
        RULE_ENGINE_ENABLED = _rule_env not in ("false", "0", "no", "off")

        if RULE_ENGINE_ENABLED:
            logger.info("Rule engine ENABLED — rule-based alerts will fire alongside AI scan")
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
        else:
            logger.warning(
                "Rule engine DISABLED (RULE_ENGINE_ENABLED=false). "
                "AI scan is the only source of alerts."
            )
        # SWING DISABLED — focus on day trade entries first.

        # AI Day Trade Scanner (Spec 27) — specialized entry detection
        # Also runs exit management scan (Spec 34 Phase 3) for open positions
        # Split cadence: SPY on SPY_FAST_SCAN_MIN (default 5), others on
        # AI_DAY_SCAN_MIN (default 15). Set SPY_FAST_SCAN_MIN=0 to disable
        # the fast SPY pass and scan SPY with everything else.
        _fast_scan_min = int(os.environ.get("SPY_FAST_SCAN_MIN", "5"))
        _day_scan_min = int(os.environ.get("AI_DAY_SCAN_MIN", "15"))
        _fast_scan_enabled = _fast_scan_min > 0

        # Master switch for all AI-powered scheduled scans (day, swing, auto-trade).
        # Set AI_SCAN_ENABLED=false to run rule-based alerts only (zero Anthropic cost).
        # On-demand AI endpoints (best setups, position advisor, etc.) still work.
        _ai_scan_env = os.environ.get("AI_SCAN_ENABLED", "true").strip().lower()
        _ai_scan_enabled = _ai_scan_env not in ("false", "0", "no", "off")

        if _ai_scan_enabled:
            def _resolve_priority_symbols() -> set[str]:
                """Union of all users' telegram_update_symbols — these get the fast cadence."""
                try:
                    with sync_session_factory() as sess:
                        from app.models.user import User as _U
                        rows = sess.query(_U.telegram_update_symbols).filter(
                            _U.telegram_update_symbols.isnot(None),
                            _U.telegram_update_symbols != "",
                        ).all()
                        syms: set[str] = set()
                        for (raw,) in rows:
                            for s in (raw or "").split(","):
                                s = s.strip().upper()
                                if s:
                                    syms.add(s)
                        return syms or {"SPY"}
                except Exception:
                    logger.debug("Failed to resolve priority symbols, defaulting to SPY", exc_info=True)
                    return {"SPY"}

            def _ai_day_scan():
                try:
                    from analytics.ai_day_scanner import day_scan_cycle, exit_scan_cycle
                    _exclude = _resolve_priority_symbols() if _fast_scan_enabled else None
                    entries = day_scan_cycle(sync_session_factory, exclude_symbols=_exclude)
                    exits = exit_scan_cycle(sync_session_factory)
                    logger.info("AI scan cycle: %d entries, %d exit signals", entries, exits)
                except Exception:
                    logger.exception("AI day scan cycle failed")

            def _ai_priority_fast_scan():
                try:
                    from analytics.ai_day_scanner import day_scan_cycle
                    _syms = _resolve_priority_symbols()
                    entries = day_scan_cycle(sync_session_factory, symbols_filter=_syms)
                    logger.info("AI priority fast scan (%s): %d entries", ",".join(sorted(_syms)), entries)
                except Exception:
                    logger.exception("AI priority fast scan failed")

            # Spec 35 Phase 2 — AI Auto-Pilot paper trade monitor (1 min cadence)
            def _auto_trade_monitor():
                try:
                    from analytics.ai_day_scanner import auto_trade_monitor_cycle
                    closed = auto_trade_monitor_cycle(sync_session_factory)
                    if closed:
                        logger.info("Auto-pilot monitor: closed %d trades", closed)
                except Exception:
                    logger.exception("Auto-trade monitor cycle failed")

            scheduler.add_job(
                _auto_trade_monitor,
                "interval",
                minutes=1,
                id="auto_trade_monitor",
                replace_existing=True,
            )

            # EOD cleanup at 4:05 PM ET (20:05 UTC during EST, 21:05 UTC during EDT)
            def _auto_trade_eod():
                try:
                    from analytics.ai_day_scanner import auto_trade_eod_cleanup
                    closed = auto_trade_eod_cleanup(sync_session_factory)
                    if closed:
                        logger.info("Auto-pilot EOD: closed %d equity trades", closed)
                except Exception:
                    logger.exception("Auto-trade EOD cleanup failed")

            scheduler.add_job(
                _auto_trade_eod,
                "cron",
                hour=20, minute=5,  # 4:05 PM ET (EDT — runs 1hr earlier on EST, fine for our use)
                id="auto_trade_eod",
                replace_existing=True,
            )

            scheduler.add_job(
                _ai_day_scan,
                "interval",
                minutes=_day_scan_min,
                id="ai_day_scan",
                replace_existing=True,
            )
            scheduler.add_job(
                _ai_day_scan,
                id="ai_day_scan_initial",
            )

            if _fast_scan_enabled:
                scheduler.add_job(
                    _ai_priority_fast_scan,
                    "interval",
                    minutes=_fast_scan_min,
                    id="ai_priority_fast_scan",
                    replace_existing=True,
                )
                scheduler.add_job(
                    _ai_priority_fast_scan,
                    id="ai_priority_fast_scan_initial",
                )
                logger.info(
                    "AI day scan split: priority symbols every %d min, others every %d min",
                    _fast_scan_min, _day_scan_min,
                )
            else:
                logger.info(
                    "AI day scan: all symbols every %d min (SPY_FAST_SCAN_MIN=0)",
                    _day_scan_min,
                )

            # AI Swing Scanner (Spec 38) — runs on 15-min interval during market hours.
            # Fires only when price is actually AT a daily/weekly level right now,
            # not at arbitrary pre-market/EOD cron times. Daily levels don't move
            # fast enough to warrant tighter cadence.
            def _ai_swing_scan():
                try:
                    from analytics.ai_swing_scanner import swing_scan_cycle
                    fired = swing_scan_cycle(sync_session_factory)
                    logger.info("Swing scan: %d deliveries", fired)
                except Exception:
                    logger.exception("Swing scan failed")

            scheduler.add_job(
                _ai_swing_scan,
                "interval",
                minutes=15,
                id="ai_swing_scan",
                replace_existing=True,
            )
        else:
            logger.info(
                "AI scans DISABLED (AI_SCAN_ENABLED=false) — rule-based alerts only"
            )

        # Cost control (2026-04-16): game_plan, premarket_brief, daily_review
        # are AI-backed scheduled jobs that burn Anthropic tokens daily without
        # clear value in current usage. Gated behind AI_SCHEDULED_JOBS_ENABLED
        # (default "false"). Set to "true" to restore.
        _ai_jobs_on = os.environ.get("AI_SCHEDULED_JOBS_ENABLED", "false").lower() == "true"

        if _ai_jobs_on:
            # Alert Sniper: Game Plan — 9:05 AM ET weekdays
            def _game_plan():
                try:
                    from analytics.game_plan import send_game_plans
                    count = send_game_plans(sync_session_factory)
                    logger.info("Game plans sent: %d users", count)
                except Exception:
                    logger.exception("Game plan generation failed")

            scheduler.add_job(
                _game_plan,
                "cron",
                hour=9, minute=5,
                timezone="America/New_York",
                day_of_week="mon-fri",
                id="game_plan",
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
        else:
            logger.info(
                "Scheduled AI jobs disabled (AI_SCHEDULED_JOBS_ENABLED=false): "
                "game_plan, premarket_brief, daily_review"
            )

        # =============================================================
        # Candle close heads-ups (NOT gated by AI/rule flags — these are
        # plain Telegram pings to remind the trader to review charts at
        # candle boundaries, useful even when V1 polling is disabled).
        #
        # Originally added in monitor.py but Railway only deploys
        # api/app/main.py via Procfile, so they were dead code there.
        # =============================================================
        try:
            import sys as _sys
            from pathlib import Path as _Path
            _root = str(_Path(__file__).resolve().parents[2])
            if _root not in _sys.path:
                _sys.path.insert(0, _root)

            from alert_config import (
                CANDLE_65_NOTIFICATIONS_ENABLED,
                ETH_CANDLE_NOTIFICATIONS_ENABLED,
            )
            from alerting.notifier import _send_telegram
            from analytics.market_hours import is_market_hours
            from apscheduler.triggers.cron import CronTrigger
            import pytz as _pytz

            # 65-min RTH candle closes: 6 per session
            _CANDLE_65_CLOSES = [
                (1, 10, 35),
                (2, 11, 40),
                (3, 12, 45),
                (4, 13, 50),
                (5, 14, 55),
                (6, 16, 0),
            ]

            def _notify_candle_close(idx: int, hour: int, minute: int) -> None:
                if not is_market_hours():
                    return
                _send_telegram(
                    f"<b>65-min candle {idx}/6 closed</b>\n"
                    f"Time: {hour:02d}:{minute:02d} ET\n"
                    f"Check your charts."
                )

            if CANDLE_65_NOTIFICATIONS_ENABLED:
                _et_tz = _pytz.timezone("America/New_York")
                for idx, hour, minute in _CANDLE_65_CLOSES:
                    scheduler.add_job(
                        _notify_candle_close,
                        CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone=_et_tz),
                        args=[idx, hour, minute],
                        id=f"candle_65_close_{idx}",
                        misfire_grace_time=30,
                        replace_existing=True,
                    )
                logger.info("Registered 6 cron jobs for 65-min candle close notifications")

            # ETH 4h candle closes (UTC): 6/day at 00, 04, 08, 12, 16, 20
            _ETH_4H_CANDLE_HOURS_UTC = [0, 4, 8, 12, 16, 20]

            def _notify_eth_candle_close(idx: int, hour_utc: int) -> None:
                _send_telegram(
                    f"<b>ETH 4h candle {idx}/6 closed</b>\n"
                    f"Time: {hour_utc:02d}:00 UTC\n"
                    f"Check the chart."
                )

            if ETH_CANDLE_NOTIFICATIONS_ENABLED:
                _utc_tz = _pytz.timezone("UTC")
                for idx, hour_utc in enumerate(_ETH_4H_CANDLE_HOURS_UTC, start=1):
                    scheduler.add_job(
                        _notify_eth_candle_close,
                        CronTrigger(hour=hour_utc, minute=0, timezone=_utc_tz),
                        args=[idx, hour_utc],
                        id=f"eth_4h_candle_close_{idx}",
                        misfire_grace_time=30,
                        replace_existing=True,
                    )
                logger.info("Registered 6 cron jobs for ETH 4h candle close notifications")
        except Exception:
            logger.exception("Failed to register candle-close notification jobs")

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
        # Gated behind AI_SCHEDULED_JOBS_ENABLED (default false) — AI call.
        if _ai_jobs_on:
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

        # Trade Replay + Auto-Journal — 4:40 PM ET weekdays. Calls Anthropic
        # for journal narrative — gated behind AI_SCAN_ENABLED so the TV-only
        # shutdown path doesn't keep burning tokens here.
        if _ai_scan_enabled:
            def _trade_replay():
                try:
                    from analytics.trade_replay import generate_replays
                    count = generate_replays(sync_session_factory)
                    logger.info("Trade replay: %d journal entries created", count)
                except Exception:
                    logger.exception("Trade replay failed")

            scheduler.add_job(
                _trade_replay,
                "cron",
                hour=16, minute=40,
                timezone="America/New_York",
                day_of_week="mon-fri",
                id="trade_replay",
                replace_existing=True,
            )

            # Weekly coaching review — Friday 5 PM ET. Anthropic-backed.
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

    # Start Telegram bot — webhook on Railway, polling for local dev
    import os as _os
    import sys
    from pathlib import Path
    _scripts = str(Path(__file__).resolve().parents[2] / "scripts")
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)

    _use_webhook = bool(_os.environ.get("DATABASE_URL"))  # Railway has DATABASE_URL
    logger.info("Telegram bot: mode=%s", "webhook" if _use_webhook else "polling")

    if _use_webhook:
        # Production: webhook mode — no 409 conflicts
        # Use Railway's direct domain — custom domains' CDN blocks Telegram POSTs
        _webhook_base = "https://worker-production-f56f.up.railway.app"
        logger.info("Telegram bot: webhook_base=%s", _webhook_base)
        try:
            from telegram_bot import setup_webhook
            if await setup_webhook(_webhook_base):
                logger.info("Telegram bot started (webhook mode)")
            else:
                logger.warning("Telegram webhook setup failed")
        except Exception:
            logger.exception("Telegram webhook setup exception")
    else:
        # Local dev: polling (no public URL)
        try:
            from telegram_bot import start_bot_thread
            if start_bot_thread():
                logger.info("Telegram bot started (polling mode)")
            else:
                logger.warning("Telegram bot not started (token missing)")
        except Exception:
            logger.exception("Telegram polling setup exception")

    yield

    # Shutdown — do NOT delete webhook (new instance already registered it)
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
        performance, coach_history, auto_trades, ai_coach, diagnostics,
        tv_webhook,  # Phase 5a — TradingView alert ingest
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
    app.include_router(performance.router, prefix="/api/v1/performance", tags=["performance"])
    app.include_router(coach_history.router, prefix="/api/v1", tags=["coach"])
    app.include_router(auto_trades.router, prefix="/api/v1/auto-trades", tags=["auto-trades"])
    app.include_router(ai_coach.router, prefix="/api/v1/ai", tags=["ai-coach"])
    app.include_router(diagnostics.router, prefix="/api/v1/diagnostics", tags=["diagnostics"])
    # Phase 5a — TradingView webhook ingest at /tv/webhook (no /api/v1 prefix
    # so the URL traders paste into Pine Script is short and stable).
    app.include_router(tv_webhook.router, prefix="/tv", tags=["tradingview"])

    # --- Telegram webhook route (must be before SPA catch-all) ---
    import sys as _sys
    from pathlib import Path as _Path
    _scripts_dir = str(_Path(__file__).resolve().parents[2] / "scripts")
    if _scripts_dir not in _sys.path:
        _sys.path.insert(0, _scripts_dir)
    try:
        from telegram_bot import get_webhook_path, process_webhook_update
        _tg_path = get_webhook_path()

        @app.post(_tg_path, include_in_schema=False)
        async def telegram_webhook(request: Request):
            data = await request.json()
            await process_webhook_update(data)
            return JSONResponse({"ok": True})

        logger.info("Telegram webhook route: POST %s", _tg_path)
    except Exception:
        logger.exception("Could not register Telegram webhook route")

    # --- Serve React frontend (production) ---
    import os
    from pathlib import Path
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    dist_dir = Path(__file__).resolve().parents[2] / "web" / "dist"
    if dist_dir.exists():
        # Serve static assets (JS, CSS, images)
        app.mount("/assets", StaticFiles(directory=str(dist_dir / "assets")), name="static")

        from fastapi.responses import RedirectResponse, JSONResponse

        # Short-link redirects for social sharing — expand to full UTM URL.
        # Usage: share tradingwithai.ai/tw (clean) → 302 redirect to /?utm_source=twitter&utm_medium=bio
        SHORT_LINKS = {
            # Platform bios
            "tw":  "utm_source=twitter&utm_medium=bio",
            "tt":  "utm_source=tiktok&utm_medium=bio",
            "ig":  "utm_source=instagram&utm_medium=bio",
            "yt":  "utm_source=youtube&utm_medium=bio",
            "li":  "utm_source=linkedin&utm_medium=bio",
            # Personal sharing
            "dm":  "utm_source=friend&utm_medium=dm",
            "fr":  "utm_source=friend&utm_medium=share",
            # Campaigns — add more as needed
            "launch": "utm_source=direct&utm_medium=campaign&utm_campaign=launch",
        }

        # Catch-all: serve index.html for any non-API route (SPA client-side routing).
        # Also handles short-link redirects inline to avoid route conflicts.
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            # Never intercept API routes — let FastAPI handle 404s
            if full_path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            # Short-link redirect (only matches if path is a single segment with no file extension)
            if full_path in SHORT_LINKS:
                return RedirectResponse(url=f"/?{SHORT_LINKS[full_path]}", status_code=302)
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
