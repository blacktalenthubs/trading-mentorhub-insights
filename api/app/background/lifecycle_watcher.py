"""Lifecycle watcher — Telegram notifications for T1/T2/stop hits on TV alerts.

Runs every ~5 minutes during US market hours. For each TV alert in the last
5 days where user_action='took', checks current price against entry/T1/T2/stop.
Fires ONE Telegram per outcome; stamps t1/t2/stop_notified_at to prevent re-fires.

Disabled by setting TV_LIFECYCLE_ALERTS_ENABLED=false in env.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

logger = logging.getLogger("lifecycle_watcher")

_LOOKBACK_DAYS = 5


def _fetch_last_prices(symbols: list[str]) -> dict[str, float]:
    """Fetch current prices via yfinance fast_info, one ticker at a time.

    Volume is small (handful of took trades) so per-symbol fetch is fine.
    """
    if not symbols:
        return {}

    import yfinance as yf

    out: dict[str, float] = {}
    for sym in symbols:
        try:
            info = yf.Ticker(sym).fast_info
            price = float(info.last_price)
            if price > 0:
                out[sym] = price
        except Exception:
            logger.debug("Lifecycle: price fetch failed for %s", sym, exc_info=True)
    return out


def check_lifecycle_outcomes(sync_session_factory) -> int:
    """Poll active took TV alerts and fire one-shot T1/T2/stop notifications.

    Returns count of notifications fired this cycle.
    """
    from app.config import get_settings
    settings = get_settings()
    if not settings.TV_LIFECYCLE_ALERTS_ENABLED:
        logger.debug("Lifecycle watcher disabled via TV_LIFECYCLE_ALERTS_ENABLED")
        return 0

    from app.models.alert import Alert
    from app.models.user import User
    from alerting.notifier import _send_telegram_to, format_lifecycle_message

    cutoff = datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)
    fired = 0

    with sync_session_factory() as db:
        active = db.execute(
            select(Alert).where(
                Alert.alert_type.like("tv_%"),
                Alert.user_action == "took",
                Alert.created_at >= cutoff,
                Alert.entry.isnot(None),
                Alert.stop.isnot(None),
            )
        ).scalars().all()

        pending = [
            a for a in active
            if (a.target_1 is not None and a.t1_notified_at is None)
            or (a.target_2 is not None and a.t2_notified_at is None)
            or (a.stop is not None and a.stop_notified_at is None)
        ]
        if not pending:
            return 0

        symbols = sorted({a.symbol for a in pending})
        prices = _fetch_last_prices(symbols)
        if not prices:
            logger.warning("Lifecycle: no prices fetched for %d symbols", len(symbols))
            return 0

        user_ids = {a.user_id for a in pending}
        user_rows = {
            u.id: u for u in db.execute(
                select(User).where(User.id.in_(user_ids))
            ).scalars().all()
        }

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

        for alert in pending:
            price = prices.get(alert.symbol)
            if price is None:
                continue

            user = user_rows.get(alert.user_id)
            if not user or not user.telegram_enabled or not user.telegram_chat_id:
                continue

            direction = (alert.direction or "BUY").upper()
            rule = (alert.alert_type or "").removeprefix("tv_") or "tv_alert"

            outcomes_to_fire: list[tuple[str, float, str]] = []  # (label, hit_price, column_name)

            if direction == "BUY":
                if alert.t1_notified_at is None and alert.target_1 and price >= alert.target_1:
                    outcomes_to_fire.append(("T1", alert.target_1, "t1_notified_at"))
                if alert.t2_notified_at is None and alert.target_2 and price >= alert.target_2:
                    outcomes_to_fire.append(("T2", alert.target_2, "t2_notified_at"))
                if alert.stop_notified_at is None and price <= alert.stop:
                    outcomes_to_fire.append(("STOP", alert.stop, "stop_notified_at"))
            else:  # SHORT
                if alert.t1_notified_at is None and alert.target_1 and price <= alert.target_1:
                    outcomes_to_fire.append(("T1", alert.target_1, "t1_notified_at"))
                if alert.t2_notified_at is None and alert.target_2 and price <= alert.target_2:
                    outcomes_to_fire.append(("T2", alert.target_2, "t2_notified_at"))
                if alert.stop_notified_at is None and price >= alert.stop:
                    outcomes_to_fire.append(("STOP", alert.stop, "stop_notified_at"))

            for label, hit_price, col in outcomes_to_fire:
                body = format_lifecycle_message(
                    outcome=label,
                    symbol=alert.symbol,
                    direction=direction,
                    entry=alert.entry,
                    stop=alert.stop,
                    hit_price=hit_price,
                    rule=rule,
                )
                # Exit button — telegram_bot.py:296 _handle_exit closes the
                # real_trade row and stops further lifecycle polling for this
                # alert. Without the button, the trader has to use /exit
                # SYMBOL PRICE manually, which they often miss.
                exit_buttons = {
                    "inline_keyboard": [[
                        {"text": "\U0001f6d1 Exit Trade", "callback_data": f"exit:{alert.id}"},
                    ]]
                }
                ok = _send_telegram_to(body, user.telegram_chat_id, reply_markup=exit_buttons)
                if ok:
                    setattr(alert, col, now_utc)
                    fired += 1
                    logger.info(
                        "Lifecycle: %s %s %s @ $%.2f notified user=%d",
                        alert.symbol, label, rule, hit_price, alert.user_id,
                    )
                else:
                    logger.warning(
                        "Lifecycle: telegram FAILED for user=%d alert=%d outcome=%s",
                        alert.user_id, alert.id, label,
                    )

        if fired:
            db.commit()

    return fired
