"""Trade replay — EOD review of today's alerts with AI-generated journal entries.

Runs after market close. For each alert the user "took", checks what happened:
did it hit T1? T2? Got stopped? Still open? Generates a 2-3 sentence replay.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import List, Optional

logger = logging.getLogger("trade_replay")


def generate_replays(sync_session_factory) -> int:
    """Generate trade journal entries for today's taken alerts.

    Returns count of journal entries created.
    """
    from app.models.alert import Alert
    from app.models.journal import TradeJournal
    from sqlalchemy import text

    today = date.today().isoformat()
    count = 0

    with sync_session_factory() as db:
        # Find all alerts the user "took" today
        taken = db.execute(
            text("""
                SELECT a.id, a.user_id, a.symbol, a.alert_type, a.direction,
                       a.entry, a.stop, a.target_1, a.target_2, a.price,
                       a.confidence, a.score, a.message, a.confluence_score
                FROM alerts a
                WHERE a.session_date = :today
                AND a.user_action = 'took'
                AND a.direction IN ('BUY', 'SHORT')
                AND NOT EXISTS (
                    SELECT 1 FROM trade_journal j
                    WHERE j.alert_id = a.id
                )
            """),
            {"today": today},
        ).fetchall()

        if not taken:
            logger.info("Trade replay: no taken alerts for %s", today)
            return 0

        for row in taken:
            alert_id = row[0]
            user_id = row[1]
            symbol = row[2]
            alert_type = row[3]
            direction = row[4]
            entry = row[5]
            stop = row[6]
            target_1 = row[7]
            target_2 = row[8]
            price = row[9]
            confidence = row[10]
            score = row[11]
            message = row[12]
            confluence = row[13]

            # Check outcome: did T1, T2, or stop fire after this alert?
            outcome = "open"
            exit_price = None
            pnl_r = None

            t1_hit = db.execute(
                text("""
                    SELECT price FROM alerts
                    WHERE user_id = :uid AND symbol = :sym
                    AND alert_type = 'target_1_hit'
                    AND session_date = :today
                    ORDER BY created_at DESC LIMIT 1
                """),
                {"uid": user_id, "sym": symbol, "today": today},
            ).fetchone()

            t2_hit = db.execute(
                text("""
                    SELECT price FROM alerts
                    WHERE user_id = :uid AND symbol = :sym
                    AND alert_type = 'target_2_hit'
                    AND session_date = :today
                    ORDER BY created_at DESC LIMIT 1
                """),
                {"uid": user_id, "sym": symbol, "today": today},
            ).fetchone()

            stop_hit = db.execute(
                text("""
                    SELECT price FROM alerts
                    WHERE user_id = :uid AND symbol = :sym
                    AND alert_type IN ('stop_loss_hit', 'auto_stop_out')
                    AND session_date = :today
                    ORDER BY created_at DESC LIMIT 1
                """),
                {"uid": user_id, "sym": symbol, "today": today},
            ).fetchone()

            risk = abs(entry - stop) if entry and stop else None

            if t2_hit:
                outcome = "t2_hit"
                exit_price = t2_hit[0]
                if risk and risk > 0 and entry:
                    pnl_r = round(abs(exit_price - entry) / risk, 1)
            elif t1_hit:
                outcome = "t1_hit"
                exit_price = t1_hit[0]
                if risk and risk > 0 and entry:
                    pnl_r = round(abs(exit_price - entry) / risk, 1)
            elif stop_hit:
                outcome = "stopped"
                exit_price = stop_hit[0]
                pnl_r = -1.0

            # Generate AI replay text
            replay_text = _generate_replay_text(
                symbol=symbol,
                direction=direction,
                alert_type=alert_type,
                entry=entry,
                stop=stop,
                target_1=target_1,
                exit_price=exit_price,
                outcome=outcome,
                pnl_r=pnl_r,
                confluence=confluence,
                score=score,
                message=message,
            )

            journal = TradeJournal(
                user_id=user_id,
                symbol=symbol,
                alert_id=alert_id,
                alert_type=alert_type,
                direction=direction,
                entry_price=entry,
                exit_price=exit_price,
                stop_price=stop,
                target_1=target_1,
                target_2=target_2,
                outcome=outcome,
                pnl_r=pnl_r,
                replay_text=replay_text,
                session_date=today,
            )
            db.add(journal)
            count += 1

        db.commit()
        logger.info("Trade replay: created %d journal entries for %s", count, today)

    return count


def _generate_replay_text(
    symbol: str,
    direction: str,
    alert_type: str,
    entry: Optional[float],
    stop: Optional[float],
    target_1: Optional[float],
    exit_price: Optional[float],
    outcome: str,
    pnl_r: Optional[float],
    confluence: int = 0,
    score: int = 0,
    message: str = "",
) -> str:
    """Generate a structured replay summary. Uses AI if available, falls back to template."""

    # Try AI generation
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            return _ai_replay(
                symbol, direction, alert_type, entry, stop, target_1,
                exit_price, outcome, pnl_r, confluence, score, message, api_key,
            )
        except Exception:
            logger.debug("AI replay failed, using template")

    # Template fallback
    outcome_text = {
        "t1_hit": f"Target 1 hit at ${exit_price:.2f}" if exit_price else "Target 1 hit",
        "t2_hit": f"Target 2 hit at ${exit_price:.2f}" if exit_price else "Target 2 hit",
        "stopped": f"Stopped out at ${exit_price:.2f}" if exit_price else "Stopped out",
        "open": "Position still open at close",
        "breakeven": "Exited at breakeven",
    }.get(outcome, outcome)

    pnl_text = f" ({pnl_r:+.1f}R)" if pnl_r is not None else ""
    conf_text = f" Confluence: {confluence}/3." if confluence else ""

    return (
        f"{symbol} {direction} via {alert_type.replace('_', ' ')}. "
        f"Entry ${entry:.2f}, stop ${stop:.2f}.{conf_text} "
        f"Outcome: {outcome_text}{pnl_text}."
    )


def _ai_replay(
    symbol, direction, alert_type, entry, stop, target_1,
    exit_price, outcome, pnl_r, confluence, score, message, api_key,
) -> str:
    """Use Anthropic API to generate a concise trade replay."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""You are a trading journal assistant. Write a 2-3 sentence trade replay.

Trade: {direction} {symbol} via {alert_type.replace('_', ' ')}
Entry: ${entry:.2f if entry else 0}, Stop: ${stop:.2f if stop else 0}, T1: ${target_1:.2f if target_1 else 0}
Score: {score}/100, Confluence: {confluence}/3
Setup: {message[:200] if message else 'N/A'}
Outcome: {outcome} at ${exit_price:.2f if exit_price else 0} ({pnl_r:+.1f}R)

Write factually. What was the setup, what happened, what can be learned. No fluff. MAX 3 sentences."""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
