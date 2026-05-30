"""Earnings refresh job — runs nightly @ 04:00 ET via APScheduler.

Three responsibilities:
  1. Pull distinct watchlist symbols across all users.
  2. For each: fetch upcoming earnings + last 4 historical quarters
     from Finnhub. Upsert both tables.
  3. After upsert, look for any (user, symbol) where the symbol's
     next_earnings_date == today + 7 and the (user, symbol, date, 't7')
     marker doesn't exist yet → send Telegram + push, insert marker.

Idempotent: re-running the same night produces identical DB state and
zero duplicate notifications (unique constraint on the marker table).

Failure mode: any single symbol that Finnhub can't resolve is logged
and skipped — the rest of the run continues.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from analytics.earnings_fetcher import (
    fetch_historical_earnings,
    fetch_upcoming_earnings,
)


logger = logging.getLogger(__name__)


def _distinct_watchlist_symbols(session) -> list[str]:
    from app.models.watchlist import WatchlistItem

    rows = session.execute(
        select(WatchlistItem.symbol).distinct()
    ).all()
    return sorted({r[0].upper() for r in rows if r[0]})


def _upsert_earnings(session, upcoming) -> None:
    """Replace the single upcoming row for this symbol. Postgres uses
    ON CONFLICT DO UPDATE; the wrapper translates correctly for SQLite
    via PostgresConnectionWrapper.
    """
    from app.models.earnings import Earnings

    existing = session.get(Earnings, upcoming.symbol)
    if existing:
        existing.next_earnings_date = upcoming.next_earnings_date
        existing.time_of_day = upcoming.time_of_day
        existing.eps_estimate = upcoming.eps_estimate
        existing.revenue_estimate = upcoming.revenue_estimate
        existing.confirmed = upcoming.confirmed
        from datetime import datetime as _dt
        existing.fetched_at = _dt.utcnow()
    else:
        session.add(Earnings(
            symbol=upcoming.symbol,
            next_earnings_date=upcoming.next_earnings_date,
            time_of_day=upcoming.time_of_day,
            eps_estimate=upcoming.eps_estimate,
            revenue_estimate=upcoming.revenue_estimate,
            confirmed=upcoming.confirmed,
        ))


def _insert_history(session, history_rows) -> int:
    """Insert any new (symbol, quarter_label) rows. Returns count inserted.
    Skips duplicates silently via INSERT IGNORE pattern.
    """
    from app.models.earnings import EarningsHistory

    inserted = 0
    for h in history_rows:
        exists = session.get(EarningsHistory, (h.symbol, h.quarter_label))
        if exists:
            continue
        session.add(EarningsHistory(
            symbol=h.symbol,
            quarter_label=h.quarter_label,
            eps_actual=h.eps_actual,
            eps_estimate=h.eps_estimate,
            surprise_pct=h.surprise_pct,
            reported_at=h.reported_at,
        ))
        inserted += 1
    return inserted


def _format_t7_message(symbol: str, e) -> tuple[str, str]:
    """Returns (telegram_body, push_title, push_body). The earnings row
    `e` is the upserted Earnings record.
    """
    day = e.next_earnings_date.strftime("%a %b %d") if e.next_earnings_date else "TBD"
    tod = e.time_of_day or "TBD"
    est_str = f" EPS est ${e.eps_estimate:.2f}." if e.eps_estimate is not None else ""
    body = (
        f"📅 <b>{symbol}</b> reports in 7 days "
        f"({day} {tod}).{est_str}\n"
        f"Pre-earnings drift window opens — watch for trend acceleration."
    )
    push_title = f"{symbol} earnings in 7 days"
    push_body = f"{day} {tod}.{est_str.strip()}"
    return body, push_title, push_body


def _send_t7_notifications(session, today: date) -> int:
    """Find watchlist symbols whose earnings is exactly 7 days out and
    fire Telegram + push for the user(s) holding them. Returns count sent.
    """
    from app.models.user import User
    from app.models.watchlist import WatchlistItem
    from app.models.earnings import Earnings, EarningsNotificationSent
    from app.models.device_token import DeviceToken
    from alerting.notifier import _send_telegram_to
    from app.services.push_service import send_push_sync

    target_date = today + timedelta(days=7)

    # Symbols hitting T-7 today.
    earnings_rows = session.execute(
        select(Earnings).where(Earnings.next_earnings_date == target_date)
    ).scalars().all()
    if not earnings_rows:
        return 0

    sent = 0
    for e in earnings_rows:
        # Who's watching this symbol?
        users = session.execute(
            select(User)
            .join(WatchlistItem, WatchlistItem.user_id == User.id)
            .where(WatchlistItem.symbol == e.symbol)
            .distinct()
        ).scalars().all()
        if not users:
            continue

        tg_body, push_title, push_body = _format_t7_message(e.symbol, e)

        for user in users:
            # Idempotency check.
            already = session.execute(
                select(EarningsNotificationSent).where(
                    EarningsNotificationSent.user_id == user.id,
                    EarningsNotificationSent.symbol == e.symbol,
                    EarningsNotificationSent.earnings_date == e.next_earnings_date,
                    EarningsNotificationSent.kind == "t7",
                )
            ).scalar_one_or_none()
            if already:
                continue

            # Telegram.
            if user.telegram_enabled and user.telegram_chat_id:
                try:
                    _send_telegram_to(tg_body, user.telegram_chat_id, parse_mode="HTML")
                except Exception:
                    logger.exception("T-7 telegram send failed for user %d / %s", user.id, e.symbol)

            # Push.
            if user.push_enabled:
                tokens = [t.token for t in session.execute(
                    select(DeviceToken).where(
                        DeviceToken.user_id == user.id,
                        DeviceToken.is_active == True,  # noqa: E712
                    )
                ).scalars().all()]
                if tokens:
                    try:
                        send_push_sync(tokens, push_title, push_body)
                    except Exception:
                        logger.exception("T-7 push failed for user %d / %s", user.id, e.symbol)

            # Insert marker so we never fire this again.
            try:
                session.add(EarningsNotificationSent(
                    user_id=user.id,
                    symbol=e.symbol,
                    earnings_date=e.next_earnings_date,
                    kind="t7",
                ))
                session.flush()
                sent += 1
            except IntegrityError:
                session.rollback()  # already exists — race or re-run, fine

    return sent


def refresh_earnings(session_factory) -> dict:
    """Entrypoint for the APScheduler cron. Returns a summary dict for
    logging.
    """
    today = date.today()
    summary = {
        "symbols": 0,
        "fetch_failures": 0,
        "new_history_rows": 0,
        "t7_notifications": 0,
    }

    with session_factory() as session:
        symbols = _distinct_watchlist_symbols(session)
        summary["symbols"] = len(symbols)
        if not symbols:
            logger.info("Earnings refresh: no watchlist symbols, exiting")
            return summary

        for symbol in symbols:
            try:
                upcoming = fetch_upcoming_earnings(symbol)
                if upcoming and upcoming.next_earnings_date:
                    _upsert_earnings(session, upcoming)
                history = fetch_historical_earnings(symbol, limit=4)
                if history:
                    summary["new_history_rows"] += _insert_history(session, history)
            except Exception:
                summary["fetch_failures"] += 1
                logger.exception("Earnings fetch failed for %s — continuing", symbol)

        session.commit()

        # Now fire T-7 notifications using the fresh data.
        try:
            summary["t7_notifications"] = _send_t7_notifications(session, today)
            session.commit()
        except Exception:
            logger.exception("T-7 notification pass failed")
            session.rollback()

    logger.info(
        "Earnings refresh complete: %d symbols, %d fetch failures, %d new history rows, %d T-7 sent",
        summary["symbols"], summary["fetch_failures"],
        summary["new_history_rows"], summary["t7_notifications"],
    )
    return summary
