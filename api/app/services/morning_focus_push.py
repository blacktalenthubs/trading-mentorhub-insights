"""Server-side push of the daily Morning Focus — the DURABLE delivery hop that needs no
session token. The local morning-leaders agent persists today's report to market_reports
(DATABASE_URL only, kind=morning_focus); this scheduled job detects that row and blasts an
APNs teaser to ALL users (the server holds the APNs creds + device tokens). Runs weekday
pre-open; guarded to push once/day. Never raises — it's a background job.

This decouples generation (local, yfinance + IBD files) from delivery (server, APNs) so the
daily agent never depends on an expiring user token.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import text

from app.cache import cache_get, cache_set
from app.services.apns import send_apns_push, apns_configured

logger = logging.getLogger(__name__)
_GUARD_TTL = 72_000   # ~20h — one push per session day


def _push_all(tokens: list[str], title: str, body: str, data: dict) -> None:
    """Fan an APNs push to every device, sync (runs from the BackgroundScheduler thread)."""
    import asyncio

    async def _go():
        for t in tokens:
            try:
                await send_apns_push(t, title, body, payload=data)
            except Exception:
                pass
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_go())
    finally:
        loop.close()


def push_morning_focus(sync_session_factory) -> None:
    """Push today's morning_focus to all users, once. No-op if not persisted yet / no
    APNs / already pushed. Runs a couple times pre-open so a slightly-late agent is caught;
    the guard prevents a double-push."""
    try:
        if not apns_configured():
            logger.info("morning-focus push: APNs not configured — skipping")
            return
        date = datetime.utcnow().strftime("%Y-%m-%d")
        guard = f"mf_pushed:{date}"
        if cache_get(guard):
            return
        with sync_session_factory() as db:
            row = db.execute(text(
                "SELECT body FROM market_reports WHERE kind = 'morning_focus' "
                "AND session_date = :d ORDER BY created_at DESC LIMIT 1"), {"d": date}).first()
            if not row:
                return  # the local agent hasn't persisted today's report yet
            tokens = [r[0] for r in db.execute(text(
                "SELECT token FROM device_tokens WHERE platform = 'ios' AND token IS NOT NULL "
                "UNION SELECT apns_token FROM users WHERE apns_enabled = true "
                "AND apns_token IS NOT NULL AND apns_token <> ''")).all() if r[0]]
        if not tokens:
            return
        try:
            doc = json.loads(row.body) or {}
            picks = (doc.get("swing") or doc.get("picks") or []) + (doc.get("daytrade") or [])
        except Exception:
            picks = []   # old markdown body — still push a generic teaser
        syms = ", ".join(p.get("symbol", "") for p in picks if p.get("symbol"))
        title = ("📋 Today's focus: " + syms) if syms else "📋 Today's focus"
        body = "Swing breakouts + day-trade key levels — tap for the plan." if syms else "Nothing to chase today. Patience."
        # type+route so the tap lands on Today › Reports. The frontend router reads
        # `type`/`route`, NOT `kind`/`tab` — without these the premarket-heat push
        # fell through to /today (Signals tab).
        _push_all(tokens, title, body, {
            "type": "market_report", "kind": "morning_focus",
            "route": "/today?tab=reports", "tab": "reports",
        })
        cache_set(guard, True, _GUARD_TTL)
        logger.info("morning-focus: pushed to %d device(s) — %s", len(tokens), syms or "(no picks)")
    except Exception:
        logger.exception("morning-focus push failed")
