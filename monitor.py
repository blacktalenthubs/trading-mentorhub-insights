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
    AI_CONVICTION_BOOST_ABOVE,
    AI_CONVICTION_BOOST_POINTS,
    AI_CONVICTION_ENABLED,
    AI_CONVICTION_SUPPRESS_BELOW,
    BUY_BURST_COOLDOWN_MINUTES,
    COOLDOWN_MINUTES,
    CRYPTO_TELEGRAM_END_HOUR,
    CRYPTO_TELEGRAM_START_HOUR,
    POLL_INTERVAL_MINUTES,
)

# Feature-flagged AI conviction filter
_ai_conviction_enabled = AI_CONVICTION_ENABLED
_ai_suppress_below = AI_CONVICTION_SUPPRESS_BELOW
_ai_boost_above = AI_CONVICTION_BOOST_ABOVE
_ai_boost_pts = AI_CONVICTION_BOOST_POINTS
from analytics.market_hours import is_market_hours
from config import is_crypto_alert_symbol
from alerting.alert_store import (
    close_all_entries_for_symbol,
    create_active_entry,
    get_active_cooldowns,
    get_active_entries,
    get_alerts_today,
    has_acked_entry,
    record_alert,
    save_cooldown,
    today_session,
    update_alert_notification,
    update_monitor_status,
    user_has_used_ack,
    was_alert_fired,
)
from alerting.narrator import generate_narrative
from alerting.notifier import notify, send_email, send_sms
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
    get_watchlist,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("monitor")

def _is_crypto_telegram_hours() -> bool:
    """Return True if current time is within crypto Telegram notification window (Central Time)."""
    try:
        import pytz
        ct = datetime.now(pytz.timezone("US/Central"))
        return CRYPTO_TELEGRAM_START_HOUR <= ct.hour < CRYPTO_TELEGRAM_END_HOUR
    except Exception:
        return True  # fail-open: send if timezone check fails


# Burst cooldown: last BUY notification time per symbol (in-memory, resets on restart)
_last_buy_notify: dict[str, datetime] = {}  # {symbol: datetime}
_last_buy_session: str = ""  # session date for clearing stale state
_spy_inside_day_notified: bool = False  # track if we sent inside day notice this session

# Tracks which date we last ran the EOD swing scan for
_eod_ran_date: str | None = None

# Single-user mode: resolve admin user ID once (lazy)
_ADMIN_UID: int | None = None


def _get_admin_uid() -> int:
    """Return the admin user ID, resolved once and cached.

    Uses ADMIN_EMAIL env var to find the correct user.  Falls back to
    the first user in the DB if not set.
    """
    global _ADMIN_UID
    if _ADMIN_UID is None:
        import os
        from db import get_db
        admin_email = os.environ.get("ADMIN_EMAIL", "vbolofinde@gmail.com")
        with get_db() as conn:
            row = conn.execute(
                "SELECT id, email FROM users WHERE email = ? LIMIT 1",
                (admin_email,),
            ).fetchone()
            if row is None:
                row = conn.execute("SELECT id, email FROM users ORDER BY id LIMIT 1").fetchone()
            _ADMIN_UID = row["id"] if row else 1
            _email = row["email"] if row else "unknown"
            logger.info("Admin UID resolved: %d (email=%s, ADMIN_EMAIL=%s)", _ADMIN_UID, _email, admin_email or "<not set>")
    return _ADMIN_UID


def poll_cycle(dry_run: bool = False, symbols_override: list[str] | None = None) -> int:
    """Run one poll cycle: fetch data, evaluate rules, send notifications.

    Args:
        dry_run: If True, print results but don't send notifications.
        symbols_override: If provided, poll only these symbols instead of the full watchlist.

    Returns the number of alerts fired.
    """
    global _last_buy_session
    session = today_session()
    total_alerts = 0

    global _spy_inside_day_notified
    # Clear stale tracking from previous sessions
    if _last_buy_session != session:
        _last_buy_notify.clear()
        _spy_inside_day_notified = False
        _last_buy_session = session

    # Sync paper trades with Alpaca (bracket legs may have filled between polls)
    if not dry_run and paper_trading_enabled():
        sync_open_trades()

    symbols = symbols_override if symbols_override is not None else get_watchlist(_get_admin_uid())
    logger.info("Poll cycle symbols (uid=%d): %s", _get_admin_uid(), ", ".join(symbols))

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
    _stop_types = {"stop_loss_hit"}
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

    # Check once whether this user has started using ACK buttons
    uid = _get_admin_uid()
    _ack_active = user_has_used_ack(uid)

    # Regime narrator: check for SPY regime shift (once per poll cycle)
    if not dry_run:
        try:
            _regime_spy_ctx = get_spy_context()
            from analytics.regime_narrator import check_regime_shift
            check_regime_shift(_regime_spy_ctx)
        except Exception:
            logger.debug("Regime narrator check failed, proceeding")

    # SPY Gate: compute once per poll cycle, pass to all evaluate_rules calls
    _spy_gate = None
    try:
        from analytics.intraday_rules import compute_spy_gate
        from analytics.intraday_data import compute_vwap, compute_opening_range
        _spy_bars = fetch_intraday("SPY")
        if not _spy_bars.empty:
            _spy_vwap = compute_vwap(_spy_bars)
            _spy_gate = compute_spy_gate(_spy_bars, _spy_vwap)

            # Morning low check: is SPY currently below its first-hour low?
            _spy_or = compute_opening_range(_spy_bars)
            if _spy_or and _spy_or.get("or_complete"):
                _spy_morning_low = _spy_or["or_low"]
                _spy_last_close = float(_spy_bars.iloc[-1]["Close"])
                _spy_below_morning_low = _spy_last_close < _spy_morning_low
                _spy_gate["morning_low"] = _spy_morning_low
                _spy_gate["below_morning_low"] = _spy_below_morning_low
            else:
                _spy_gate["below_morning_low"] = False
                _spy_gate["morning_low"] = 0

            # SPY inside day check: after morning range forms (6+ bars = 30 min),
            # if SPY is still within yesterday's range, it's an inside day.
            # Every day starts "inside" until price breaks out, so we wait for
            # the opening range to confirm.
            _spy_inside_day = False
            try:
                _spy_prior = fetch_prior_day("SPY")
                if _spy_prior and len(_spy_bars) >= 6:  # wait for opening range
                    _spy_pdh = _spy_prior.get("high", 0)
                    _spy_pdl = _spy_prior.get("low", 0)
                    _spy_session_high = float(_spy_bars["High"].max())
                    _spy_session_low = float(_spy_bars["Low"].min())
                    if _spy_pdh > 0 and _spy_pdl > 0:
                        _spy_inside_day = _spy_session_high < _spy_pdh and _spy_session_low > _spy_pdl
            except Exception:
                pass
            _spy_gate["inside_day"] = _spy_inside_day

            # Send one-time Telegram notice when SPY inside day is first detected
            if _spy_inside_day and not _spy_inside_day_notified:
                _spy_inside_day_notified = True
                try:
                    from alerting.notifier import _send_telegram
                    _id_range = f"${_spy_pdl:.2f} – ${_spy_pdh:.2f}"
                    _send_telegram(
                        f"<b>NOTICE — SPY INSIDE DAY</b>\n"
                        f"Trading within yesterday's range {_id_range}\n"
                        f"Other equity alerts suppressed until breakout"
                    )
                    logger.info("SPY inside day notice sent")
                except Exception:
                    logger.debug("Failed to send SPY inside day notice")

            _ml_status = "BELOW" if _spy_gate["below_morning_low"] else "ABOVE"
            _id_status = " | INSIDE DAY" if _spy_inside_day else ""
            logger.info(
                "SPY Gate: %s (VWAP dom %.0f%%, EMA %s) | Morning Low: %s $%.2f%s — %s",
                _spy_gate["gate"].upper(),
                _spy_gate["vwap_dominance"] * 100,
                "above" if _spy_gate["above_ema"] else "below",
                _ml_status,
                _spy_gate.get("morning_low", 0),
                _id_status,
                _spy_gate["reason"],
            )
    except Exception:
        logger.debug("SPY Gate computation failed, proceeding without gate")

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
                is_cooled_down=symbol in cooled_symbols,
                fired_today=fired_today,
                daily_plan=plan,
                is_crypto=_is_crypto,
                spy_gate=_spy_gate,
            )

            for signal in signals:
                # Gate: suppress SELL signals for un-ACK'd symbols (no position to exit)
                # NOTICE alerts are informational — always let them through
                if _ack_active and signal.direction == "SELL":
                    if not has_acked_entry(symbol, uid, session):
                        logger.debug("%s: suppressing SELL %s (not ACK'd)", symbol, signal.alert_type.value)
                        continue

                signal.narrative = generate_narrative(signal)

                # Cluster narrator: if signal has confirming signals, generate
                # a richer AI synthesis instead of the default narrative
                if "[+" in signal.message and "confirming:" in signal.message:
                    try:
                        import re
                        _match = re.search(r"\[\+\d+ confirming: (.+?)\]", signal.message)
                        if _match:
                            _conf_types = [t.strip() for t in _match.group(1).split(",")]
                            from analytics.cluster_narrator import narrate_cluster
                            _cluster_narrative = narrate_cluster(signal, _conf_types)
                            if _cluster_narrative:
                                signal.narrative = _cluster_narrative
                    except Exception:
                        logger.debug("%s: cluster narrator failed, using default", symbol)

                # AI Conviction Filter (feature-flagged)
                if _ai_conviction_enabled and signal.direction == "BUY":
                    try:
                        from analytics.ai_conviction import score_conviction
                        _conv, _reason = score_conviction(signal, spy_context=spy_ctx)
                        signal.ai_conviction = _conv
                        signal.ai_reasoning = _reason
                        if _conv < _ai_suppress_below:
                            logger.info(
                                "%s: AI conviction %d < %d — tagging LOW %s (%s)",
                                symbol, _conv, _ai_suppress_below,
                                signal.alert_type.value, _reason,
                            )
                            signal.message += f" | AI conviction LOW ({_conv})"
                        elif _conv >= _ai_boost_above:
                            signal.score = min(100, signal.score + _ai_boost_pts)
                            signal.score_v2 = min(100, signal.score_v2 + _ai_boost_pts)
                            signal.message += f" | AI conviction HIGH ({_conv})"
                        logger.info(
                            "%s: AI conviction=%d for %s: %s",
                            symbol, _conv, signal.alert_type.value, _reason[:80],
                        )
                    except Exception:
                        logger.debug("%s: AI conviction failed, proceeding", symbol)

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

                # Single-user mode: record alert + entries for admin uid
                _non_entry_types = {AlertType.GAP_FILL, AlertType.SUPPORT_BREAKDOWN, AlertType.RESISTANCE_PRIOR_HIGH, AlertType.HOURLY_RESISTANCE_APPROACH, AlertType.MA_RESISTANCE, AlertType.RESISTANCE_PRIOR_LOW, AlertType.OPENING_RANGE_BREAKDOWN}
                alert_id = record_alert(signal, session, False, False, user_id=uid)

                if alert_id is None:
                    logger.debug("%s: dedup (DB constraint) skip %s", symbol, signal.alert_type.value)
                    continue

                if signal.direction == "BUY" and signal.alert_type not in _non_entry_types:
                    # Only create entry if no active entry exists for this symbol
                    # Prevents multiple entries from consolidated signals
                    _existing_entries = get_active_entries(symbol, session, user_id=uid)
                    if not _existing_entries:
                        if not _ack_active:
                            create_active_entry(signal, session, user_id=uid)
                        # else: created on ACK callback
                    else:
                        logger.debug(
                            "%s: skip entry creation — already have %d active entries",
                            symbol, len(_existing_entries),
                        )

                if signal.alert_type == AlertType.STOP_LOSS_HIT:
                    close_all_entries_for_symbol(symbol, session, user_id=uid)
                    save_cooldown(symbol, COOLDOWN_MINUTES, reason=signal.alert_type.value, session_date=session, user_id=uid)

                if signal.alert_type in (AlertType.TARGET_1_HIT, AlertType.TARGET_2_HIT):
                    close_all_entries_for_symbol(symbol, session, user_id=uid)

                # Burst cooldown: skip Telegram for repeat BUY alerts on
                # the same symbol within BUY_BURST_COOLDOWN_MINUTES.
                # Alert is already saved to DB above — just suppress notification.
                _burst_suppressed = False
                if signal.direction == "BUY" and BUY_BURST_COOLDOWN_MINUTES > 0:
                    _prev = _last_buy_notify.get(symbol)
                    _now = datetime.utcnow()
                    if _prev and (_now - _prev).total_seconds() < BUY_BURST_COOLDOWN_MINUTES * 60:
                        _burst_suppressed = True
                        logger.info(
                            "BURST COOLDOWN: %s %s %s @ $%.2f — skipping notification (last BUY notify %ds ago)",
                            signal.direction, symbol, signal.alert_type.value,
                            signal.price, (_now - _prev).total_seconds(),
                        )

                # Crypto quiet hours: record to DB but skip Telegram outside US hours
                _crypto_quiet = _is_crypto and not _is_crypto_telegram_hours()
                if _crypto_quiet:
                    logger.info(
                        "%s: crypto quiet hours — %s recorded to DB (dashboard only)",
                        symbol, signal.alert_type.value,
                    )

                # Single group notification
                _telegram_muted = getattr(signal, "_suppress_telegram", False) or _crypto_quiet
                if _burst_suppressed or _telegram_muted:
                    email_sent, sms_sent = False, False
                    if _telegram_muted:
                        logger.info(
                            "%s: %s recorded to DB (Telegram muted — dashboard only)",
                            symbol, signal.alert_type.value,
                        )
                else:
                    email_sent, sms_sent = notify(signal, alert_id=alert_id)
                    if signal.direction == "BUY":
                        _last_buy_notify[symbol] = datetime.utcnow()
                update_alert_notification(alert_id, email_sent, sms_sent)

                fired_today.add((symbol, signal.alert_type.value))
                total_alerts += 1

                logger.info(
                    "ALERT: %s %s %s @ $%.2f (email=%s, sms=%s%s)",
                    signal.direction, signal.symbol, signal.alert_type.value,
                    signal.price, email_sent, sms_sent,
                    " [burst-suppressed]" if _burst_suppressed else "",
                )

                # Paper trading: place bracket order on BUY/SHORT entries
                if signal.direction in ("BUY", "SHORT") and signal.alert_type not in _non_entry_types:
                    if paper_trading_enabled():
                        place_bracket_order(signal, alert_id=alert_id)

                # Stop loss hit: close paper position
                if signal.alert_type == AlertType.STOP_LOSS_HIT:
                    if paper_trading_enabled():
                        paper_close_position(symbol, exit_price=signal.price, reason=signal.alert_type.value)

                # Target hit: close paper position
                if signal.alert_type in (AlertType.TARGET_1_HIT, AlertType.TARGET_2_HIT):
                    if paper_trading_enabled():
                        paper_close_position(symbol, exit_price=signal.price, reason=signal.alert_type.value)

                # Any SELL signal: close paper position (exit long)
                # Covers resistance, rejection, breakdown, trailing stop, etc.
                _exit_long_types = {
                    AlertType.RESISTANCE_PRIOR_LOW,
                    AlertType.RESISTANCE_PRIOR_HIGH,
                    AlertType.PDH_REJECTION,
                    AlertType.SUPPORT_BREAKDOWN,
                    AlertType.OPENING_RANGE_BREAKDOWN,
                    AlertType.MA_RESISTANCE,
                    AlertType.EMA_RESISTANCE,
                    AlertType.WEEKLY_HIGH_RESISTANCE,
                    AlertType.HOURLY_RESISTANCE_APPROACH,
                    AlertType.TRAILING_STOP_HIT,
                }
                if signal.direction == "SELL" and signal.alert_type in _exit_long_types:
                    if paper_trading_enabled():
                        paper_close_position(symbol, exit_price=signal.price, reason=signal.alert_type.value)

        except Exception:
            logger.exception("Error processing %s", symbol)

    if not dry_run:
        update_monitor_status(len(symbols), total_alerts, "running")

    # Exit Coach: DISABLED — focusing on entry quality. User exits via Telegram button.
    # Position updates also disabled. Will re-enable once entries are perfected.
    if False and not dry_run:
        try:
            from analytics.exit_coach import check_positions as exit_coach_check
            from analytics.intraday_data import compute_vwap

            # Build current prices and VWAPs from latest poll data
            _exit_prices = {}
            _exit_vwaps = {}
            for sym in symbols:
                try:
                    _bars = fetch_intraday_crypto(sym) if is_crypto_alert_symbol(sym) else fetch_intraday(sym)
                    if not _bars.empty:
                        _exit_prices[sym] = float(_bars.iloc[-1]["Close"])
                        _vwap_s = compute_vwap(_bars)
                        if not _vwap_s.empty:
                            _exit_vwaps[sym] = float(_vwap_s.iloc[-1])
                except Exception:
                    pass

            coach_msgs = exit_coach_check(
                symbols, session, user_id=uid,
                current_prices=_exit_prices,
                current_vwaps=_exit_vwaps,
            )
            if coach_msgs:
                logger.info("Exit coach: sent %d coaching messages", coach_msgs)
        except Exception:
            logger.debug("Exit coach check failed", exc_info=True)

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

    # Post-Market Performance Review (data-driven scorecard)
    try:
        from analytics.post_market_review import send_post_market_review
        send_post_market_review(user_id=_get_admin_uid())
    except Exception:
        logger.exception("Post-market review failed")

    # EOD AI Review
    try:
        from analytics.eod_review import send_eod_review
        send_eod_review()
    except Exception:
        logger.exception("EOD review failed")

    # EOD Cleanup: close all equity active entries for clean start tomorrow
    # Crypto entries persist (24h market). This ensures no stale positions
    # carry over and trigger ghost alerts the next morning.
    try:
        from db import get_db
        with get_db() as conn:
            cur = conn.execute(
                "DELETE FROM active_entries WHERE symbol NOT LIKE '%%-USD'"
            )
            equity_closed = cur.rowcount
            conn.commit()
        if equity_closed:
            logger.info("EOD cleanup: closed %d equity active entries", equity_closed)
    except Exception:
        logger.exception("EOD active entries cleanup failed")

    # EOD Cleanup: close stale open real trades for equities
    # Ensures trades page starts clean each morning.
    try:
        from db import get_db as _get_db2
        with _get_db2() as conn:
            cur = conn.execute(
                """UPDATE real_trades SET status = 'closed',
                   closed_at = CURRENT_TIMESTAMP,
                   notes = COALESCE(notes, '') || ' [auto-closed at EOD]'
                   WHERE status = 'open' AND symbol NOT LIKE '%%-USD'"""
            )
            trades_closed = cur.rowcount
            conn.commit()
        if trades_closed:
            logger.info("EOD cleanup: closed %d equity open trades", trades_closed)
    except Exception:
        logger.exception("EOD real trades cleanup failed")

    # Weekly Alert Tuning Report — send on Fridays after close
    try:
        import pytz as _pytz
        now_et = datetime.now(_pytz.timezone("US/Eastern"))
        if now_et.weekday() == 4:  # Friday
            from analytics.alert_tuner import send_weekly_tuning_report
            send_weekly_tuning_report()
    except Exception:
        logger.exception("Weekly tuning report failed")

    # Weekly AI Journal — send on Sundays after market close
    try:
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

        try:
            if not is_market_hours():
                _maybe_run_eod()
                # Outside market hours: still poll crypto symbols if any exist
                all_symbols = get_watchlist(_get_admin_uid())
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
            # Position updates DISABLED — focusing on entry quality testing
            # try:
            #     import pytz as _pytz
            #     now_et = datetime.now(_pytz.timezone("US/Eastern"))
            #     if now_et.minute < POLL_INTERVAL_MINUTES + 1:
            #         from analytics.position_advisor import send_position_updates
            #         send_position_updates()
            # except Exception:
            #     logger.exception("Position advisor failed")
            pass
        except Exception:
            logger.exception("CRITICAL: scheduled_poll failed — scheduler will retry next interval")

    # Run immediately on start
    watchlist = get_watchlist(_get_admin_uid())
    logger.info("Starting monitor — watchlist: %s", ", ".join(watchlist))
    logger.info("Poll interval: %d minutes", POLL_INTERVAL_MINUTES)

    try:
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
    except Exception:
        logger.exception("Initial poll failed — scheduler will handle retries")

    scheduler.add_job(scheduled_poll, "interval", minutes=POLL_INTERVAL_MINUTES)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Monitor stopped")
        update_monitor_status(0, 0, "stopped")


def run_test():
    """Send a test alert with ACK buttons to verify notification + button flow."""
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
        message="Test alert — tap Took It or Skip to test ACK flow",
    )

    # Record alert to get an ID for buttons
    uid = _get_admin_uid()
    session = today_session()
    alert_id = record_alert(test_signal, session, user_id=uid)
    logger.info("Recorded test alert_id=%s", alert_id)

    # Send with buttons
    email_ok, sms_ok = notify(test_signal, alert_id=alert_id)
    logger.info("Email: %s", "OK" if email_ok else "FAILED")
    logger.info("Telegram: %s", "OK" if sms_ok else "FAILED")


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
