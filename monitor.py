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
from datetime import datetime

from alert_config import (
    COOLDOWN_MINUTES,
    POLL_INTERVAL_MINUTES,
)
from analytics.market_hours import is_market_hours
from config import is_crypto_alert_symbol
from alerting.alert_store import (
    close_all_entries_for_symbol,
    create_active_entry,
    get_active_cooldowns,
    get_active_entries,
    get_alerts_today,
    record_alert,
    save_cooldown,
    today_session,
    update_monitor_status,
    was_alert_fired,
)
from alerting.narrator import generate_narrative
from alerting.notifier import notify, notify_user, send_email, send_sms
from alerting.paper_trader import (
    close_position as paper_close_position,
    is_enabled as paper_trading_enabled,
    place_bracket_order,
    sync_open_trades,
)
from analytics.intraday_data import fetch_intraday, fetch_intraday_crypto, fetch_prior_day, get_spy_context
from analytics.intraday_rules import AlertSignal, AlertType, evaluate_rules
from db import (
    init_db,
    get_all_daily_plans,
    get_all_watchlist_symbols,
    get_daily_plan,
    get_notification_prefs,
    get_user_tier,
    get_users_for_symbol,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("monitor")

# Module-level state for auto stop-out tracking (cooldowns are DB-persisted)
_auto_stop_entries: dict[str, dict] = {}  # {symbol: {entry_price, stop_price, alert_type}}
_auto_stop_session: str = ""  # session date when entries were created

# Tracks which date we last ran the EOD swing scan for
_eod_ran_date: str | None = None


def poll_cycle(dry_run: bool = False, symbols_override: list[str] | None = None) -> int:
    """Run one poll cycle: fetch data, evaluate rules, send notifications.

    Args:
        dry_run: If True, print results but don't send notifications.
        symbols_override: If provided, poll only these symbols instead of the full watchlist.

    Returns the number of alerts fired.
    """
    global _auto_stop_session
    session = today_session()
    total_alerts = 0

    # Clear stale auto-stop entries from previous sessions
    if _auto_stop_session != session:
        _auto_stop_entries.clear()
        _auto_stop_session = session
        logger.info("New session %s — cleared stale auto-stop entries", session)

    # Sync paper trades with Alpaca (bracket legs may have filled between polls)
    if not dry_run and paper_trading_enabled():
        sync_open_trades()

    symbols = symbols_override if symbols_override is not None else get_all_watchlist_symbols()

    # Seed daily plans if none exist for today's session (ensures plans exist
    # even if nobody opened the Scanner page before the monitor started).
    existing_plans = get_all_daily_plans(session)
    if not existing_plans:
        logger.info("No daily plans for %s — seeding via scan_watchlist()", session)
        try:
            from analytics.signal_engine import scan_watchlist
            scan_watchlist(symbols)
        except Exception:
            logger.exception("Failed to seed daily plans")

    cooled_symbols = get_active_cooldowns(session)

    # Build fired_today from DB so evaluate_rules() filters already-fired signals
    db_alerts = get_alerts_today(session)
    fired_today: set[tuple[str, str]] = {
        (a["symbol"], a["alert_type"]) for a in db_alerts
    }

    # After a stop-out + cooldown expiry, allow BUY signals to re-fire.
    # Identify symbols that were stopped out and whose cooldown has expired.
    _stop_types = {"stop_loss_hit", "auto_stop_out"}
    stopped_symbols = {
        a["symbol"] for a in db_alerts if a["alert_type"] in _stop_types
    }
    # For stopped symbols no longer in cooldown, remove BUY alerts from dedup
    _sell_types = _stop_types | {
        "target_1_hit", "target_2_hit", "support_breakdown",
        "resistance_prior_high", "resistance_prior_low",
        "hourly_resistance_approach", "ma_resistance",
        "weekly_high_resistance", "ema_resistance",
        "opening_range_breakdown",
    }
    for sym in stopped_symbols:
        if sym not in cooled_symbols:
            fired_today = {
                (s, at) for s, at in fired_today
                if s != sym or at in _sell_types
            }

    for symbol in symbols:
        try:
            _is_crypto = is_crypto_alert_symbol(symbol)
            intraday = fetch_intraday_crypto(symbol) if _is_crypto else fetch_intraday(symbol)
            prior_day = fetch_prior_day(symbol, is_crypto=_is_crypto)

            if intraday.empty:
                logger.warning("%s: no intraday data", symbol)
                continue

            active = get_active_entries(symbol, session)
            spy_ctx = None if _is_crypto else get_spy_context()
            plan = get_daily_plan(symbol, session)
            signals = evaluate_rules(
                symbol, intraday, prior_day, active,
                spy_context=spy_ctx,
                auto_stop_entries=_auto_stop_entries.get(symbol),
                is_cooled_down=symbol in cooled_symbols,
                fired_today=fired_today,
                daily_plan=plan,
                is_crypto=_is_crypto,
            )

            for signal in signals:
                signal.narrative = generate_narrative(signal)

                if dry_run:
                    if was_alert_fired(symbol, signal.alert_type.value, session):
                        continue
                    logger.info(
                        "[DRY RUN] %s %s %s @ $%.2f — %s",
                        signal.direction, signal.symbol, signal.alert_type.value,
                        signal.price, signal.message,
                    )
                    total_alerts += 1
                    continue

                if was_alert_fired(symbol, signal.alert_type.value, session):
                    logger.debug("%s: dedup skip %s", symbol, signal.alert_type.value)
                    continue

                # Per-user notify_user() handles all notifications below;
                # the old global notify() sent duplicates to the same chat ID.
                email_sent, sms_sent = False, False

                # Per-user: record alert, entries, cooldowns, and notifications
                _non_entry_types = {AlertType.GAP_FILL, AlertType.SUPPORT_BREAKDOWN, AlertType.RESISTANCE_PRIOR_HIGH, AlertType.HOURLY_RESISTANCE_APPROACH, AlertType.MA_RESISTANCE, AlertType.RESISTANCE_PRIOR_LOW, AlertType.OPENING_RANGE_BREAKDOWN}
                alert_id = None
                for uid in get_users_for_symbol(symbol):
                    alert_id = record_alert(signal, session, email_sent, sms_sent, user_id=uid)

                    if signal.direction == "BUY" and signal.alert_type not in _non_entry_types:
                        create_active_entry(signal, session, user_id=uid)

                    if signal.alert_type in (AlertType.STOP_LOSS_HIT, AlertType.AUTO_STOP_OUT):
                        close_all_entries_for_symbol(symbol, session, user_id=uid)
                        save_cooldown(symbol, COOLDOWN_MINUTES, reason=signal.alert_type.value, session_date=session, user_id=uid)

                    if signal.alert_type in (AlertType.TARGET_1_HIT, AlertType.TARGET_2_HIT):
                        close_all_entries_for_symbol(symbol, session, user_id=uid)

                    # Per-user DM (Pro/Elite/Admin)
                    tier = get_user_tier(uid)
                    if tier in ("pro", "elite", "admin"):
                        prefs = get_notification_prefs(uid)
                        if prefs:
                            notify_user(signal, prefs)

                fired_today.add((symbol, signal.alert_type.value))
                total_alerts += 1

                logger.info(
                    "ALERT: %s %s %s @ $%.2f (email=%s, sms=%s)",
                    signal.direction, signal.symbol, signal.alert_type.value,
                    signal.price, email_sent, sms_sent,
                )

                # Module-level auto-stop tracking (for evaluate_rules)
                if signal.direction == "BUY" and signal.alert_type not in _non_entry_types:
                    if signal.entry and signal.stop:
                        _auto_stop_entries[symbol] = {
                            "entry_price": signal.entry,
                            "stop_price": signal.stop,
                            "alert_type": signal.alert_type.value,
                        }
                    if paper_trading_enabled():
                        place_bracket_order(signal, alert_id=alert_id)

                # Stop loss / auto stop-out: clear auto-stop tracking + paper
                if signal.alert_type in (AlertType.STOP_LOSS_HIT, AlertType.AUTO_STOP_OUT):
                    _auto_stop_entries.pop(symbol, None)
                    if paper_trading_enabled():
                        paper_close_position(symbol, exit_price=signal.price, reason=signal.alert_type.value)

                # Target hit: close paper position
                if signal.alert_type in (AlertType.TARGET_1_HIT, AlertType.TARGET_2_HIT):
                    if paper_trading_enabled():
                        paper_close_position(symbol, exit_price=signal.price, reason=signal.alert_type.value)

                # Resistance SELL signals: close paper position (exit long)
                _exit_long_types = {
                    AlertType.RESISTANCE_PRIOR_LOW,
                    AlertType.RESISTANCE_PRIOR_HIGH,
                    AlertType.SUPPORT_BREAKDOWN,
                    AlertType.OPENING_RANGE_BREAKDOWN,
                }
                if signal.direction == "SELL" and signal.alert_type in _exit_long_types:
                    if paper_trading_enabled():
                        paper_close_position(symbol, exit_price=signal.price, reason=signal.alert_type.value)

        except Exception:
            logger.exception("Error processing %s", symbol)

    if not dry_run:
        update_monitor_status(len(symbols), total_alerts, "running")

    return total_alerts


def _maybe_run_eod() -> None:
    """Run swing EOD scan once per session, after market close on weekdays."""
    global _eod_ran_date
    import pytz

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

    # EOD AI Review
    try:
        from analytics.eod_review import send_eod_review
        send_eod_review()
    except Exception:
        logger.exception("EOD review failed")

    # Weekly AI Journal — send on Sundays after market close
    try:
        import pytz as _pytz
        now_et = datetime.now(_pytz.timezone("US/Eastern"))
        if now_et.weekday() == 6:  # Sunday
            from analytics.journal_insights import send_weekly_journals
            send_weekly_journals()
    except Exception:
        logger.exception("Weekly journal failed")


def run_monitor():
    """Start the APScheduler-based monitor loop."""
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler()

    def scheduled_poll():
        # Pre-market brief: send once between 9:10-9:29 AM ET
        try:
            from analytics.market_hours import is_premarket
            if is_premarket():
                import pytz as _pytz
                now_et = datetime.now(_pytz.timezone("US/Eastern"))
                if now_et.hour == 9 and now_et.minute >= 10:
                    from analytics.premarket_brief import (
                        send_premarket_brief,
                        send_ai_premarket_brief,
                    )
                    send_premarket_brief()
                    # AI game plan for Pro/Elite users (after data brief)
                    try:
                        send_ai_premarket_brief()
                    except Exception:
                        logger.exception("AI pre-market brief failed")
        except Exception:
            logger.exception("Pre-market brief failed")

        if not is_market_hours():
            _maybe_run_eod()
            # Outside market hours: still poll crypto symbols if any exist
            all_symbols = get_all_watchlist_symbols()
            crypto_symbols = [s for s in all_symbols if is_crypto_alert_symbol(s)]
            if crypto_symbols:
                logger.info("Market closed — polling crypto only: %s", ", ".join(crypto_symbols))
                alerts = poll_cycle(symbols_override=crypto_symbols)
                logger.info("Crypto poll complete: %d alerts fired", alerts)
            else:
                logger.info("Market closed — skipping poll")
                update_monitor_status(0, 0, "market_closed")
            return
        alerts = poll_cycle()
        logger.info("Poll complete: %d alerts fired", alerts)

        # Position advisor: send updates hourly during market hours
        try:
            import pytz as _pytz
            now_et = datetime.now(_pytz.timezone("US/Eastern"))
            if now_et.minute < POLL_INTERVAL_MINUTES + 1:  # ~top of hour
                from analytics.position_advisor import send_position_updates
                send_position_updates()
        except Exception:
            logger.exception("Position advisor failed")

    # Run immediately on start
    watchlist = get_all_watchlist_symbols()
    logger.info("Starting monitor — watchlist: %s", ", ".join(watchlist))
    logger.info("Poll interval: %d minutes", POLL_INTERVAL_MINUTES)

    if is_market_hours():
        poll_cycle()
    else:
        crypto_symbols = [s for s in watchlist if is_crypto_alert_symbol(s)]
        if crypto_symbols:
            logger.info("Market closed — initial crypto poll: %s", ", ".join(crypto_symbols))
            poll_cycle(symbols_override=crypto_symbols)
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
