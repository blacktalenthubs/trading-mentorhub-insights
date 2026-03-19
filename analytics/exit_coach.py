"""Real-Time Exit Coach — monitors open positions and sends exit signals.

Runs every poll cycle (2 min). For each position the user "Took It" on:
- Tracks unrealized P&L
- Sends "Tighten Stop" after T1 hit (move stop to breakeven)
- Sends VWAP rejection warning when price stalls at VWAP
- Sends breakdown exit when support breaks while in position
- Sends trailing stop updates based on price action
"""

from __future__ import annotations

import logging
from datetime import datetime

import pytz

from alerting.alert_store import (
    get_active_entries,
    today_session,
)
from alerting.notifier import _send_telegram_to, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from db import get_db

logger = logging.getLogger("exit_coach")

ET = pytz.timezone("US/Eastern")

# Track what coaching messages we've already sent this session
# Key: (symbol, alert_type, coach_signal) → prevents spam
_coached_today: set[tuple[str, str, str]] = set()
_coached_session: str = ""


def _reset_if_new_session() -> None:
    """Clear coached set on new session."""
    global _coached_today, _coached_session
    session = today_session()
    if _coached_session != session:
        _coached_today.clear()
        _coached_session = session


def _already_coached(symbol: str, alert_type: str, signal: str) -> bool:
    """Check if we already sent this coaching signal today."""
    return (symbol, alert_type, signal) in _coached_today


def _mark_coached(symbol: str, alert_type: str, signal: str) -> None:
    """Mark a coaching signal as sent."""
    _coached_today.add((symbol, alert_type, signal))


def _send_coach_message(message: str) -> bool:
    """Send a coaching message via Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    return _send_telegram_to(message, TELEGRAM_CHAT_ID, parse_mode="HTML")


def _update_stop_to_breakeven(symbol: str, entry_price: float, session: str, user_id: int | None = None) -> None:
    """After T1 hit, move stop to breakeven (entry price)."""
    with get_db() as conn:
        if user_id is not None:
            conn.execute(
                """UPDATE active_entries SET stop_price = ?
                   WHERE symbol = ? AND session_date = ? AND status = 'active'
                     AND (user_id = ? OR user_id IS NULL)""",
                (entry_price, symbol, session, user_id),
            )
        else:
            conn.execute(
                """UPDATE active_entries SET stop_price = ?
                   WHERE symbol = ? AND session_date = ? AND status = 'active'""",
                (entry_price, symbol, session),
            )
    logger.info("Exit coach: moved %s stop to breakeven $%.2f", symbol, entry_price)


def check_positions(
    symbols: list[str],
    session: str | None = None,
    user_id: int | None = None,
    current_prices: dict[str, float] | None = None,
    current_vwaps: dict[str, float] | None = None,
) -> int:
    """Check all active positions and send coaching signals.

    Args:
        symbols: List of watchlist symbols to check.
        session: Session date (defaults to today).
        user_id: User ID for filtering entries.
        current_prices: Dict of symbol → current price.
        current_vwaps: Dict of symbol → current VWAP.

    Returns number of coaching messages sent.
    """
    _reset_if_new_session()
    session = session or today_session()
    messages_sent = 0

    for symbol in symbols:
        entries = get_active_entries(symbol, session, user_id=user_id)
        if not entries:
            continue

        price = current_prices.get(symbol) if current_prices else None
        vwap = current_vwaps.get(symbol) if current_vwaps else None

        for entry in entries:
            entry_price = entry.get("entry_price", 0)
            stop_price = entry.get("stop_price", 0)
            t1 = entry.get("target_1", 0)
            t2 = entry.get("target_2", 0)
            alert_type = entry.get("alert_type", "")

            if not entry_price or not price:
                continue

            risk = entry_price - stop_price if stop_price else 0
            pnl = price - entry_price
            pnl_pct = (pnl / entry_price * 100) if entry_price > 0 else 0
            r_multiple = (pnl / risk) if risk > 0 else 0

            label = alert_type.replace("_", " ").title()

            # --- T1 Hit: Tighten stop to breakeven ---
            if t1 and price >= t1 and not _already_coached(symbol, alert_type, "t1_tighten"):
                _mark_coached(symbol, alert_type, "t1_tighten")
                _update_stop_to_breakeven(symbol, entry_price, session, user_id)
                msg = (
                    f"<b>TIGHTEN STOP — {symbol}</b>\n"
                    f"T1 ${t1:.2f} hit ({r_multiple:.1f}R)\n"
                    f"Stop moved to breakeven ${entry_price:.2f}\n"
                    f"Let runner ride to T2 ${t2:.2f}" if t2 else
                    f"<b>TIGHTEN STOP — {symbol}</b>\n"
                    f"T1 ${t1:.2f} hit ({r_multiple:.1f}R)\n"
                    f"Stop moved to breakeven ${entry_price:.2f}"
                )
                if _send_coach_message(msg):
                    messages_sent += 1

            # --- T2 Hit: Close full position ---
            if t2 and price >= t2 and not _already_coached(symbol, alert_type, "t2_close"):
                _mark_coached(symbol, alert_type, "t2_close")
                msg = (
                    f"<b>CLOSE POSITION — {symbol}</b>\n"
                    f"T2 ${t2:.2f} hit ({r_multiple:.1f}R)\n"
                    f"Full target reached. Take profits."
                )
                if _send_coach_message(msg):
                    messages_sent += 1

            # --- Stop Hit: Exit immediately ---
            if stop_price and price <= stop_price and not _already_coached(symbol, alert_type, "stop_exit"):
                _mark_coached(symbol, alert_type, "stop_exit")
                msg = (
                    f"<b>EXIT NOW — {symbol}</b>\n"
                    f"Stop ${stop_price:.2f} hit\n"
                    f"Entry ${entry_price:.2f} → Exit ${price:.2f} ({pnl_pct:+.1f}%)\n"
                    f"Loss: ${pnl:.2f}/share"
                )
                if _send_coach_message(msg):
                    messages_sent += 1

            # --- VWAP Rejection: price reached VWAP but getting rejected ---
            if (vwap and entry_price < vwap and price < vwap
                    and not _already_coached(symbol, alert_type, "vwap_reject")):
                # Check if price was near VWAP recently (within 0.2%) but now pulling away
                vwap_dist = abs(price - vwap) / vwap
                if 0.002 < vwap_dist < 0.008 and pnl > 0:
                    # Price was near VWAP and now pulling back — potential rejection
                    _mark_coached(symbol, alert_type, "vwap_reject")
                    msg = (
                        f"<b>VWAP CAUTION — {symbol}</b>\n"
                        f"Price ${price:.2f} pulling back from VWAP ${vwap:.2f}\n"
                        f"P&L: {pnl_pct:+.1f}% ({r_multiple:.1f}R)\n"
                        f"Consider taking profits if momentum fades"
                    )
                    if _send_coach_message(msg):
                        messages_sent += 1

            # --- Holding position update (every 30 min, positive P&L) ---
            now = datetime.now(ET)
            if (now.minute < 3 and now.hour % 1 == 0  # ~top of each hour
                    and not _already_coached(symbol, alert_type, f"update_{now.hour}")):
                _mark_coached(symbol, alert_type, f"update_{now.hour}")
                status = "profit" if pnl >= 0 else "drawdown"
                msg = (
                    f"<b>POSITION UPDATE — {symbol}</b>\n"
                    f"Entry: ${entry_price:.2f} | Current: ${price:.2f}\n"
                    f"P&L: {pnl_pct:+.1f}% ({r_multiple:+.1f}R)\n"
                    f"Stop: ${stop_price:.2f} | T1: ${t1:.2f}"
                    + (f" | T2: ${t2:.2f}" if t2 else "")
                )
                if _send_coach_message(msg):
                    messages_sent += 1

    return messages_sent
