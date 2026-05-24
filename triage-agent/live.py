"""Live triage worker.

Subscribes to the `new_alert` Postgres NOTIFY channel and triages each new
alert as it lands. Decoupled from the existing trade-analytics pipeline:
the existing pipeline keeps inserting into `alerts` exactly as today; the
DB trigger fires pg_notify; this worker LISTENs and reacts.

Lifecycle:

   ① on startup: catch up from cursor (any alerts inserted while we were down)
   ② open a LISTEN connection
   ③ poll for notifications; for each id, fetch the row + triage + route
   ④ heartbeat on idle; daily cost cap; persistent cursor

Run:
   python live.py                    # default user_id=3, conviction channel
   python live.py --dry-run          # don't actually send Telegram, just print
   python live.py --catchup-only     # process backlog and exit
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import select as pyselect
import signal
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

import telegram_post
import triage as triage_mod

# Optional cron-driven jobs (premarket brief + EOD recap)
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    _SCHEDULER_AVAILABLE = True
except ImportError:
    _SCHEDULER_AVAILABLE = False

# ──────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────
DATABASE_URL    = os.environ["DATABASE_URL"]
USER_ID         = int(os.environ.get("TRIAGE_USER_ID", "3"))
CHANNEL         = "new_alert"
CURSOR_PATH     = Path(os.environ.get("TRIAGE_CURSOR_FILE", ".triage-cursor"))
AUDIT_LOG_PATH  = Path(os.environ.get("TRIAGE_AUDIT_FILE", ".triage-audit.jsonl"))
DAILY_USD_CAP   = float(os.environ.get("TRIAGE_DAILY_USD_CAP", "1.50"))

# Premarket / EOD scheduler — set ENABLE_PREMARKET_BRIEF=true to activate.
# Default false so existing deploys aren't surprised by new behavior.
ENABLE_PREMARKET_BRIEF = os.environ.get("ENABLE_PREMARKET_BRIEF", "false").lower() == "true"
PREMARKET_HOUR_ET   = int(os.environ.get("PREMARKET_HOUR_ET", "8"))
PREMARKET_MINUTE_ET = int(os.environ.get("PREMARKET_MINUTE_ET", "30"))
EOD_HOUR_ET         = int(os.environ.get("EOD_HOUR_ET", "16"))
EOD_MINUTE_ET       = int(os.environ.get("EOD_MINUTE_ET", "5"))

# Post mode — controls what the agent sends to Telegram.
# Default 'all' = post every verdict (validation phase: see all data,
# judge accuracy). Switch to 'high_only' once the agent is trusted.
POST_MODE       = os.environ.get("TRIAGE_POST_MODE", "all").lower()

# Mute NOTICE-direction alerts. Default FALSE — NOTICEs reach Telegram
# (SPY/QQQ only — non-index NOTICEs filtered separately, see process_alert).
# Set to true to mute NOTICEs entirely; the per-session cap still applies
# when enabled. Old behavior was mute=true; now NOTICEs are core context
# for SPY/QQQ macro alignment.
MUTE_NOTICE_ALERTS = os.environ.get("MUTE_NOTICE_ALERTS", "true").lower() == "true"

# Rolling-window cooldown on MA/EMA alerts. ETH trades 24/7 and the
# midnight-anchored "2/day cap" was a poor fit — a fire at 23:45 ET could
# fire again at 00:01 ET. Switched to a rolling time window: after an
# MA alert of (symbol, alert_type) fires, the same combo is blocked for
# the next MA_COOLDOWN_HOURS hours (default 4).
#
# ONLY applies to symbols in MA_COOLDOWN_SYMBOLS (default: ETH-USD).
# Equity MA bounces are NOT throttled here — dedup + cooldown handle
# them already, and we don't want to miss valid 2nd/3rd entries on a
# trend day.
MA_COOLDOWN_HOURS = float(os.environ.get("MA_COOLDOWN_HOURS", "4"))
MA_COOLDOWN_SYMBOLS = set(
    s.strip().upper()
    for s in os.environ.get("MA_COOLDOWN_SYMBOLS",
                             os.environ.get("MA_DAILY_CAP_SYMBOLS", "ETH-USD")).split(",")
    if s.strip()
)

HEARTBEAT_SECS  = 30
RECONNECT_SECS  = 5

if POST_MODE not in {"all", "high_only", "high_mute"}:
    raise SystemExit(f"TRIAGE_POST_MODE='{POST_MODE}' invalid. "
                     f"Use one of: all, high_only, high_mute.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s | %(message)s",
)
logger = logging.getLogger("triage.live")


# ──────────────────────────────────────────────────────────────────
# CURSOR + AUDIT
# ──────────────────────────────────────────────────────────────────
def load_cursor():
    try:
        cur = int(CURSOR_PATH.read_text().strip() or "0")
    except FileNotFoundError:
        cur = 0
    # First-run bootstrap: if INITIAL_CURSOR env var is set and our cursor is
    # below it, jump forward. Lets ops skip a backfill on first deploy without
    # shell access (set INITIAL_CURSOR on Railway, redeploy, done).
    initial = os.environ.get("INITIAL_CURSOR")
    if initial:
        try:
            initial_int = int(initial)
            if cur < initial_int:
                logger.info("INITIAL_CURSOR=%d > current cursor=%d — jumping forward",
                            initial_int, cur)
                CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
                CURSOR_PATH.write_text(str(initial_int))
                cur = initial_int
        except ValueError:
            logger.warning("INITIAL_CURSOR=%r is not an int, ignoring", initial)
    return cur

def save_cursor(alert_id):
    CURSOR_PATH.write_text(str(alert_id))

def write_audit(record):
    record["ts"] = datetime.now(timezone.utc).isoformat()
    line = json.dumps(record, default=str)
    with AUDIT_LOG_PATH.open("a") as f:
        f.write(line + "\n")


# ──────────────────────────────────────────────────────────────────
# DB HELPERS
# ──────────────────────────────────────────────────────────────────
ALERT_COLUMNS = """id, symbol, alert_type, direction, price,
                   entry, stop, target_1, target_2,
                   volume_ratio, cvd_diverging, confidence,
                   stage, vwap_slope_pct, inside_day,
                   user_id, session_date, created_at, suppressed_reason"""

def fetch_alert_by_id(alert_id):
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"SELECT {ALERT_COLUMNS} FROM alerts WHERE id = %s", (alert_id,))
            return cur.fetchone()

def fetch_alerts_since(cursor_id, user_id):
    """All alerts with id > cursor_id for the user, oldest first."""
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"""SELECT {ALERT_COLUMNS} FROM alerts
                            WHERE id > %s AND user_id = %s
                            ORDER BY id ASC""",
                        (cursor_id, user_id))
            return list(cur.fetchall())


def count_prior_fires_today(symbol, alert_type, session_date, current_id, user_id):
    """Count earlier alerts with the same (symbol, alert_type) on this session_date.
    Used by the NOTICE per-session cap.
    """
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT COUNT(*) FROM alerts
                            WHERE user_id = %s
                              AND symbol = %s
                              AND alert_type = %s
                              AND session_date = %s
                              AND id < %s""",
                        (user_id, symbol, alert_type, session_date, current_id))
            return cur.fetchone()[0] or 0


def has_recent_fire(symbol, alert_type, current_id, user_id, hours):
    """True if there was a prior fire of (symbol, alert_type) within the
    last `hours` hours, measured against the current alert's created_at.
    Used by the MA cooldown — rolling window, not session-bucketed.
    Returns also the timestamp of that prior fire (or None).
    """
    cutoff_minutes = hours * 60
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Look up the current alert's created_at, then check for any
            # prior fire with the same (symbol, alert_type) more recent
            # than (current_created_at - hours).
            cur.execute("""SELECT created_at FROM alerts WHERE id = %s""", (current_id,))
            curr_row = cur.fetchone()
            if curr_row is None:
                return False, None
            current_created_at = curr_row[0]
            cur.execute("""SELECT created_at FROM alerts
                            WHERE user_id = %s
                              AND symbol = %s
                              AND alert_type = %s
                              AND id < %s
                              AND created_at > %s - (%s || ' minutes')::interval
                            ORDER BY id DESC LIMIT 1""",
                        (user_id, symbol, alert_type, current_id,
                         current_created_at, cutoff_minutes))
            prior = cur.fetchone()
            return (prior is not None), (prior[0] if prior else None)


def is_ma_alert(alert):
    """True if this alert is an MA bounce / rejection subject to the rolling
    cooldown. Restricted to symbols in MA_COOLDOWN_SYMBOLS (default:
    ETH-USD) — equity MA bounces are not throttled here because dedup +
    cooldown logic already handles them, and throttling risks missing
    valid 2nd/3rd entries on a trend day.
    """
    symbol = (alert.get("symbol") or "").upper()
    if symbol not in MA_COOLDOWN_SYMBOLS:
        return False
    at = (alert.get("alert_type") or "")
    return at.startswith("tv_ma_bounce_long_v3_ema") or at.startswith("tv_ma_rejection_short_v3_ema")


# ──────────────────────────────────────────────────────────────────
# COST TRACKING (rough — based on per-step Haiku rates)
# ──────────────────────────────────────────────────────────────────
class CostBudget:
    HAIKU_PER_STEP_USD = 0.002      # rough — input + output per agent turn
    SONNET_PER_STEP_USD = 0.012

    def __init__(self, daily_cap):
        self.daily_cap = daily_cap
        self.spent = 0.0
        self.day = date.today()

    def _reset_if_new_day(self):
        if date.today() != self.day:
            logger.info("cost cap day rollover — resetting from $%.4f to 0", self.spent)
            self.spent = 0.0
            self.day = date.today()

    def charge(self, steps, model="haiku"):
        self._reset_if_new_day()
        rate = self.SONNET_PER_STEP_USD if "sonnet" in (model or "").lower() else self.HAIKU_PER_STEP_USD
        cost = steps * rate
        self.spent += cost
        return cost

    def under_cap(self):
        self._reset_if_new_day()
        return self.spent < self.daily_cap


# ──────────────────────────────────────────────────────────────────
# ROUTING — what to do per verdict
# ──────────────────────────────────────────────────────────────────
def route(alert, result, dry_run=False):
    verdict = result.get("verdict")
    audit = {
        "alert_id":      alert["id"],
        "symbol":        alert["symbol"],
        "alert_type":    alert["alert_type"],
        "verdict":       verdict,
        "agent_verdict": result.get("agent_verdict"),
        "reason":        result.get("reason"),
        "steps_used":    result.get("steps_used"),
        "proximity":     result.get("proximity_match"),
        "sector":        (result.get("sector") or {}).get("sector") if (result.get("sector") or {}).get("in_sector") else None,
        "sector_aligned": (result.get("sector") or {}).get("aligned"),
        "index_aligned":  bool((result.get("index") or {}).get("aligned_with_index")),
        "post_mode":      POST_MODE,
        "dry_run":        dry_run,
    }

    if dry_run:
        logger.info("[DRY-RUN] %s #%s %s — would post (mode=%s)",
                    verdict, alert["id"], alert["symbol"], POST_MODE)
        audit["telegram_sent"] = "dry_run"
    else:
        sent = telegram_post.send_verdict(alert, result, mode=POST_MODE)
        if sent is None:
            audit["telegram_sent"] = "skipped_per_post_mode"
            logger.info("%s #%s %s — skipped per post_mode=%s",
                        verdict, alert["id"], alert["symbol"], POST_MODE)
        elif sent:
            audit["telegram_sent"] = True
            logger.info("%s #%s %s — posted",
                        verdict, alert["id"], alert["symbol"])
        else:
            audit["telegram_sent"] = False
            logger.warning("%s #%s %s — telegram FAILED",
                           verdict, alert["id"], alert["symbol"])

    write_audit(audit)


# ──────────────────────────────────────────────────────────────────
# CORE PROCESSOR
# ──────────────────────────────────────────────────────────────────
def process_alert(alert_id, budget, dry_run=False):
    """Fetch + filter + triage + route. Updates cursor on success."""
    alert = fetch_alert_by_id(alert_id)
    if alert is None:
        logger.warning("notify referenced #%s but row not found (already deleted?)", alert_id)
        save_cursor(alert_id)
        return

    if alert["user_id"] != USER_ID:
        # Not our user — still bump the cursor so we don't re-evaluate it.
        save_cursor(alert_id)
        return

    # Per-type enablement gate. Alerts whose type the user toggled OFF in
    # Settings > Alert Types are persisted by the webhook with
    # suppressed_reason set — recorded for in-app review only. Never triage
    # or post them to Telegram.
    if alert.get("suppressed_reason"):
        logger.info("NOT_ROUTED #%s %s %s — suppressed_reason=%s, skipping",
                    alert_id, alert.get("symbol"), alert.get("alert_type"),
                    alert["suppressed_reason"])
        write_audit({"alert_id": alert_id, "symbol": alert.get("symbol"),
                     "alert_type": alert.get("alert_type"),
                     "verdict": "NOT_ROUTED",
                     "reason": f"suppressed_reason={alert['suppressed_reason']}"})
        save_cursor(alert_id)
        return

    # NOTICE alerts are index-only (SPY/QQQ/AIQ/NDX) by default. Non-index
    # NOTICE-direction alerts (e.g., a weekly-level cross on AAPL that
    # degraded to NOTICE) are dropped before they can reach Telegram,
    # regardless of mute flag.
    #
    # ALLOWLIST (2026-05-16): tv_htf_proximity_* fire on all stocks and
    # bypass BOTH the non-index NOTICE drop AND MUTE_NOTICE_ALERTS — they
    # are high-signal "stock is approaching a key weekly/monthly level"
    # heads-ups that the user explicitly wants delivered everywhere.
    HTF_PROXIMITY_TYPES = {
        "tv_htf_proximity_pwh",
        "tv_htf_proximity_pwl",
        "tv_htf_proximity_pmh",
        "tv_htf_proximity_pml",
    }
    _direction = (alert.get("direction") or "").upper()
    _symbol_upper = (alert.get("symbol") or "").upper()
    _alert_type = alert.get("alert_type") or ""
    _htf_proximity_bypass = _alert_type in HTF_PROXIMITY_TYPES
    if _direction == "NOTICE" and _symbol_upper not in {"SPY", "QQQ", "AIQ", "NDX"} and not _htf_proximity_bypass:
        logger.info("NOTICE #%s %s %s — non-index NOTICE dropped",
                    alert_id, alert["symbol"], alert["alert_type"])
        write_audit({"alert_id": alert_id, "symbol": alert["symbol"],
                     "alert_type": alert["alert_type"], "verdict": "NOTICE_NON_INDEX_DROPPED",
                     "reason": "NOTICE direction restricted to SPY/QQQ"})
        save_cursor(alert_id)
        return

    if MUTE_NOTICE_ALERTS and _direction == "NOTICE" and not _htf_proximity_bypass:
        logger.info("NOTICE #%s %s %s — muted (MUTE_NOTICE_ALERTS=true)",
                    alert_id, alert["symbol"], alert["alert_type"])
        write_audit({"alert_id": alert_id, "symbol": alert["symbol"],
                     "alert_type": alert["alert_type"], "verdict": "NOTICE_MUTED",
                     "reason": "MUTE_NOTICE_ALERTS env flag"})
        save_cursor(alert_id)
        return

    # MA/EMA rolling cooldown — ETH-only by default. If the same
    # (symbol, alert_type) fired within the last MA_COOLDOWN_HOURS hours,
    # skip this one. Better fit for 24/7 crypto than a midnight-anchored
    # session cap.
    if is_ma_alert(alert):
        recent, prior_ts = has_recent_fire(
            alert["symbol"], alert["alert_type"],
            alert_id, USER_ID, MA_COOLDOWN_HOURS,
        )
        if recent:
            logger.info(
                "COOLDOWN_HIT #%s %s %s — prior fire at %s within %.1fh window, skipping",
                alert_id, alert["symbol"], alert["alert_type"],
                prior_ts, MA_COOLDOWN_HOURS,
            )
            write_audit({
                "alert_id": alert_id, "symbol": alert["symbol"],
                "alert_type": alert["alert_type"], "verdict": "MA_COOLDOWN_HIT",
                "reason": f"prior fire {prior_ts} within {MA_COOLDOWN_HOURS}h cooldown",
            })
            save_cursor(alert_id)
            return

    if not budget.under_cap():
        logger.warning("daily cost cap $%.2f hit; queuing #%s as audit-only",
                       budget.daily_cap, alert_id)
        write_audit({"alert_id": alert_id, "verdict": "OVER_BUDGET",
                     "reason": "daily cost cap reached"})
        save_cursor(alert_id)
        return

    try:
        result = triage_mod.triage(dict(alert), user_id=USER_ID)
    except Exception:
        logger.exception("triage threw for alert #%s", alert_id)
        write_audit({"alert_id": alert_id, "verdict": "ERROR",
                     "reason": "triage exception"})
        save_cursor(alert_id)
        return

    cost = budget.charge(result.get("steps_used", 1), model=triage_mod.MODEL)
    logger.info("triaged #%s %s -> %s  (steps=%d, $%.4f spent today)",
                alert_id, alert["symbol"], result["verdict"],
                result.get("steps_used", 0), budget.spent)

    route(alert, result, dry_run=dry_run)
    save_cursor(alert_id)


# ──────────────────────────────────────────────────────────────────
# CATCHUP (startup) + LISTEN (steady-state)
# ──────────────────────────────────────────────────────────────────
def catchup(budget, dry_run=False):
    cursor = load_cursor()
    pending = fetch_alerts_since(cursor, user_id=USER_ID)
    if not pending:
        logger.info("catchup: cursor=%s, no missed alerts", cursor)
        return
    logger.info("catchup: cursor=%s, processing %d missed alerts", cursor, len(pending))
    for a in pending:
        process_alert(a["id"], budget, dry_run=dry_run)
    logger.info("catchup complete")


def listen_forever(budget, dry_run=False):
    """LISTEN on the new_alert channel and process incoming notifications."""
    while True:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            with conn.cursor() as cur:
                cur.execute(f"LISTEN {CHANNEL};")
            logger.info("LISTEN on '%s' — waiting for new alerts", CHANNEL)

            while True:
                if pyselect.select([conn], [], [], HEARTBEAT_SECS) == ([], [], []):
                    logger.debug("heartbeat — alive, $%.4f spent today", budget.spent)
                    continue
                conn.poll()
                while conn.notifies:
                    notify = conn.notifies.pop(0)
                    try:
                        alert_id = int(notify.payload)
                    except ValueError:
                        logger.warning("non-int notify payload: %r", notify.payload)
                        continue
                    process_alert(alert_id, budget, dry_run=dry_run)
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            logger.warning("DB connection lost (%s) — reconnecting in %ds", e, RECONNECT_SECS)
            try: conn.close()
            except Exception: pass
            time.sleep(RECONNECT_SECS)
            # On reconnect, run catchup so we don't miss alerts that came in
            # while we were disconnected.
            catchup(budget, dry_run=dry_run)
        except KeyboardInterrupt:
            logger.info("interrupted — shutting down")
            try: conn.close()
            except Exception: pass
            return


def start_premarket_scheduler():
    """Start the background scheduler for premarket / EOD jobs.
    Returns the scheduler (so caller can shut it down on exit) or None if disabled.
    """
    if not ENABLE_PREMARKET_BRIEF:
        logger.info("premarket brief scheduler disabled (ENABLE_PREMARKET_BRIEF=false)")
        return None
    if not _SCHEDULER_AVAILABLE:
        logger.warning("APScheduler not installed; premarket brief disabled")
        return None

    try:
        import pytz
        et_tz = pytz.timezone("America/New_York")
    except Exception:
        logger.exception("pytz unavailable; premarket brief disabled")
        return None

    scheduler = BackgroundScheduler(timezone=et_tz)

    def _safe_premarket():
        try:
            from premarket import run_premarket_brief
            run_premarket_brief(send=True)
        except Exception:
            logger.exception("premarket brief job failed")

    def _safe_eod():
        try:
            from eod import run_eod_recap
            run_eod_recap(send=True)
        except Exception:
            logger.exception("eod recap job failed")

    # Mon-Fri only (no weekend briefs)
    scheduler.add_job(
        _safe_premarket,
        CronTrigger(hour=PREMARKET_HOUR_ET, minute=PREMARKET_MINUTE_ET,
                    day_of_week="mon-fri", timezone=et_tz),
        id="premarket_brief", replace_existing=True,
    )
    scheduler.add_job(
        _safe_eod,
        CronTrigger(hour=EOD_HOUR_ET, minute=EOD_MINUTE_ET,
                    day_of_week="mon-fri", timezone=et_tz),
        id="eod_recap", replace_existing=True,
    )
    scheduler.start()
    logger.info("scheduler started: premarket %02d:%02d ET, EOD %02d:%02d ET (mon-fri)",
                PREMARKET_HOUR_ET, PREMARKET_MINUTE_ET, EOD_HOUR_ET, EOD_MINUTE_ET)
    return scheduler


def main():
    p = argparse.ArgumentParser(description="Live triage agent.")
    p.add_argument("--dry-run", action="store_true",
                   help="Don't actually post to Telegram; just log what would happen.")
    p.add_argument("--catchup-only", action="store_true",
                   help="Process backlog since cursor and exit.")
    args = p.parse_args()

    logger.info("starting triage worker — user_id=%d, post_mode=%s, "
                "daily_cap=$%.2f, dry_run=%s, premarket=%s",
                USER_ID, POST_MODE, DAILY_USD_CAP, args.dry_run, ENABLE_PREMARKET_BRIEF)
    budget = CostBudget(DAILY_USD_CAP)

    catchup(budget, dry_run=args.dry_run)

    if args.catchup_only:
        logger.info("catchup-only mode — exiting")
        return

    # Graceful shutdown on SIGTERM (Railway sends this)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    # Background scheduler for premarket + EOD briefs (if enabled)
    sched = start_premarket_scheduler()

    try:
        listen_forever(budget, dry_run=args.dry_run)
    finally:
        if sched is not None:
            try: sched.shutdown(wait=False)
            except Exception: pass


if __name__ == "__main__":
    main()
