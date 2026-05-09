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

# ──────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────
DATABASE_URL    = os.environ["DATABASE_URL"]
USER_ID         = int(os.environ.get("TRIAGE_USER_ID", "3"))
CHANNEL         = "new_alert"
CURSOR_PATH     = Path(os.environ.get("TRIAGE_CURSOR_FILE", ".triage-cursor"))
AUDIT_LOG_PATH  = Path(os.environ.get("TRIAGE_AUDIT_FILE", ".triage-audit.jsonl"))
DAILY_USD_CAP   = float(os.environ.get("TRIAGE_DAILY_USD_CAP", "1.50"))

# Post mode — controls what the agent sends to Telegram.
# Default 'all' = post every verdict (validation phase: see all data,
# judge accuracy). Switch to 'high_only' once the agent is trusted.
POST_MODE       = os.environ.get("TRIAGE_POST_MODE", "all").lower()
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
        return int(CURSOR_PATH.read_text().strip() or "0")
    except FileNotFoundError:
        return 0

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
                   user_id, session_date, created_at"""

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


def main():
    p = argparse.ArgumentParser(description="Live triage agent.")
    p.add_argument("--dry-run", action="store_true",
                   help="Don't actually post to Telegram; just log what would happen.")
    p.add_argument("--catchup-only", action="store_true",
                   help="Process backlog since cursor and exit.")
    args = p.parse_args()

    logger.info("starting triage worker — user_id=%d, post_mode=%s, "
                "daily_cap=$%.2f, dry_run=%s",
                USER_ID, POST_MODE, DAILY_USD_CAP, args.dry_run)
    budget = CostBudget(DAILY_USD_CAP)

    catchup(budget, dry_run=args.dry_run)

    if args.catchup_only:
        logger.info("catchup-only mode — exiting")
        return

    # Graceful shutdown on SIGTERM (Railway sends this)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    listen_forever(budget, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
