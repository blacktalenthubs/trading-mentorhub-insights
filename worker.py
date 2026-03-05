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
        logger.info("Starting Railway alert monitor worker")
        run_monitor()


if __name__ == "__main__":
    main()
