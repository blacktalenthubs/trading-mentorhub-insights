"""Railway alert monitor worker.

Standalone entry point that runs poll_cycle() on a schedule via APScheduler.
Deployed on Railway ($5/mo) to avoid Streamlit Cloud sleep killing the monitor.

Usage:
    python worker.py          # Start the monitor loop
    python worker.py --test   # Send a test notification and exit
"""

from __future__ import annotations

import logging
import os
import sys
import time

# Ensure project root is on sys.path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("worker")

MAX_RESTARTS = 10
RESTART_DELAY_SECONDS = 30


def main():
    import argparse

    from db import init_db
    from monitor import run_monitor, run_test

    parser = argparse.ArgumentParser(description="Railway alert monitor worker")
    parser.add_argument("--test", action="store_true",
                        help="Send test notification and exit")
    args = parser.parse_args()

    logger.info("Initializing database...")
    init_db()

    if args.test:
        run_test()
    else:
        # Start Telegram bot listener in background thread
        # so /start deep-link tokens can be processed
        try:
            from scripts.telegram_bot import start_bot_thread
            if start_bot_thread():
                logger.info("Telegram bot listener active")
        except Exception:
            logger.exception("Failed to start Telegram bot listener")

        # Restart loop: if run_monitor() crashes, wait and retry
        restarts = 0
        while restarts < MAX_RESTARTS:
            try:
                logger.info("Starting Railway alert monitor worker (attempt %d)", restarts + 1)
                run_monitor()
                break  # clean exit (KeyboardInterrupt/SystemExit)
            except (KeyboardInterrupt, SystemExit):
                logger.info("Worker stopped by signal")
                break
            except Exception:
                restarts += 1
                logger.exception(
                    "Worker crashed (restart %d/%d) — restarting in %ds",
                    restarts, MAX_RESTARTS, RESTART_DELAY_SECONDS,
                )
                if restarts < MAX_RESTARTS:
                    time.sleep(RESTART_DELAY_SECONDS)

        if restarts >= MAX_RESTARTS:
            logger.critical("Worker exceeded %d restarts — exiting", MAX_RESTARTS)
            sys.exit(1)


if __name__ == "__main__":
    main()
