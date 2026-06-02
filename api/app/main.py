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
    import app.models.screener  # noqa: F401  # spec 62 — screener_universe + screener_snapshot

    # Auto-create new tables (usage_limits etc.) and add missing columns
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Seed the alert-type enablement catalogue (idempotent — never
        # overwrites existing rows, so user toggles persist).
        try:
            from app.models.alert_type_config import seed_alert_type_config
            await seed_alert_type_config(conn)
            logger.info("Alert type config seeded/verified")
        except Exception as e:
            logger.warning("Alert type config seed skipped: %s", e)

        # Spec 58 (2026-05-23) — retirement is now handled by
        # OBSOLETE_ALERT_TYPES in alert_type_config.py, which DELETES
        # retired rows during seed_alert_type_config() above. The earlier
        # soft-disable migration here had a tv_ prefix bug AND was
        # superseded by the cleaner DELETE approach. Block removed.
        # Migration: add trial_ends_at column if missing (idempotent)
        from sqlalchemy import text
        try:
            await conn.execute(text(
                "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMP"
            ))
            logger.info("Migration: trial_ends_at column ensured")
        except Exception as e:
            logger.warning("Migration ALTER TABLE trial_ends_at: %s", e)

        # Migration (May 2026): add watchlist.group_id FK for sector groups.
        # create_all() doesn't ALTER existing tables, so this is needed for
        # databases that pre-date the watchlist_group feature.
        try:
            await conn.execute(text(
                "ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS group_id INTEGER "
                "REFERENCES watchlist_group(id) ON DELETE SET NULL"
            ))
            logger.info("Migration: watchlist.group_id column ensured")
        except Exception as e:
            logger.warning("Migration ALTER TABLE watchlist.group_id: %s", e)

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

        # Migration: chart_levels columns — a prod table predating user_id (and
        # label/color/created_at) 500s every /charts/levels query (create_all
        # never ALTERs existing tables). user_id was the actual missing column.
        for col_def in [
            "ALTER TABLE chart_levels ADD COLUMN IF NOT EXISTS user_id INTEGER",
            "ALTER TABLE chart_levels ADD COLUMN IF NOT EXISTS label VARCHAR(100) DEFAULT ''",
            "ALTER TABLE chart_levels ADD COLUMN IF NOT EXISTS color VARCHAR(20) DEFAULT '#3498db'",
            "ALTER TABLE chart_levels ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()",
            "CREATE INDEX IF NOT EXISTS ix_chart_levels_user_id ON chart_levels(user_id)",
        ]:
            try:
                await conn.execute(text(col_def))
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
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS outcome VARCHAR(20)",
            # User-supplied exit price → real R-multiple per Took alert (Trades page)
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS exit_price REAL",
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS entry_guidance TEXT",
            # P3: record suppressed_reason for tagged signals (noise, stale, overhead MA)
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS suppressed_reason VARCHAR(200)",
            # TV alert lifecycle notifications: stamped when T1/T2/stop hit and Telegram fired
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS t1_notified_at TIMESTAMP",
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS t2_notified_at TIMESTAMP",
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS stop_notified_at TIMESTAMP",
            # TV v2 Pine: order-flow payload fields. Numeric values stored so
            # the alert tuner can correlate exact thresholds to outcomes.
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS volume_ratio REAL",
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS cvd_delta REAL",
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS cvd_diverging INTEGER DEFAULT 0",
            # Spec 58 (2026-05-24) — surface day-type stage + VWAP slope on the
            # Telegram message. Stored numerically so the EOD analytics can
            # correlate stage/slope thresholds with outcomes.
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS stage TEXT",
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS vwap_slope_pct REAL",
            # Inside-day flag (today_open between PDH and PDL) — surfaces on
            # Telegram so the trader knows the day is structurally range-bound,
            # which means scalp levels rather than chase breakouts.
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS inside_day INTEGER DEFAULT 0",
            # Setup grade — A/B/C from vol+slope. Spec 61 follow-up. Default 'C'
            # for legacy rows; the startup backfill below recomputes from existing
            # vol_ratio + vwap_slope_pct so historical fires aren't all stuck at C.
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS grade VARCHAR(1) DEFAULT 'C'",
            # User-level minimum grade filter (A/B/C). 'C' = no filter.
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS min_alert_grade VARCHAR(1) DEFAULT 'C'",
            # Real outcome backfill columns — Feature 2. Computed nightly from
            # post-fire Alpaca intraday bars; NOT the synthetic fixed-% T1/T2.
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS real_outcome VARCHAR(20)",
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS mfe_r REAL",
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS mae_r REAL",
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS outcome_computed_at TIMESTAMP",
            # Spec 62 — screener snapshot kind (in_play | swing)
            "ALTER TABLE screener_snapshot ADD COLUMN IF NOT EXISTS kind VARCHAR(16) DEFAULT 'in_play'",
            # iOS APNs push notifications (Capacitor mobile app) — 2026-05-26
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS apns_token VARCHAR(200)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS apns_enabled BOOLEAN DEFAULT FALSE",
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
            # OAuth (Google / Apple) — nullable so password-only accounts still validate
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_provider VARCHAR(16)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS oauth_sub VARCHAR(255)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(500)",
            "ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL",
            "CREATE INDEX IF NOT EXISTS ix_users_oauth_sub ON users (oauth_sub)",
            # Activation tracking — bumped on /auth/me (called by React Query
            # on every page load), so DAU/WAU and the day-30 active-user
            # target are queryable in plain SQL.
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP",
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

        # Backfill alerts.grade for historical rows. Pure compute from
        # existing volume_ratio + vwap_slope_pct so the new column is
        # populated correctly on first deploy and queries can rely on it.
        # Idempotent — re-running gives identical results.
        try:
            await conn.execute(text("""
                UPDATE alerts SET grade = CASE
                    WHEN COALESCE(volume_ratio, 0) >= 2.0
                         AND COALESCE(vwap_slope_pct, 0) >= 0.05 THEN 'A'
                    WHEN COALESCE(volume_ratio, 0) >= 2.0
                         OR  COALESCE(vwap_slope_pct, 0) >= 0.05 THEN 'B'
                    ELSE 'C'
                END
            """))
            logger.info("Migration: alerts.grade backfilled from vol+slope")
        except Exception as e:
            logger.warning("Migration grade backfill skipped: %s", e)

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
        # Expose to routers (e.g. the manual /swing/scan trigger).
        app.state.sync_session_factory = sync_session_factory

        scheduler = BackgroundScheduler()
        # Start the scheduler + capture the main loop IMMEDIATELY, before any job
        # registration. The whole block below is one big try/except, so a single
        # unguarded throw used to skip scheduler.start() entirely → NO scheduled
        # jobs fired (in-play interval, swing cron, social cron all dead, while
        # manual background-task endpoints kept working). BackgroundScheduler
        # accepts add_job() after start(), so starting first is safe and makes
        # job registration failures non-fatal to the scheduler.
        try:
            import asyncio as _asyncio_early
            from app.services.screener_service import set_main_loop as _set_main_loop_early
            _set_main_loop_early(_asyncio_early.get_running_loop())
        except Exception:
            logger.exception("Failed to capture main loop for scheduler")
        scheduler.start()
        logger.info("Scheduler started (jobs register below; failures are non-fatal)")

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

            # Swing Scanner (spec 56) — deterministic, runs on a 15-min interval
            # during market hours. Not an AI/LLM scan; pure math on daily bars.
            def _swing_scan():
                try:
                    from analytics.swing_scanner import swing_scan_cycle
                    fired = swing_scan_cycle(sync_session_factory)
                    logger.info("Swing scan: %d deliveries", fired)
                except Exception:
                    logger.exception("Swing scan failed")

            scheduler.add_job(
                _swing_scan,
                "interval",
                minutes=15,
                id="swing_scan",
                replace_existing=True,
            )

            # Daily EOD swing scan — 4:10 PM ET Mon-Fri, after the daily bar
            # has closed so the qualifier sees a finalized close. force=True
            # bypasses the in-cycle market-hours gate. Pairs with the 15-min
            # intraday scan: intraday catches setups as they form, EOD gives
            # the final-close confirmation pass for the next-day game plan.
            # Set SWING_SCAN_SCHEDULED=0 in Railway to disable.
            if os.environ.get("SWING_SCAN_SCHEDULED", "true").lower() not in ("0", "false", "no"):
                from apscheduler.triggers.cron import CronTrigger
                import pytz as _pytz
                et_tz = _pytz.timezone("America/New_York")

                def _swing_scan_eod():
                    try:
                        from analytics.swing_scanner import swing_scan_cycle
                        fired = swing_scan_cycle(sync_session_factory, force=True)
                        logger.info("Swing EOD scan: %d deliveries", fired)
                    except Exception:
                        logger.exception("Swing EOD scan failed")

                scheduler.add_job(
                    _swing_scan_eod,
                    CronTrigger(day_of_week="mon-fri", hour=16, minute=10, timezone=et_tz),
                    id="swing_scan_eod",
                    misfire_grace_time=300,
                    replace_existing=True,
                )
                logger.info("Registered daily swing scan cron: 16:10 ET, Mon-Fri")

            # Real-outcome backfill (spec 61 follow-up Feature 2) — runs at
            # 4:30 PM ET Mon-Fri after the session closes. Walks every long
            # alert from today's session, pulls 5m bars from Alpaca, computes
            # MFE / MAE in R-multiples + worked/failed/inconclusive label.
            # Powers the AI Friday retro + truthful Performance numbers.
            # Set REAL_OUTCOMES_ENABLED=0 in Railway to disable.
            if os.environ.get("REAL_OUTCOMES_ENABLED", "true").lower() not in ("0", "false", "no"):
                from apscheduler.triggers.cron import CronTrigger as _CT_OUT
                import pytz as _pytz_out
                _et_out = _pytz_out.timezone("America/New_York")

                def _real_outcomes_eod():
                    try:
                        from analytics.alert_outcomes import compute_outcomes_for_session
                        from datetime import date as _date
                        summary = compute_outcomes_for_session(sync_session_factory, _date.today())
                        logger.info("Real outcomes EOD: %s", summary)
                    except Exception:
                        logger.exception("Real outcomes EOD failed")

                scheduler.add_job(
                    _real_outcomes_eod,
                    _CT_OUT(day_of_week="mon-fri", hour=16, minute=30, timezone=_et_out),
                    id="real_outcomes_eod",
                    misfire_grace_time=600,
                    replace_existing=True,
                )
                logger.info("Registered real-outcomes cron: 16:30 ET, Mon-Fri")

            # AI Friday Retrospective (Feature 5 of the spec 61 follow-up).
            # Reads the week's alerts + real outcomes (Feature 2 must have run
            # by now — the outcomes cron is 16:30, this is 17:00, so today's
            # alerts are graded). Sends one personalized Telegram lessons
            # message per user per Friday. Idempotent on (user, today, retro).
            # Set WEEKLY_RETRO_ENABLED=0 in Railway to disable.
            if os.environ.get("WEEKLY_RETRO_ENABLED", "true").lower() not in ("0", "false", "no"):
                from apscheduler.triggers.cron import CronTrigger as _CT_RETRO
                import pytz as _pytz_retro
                _et_retro = _pytz_retro.timezone("America/New_York")

                def _weekly_retro():
                    try:
                        from analytics.ai_weekly_retro import send_weekly_retros
                        summary = send_weekly_retros(sync_session_factory)
                        logger.info("Weekly retro summary: %s", summary)
                    except Exception:
                        logger.exception("Weekly retro failed")

                scheduler.add_job(
                    _weekly_retro,
                    _CT_RETRO(day_of_week="fri", hour=17, minute=0, timezone=_et_retro),
                    id="weekly_retro",
                    misfire_grace_time=3600,
                    replace_existing=True,
                )
                logger.info("Registered AI Friday retrospective cron: 17:00 ET Fri")

            # Earnings refresh (spec 61) — nightly @ 04:00 ET, every day
            # including weekends so Monday's tab is fresh. Pulls Finnhub
            # calendar + history for every watchlist symbol, upserts both
            # tables, and fires T-7 notifications for any symbol whose
            # earnings is exactly 7 days out. Set EARNINGS_REFRESH_ENABLED=0
            # in Railway to disable.
            if os.environ.get("EARNINGS_REFRESH_ENABLED", "true").lower() not in ("0", "false", "no"):
                from apscheduler.triggers.cron import CronTrigger as _CronTrigger
                import pytz as _pytz2
                _et = _pytz2.timezone("America/New_York")

                def _earnings_refresh():
                    try:
                        from analytics.earnings_refresh import refresh_earnings
                        summary = refresh_earnings(sync_session_factory)
                        logger.info("Earnings refresh summary: %s", summary)
                    except Exception:
                        logger.exception("Earnings refresh failed")

                scheduler.add_job(
                    _earnings_refresh,
                    _CronTrigger(hour=4, minute=0, timezone=_et),
                    id="earnings_refresh",
                    misfire_grace_time=3600,
                    replace_existing=True,
                )
                logger.info("Registered nightly earnings refresh cron: 04:00 ET")
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

        else:
            logger.info(
                "Scheduled AI jobs disabled (AI_SCHEDULED_JOBS_ENABLED=false): "
                "game_plan, daily_review"
            )

        # =============================================================
        # Premarket sector heat brief — REMOVED 2026-05-09.
        # The triage-agent service now owns the morning brief at 8:30 ET
        # (richer: LLM polish, top picks with composite score, EOD recap).
        # The legacy app/services/sector_brief.py remains for the manual
        # test endpoint at routers/market.py:fire_sector_brief_test, but
        # is no longer scheduled.
        # =============================================================

        # =============================================================
        # TV alert lifecycle watcher — fires Telegram for T1/T2/stop hits
        # on alerts the user pressed Took. One notification per outcome.
        # Set TV_LIFECYCLE_ALERTS_ENABLED=false to disable.
        # =============================================================
        def _lifecycle_watcher_job():
            try:
                from app.background.lifecycle_watcher import check_lifecycle_outcomes
                fired = check_lifecycle_outcomes(sync_session_factory)
                if fired:
                    logger.info("Lifecycle watcher: fired %d notifications", fired)
            except Exception:
                logger.exception("Lifecycle watcher failed")

        # Run 24/7 — crypto trades on weekends and outside US market hours,
        # so gating to mon-fri 9-16 ET caused missed T1/T2/STOP notifications
        # for ETH/BTC trades that hit targets off-hours.
        # Cost is bounded: watcher only polls symbols with TOOK alerts in the
        # last 5 days; no-op when none.
        scheduler.add_job(
            _lifecycle_watcher_job,
            "cron",
            minute="*/5",
            id="lifecycle_watcher",
            replace_existing=True,
        )
        logger.info("Lifecycle watcher cron registered: every 5 min, 24/7 (crypto-friendly)")

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
            from alerting.notifier import _send_telegram, _send_telegram_to
            from analytics.market_hours import is_market_hours
            from apscheduler.triggers.cron import CronTrigger
            import pytz as _pytz

            logger.info(
                "Candle pings config: CANDLE_65=%s ETH_CANDLE=%s",
                CANDLE_65_NOTIFICATIONS_ENABLED, ETH_CANDLE_NOTIFICATIONS_ENABLED,
            )

            # Broadcast helper — queries users table for all chat_ids and
            # sends to each (mirrors how the TV webhook fans out). Falls
            # back to legacy TELEGRAM_CHAT_ID broadcast if DB query yields
            # nothing. Logs aggressively so Railway logs show exactly
            # what's happening at each step.
            def _broadcast_telegram(body: str, label: str) -> int:
                logger.info("CANDLE PING FIRE: %s — broadcasting to users", label)
                sent = 0
                tried = 0
                try:
                    from sqlalchemy import text
                    with sync_session_factory() as db:
                        rows = db.execute(text(
                            "SELECT telegram_chat_id FROM users "
                            "WHERE telegram_chat_id IS NOT NULL "
                            "AND telegram_chat_id != ''"
                        )).fetchall()
                    chat_ids = [r[0] for r in rows]
                    logger.info("CANDLE PING %s: %d users with chat_id", label, len(chat_ids))
                    for cid in chat_ids:
                        tried += 1
                        ok = _send_telegram_to(body, cid)
                        if ok:
                            sent += 1
                        else:
                            logger.warning("CANDLE PING %s: send to chat_id=%s failed", label, cid)
                    logger.info("CANDLE PING %s: sent=%d/%d", label, sent, tried)
                    if sent == 0:
                        # Fallback to legacy broadcast in case of DB issue
                        logger.warning("CANDLE PING %s: per-user broadcast sent 0 — trying legacy", label)
                        if _send_telegram(body):
                            sent = 1
                except Exception:
                    logger.exception("CANDLE PING %s: broadcast exception", label)
                return sent

            # 60-min RTH candle pings (switched from 65-min 2026-05-19): 6 per session.
            # Matches TradingView's "1h" bar boundaries for US equities — opens at
            # 09:30 ET, so 60-min bars close at 10:30, 11:30, 12:30, 13:30, 14:30, 15:30.
            # The 16:00 market close itself signals the final 30-min partial bar.
            # 15:30 ping tagged "FINAL 30 MIN remaining" (mirrors the prior
            # 14:55 "FINAL HOUR starting" anchor).
            # Tuple: (idx, hour, minute, is_final)
            _CANDLE_60_SCHEDULE = [
                (1, 10, 30, False),
                (2, 11, 30, False),
                (3, 12, 30, False),
                (4, 13, 30, False),
                (5, 14, 30, False),
                (6, 15, 30, True),  # final 30 min remaining
            ]

            def _notify_candle_close(idx: int, hour: int, minute: int, is_final: bool) -> None:
                if not is_market_hours():
                    logger.info("CANDLE PING SKIP: 60-min #%d outside market hours", idx)
                    return
                if is_final:
                    body = (
                        f"<b>60-min candle 6 closed — FINAL 30 MIN remaining</b>\n"
                        f"Time: {hour:02d}:{minute:02d} ET → 16:00 ET market close\n"
                        f"Last hourly close in session."
                    )
                else:
                    body = (
                        f"<b>60-min candle {idx} closed</b>\n"
                        f"Time: {hour:02d}:{minute:02d} ET\n"
                        f"Check your charts."
                    )
                _broadcast_telegram(body, f"60min#{idx}")

            # Env var kept as CANDLE_65_NOTIFICATIONS_ENABLED for Railway
            # backward compat — renaming would silently disable any
            # explicit-false override that's currently set.
            if CANDLE_65_NOTIFICATIONS_ENABLED:
                _et_tz = _pytz.timezone("America/New_York")
                for idx, hour, minute, is_final in _CANDLE_60_SCHEDULE:
                    scheduler.add_job(
                        _notify_candle_close,
                        CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone=_et_tz),
                        args=[idx, hour, minute, is_final],
                        id=f"candle_60_close_{idx}",
                        misfire_grace_time=30,
                        replace_existing=True,
                    )
                logger.info("Registered 6 cron jobs for 60-min candle ping schedule")

            # ETH 4h candle closes (UTC, 24/7): 6/day at 00, 04, 08, 12, 16, 20.
            # No "final candle" framing since crypto trades continuously.
            # Plus a startup fire on every Railway redeploy as a sanity check
            # that the pipeline is healthy.
            _ETH_4H_SCHEDULE = [
                (1, 0),
                (2, 4),
                (3, 8),
                (4, 12),
                (5, 16),
                (6, 20),
            ]

            def _notify_eth_candle_close(idx: int, hour_utc: int) -> None:
                _broadcast_telegram(
                    f"<b>ETH 4h candle {idx}/6 closed</b>\n"
                    f"Time: {hour_utc:02d}:00 UTC\n"
                    f"Check the chart.",
                    f"ETH4h#{idx}",
                )

            if ETH_CANDLE_NOTIFICATIONS_ENABLED:
                # 6 cron jobs at real 4h UTC candle close boundaries.
                # Validated against actual Coinbase ETH-USD candle closes
                # via 5-min cron alignment test (PR #66) — fires within
                # 1-2s of the real bar close.
                _utc_tz = _pytz.timezone("UTC")
                for idx, hour_utc in _ETH_4H_SCHEDULE:
                    scheduler.add_job(
                        _notify_eth_candle_close,
                        CronTrigger(hour=hour_utc, minute=0, timezone=_utc_tz),
                        args=[idx, hour_utc],
                        id=f"eth_4h_close_{idx}",
                        misfire_grace_time=30,
                        replace_existing=True,
                    )
                logger.info("Registered ETH 4h candle pings (6 UTC cron jobs)")
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

        # In-Play Volume Screener (spec 62): weekly universe rebuild + market-hours
        # refresh. Sync wrappers drive the async DB via asyncio.run. Market-hours
        # gating is inside the job; the interval fires year-round but no-ops when closed.
        try:
            from app.services.screener_service import refresh_in_play_job, rebuild_universe_job
            _scr_min = int(settings.SCREENER_REFRESH_MINUTES)
            scheduler.add_job(
                rebuild_universe_job, "cron", hour=6, minute=0,
                timezone="America/New_York", day_of_week="sun",
                id="screener_universe_rebuild", replace_existing=True,
            )
            scheduler.add_job(
                refresh_in_play_job, "interval", minutes=_scr_min,
                id="screener_in_play_refresh", replace_existing=True,
            )
            # Swing screener: daily-bar scan, NOT market-gated (valid all week).
            # Two scheduled runs — anticipate in the morning (yesterday's settled
            # bar), confirm into the close (today's near-final bar, 30 min before
            # the bell — the "trade the close" read). Plus on-demand.
            from app.services.screener_service import (
                refresh_swing_job, refresh_swing_small_job,
                refresh_swing_close_job, refresh_swing_small_close_job, bootstrap_job,
            )
            scheduler.add_job(
                refresh_swing_job, "cron", hour=7, minute=30,
                timezone="America/New_York",
                id="screener_swing_refresh", replace_existing=True,
            )
            scheduler.add_job(
                refresh_swing_small_job, "cron", hour=7, minute=40,
                timezone="America/New_York",
                id="screener_swing_small_refresh", replace_existing=True,
            )
            # Close runs — 30 min before the 4 PM ET close, market days only.
            scheduler.add_job(
                refresh_swing_close_job, "cron", day_of_week="mon-fri", hour=15, minute=30,
                timezone="America/New_York",
                id="screener_swing_close", replace_existing=True,
            )
            scheduler.add_job(
                refresh_swing_small_close_job, "cron", day_of_week="mon-fri", hour=15, minute=35,
                timezone="America/New_York",
                id="screener_swing_small_close", replace_existing=True,
            )
            # Scheduler jobs run on worker threads but the async DB engine is bound
            # to this (the app's main) loop — hand it to the service so jobs submit
            # their coroutines back to it instead of a dead asyncio.run() loop.
            import asyncio as _asyncio
            from app.services.screener_service import set_main_loop
            set_main_loop(_asyncio.get_running_loop())
            # One-shot on startup: build universe if empty + initial swing scan,
            # so both screeners self-populate on deploy (idempotent across restarts).
            scheduler.add_job(bootstrap_job, id="screener_bootstrap", replace_existing=True)
            logger.info("Screener jobs registered (weekly rebuild + %d-min in-play + daily swing + bootstrap)", _scr_min)
        except Exception:
            logger.exception("Failed to register screener jobs")

        # Social Buzz (Apewisdom-fed) — hourly refresh that pulls top
        # discussed tickers from retail social, filters against our
        # screener_universe, cross-references today's Grade-A alerts.
        # Cheap: one HTTP call per hour, no per-symbol API loops.
        # Set SOCIAL_BUZZ_ENABLED=0 in Railway to disable.
        if os.environ.get("SOCIAL_BUZZ_ENABLED", "true").lower() not in ("0", "false", "no"):
            try:
                def _social_buzz_refresh():
                    try:
                        from analytics.social_buzz import refresh_social_buzz
                        summary = refresh_social_buzz(sync_session_factory)
                        logger.info("Social buzz refresh: %s", summary)
                    except Exception:
                        logger.exception("Social buzz refresh failed")

                def _social_buzz_cleanup():
                    try:
                        from analytics.social_buzz import cleanup_old_snapshots
                        cleanup_old_snapshots(sync_session_factory, keep_days=7)
                    except Exception:
                        logger.exception("Social buzz cleanup failed")

                scheduler.add_job(
                    _social_buzz_refresh, "interval", minutes=60,
                    id="social_buzz_refresh", replace_existing=True,
                )
                # Self-populate on startup so the tab isn't empty until 4am ET tomorrow.
                scheduler.add_job(_social_buzz_refresh, id="social_buzz_initial")

                # Social + Grade-A cross-detect — every 5 min during market hours,
                # scan the top trending symbols for intraday Grade A. When detected,
                # fire a push notification (once per (symbol, day)) to all users
                # with push enabled. The "🔥 Social + Grade A" moment — symbols
                # the user might NOT have on their TV setup but that just lined
                # up across both signals.
                def _social_grade_a_check():
                    try:
                        from analytics.social_grade_a_watch import check_social_grade_a
                        summary = check_social_grade_a(sync_session_factory)
                        logger.info("Social+A check: %s", summary)
                    except Exception:
                        logger.exception("Social+A check failed")

                scheduler.add_job(
                    _social_grade_a_check, "interval", minutes=5,
                    id="social_grade_a_check", replace_existing=True,
                )
                # Weekly cleanup of stale snapshots.
                scheduler.add_job(
                    _social_buzz_cleanup, "cron", day_of_week="sun", hour=3, minute=0,
                    timezone="America/New_York",
                    id="social_buzz_cleanup", replace_existing=True,
                )
                logger.info("Registered Social Buzz cron: hourly refresh + Sun 3am cleanup")
            except Exception:
                logger.exception("Failed to register Social Buzz cron")

        # scheduler already started at the top of this block (start-early so a
        # late registration failure can't kill all scheduled jobs).
        logger.info("Background monitor jobs registered (3-min poll + EOD/premarket/weekly jobs)")
    except Exception:
        logger.exception("Failed to register some background jobs (scheduler still running)")

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

    # Redirect any prior/retired domain → the current brand domain.
    # Requirements for a redirect to fire: the old domain must still be owned,
    # have DNS pointed at this Railway service, and be added as a Railway custom
    # domain (so TLS terminates and the request reaches this app).
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import RedirectResponse

    CANONICAL_DOMAIN = "https://www.busytradersdesk.com"

    # Web-only legacy domains — safe to 301 immediately (no app loads its UI here).
    LEGACY_DOMAINS = (
        "tradesignalwithai.com",
        "aicopilottrader.com",
        # NOTE: do NOT add "tradingwithai.ai" until the rebranded iOS build is live
        # in the App Store. Installed Capacitor apps load their UI from
        # www.tradingwithai.ai; redirecting that host to a different origin can
        # break the native bridge. Keep it serving the app directly for now, then
        # add it here once App Store adoption is high.
    )

    class DomainRedirectMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            host = request.headers.get("host", "")
            path = request.url.path
            # Exclude /api/ + /telegram/ + health so installed mobile apps and
            # webhooks that still call the old host keep working.
            if (
                any(d in host for d in LEGACY_DOMAINS)
                and not path.startswith(("/api/", "/telegram/"))
                and path != "/healthz"
            ):
                new_url = f"{CANONICAL_DOMAIN}{path}"
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
        performance, coach_history, auto_trades,
        tv_webhook,  # Phase 5a — TradingView alert ingest
        public,      # Public (unauth) EOD report endpoints
        focus_list,  # Persisted daily focus list from AI Best Setups
        alert_config,  # Per-alert-type enable/disable toggles
        earnings,    # Spec 61 — Watchlist earnings calendar + T-7 notifications
        screener,    # Spec 62 — In-Play Volume Screener
        fundamentals,  # Watchlist Details tab — fundamentals + analyst ratings + AI views
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
    app.include_router(screener.router, prefix="/api/v1/screener", tags=["screener"])
    app.include_router(coach_history.router, prefix="/api/v1", tags=["coach"])
    app.include_router(auto_trades.router, prefix="/api/v1/auto-trades", tags=["auto-trades"])
    app.include_router(focus_list.router, prefix="/api/v1/ai", tags=["focus-list"])
    app.include_router(alert_config.router, prefix="/api/v1/alert-config", tags=["alert-config"])
    app.include_router(earnings.router, prefix="/api/v1/earnings", tags=["earnings"])
    app.include_router(fundamentals.router, prefix="/api/v1/fundamentals", tags=["fundamentals"])
    # Phase 5a — TradingView webhook ingest at /tv/webhook (no /api/v1 prefix
    # so the URL traders paste into Pine Script is short and stable).
    app.include_router(tv_webhook.router, prefix="/tv", tags=["tradingview"])
    # Public (unauthenticated) EOD report — shareable links for marketing.
    app.include_router(public.router, prefix="/api/v1/public", tags=["public"])

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
