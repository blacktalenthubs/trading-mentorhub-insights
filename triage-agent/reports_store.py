"""Market-report persistence + in-app push fan-out for the triage agent.

Both daily intelligence reports — the Premarket Heat brief (premarket.py) and
the EOD Recap (eod.py) — call `publish(kind, et, body)` here. That does two
things so the app can fully replace Telegram:

  1. PERSIST the report body to the `market_reports` table, which the API
     exposes at /intel/market-report/latest and the Today -> Recap tab renders.
  2. PUSH an in-app APNs notification ("Premarket Heat is ready", etc.) to every
     registered device, so users get notified when a report drops without
     needing Telegram.

Both steps are best-effort and never raise into the caller — a failed push or a
missing APNS_* env must not block the report (and its Telegram fallback) from
going out. This mirrors how `telegram_post.py` duplicates the API's notifier
rather than importing it, since triage-agent is a separate service.
"""
from __future__ import annotations

import logging
import os
import re

import psycopg2

logger = logging.getLogger("triage.reports")

DATABASE_URL = os.environ.get("DATABASE_URL")

# Human-facing push titles per report kind.
_TITLES = {
    "premarket": "📊 Premarket Heat",
    "eod": "📊 EOD Recap",
}


def publish(kind: str, et, body: str, send: bool = True) -> None:
    """Persist a report and (if send) push an in-app notification. Best-effort."""
    _persist(kind, et, body)
    if send:
        try:
            n = _push(kind, et, body)
            logger.info("reports: %s pushed to %d device(s)", kind, n)
        except Exception:
            logger.exception("reports: push failed for %s", kind)


def _persist(kind: str, et, body: str) -> None:
    """UPSERT the report into market_reports, keyed (kind, session_date)."""
    if not DATABASE_URL:
        return
    try:
        sd = et.strftime("%Y-%m-%d")
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS market_reports (
                        kind         TEXT NOT NULL,
                        session_date TEXT NOT NULL,
                        body         TEXT NOT NULL,
                        created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (kind, session_date)
                    )""")
                cur.execute("""
                    INSERT INTO market_reports (kind, session_date, body, created_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (kind, session_date) DO UPDATE
                        SET body = EXCLUDED.body, created_at = NOW()
                """, (kind, sd, body))
            conn.commit()
        logger.info("reports: %s persisted for %s", kind, sd)
    except Exception:
        logger.exception("reports: persist failed for %s", kind)


def _summary(body: str) -> str:
    """Pick a short one-liner for the push body — the SPY tape line if present,
    else the first meaningful non-emoji-header line. Capped for APNs."""
    lines = [ln.strip() for ln in (body or "").splitlines() if ln.strip()]
    for ln in lines:
        if "SPY" in ln:
            return ln[:160]
    # Skip the lone emoji/header line; take the first line with real content.
    for ln in lines:
        if re.search(r"[A-Za-z]{3,}", ln):
            return ln[:160]
    return "Tap to read the full report."


def _device_tokens() -> list[str]:
    """All registered iOS push tokens — union of the device_tokens table and the
    legacy users.apns_token column (the path live alert pushes use)."""
    if not DATABASE_URL:
        return []
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT token FROM device_tokens WHERE platform = 'ios'
                    UNION
                    SELECT apns_token FROM users
                     WHERE apns_enabled = true
                       AND apns_token IS NOT NULL AND apns_token <> ''
                """)
                return [r[0] for r in cur.fetchall() if r[0]]
    except Exception:
        logger.exception("reports: token query failed")
        return []


def _push(kind: str, et, body: str) -> int:
    """Fan an APNs notification out to every registered device. Returns the count
    delivered. No-ops gracefully if APNs isn't configured or aioapns is absent."""
    required = ("APNS_AUTH_KEY", "APNS_KEY_ID", "APNS_TEAM_ID", "APNS_BUNDLE_ID")
    if not all(os.environ.get(k) for k in required):
        logger.info("reports: APNs not configured (set APNS_* env), skipping push")
        return 0
    try:
        from aioapns import APNs, NotificationRequest, PushType
    except ImportError:
        logger.info("reports: aioapns not installed, skipping push")
        return 0

    tokens = _device_tokens()
    if not tokens:
        logger.info("reports: no registered devices, skipping push")
        return 0

    title = f"{_TITLES.get(kind, 'Market Report')} — {et.strftime('%a %-I:%M %p ET')}"
    summary = _summary(body)
    # Deep-link payload so a tap opens the Today -> Reports tab on the report.
    payload = {"type": "market_report", "kind": kind, "route": "/today?tab=reports"}

    import asyncio

    async def _fan_out() -> int:
        use_sandbox = os.environ.get("APNS_USE_SANDBOX", "0") == "1"
        client = APNs(
            key=os.environ["APNS_AUTH_KEY"],
            key_id=os.environ["APNS_KEY_ID"],
            team_id=os.environ["APNS_TEAM_ID"],
            topic=os.environ["APNS_BUNDLE_ID"],
            use_sandbox=use_sandbox,
        )
        message = {
            "aps": {
                "alert": {"title": title, "body": summary},
                "sound": "default",
                "thread-id": f"report-{kind}",
            },
            "data": payload,
        }
        sent = 0
        for tok in tokens:
            try:
                req = NotificationRequest(
                    device_token=tok, message=message, push_type=PushType.ALERT,
                )
                res = await client.send_notification(req)
                if res.is_successful:
                    sent += 1
                else:
                    logger.warning("reports: APNs failed token=%s… %s",
                                   tok[:12], res.description)
            except Exception:
                logger.exception("reports: APNs send raised for token=%s…", tok[:12])
        return sent

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_fan_out())
    finally:
        loop.close()
