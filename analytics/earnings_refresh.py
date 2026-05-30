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


# Sentinel symbol used on the per-day digest marker so the unique
# constraint (user_id, symbol, earnings_date, kind) gives us exactly one
# digest per (user, day). The marker's earnings_date stores today's date
# (the day the digest covers), not any real symbol's earnings date.
_DIGEST_SENTINEL_SYMBOL = "__DIGEST__"


def _format_digest_message(rows: list[tuple], today: date) -> tuple[str, str, str]:
    """Build the daily earnings-this-week digest.

    `rows` is a list of (symbol, next_earnings_date, time_of_day, eps_estimate)
    sorted by next_earnings_date ASC.

    Returns (telegram_body, push_title, push_body).
    """
    lines = []
    for symbol, edate, tod, eps in rows:
        days_until = (edate - today).days
        when = "today" if days_until == 0 else (
            "tomorrow" if days_until == 1 else f"in {days_until}d"
        )
        day_str = edate.strftime("%a %b %d")
        tod_str = tod or "TBD"
        eps_str = f" · EPS est ${eps:.2f}" if eps is not None else ""
        lines.append(f"• <b>{symbol}</b> — {day_str} {tod_str}{eps_str} <i>({when})</i>")

    n = len(rows)
    sym_word = "symbol" if n == 1 else "symbols"
    body = (
        f"📅 <b>Earnings this week ({n} {sym_word})</b>\n\n"
        + "\n".join(lines)
        + "\n\nPre-earnings drift window — watch for trend acceleration or fade."
    )

    push_title = f"Earnings this week ({n} {sym_word})"
    # Push gets a short comma list — APNs body is best kept under ~150 chars.
    push_body = ", ".join(s for s, *_ in rows)
    return body, push_title, push_body


def _send_weekly_digest(session, today: date) -> int:
    """Send a per-user digest listing every watchlist symbol reporting
    in the next 0-7 days. One Telegram + push per user per day.

    Idempotency: marker row (user_id, symbol=__DIGEST__, earnings_date=today,
    kind="weekly_digest"). Same user re-running the job on the same day
    is a no-op.
    """
    from app.models.user import User
    from app.models.watchlist import WatchlistItem
    from app.models.earnings import Earnings, EarningsNotificationSent
    from app.models.device_token import DeviceToken
    from alerting.notifier import _send_telegram_to
    from app.services.push_service import send_push_sync

    window_end = today + timedelta(days=7)

    # Per user, collect their in-window earnings rows.
    # One query, grouped in Python — cheap at this scale.
    rows = session.execute(
        select(
            User.id, User.telegram_chat_id, User.telegram_enabled, User.push_enabled,
            Earnings.symbol, Earnings.next_earnings_date,
            Earnings.time_of_day, Earnings.eps_estimate,
        )
        .join(WatchlistItem, WatchlistItem.user_id == User.id)
        .join(Earnings, Earnings.symbol == WatchlistItem.symbol)
        .where(
            Earnings.next_earnings_date >= today,
            Earnings.next_earnings_date <= window_end,
        )
        .order_by(User.id, Earnings.next_earnings_date)
    ).all()

    if not rows:
        return 0

    # Group by user_id, preserving date sort within each group.
    by_user: dict[int, dict] = {}
    for uid, chat, tg_on, push_on, sym, edate, tod, eps in rows:
        u = by_user.setdefault(uid, {
            "chat": chat, "tg_on": tg_on, "push_on": push_on, "rows": []
        })
        u["rows"].append((sym, edate, tod, eps))

    sent = 0
    for uid, u in by_user.items():
        # Idempotency: did this user already get today's digest?
        already = session.execute(
            select(EarningsNotificationSent).where(
                EarningsNotificationSent.user_id == uid,
                EarningsNotificationSent.symbol == _DIGEST_SENTINEL_SYMBOL,
                EarningsNotificationSent.earnings_date == today,
                EarningsNotificationSent.kind == "weekly_digest",
            )
        ).scalar_one_or_none()
        if already:
            continue

        tg_body, push_title, push_body = _format_digest_message(u["rows"], today)

        # Telegram.
        if u["tg_on"] and u["chat"]:
            try:
                _send_telegram_to(tg_body, u["chat"], parse_mode="HTML")
            except Exception:
                logger.exception("Weekly digest telegram failed for user %d", uid)

        # Push.
        if u["push_on"]:
            tokens = [t.token for t in session.execute(
                select(DeviceToken).where(
                    DeviceToken.user_id == uid,
                    DeviceToken.is_active == True,  # noqa: E712
                )
            ).scalars().all()]
            if tokens:
                try:
                    send_push_sync(tokens, push_title, push_body)
                except Exception:
                    logger.exception("Weekly digest push failed for user %d", uid)

        try:
            session.add(EarningsNotificationSent(
                user_id=uid,
                symbol=_DIGEST_SENTINEL_SYMBOL,
                earnings_date=today,
                kind="weekly_digest",
            ))
            session.flush()
            sent += 1
        except IntegrityError:
            session.rollback()

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
        "weekly_digests": 0,
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

        # Now fire the daily "earnings this week" digest using the fresh data.
        try:
            summary["weekly_digests"] = _send_weekly_digest(session, today)
            session.commit()
        except Exception:
            logger.exception("Weekly digest pass failed")
            session.rollback()

    logger.info(
        "Earnings refresh complete: %d symbols, %d fetch failures, %d new history rows, %d weekly digests sent",
        summary["symbols"], summary["fetch_failures"],
        summary["new_history_rows"], summary["weekly_digests"],
    )
    return summary
