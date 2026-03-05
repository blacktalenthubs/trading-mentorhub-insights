"""Background monitor thread — auto-polls during market hours.

Starts a daemon thread on first import that runs `poll_cycle()` every
POLL_INTERVAL_MINUTES while the market is open.  The thread is safe to
import from Streamlit (it starts at most once per process).
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger("monitor_thread")

_started = False
_lock = threading.Lock()

# Tracks which date we last ran the EOD swing scan for
_eod_ran_date: str | None = None


def _monitor_loop() -> None:
    """Blocking loop that polls every interval during market hours."""
    from alert_config import POLL_INTERVAL_MINUTES
    from analytics.market_hours import is_market_hours
    from db import init_db
    from monitor import poll_cycle

    init_db()
    interval_sec = POLL_INTERVAL_MINUTES * 60
    logger.info("Background monitor thread started (interval=%ds)", interval_sec)

    # Always run one initial poll on startup so the DB has data even after deploy
    try:
        alerts = poll_cycle(dry_run=False)
        logger.info("Initial poll complete: %d alerts fired", alerts)
    except Exception:
        logger.exception("Initial poll failed")

    while True:
        time.sleep(interval_sec)
        try:
            if is_market_hours():
                alerts = poll_cycle(dry_run=False)
                logger.info("Background poll complete: %d alerts fired", alerts)
            else:
                _maybe_run_eod()
                logger.debug("Market closed — sleeping")
        except Exception:
            logger.exception("Background monitor error")


def _maybe_run_eod() -> None:
    """Run swing EOD scan once per session, after market close on weekdays."""
    global _eod_ran_date
    from datetime import datetime

    import pytz

    from alerting.alert_store import today_session
    from alerting.swing_scanner import swing_scan_eod

    today = today_session()
    if _eod_ran_date == today:
        return  # already ran today

    et = pytz.timezone("US/Eastern")
    now = datetime.now(et)
    if now.weekday() >= 5:
        return  # weekend
    if now.hour < 16:
        return  # before close

    _eod_ran_date = today
    logger.info("Running EOD swing scan for %s", today)
    try:
        count = swing_scan_eod()
        logger.info("EOD swing scan complete: %d signals", count)
    except Exception:
        logger.exception("EOD swing scan failed")


def start() -> None:
    """Start the background monitor thread (idempotent — only starts once)."""
    global _started
    with _lock:
        if _started:
            return
        _started = True

    t = threading.Thread(target=_monitor_loop, daemon=True, name="monitor-bg")
    t.start()
    logger.info("Background monitor thread launched")
