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


def _monitor_loop() -> None:
    """Blocking loop that polls every interval during market hours."""
    from alert_config import POLL_INTERVAL_MINUTES
    from analytics.market_hours import is_market_hours
    from db import init_db
    from monitor import poll_cycle

    init_db()
    interval_sec = POLL_INTERVAL_MINUTES * 60
    logger.info("Background monitor thread started (interval=%ds)", interval_sec)

    while True:
        try:
            if is_market_hours():
                alerts = poll_cycle(dry_run=False)
                logger.info("Background poll complete: %d alerts fired", alerts)
            else:
                logger.debug("Market closed — sleeping")
        except Exception:
            logger.exception("Background monitor error")

        time.sleep(interval_sec)


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
