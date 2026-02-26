"""Standalone day-trade alert monitor.

Polls every 3 minutes during market hours, evaluates rules, sends notifications.

Usage:
    python monitor.py              # Run the live monitor
    python monitor.py --dry-run    # Fetch + evaluate, print results (no notifications)
    python monitor.py --test       # Send a test email + SMS and exit
"""

from __future__ import annotations

import argparse
import logging
import sys

from alert_config import (
    ALERT_WATCHLIST,
    POLL_INTERVAL_MINUTES,
)
from analytics.market_hours import is_market_hours
from alerting.alert_store import (
    close_all_entries_for_symbol,
    create_active_entry,
    get_active_entries,
    record_alert,
    today_session,
    update_monitor_status,
    was_alert_fired,
)
from alerting.notifier import notify, send_email, send_sms
from analytics.intraday_data import fetch_intraday, fetch_prior_day, get_spy_context
from analytics.intraday_rules import AlertSignal, AlertType, evaluate_rules
from db import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("monitor")


def poll_cycle(dry_run: bool = False) -> int:
    """Run one poll cycle: fetch data, evaluate rules, send notifications.

    Returns the number of alerts fired.
    """
    session = today_session()
    total_alerts = 0

    for symbol in ALERT_WATCHLIST:
        try:
            intraday = fetch_intraday(symbol)
            prior_day = fetch_prior_day(symbol)

            if intraday.empty:
                logger.warning("%s: no intraday data", symbol)
                continue

            active = get_active_entries(symbol, session)
            spy_ctx = get_spy_context()
            signals = evaluate_rules(symbol, intraday, prior_day, active, spy_context=spy_ctx)

            for signal in signals:
                # Dedup: skip if already fired today
                if was_alert_fired(symbol, signal.alert_type.value, session):
                    continue

                if dry_run:
                    logger.info(
                        "[DRY RUN] %s %s %s @ $%.2f — %s",
                        signal.direction, signal.symbol, signal.alert_type.value,
                        signal.price, signal.message,
                    )
                    total_alerts += 1
                    continue

                # Notify
                email_sent, sms_sent = notify(signal)

                # Record
                record_alert(signal, session, email_sent, sms_sent)

                # Track active entries for BUY signals
                if signal.direction == "BUY":
                    create_active_entry(signal, session)

                # Stop loss cancels all active entries for this symbol
                if signal.alert_type == AlertType.STOP_LOSS_HIT:
                    close_all_entries_for_symbol(symbol, session)

                logger.info(
                    "ALERT: %s %s %s @ $%.2f (email=%s, sms=%s)",
                    signal.direction, signal.symbol, signal.alert_type.value,
                    signal.price, email_sent, sms_sent,
                )
                total_alerts += 1

        except Exception:
            logger.exception("Error processing %s", symbol)

    if not dry_run:
        update_monitor_status(len(ALERT_WATCHLIST), total_alerts, "running")

    return total_alerts


def run_monitor():
    """Start the APScheduler-based monitor loop."""
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler()

    def scheduled_poll():
        if not is_market_hours():
            logger.info("Market closed — skipping poll")
            update_monitor_status(0, 0, "market_closed")
            return
        alerts = poll_cycle()
        logger.info("Poll complete: %d alerts fired", alerts)

    # Run immediately on start
    logger.info("Starting monitor — watchlist: %s", ", ".join(ALERT_WATCHLIST))
    logger.info("Poll interval: %d minutes", POLL_INTERVAL_MINUTES)

    if is_market_hours():
        poll_cycle()
    else:
        logger.info("Market closed — waiting for open")
        update_monitor_status(0, 0, "waiting_for_open")

    scheduler.add_job(scheduled_poll, "interval", minutes=POLL_INTERVAL_MINUTES)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Monitor stopped")
        update_monitor_status(0, 0, "stopped")


def run_test():
    """Send a test email and SMS to verify notification config."""
    test_signal = AlertSignal(
        symbol="TEST",
        alert_type=AlertType.MA_BOUNCE_20,
        direction="BUY",
        price=100.00,
        entry=100.00,
        stop=99.00,
        target_1=101.00,
        target_2=102.00,
        confidence="high",
        message="Test alert — ignore this message",
    )

    logger.info("Sending test email...")
    email_ok = send_email(test_signal)
    logger.info("Email: %s", "OK" if email_ok else "FAILED (check .env config)")

    logger.info("Sending test SMS...")
    sms_ok = send_sms(test_signal)
    logger.info("SMS: %s", "OK" if sms_ok else "FAILED (check .env config)")


def main():
    parser = argparse.ArgumentParser(description="Day-trade alert monitor")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch + evaluate, print results (no notifications)")
    parser.add_argument("--test", action="store_true",
                        help="Send test email + SMS and exit")
    args = parser.parse_args()

    init_db()

    if args.test:
        run_test()
    elif args.dry_run:
        logger.info("Dry run — fetching data and evaluating rules...")
        alerts = poll_cycle(dry_run=True)
        logger.info("Dry run complete: %d signals would fire", alerts)
    else:
        run_monitor()


if __name__ == "__main__":
    main()
