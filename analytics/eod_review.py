"""EOD AI Review — Claude-powered end-of-day session analysis via Telegram."""

from __future__ import annotations

import logging
from datetime import datetime

import pytz

from alert_config import ANTHROPIC_API_KEY
from alerting.alert_store import get_session_summary, today_session
from alerting.notifier import _send_telegram, _send_telegram_to
from analytics.intraday_data import get_spy_context
from db import get_db

logger = logging.getLogger(__name__)

ET = pytz.timezone("US/Eastern")

# Once-per-day guard
_eod_review_sent_date: str | None = None

_EOD_MODEL = "claude-sonnet-4-20250514"
_MAX_PROMPT_ALERTS = 30

_SYSTEM_PROMPT = """\
You are a concise day-trading coach. Given today's alert session data, write a \
short end-of-day review for a swing/day trader.

Include:
1. Scorecard (1 line): W/L count, T1/T2 hit rates
2. Best setup of the day: which alert worked and why
3. Worst setup: what went wrong
4. Pattern observation: any trends across alert types, times, or symbols
5. Paper trade summary if any ran today
6. 1-2 actionable takeaways for tomorrow

Rules:
- Be direct and specific — reference actual symbols, prices, and alert types
- Keep the entire review under 200 words
- No markdown formatting (no bold, italic, headers) — plain text only
- If there were no alerts, say so briefly"""


def _resolve_api_key() -> str:
    """Return Anthropic API key: env var first, then DB fallback."""
    if ANTHROPIC_API_KEY:
        return ANTHROPIC_API_KEY
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT anthropic_api_key FROM user_notification_prefs "
                "WHERE anthropic_api_key != '' LIMIT 1"
            ).fetchone()
            return row["anthropic_api_key"] if row else ""
    except Exception:
        return ""


def _build_eod_prompt(summary: dict, spy_ctx: dict) -> str:
    """Structure session data into a prompt for Claude."""
    lines = [
        f"Session date: {today_session()}",
        f"SPY: ${spy_ctx.get('close', 0):.2f} | Regime: {spy_ctx.get('regime', 'UNKNOWN')} | "
        f"Trend: {spy_ctx.get('trend', 'unknown')}",
        "",
        "--- SESSION SCORECARD ---",
        f"Total alerts: {summary['total']}",
        f"Buys: {summary['buy_count']} | Sells: {summary['sell_count']}",
        f"T1 hits: {summary['t1_hits']} | T2 hits: {summary['t2_hits']}",
        f"Stopped out: {summary['stopped_out']}",
        f"Symbols active: {', '.join(summary.get('symbols', []))}",
        "",
        "--- ALERT TYPES ---",
    ]

    for atype, count in sorted(summary.get("signals_by_type", {}).items()):
        lines.append(f"  {atype}: {count}")

    lines.append("")
    lines.append("--- ALERT DETAILS (chronological) ---")

    alerts = summary.get("alerts", [])
    for alert in alerts[:_MAX_PROMPT_ALERTS]:
        symbol = alert.get("symbol", "?")
        atype = alert.get("alert_type", "?")
        direction = alert.get("direction", "?")
        price = alert.get("price", 0)
        score = alert.get("score", 0)
        time_str = alert.get("created_at", "")
        msg = alert.get("message", "")

        parts = [f"Symbol: {symbol} | {direction} | {atype} | ${price:.2f}"]
        if score:
            parts.append(f"Score: {score}")
        if time_str:
            parts.append(f"Time: {time_str}")
        if msg:
            parts.append(f"Note: {msg[:100]}")
        lines.append("  ".join(parts))

    if len(alerts) > _MAX_PROMPT_ALERTS:
        lines.append(f"  ... and {len(alerts) - _MAX_PROMPT_ALERTS} more alerts (omitted)")

    # Paper trades today
    try:
        session = today_session()
        with get_db() as conn:
            paper_rows = conn.execute(
                "SELECT * FROM paper_trades WHERE session_date = ?",
                (session,),
            ).fetchall()
        if paper_rows:
            paper_trades = [dict(r) for r in paper_rows]
            open_count = sum(1 for t in paper_trades if t.get("status") == "open")
            closed_count = len(paper_trades) - open_count
            paper_pnl = sum(t.get("pnl", 0) or 0 for t in paper_trades if t.get("pnl") is not None)

            lines.append("")
            lines.append("--- PAPER TRADES TODAY ---")
            lines.append(f"Total: {len(paper_trades)} | Open: {open_count} | Closed: {closed_count} | P&L: ${paper_pnl:.2f}")
            for t in paper_trades:
                pnl = t.get("pnl")
                pnl_str = f"P&L: ${pnl:.2f}" if pnl is not None else "open"
                lines.append(
                    f"  {t['symbol']} {t.get('direction', 'BUY')} {t.get('shares', '?')} shares "
                    f"@ ${t.get('entry_price', 0):.2f} | {t.get('status', '?')} | {pnl_str}"
                )
    except Exception:
        logger.debug("EOD: paper trades section failed")

    return "\n".join(lines)


def build_eod_review() -> str | None:
    """Build EOD review by calling Claude with today's session data.

    Returns formatted review string or None on failure/no data.
    """
    api_key = _resolve_api_key()
    if not api_key:
        logger.info("EOD review: no API key available")
        return None

    summary = get_session_summary()
    if summary["total"] == 0:
        logger.info("EOD review: no alerts today")
        return None

    spy_ctx = get_spy_context()
    prompt = _build_eod_prompt(summary, spy_ctx)

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=_EOD_MODEL,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0,
        )
        review_text = response.content[0].text.strip()

        now_et = datetime.now(ET)
        date_str = now_et.strftime("%b %-d, %Y")
        return f"EOD REVIEW \u2014 {date_str}\n\n{review_text}"

    except Exception:
        logger.exception("Failed to generate EOD review")
        return None


def send_eod_review() -> bool:
    """Send the EOD AI review via Telegram (once per day).

    Returns True if sent, False if skipped or failed.
    """
    global _eod_review_sent_date

    session = today_session()
    if _eod_review_sent_date == session:
        logger.debug("EOD review already sent for %s", session)
        return False

    review = build_eod_review()
    if not review:
        return False

    try:
        from db import get_pro_users_with_telegram
        users = get_pro_users_with_telegram()
    except Exception:
        users = []

    any_sent = False
    for u in users:
        chat_id = u.get("telegram_chat_id", "")
        if not chat_id:
            continue
        try:
            ok = _send_telegram_to(review, chat_id)
            if ok:
                any_sent = True
        except Exception:
            pass

    if any_sent:
        _eod_review_sent_date = session
        logger.info("EOD review sent for %s", session)
    return any_sent
