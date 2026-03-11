"""AI Trade Review — post-trade analysis when a trade closes.

Generates a structured AI review of a completed trade, analyzing decision
quality, what worked, what didn't, and lessons for future trades.
No protected business logic — pure analysis layer.
"""

from __future__ import annotations

import logging
from typing import Generator

logger = logging.getLogger(__name__)


def generate_trade_review(trade: dict) -> Generator[str, None, None]:
    """Stream an AI post-trade review for a closed trade.

    *trade* should be a full real_trades row dict (including entry_price,
    exit_price, pnl, alert_type, direction, symbol, shares, stop_price,
    target_price, notes, session_date, opened_at, closed_at, status).

    Yields streamed text chunks. Raises ValueError if no API key.
    """
    from alerting.narrator import _resolve_api_key
    from alert_config import CLAUDE_MODEL

    api_key = _resolve_api_key()
    if not api_key:
        raise ValueError("No Anthropic API key configured.")

    # Build context from trade data
    symbol = trade.get("symbol", "?")
    direction = trade.get("direction", "BUY")
    entry = trade.get("entry_price", 0)
    exit_price = trade.get("exit_price", 0)
    pnl = trade.get("pnl", 0)
    shares = trade.get("shares", 0)
    stop = trade.get("stop_price")
    target = trade.get("target_price")
    target_2 = trade.get("target_2_price")
    alert_type = (trade.get("alert_type") or "unknown").replace("_", " ")
    status = trade.get("status", "closed")
    trade_type = trade.get("trade_type", "intraday")
    notes = trade.get("notes", "") or ""
    session_date = trade.get("session_date", "")
    opened_at = trade.get("opened_at", "")
    closed_at = trade.get("closed_at", "")

    # Compute trade metrics
    risk = abs(entry - stop) if stop else 0
    risk_pct = (risk / entry * 100) if entry > 0 and risk > 0 else 0
    pnl_pct = (pnl / (entry * shares) * 100) if entry > 0 and shares > 0 else 0
    r_multiple = (pnl / (risk * shares)) if risk > 0 and shares > 0 else 0
    hit_target = exit_price >= target if target and direction == "BUY" else False
    hit_stop = status == "stopped"

    # Fetch win rate for this alert type
    win_rate_str = ""
    try:
        from analytics.intel_hub import get_alert_win_rates
        wr = get_alert_win_rates(90)
        by_type = wr.get("by_alert_type", {})
        raw_type = trade.get("alert_type", "")
        if raw_type in by_type:
            wr_data = by_type[raw_type]
            win_rate_str = f"Historical win rate for {alert_type}: {wr_data['win_rate']}% ({wr_data['total']} signals)"
    except Exception:
        pass

    context_parts = [
        f"Closed trade review for {symbol}:",
        f"Direction: {direction}",
        f"Entry: ${entry:.2f} | Exit: ${exit_price:.2f}",
        f"Shares: {shares} | P&L: ${pnl:+,.2f} ({pnl_pct:+.1f}%)",
        f"Status: {status} ({'winner' if pnl > 0 else 'loser'})",
        f"Alert type: {alert_type} | Trade type: {trade_type}",
    ]
    if stop:
        context_parts.append(f"Stop: ${stop:.2f} (risk: ${risk:.2f}, {risk_pct:.1f}%)")
    if target:
        context_parts.append(f"Target: ${target:.2f} {'(HIT)' if hit_target else '(not reached)'}")
    if target_2:
        context_parts.append(f"Target 2: ${target_2:.2f}")
    if risk > 0:
        context_parts.append(f"R-multiple: {r_multiple:+.1f}R")
    if session_date:
        context_parts.append(f"Session: {session_date}")
    if opened_at and closed_at:
        context_parts.append(f"Opened: {opened_at} | Closed: {closed_at}")
    if notes:
        context_parts.append(f"Trader notes: {notes}")
    if win_rate_str:
        context_parts.append(win_rate_str)

    context = "\n".join(context_parts)

    prompt = (
        f"Review this closed {symbol} trade. Analyze:\n"
        "1. DECISION QUALITY — Was the entry setup valid? Was the risk/reward acceptable?\n"
        "2. EXECUTION — Did the trader manage the trade well (stop placement, exit timing)?\n"
        "3. OUTCOME vs PROCESS — Separate luck from skill. A losing trade can be a good decision.\n"
        "4. KEY LESSON — One actionable takeaway for future trades of this type.\n"
        "5. GRADE — Rate the trade A/B/C/D (decision quality, not just P&L).\n\n"
        "Keep it concise (5-8 lines). Be honest but constructive."
    )

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=512,
        system=(
            "You are a trading performance coach reviewing completed trades. "
            "Focus on decision quality over outcome. Use plain numbers for dollars "
            "(no $ symbol). Be direct and actionable."
        ),
        messages=[{"role": "user", "content": f"{prompt}\n\n{context}"}],
    ) as stream:
        for chunk in stream.text_stream:
            yield chunk


def save_trade_review(trade_id: int, review_text: str) -> None:
    """Persist the AI review text to the real_trades table."""
    from db import get_db

    with get_db() as conn:
        conn.execute(
            "UPDATE real_trades SET ai_review=? WHERE id=?",
            (review_text, trade_id),
        )


def get_trade_review(trade_id: int) -> str | None:
    """Fetch saved AI review for a trade. Returns None if not yet reviewed."""
    from db import get_db

    with get_db() as conn:
        row = conn.execute(
            "SELECT ai_review FROM real_trades WHERE id=?",
            (trade_id,),
        ).fetchone()
        if row and row["ai_review"]:
            return row["ai_review"]
    return None
