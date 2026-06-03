"""Per-user watchlist-buzz push.

When a stock on a user's watchlist enters the trending Social Buzz list or
spikes in mentions, notify that user (Telegram + push). Runs hourly, right
after the social-buzz refresh writes a new snapshot.

Per-(user, symbol, day) idempotent via the EarningsNotificationSent marker
(kind='watchlist_buzz') — that table carries user_id (unlike ScreenerAlertLog),
so it dedups per user. Mirrors analytics/earnings_refresh._send_weekly_digest.

sqlalchemy imports are kept inside functions so the pure _qualifies / _format
helpers are unit-testable without the DB layer installed.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

WATCHLIST_BUZZ_TOP_N = 15      # "entered the trending list" = within the top 15
SPIKE_GROWTH_PCT = 50.0        # OR mention growth >= this
_KIND = "watchlist_buzz"


def _qualifies(entry: dict, rank: int) -> Optional[str]:
    """Return a short human reason this symbol is worth a ping, or None.

    Pure — no DB. Order matters: the strongest, most specific reason wins.
    """
    if entry.get("accelerating"):
        return "buzz accelerating"
    growth = entry.get("growth_pct")
    if growth is not None and growth >= SPIKE_GROWTH_PCT:
        return f"+{growth:.0f}% mentions today"
    if rank <= WATCHLIST_BUZZ_TOP_N:
        return f"#{rank} most-talked-about"
    return None


def _format(symbol: str, entry: dict, reason: str) -> tuple[str, str, str]:
    """(telegram_html, push_title, push_body). Pure."""
    mentions = entry.get("mentions") or 0
    sentiment = entry.get("sentiment")
    sent = f" · {sentiment}" if sentiment else ""
    tg = (f"🔔 <b>{symbol}</b> is trending — {reason} "
          f"({mentions} mentions{sent}). It's on your watchlist.")
    push_title = f"🔔 {symbol} is trending"
    push_body = f"On your watchlist — {reason} ({mentions} mentions{sent})."
    return tg, push_title, push_body


def _latest_entries(session) -> list[dict]:
    from sqlalchemy import desc, select
    from app.models.social_buzz import SocialBuzzSnapshot

    row = session.execute(
        select(SocialBuzzSnapshot)
        .order_by(desc(SocialBuzzSnapshot.captured_at))
        .limit(1)
    ).scalar_one_or_none()
    return (row.entries or []) if row else []


def check_watchlist_buzz(session_factory) -> dict:
    """APScheduler entrypoint. Returns a summary dict for logging."""
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    from app.models.user import User
    from app.models.watchlist import WatchlistItem
    from app.models.earnings import EarningsNotificationSent
    from app.models.device_token import DeviceToken
    from alerting.notifier import _send_telegram_to
    from app.services.push_service import send_push_sync

    summary = {"buzz_symbols": 0, "candidates": 0, "sent": 0, "skipped_no_buzz": False}
    today = date.today()

    with session_factory() as session:
        entries = _latest_entries(session)
        if not entries:
            summary["skipped_no_buzz"] = True
            return summary

        rank_by_sym: dict[str, int] = {}
        entry_by_sym: dict[str, dict] = {}
        for i, e in enumerate(entries):
            sym = (e.get("symbol") or "").upper()
            if sym:
                rank_by_sym.setdefault(sym, i + 1)
                entry_by_sym.setdefault(sym, e)
        summary["buzz_symbols"] = len(entry_by_sym)

        # Every (user, watchlist symbol) pair — one query, grouped in Python.
        rows = session.execute(
            select(User.id, User.telegram_chat_id, User.telegram_enabled,
                   User.push_enabled, WatchlistItem.symbol)
            .join(WatchlistItem, WatchlistItem.user_id == User.id)
        ).all()

        for uid, chat, tg_on, push_on, sym in rows:
            symu = (sym or "").upper()
            entry = entry_by_sym.get(symu)
            if entry is None:
                continue
            reason = _qualifies(entry, rank_by_sym.get(symu, 9999))
            if not reason:
                continue
            summary["candidates"] += 1

            already = session.execute(
                select(EarningsNotificationSent).where(
                    EarningsNotificationSent.user_id == uid,
                    EarningsNotificationSent.symbol == symu,
                    EarningsNotificationSent.earnings_date == today,
                    EarningsNotificationSent.kind == _KIND,
                )
            ).scalar_one_or_none()
            if already:
                continue

            tg_body, push_title, push_body = _format(symu, entry, reason)

            if tg_on and chat:
                try:
                    _send_telegram_to(tg_body, chat, parse_mode="HTML")
                except Exception:
                    logger.exception("watchlist_buzz telegram failed for user %d / %s", uid, symu)

            if push_on:
                tokens = [t.token for t in session.execute(
                    select(DeviceToken).where(
                        DeviceToken.user_id == uid,
                        DeviceToken.is_active == True,  # noqa: E712
                    )
                ).scalars().all()]
                if tokens:
                    try:
                        send_push_sync(
                            tokens, push_title, push_body,
                            data={"symbol": symu, "kind": _KIND},
                            thread_id="watchlist_buzz",
                        )
                    except Exception:
                        logger.exception("watchlist_buzz push failed for user %d / %s", uid, symu)

            try:
                session.add(EarningsNotificationSent(
                    user_id=uid, symbol=symu, earnings_date=today, kind=_KIND,
                ))
                session.flush()
                summary["sent"] += 1
            except IntegrityError:
                session.rollback()

        session.commit()

    logger.info("Watchlist buzz check: %s", summary)
    return summary
