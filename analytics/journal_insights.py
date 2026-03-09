"""Weekly AI Trading Journal — personalized trade pattern analysis.

Analyzes the user's real trades from the past week to identify:
- Setup preferences (which alert types they take vs skip)
- Win rates by type, time of day, and symbol
- Behavioral patterns (early exits, oversized positions, etc.)
- Specific improvement recommendations

Delivered via Telegram on Sunday evening for Pro/Elite users.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import pytz

logger = logging.getLogger(__name__)

ET = pytz.timezone("US/Eastern")

_JOURNAL_MODEL = "claude-sonnet-4-20250514"

# Once-per-week guard
_journal_sent_week: str | None = None

_SYSTEM_PROMPT = """\
You are a trading performance coach analyzing a trader's weekly data. \
Given their closed trades, alert history, and performance stats, write a \
personalized weekly review.

Structure your response EXACTLY like this:

WEEKLY SCORECARD:
[1 line: X trades, Y wins, Z losses, total P&L, win rate]

EDGE THIS WEEK:
[1-2 sentences: what worked well — specific setup types, times, symbols]

LEAK THIS WEEK:
[1-2 sentences: what cost money — specific patterns, behaviors, mistakes]

PATTERN SPOTTED:
[1-2 sentences: behavioral observation the trader may not notice themselves]

NEXT WEEK'S FOCUS:
[2-3 bullet points: specific, actionable improvements]

Rules:
- Be specific — use actual symbols, P&L amounts, and alert types from the data
- Be honest about losses but constructive
- Focus on controllable behaviors, not market randomness
- If not enough data for an insight, say "Not enough trades this week for [X]"
- Keep the entire review under 200 words
- No markdown formatting — plain text only
- Write dollar amounts WITHOUT the $ symbol"""


def _get_week_boundaries() -> tuple[str, str]:
    """Return (start_date, end_date) ISO strings for the past 7 days."""
    today = date.today()
    start = today - timedelta(days=7)
    return start.isoformat(), today.isoformat()


def _build_journal_prompt(user_id: int) -> str | None:
    """Gather user's weekly trading data and build the AI prompt.

    Returns the prompt string or None if no trade data exists.
    """
    start_date, end_date = _get_week_boundaries()

    lines: list[str] = [f"Week: {start_date} to {end_date}", ""]

    # Closed trades this week
    try:
        from alerting.real_trade_store import get_closed_trades
        all_closed = get_closed_trades(limit=500)
        # Filter to this user's trades from the past week
        week_trades = [
            t for t in all_closed
            if t.get("closed_at", "") >= start_date
            and t.get("user_id") == user_id
        ]
    except Exception:
        logger.debug("Journal: could not fetch closed trades")
        week_trades = []

    if not week_trades:
        # Try without user_id filter (single-user mode)
        try:
            from alerting.real_trade_store import get_closed_trades
            all_closed = get_closed_trades(limit=500)
            week_trades = [
                t for t in all_closed
                if t.get("closed_at", "") >= start_date
            ]
        except Exception:
            week_trades = []

    if not week_trades:
        return None

    # Aggregate stats
    total_pnl = sum(t.get("pnl", 0) for t in week_trades)
    wins = [t for t in week_trades if t.get("pnl", 0) > 0]
    losses = [t for t in week_trades if t.get("pnl", 0) <= 0]
    win_rate = len(wins) / len(week_trades) * 100 if week_trades else 0

    lines.append("CLOSED TRADES THIS WEEK:")
    lines.append(
        f"  Total: {len(week_trades)} | Wins: {len(wins)} | Losses: {len(losses)} | "
        f"P&L: ${total_pnl:.2f} | Win Rate: {win_rate:.0f}%"
    )

    if wins:
        avg_win = sum(t.get("pnl", 0) for t in wins) / len(wins)
        lines.append(f"  Avg Win: ${avg_win:.2f}")
    if losses:
        avg_loss = sum(t.get("pnl", 0) for t in losses) / len(losses)
        lines.append(f"  Avg Loss: ${avg_loss:.2f}")

    lines.append("")
    lines.append("TRADE DETAILS:")
    for t in week_trades[:20]:
        symbol = t.get("symbol", "?")
        direction = t.get("direction", "?")
        pnl = t.get("pnl", 0)
        status = t.get("status", "closed")
        trade_type = t.get("trade_type", "intraday")
        entry = t.get("entry_price", 0)
        exit_price = t.get("exit_price", 0)
        opened = t.get("opened_at", "")
        closed = t.get("closed_at", "")

        lines.append(
            f"  {symbol} {direction} | Entry: ${entry:.2f} Exit: ${exit_price:.2f} | "
            f"P&L: ${pnl:.2f} | Status: {status} | Type: {trade_type}"
        )

    if len(week_trades) > 20:
        lines.append(f"  ... and {len(week_trades) - 20} more trades")

    # Alert history for the week (what was available vs what they took)
    try:
        from alerting.alert_store import get_session_dates, get_session_summary
        session_dates = get_session_dates() or []
        week_dates = [d for d in session_dates if start_date <= d <= end_date]

        total_alerts = 0
        buy_alerts = 0
        t1_hits = 0
        stopped_out = 0
        for sd in week_dates[:5]:
            summary = get_session_summary(sd)
            if summary:
                total_alerts += summary.get("total", 0)
                buy_alerts += summary.get("buy_count", 0)
                t1_hits += summary.get("t1_hits", 0)
                stopped_out += summary.get("stopped_out", 0)

        if total_alerts:
            lines.append("")
            lines.append("ALERT ACTIVITY THIS WEEK:")
            lines.append(
                f"  Total alerts: {total_alerts} | BUY signals: {buy_alerts} | "
                f"T1 hits: {t1_hits} | Stopped out: {stopped_out}"
            )
            if buy_alerts > 0:
                take_rate = len(week_trades) / buy_alerts * 100
                lines.append(f"  Trade take rate: {take_rate:.0f}% of BUY signals")
    except Exception:
        logger.debug("Journal: could not fetch alert history")

    return "\n".join(lines)


def build_weekly_journal(user_id: int) -> str | None:
    """Generate the AI weekly journal for a user.

    Returns the journal text or None if not enough data.
    """
    from alert_config import ANTHROPIC_API_KEY

    api_key = ANTHROPIC_API_KEY
    if not api_key:
        try:
            from db import get_db
            with get_db() as conn:
                row = conn.execute(
                    "SELECT anthropic_api_key FROM user_notification_prefs "
                    "WHERE anthropic_api_key != '' LIMIT 1"
                ).fetchone()
                api_key = row["anthropic_api_key"] if row else ""
        except Exception:
            pass

    if not api_key:
        logger.info("Weekly journal: no API key available")
        return None

    prompt = _build_journal_prompt(user_id)
    if not prompt:
        logger.info("Weekly journal: no trade data for user %s", user_id)
        return None

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=_JOURNAL_MODEL,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0,
        )
        journal = response.content[0].text.strip()

        now_et = datetime.now(ET)
        week_start, week_end = _get_week_boundaries()
        return f"WEEKLY AI JOURNAL \u2014 {week_start} to {week_end}\n\n{journal}"

    except Exception:
        logger.exception("Weekly journal: AI call failed for user %s", user_id)
        return None


def send_weekly_journals() -> bool:
    """Send weekly AI journal to Elite users via Telegram.

    Should be called on Sunday evening (after market close).
    Uses once-per-week guard to prevent duplicates.

    Returns True if at least one journal was sent.
    """
    global _journal_sent_week

    # Week key = ISO week number
    today = date.today()
    week_key = f"{today.year}-W{today.isocalendar()[1]:02d}"

    if _journal_sent_week == week_key:
        logger.debug("Weekly journal already sent for %s", week_key)
        return False

    # Only Elite users get the weekly journal
    try:
        from db import get_pro_users_with_telegram
        users = get_pro_users_with_telegram()
        elite_users = [u for u in users if u.get("tier") in ("elite", "admin")]
    except Exception:
        logger.exception("Weekly journal: failed to get user list")
        return False

    if not elite_users:
        logger.info("Weekly journal: no Elite users with Telegram")
        return False

    any_sent = False
    for u in elite_users:
        user_id = u["user_id"]
        chat_id = u.get("telegram_chat_id", "")
        if not chat_id:
            continue

        journal = build_weekly_journal(user_id)
        if not journal:
            continue

        from alerting.notifier import _send_telegram_to
        ok = _send_telegram_to(journal, chat_id)
        if ok:
            any_sent = True
            logger.info("Weekly journal sent to user %s", user_id)

    if any_sent:
        _journal_sent_week = week_key
        logger.info("Weekly journals delivered for %s", week_key)

    return any_sent
