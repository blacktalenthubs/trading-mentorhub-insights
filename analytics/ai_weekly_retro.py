"""AI Friday Retrospective — sends a personalized "this week's lessons"
Telegram message every Friday at 5:00 PM ET.

Reads the week's alerts (Mon-Fri) + their REAL outcomes (computed by
analytics/alert_outcomes.py from post-fire Alpaca bars, NOT synthetic
T1/T2). Asks Claude to surface 3 plain-English takeaways per user:
  1. What worked best this week (pattern + grade combo)
  2. What signals slipped through (low-grade noise, missed setups)
  3. What to watch next week (earnings on watchlist + recent edge)

Idempotent: marker row in `earnings_notifications_sent` with
kind='weekly_retro' prevents re-sending on the same Friday.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select, text

logger = logging.getLogger(__name__)


_RETRO_SENTINEL_SYMBOL = "__RETRO__"


def _build_user_prompt(user_id: int, session) -> Optional[dict]:
    """Build the data bundle for Claude. Returns None if the user has
    no graded alerts this week — no point spending tokens on an empty
    week.
    """
    from app.models.alert import Alert
    from app.models.earnings import Earnings
    from app.models.watchlist import WatchlistItem
    from app.models.alert_type_config import OBSOLETE_ALERT_TYPES

    today = date.today()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)

    obs_list = list(OBSOLETE_ALERT_TYPES)

    # Week's alerts with real outcomes computed.
    alerts = session.execute(text("""
        SELECT symbol, alert_type, grade, volume_ratio, vwap_slope_pct,
               real_outcome, mfe_r, mae_r, created_at, direction
        FROM alerts
        WHERE user_id = :uid
          AND session_date BETWEEN :a AND :b
          AND NOT (alert_type = ANY(:obs))
        ORDER BY created_at ASC
    """), {
        "uid": user_id,
        "a": monday.isoformat(),
        "b": friday.isoformat(),
        "obs": obs_list,
    }).all()

    if not alerts:
        return None

    # Pattern aggregates from real outcomes.
    pattern_stats: dict[str, dict] = {}
    for sym, at, grade, vol, slope, outcome, mfe, mae, ts, direction in alerts:
        p = pattern_stats.setdefault(at, {
            "fires": 0, "graded": 0, "worked": 0, "failed": 0,
            "by_grade": {"A": 0, "B": 0, "C": 0},
            "best_mfe_r": 0.0,
        })
        p["fires"] += 1
        if grade in p["by_grade"]:
            p["by_grade"][grade] += 1
        if outcome in ("worked", "failed"):
            p["graded"] += 1
            if outcome == "worked":
                p["worked"] += 1
            else:
                p["failed"] += 1
        if mfe is not None and mfe > p["best_mfe_r"]:
            p["best_mfe_r"] = round(float(mfe), 2)

    # Top 3 individual fires by MFE this week (real winners).
    top_fires = sorted(
        [a for a in alerts if a[6] is not None],   # has mfe_r
        key=lambda r: float(r[6]),
        reverse=True,
    )[:3]
    top_fires_payload = [{
        "symbol": r[0], "pattern": r[1], "grade": r[2],
        "mfe_r": round(float(r[6]), 2),
        "outcome": r[5],
        "when": r[8].isoformat() if r[8] else None,
    } for r in top_fires]

    # Next week's earnings on this user's watchlist (already populated
    # nightly by analytics/earnings_refresh.py).
    next_week_end = friday + timedelta(days=10)
    earnings_rows = session.execute(text("""
        SELECT e.symbol, e.next_earnings_date, e.time_of_day, e.eps_estimate
        FROM earnings e
        JOIN watchlist w ON w.symbol = e.symbol
        WHERE w.user_id = :uid
          AND e.next_earnings_date BETWEEN :a AND :b
        ORDER BY e.next_earnings_date ASC
    """), {
        "uid": user_id,
        "a": (friday + timedelta(days=1)).isoformat(),
        "b": next_week_end.isoformat(),
    }).all()
    upcoming_earnings = [{
        "symbol": r[0],
        "date": r[1].isoformat(),
        "when": r[2],
        "eps_est": r[3],
    } for r in earnings_rows]

    return {
        "week_start": monday.isoformat(),
        "week_end": friday.isoformat(),
        "total_fires": len(alerts),
        "patterns": {
            at: {
                **stats,
                "real_worked_pct": round(stats["worked"] / stats["graded"] * 100, 1)
                                    if stats["graded"] else None,
            }
            for at, stats in pattern_stats.items()
        },
        "top_fires_by_mfe": top_fires_payload,
        "upcoming_earnings": upcoming_earnings,
    }


_SYSTEM_PROMPT = """You are a concise trading coach writing a Friday \
retrospective for a busy professional trader.

Read the data and produce a SHORT Telegram message (under 700 chars total) \
with exactly THREE bullet sections:

• What worked: name the SINGLE best pattern+grade combo by real_worked_pct \
(only if graded >= 2). One sentence.

• Watch the noise: name 1-2 patterns where most fires were grade C OR had \
real_worked_pct under 40%. One sentence on what to tighten.

• Next week: list upcoming earnings on the watchlist (max 4 symbols with \
day-of-week + BMO/AMC). Plus one sentence on which setup type to favor \
based on what worked this week.

Use these constraints:
- Plain English, no jargon undefined. "PDH" is OK, "v2 quality gate" is not.
- No promotional language ("strong setup!"). Stick to factual observations.
- Use HTML for Telegram: <b>bold ticker symbols</b>, no markdown.
- Start with "📈 <b>Week of {start} - {end}</b>".
- No preamble, no signoff. The message IS the content."""


def _call_claude(prompt_data: dict) -> Optional[str]:
    """Call Claude Sonnet to generate the retro message. Returns text
    or None on failure.
    """
    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — weekly retro skipped")
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        user_msg = (
            "Here's this week's trading data. Build the Friday retrospective.\n\n"
            + json.dumps(prompt_data, indent=2, default=str)
        )
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=600,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
            timeout=30.0,
        )
        return resp.content[0].text.strip()
    except Exception:
        logger.exception("Weekly retro Claude call failed")
        return None


def send_weekly_retros(session_factory) -> dict:
    """Entrypoint — fire the Friday retro for every user with Telegram
    enabled. Idempotent on (user_id, today, kind='weekly_retro').
    Returns summary dict for logging.
    """
    from app.models.user import User
    from app.models.earnings import EarningsNotificationSent
    from alerting.notifier import _send_telegram_to

    today = date.today()
    summary = {"checked": 0, "sent": 0, "skipped_no_data": 0,
               "skipped_already_sent": 0, "skipped_claude_fail": 0}

    with session_factory() as session:
        users = session.execute(
            select(User).where(
                User.telegram_enabled == True,  # noqa: E712
                User.telegram_chat_id.isnot(None),
            )
        ).scalars().all()

        for u in users:
            summary["checked"] += 1

            already = session.execute(
                select(EarningsNotificationSent).where(
                    EarningsNotificationSent.user_id == u.id,
                    EarningsNotificationSent.symbol == _RETRO_SENTINEL_SYMBOL,
                    EarningsNotificationSent.earnings_date == today,
                    EarningsNotificationSent.kind == "weekly_retro",
                )
            ).scalar_one_or_none()
            if already:
                summary["skipped_already_sent"] += 1
                continue

            data = _build_user_prompt(u.id, session)
            if not data:
                summary["skipped_no_data"] += 1
                continue

            body = _call_claude(data)
            if not body:
                summary["skipped_claude_fail"] += 1
                continue

            try:
                _send_telegram_to(body, u.telegram_chat_id, parse_mode="HTML")
            except Exception:
                logger.exception("Weekly retro telegram send failed for user %d", u.id)
                continue

            session.add(EarningsNotificationSent(
                user_id=u.id,
                symbol=_RETRO_SENTINEL_SYMBOL,
                earnings_date=today,
                kind="weekly_retro",
                sent_at=datetime.utcnow(),
            ))
            session.flush()
            summary["sent"] += 1

        session.commit()

    logger.info("Weekly retro summary: %s", summary)
    return summary
