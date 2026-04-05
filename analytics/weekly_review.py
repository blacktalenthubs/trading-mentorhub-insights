"""Weekly Performance Review — AI-generated coaching summary.

Analyzes user's trading week: wins/losses by pattern, timing insights,
behavioral observations, and personalized recommendations.

Scheduled: Friday 5 PM ET or Sunday 6 PM ET.
Sent via Telegram to Pro+ users.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

_REVIEW_MODEL = "claude-sonnet-4-20250514"

_SYSTEM_PROMPT = """\
You are a trading coach writing a weekly performance review for a learning trader. \
Given their week's trading data (alerts taken, skipped, outcomes), write a concise \
coaching summary.

Structure your response EXACTLY like this:

PERFORMANCE:
[2-3 bullet points: total trades, wins/losses, WR%, best/worst trade]

PATTERNS:
[2-3 bullet points: which alert types won, which lost, any pattern in behavior]

COACHING:
[2-3 sentences: ONE specific, actionable improvement based on the data. \
Reference actual numbers. Be encouraging but honest.]

NEXT WEEK:
[1-2 sentences: what to focus on, market context if relevant]

Rules:
- Be specific — use actual trade data, symbol names, and dollar amounts
- Reference pattern types by name (e.g., "PDL reclaim", "EMA bounce")
- If they skipped alerts that would have won, mention it constructively
- If they have a losing pattern (e.g., breakouts in choppy regime), flag it
- Keep total response under 200 words
- No markdown formatting — plain text only
- Frame as education and coaching, not financial advice
- Be encouraging — celebrate wins before addressing improvements"""


def build_weekly_review(user_id: int, days: int = 7) -> str | None:
    """Build weekly review data for a user and generate AI coaching.

    Returns the formatted review text, or None if insufficient data.
    """
    from db import get_db

    cutoff = (date.today() - timedelta(days=days)).isoformat()

    with get_db() as conn:
        # Get user's alerts with outcomes
        alerts = conn.execute(
            """SELECT a.symbol, a.alert_type, a.direction, a.price, a.entry,
                      a.stop, a.target_1, a.score, a.user_action, a.session_date
               FROM alerts a
               WHERE a.user_id = ? AND a.session_date >= ?
                 AND a.direction IN ('BUY', 'SHORT')
                 AND a.alert_type NOT IN ('target_1_hit', 'target_2_hit',
                                          'stop_loss_hit', 'auto_stop_out')
               ORDER BY a.created_at""",
            (user_id, cutoff),
        ).fetchall()

        if not alerts or len(alerts) < 3:
            return None

        # Get outcomes
        outcomes = conn.execute(
            """SELECT symbol, session_date, alert_type
               FROM alerts
               WHERE user_id = ? AND session_date >= ?
                 AND alert_type IN ('target_1_hit', 'target_2_hit',
                                    'stop_loss_hit', 'auto_stop_out')""",
            (user_id, cutoff),
        ).fetchall()

    # Build outcome lookup
    wins_set = set()
    losses_set = set()
    for o in outcomes:
        key = (o["symbol"], o["session_date"])
        if o["alert_type"] in ("target_1_hit", "target_2_hit"):
            wins_set.add(key)
        else:
            losses_set.add(key)

    # Analyze
    took = [a for a in alerts if a["user_action"] == "took"]
    skipped = [a for a in alerts if a["user_action"] == "skipped"]
    no_action = [a for a in alerts if not a["user_action"]]

    took_wins = [a for a in took if (a["symbol"], a["session_date"]) in wins_set]
    took_losses = [a for a in took if (a["symbol"], a["session_date"]) in losses_set]
    skipped_would_win = [a for a in skipped if (a["symbol"], a["session_date"]) in wins_set]

    # Build data prompt
    lines = [
        f"WEEKLY TRADING DATA (last {days} days):",
        f"Total alerts: {len(alerts)}",
        f"Took: {len(took)} | Skipped: {len(skipped)} | No action: {len(no_action)}",
        f"Took wins: {len(took_wins)} | Took losses: {len(took_losses)}",
        f"Win rate on took: {len(took_wins)}/{max(len(took_wins)+len(took_losses),1)*100:.0f}%" if took_wins or took_losses else "Win rate: N/A (no closed trades)",
    ]

    if skipped_would_win:
        lines.append(f"Skipped alerts that would have won: {len(skipped_would_win)}")
        for a in skipped_would_win[:3]:
            lines.append(f"  - {a['symbol']} {a['alert_type'].replace('_',' ')} (score {a['score']})")

    # Pattern breakdown
    type_counts: dict[str, dict] = {}
    for a in took:
        at = a["alert_type"].replace("_", " ").title()
        key = (a["symbol"], a["session_date"])
        if at not in type_counts:
            type_counts[at] = {"total": 0, "wins": 0, "losses": 0}
        type_counts[at]["total"] += 1
        if key in wins_set:
            type_counts[at]["wins"] += 1
        elif key in losses_set:
            type_counts[at]["losses"] += 1

    if type_counts:
        lines.append("\nPATTERN BREAKDOWN (trades taken):")
        for pat, counts in sorted(type_counts.items(), key=lambda x: x[1]["total"], reverse=True):
            total = counts["total"]
            w = counts["wins"]
            l = counts["losses"]
            wr = f"{w}/{w+l} ({w/(w+l)*100:.0f}%)" if w + l > 0 else "open"
            lines.append(f"  {pat}: {total} trades, {wr}")

    data_prompt = "\n".join(lines)

    # Generate AI review
    from alert_config import ANTHROPIC_API_KEY
    api_key = ANTHROPIC_API_KEY
    if not api_key:
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=_REVIEW_MODEL,
            max_tokens=500,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": data_prompt}],
            timeout=30.0,
        )
        review = response.content[0].text.strip()

        today = date.today().strftime("%b %-d, %Y")
        start = (date.today() - timedelta(days=days)).strftime("%b %-d")
        header = f"WEEKLY COACHING REVIEW — {start} to {today}"
        return f"{header}\n\n{review}"

    except Exception:
        logger.exception("Weekly review AI generation failed")
        return None


def send_weekly_reviews() -> int:
    """Send weekly reviews to all Pro users with Telegram.

    Returns count of reviews sent.
    """
    from db import get_pro_users_with_telegram
    from alerting.notifier import _send_telegram_to

    users = get_pro_users_with_telegram()
    sent = 0

    for u in users:
        user_id = u["user_id"]
        chat_id = u.get("telegram_chat_id", "")
        if not chat_id:
            continue

        review = build_weekly_review(user_id)
        if not review:
            logger.info("Weekly review: insufficient data for user %d", user_id)
            continue

        ok = _send_telegram_to(review, chat_id)
        if ok:
            sent += 1
            logger.info("Weekly review sent to user %d", user_id)

    logger.info("Weekly reviews sent: %d of %d users", sent, len(users))
    return sent
