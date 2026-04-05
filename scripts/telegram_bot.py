#!/usr/bin/env python3
"""Telegram bot handler for deep-link token verification and trade ACK.

Listens for:
- /start <token> — links Telegram chat_id to TradeCoPilot account
- Inline button callbacks — Took It / Skip / Exited / Still Holding

Usage:
    TELEGRAM_BOT_TOKEN=xxx python scripts/telegram_bot.py

Requires: python-telegram-bot (pip install python-telegram-bot)
"""

from __future__ import annotations

import os
import sys
import logging
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def handle_start(token: str, chat_id: int) -> str:
    """Validate a deep-link token and link the Telegram chat_id to the user."""
    from db import get_db, init_db
    from db import upsert_notification_prefs, get_notification_prefs

    logger.info("handle_start called: token=%s... chat_id=%s", token[:8], chat_id)
    init_db()

    with get_db() as conn:
        row = conn.execute(
            """SELECT user_id, expires_at, used
               FROM telegram_link_tokens WHERE token = ?""",
            (token,),
        ).fetchone()

    if not row:
        logger.warning("Token not found in DB: %s...", token[:8])
        return "Invalid link token. Please generate a new one from Settings."

    if row["used"]:
        logger.info("Token already used: %s...", token[:8])
        return "This link has already been used."

    expires_at = row["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at < datetime.utcnow():
        logger.info("Token expired: %s...", token[:8])
        return "This link has expired. Please generate a new one from Settings."

    user_id = row["user_id"]

    # Mark token as used
    with get_db() as conn:
        conn.execute(
            "UPDATE telegram_link_tokens SET used = 1 WHERE token = ?",
            (token,),
        )

    # Check if this Telegram chat_id is already linked to a DIFFERENT user.
    # One Telegram account can only receive alerts for one TradeCoPilot account
    # at a time — otherwise the user sees alerts from multiple watchlists mixed.
    with get_db() as conn:
        existing = conn.execute(
            """SELECT n.user_id, u.email
               FROM user_notification_prefs n
               JOIN users u ON u.id = n.user_id
               WHERE n.telegram_chat_id = ? AND n.user_id != ?""",
            (str(chat_id), user_id),
        ).fetchall()
    if existing:
        for prev in existing:
            logger.info(
                "Unlinking Telegram chat_id=%s from previous user_id=%s (%s)",
                chat_id, prev["user_id"], prev["email"],
            )
            upsert_notification_prefs(
                prev["user_id"],
                telegram_chat_id="",
                notification_email=get_notification_prefs(prev["user_id"]).get("notification_email", ""),
                telegram_enabled=False,
                email_enabled=bool(get_notification_prefs(prev["user_id"]).get("email_enabled", 1)),
                anthropic_api_key=get_notification_prefs(prev["user_id"]).get("anthropic_api_key", ""),
            )

    # Update user's notification prefs with chat_id
    prefs = get_notification_prefs(user_id) or {}
    upsert_notification_prefs(
        user_id,
        telegram_chat_id=str(chat_id),
        notification_email=prefs.get("notification_email", ""),
        telegram_enabled=True,
        email_enabled=bool(prefs.get("email_enabled", 1)),
        anthropic_api_key=prefs.get("anthropic_api_key", ""),
    )

    logger.info("Linked Telegram chat_id=%s to user_id=%s", chat_id, user_id)
    msg = (
        "Your Telegram account is now linked to TradeCoPilot! "
        "You'll receive DM alerts here for your watchlist signals."
    )
    if existing:
        prev_emails = ", ".join(r["email"] for r in existing)
        msg += (
            f"\n\nNote: This Telegram was previously linked to {prev_emails}. "
            "That account's Telegram alerts have been disabled to avoid "
            "mixed alerts. Only your current account's watchlist will be notified."
        )
    return msg


# ---------------------------------------------------------------------------
# Trade ACK callback handlers
# ---------------------------------------------------------------------------

def _find_alert(alert_id: int) -> dict | None:
    """Look up alert by ID — uses db.py get_db() which handles Postgres/SQLite."""
    try:
        from db import get_db
        with get_db() as conn:
            row = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
            if row:
                return dict(row)
    except Exception:
        logger.debug("_find_alert: DB lookup failed", exc_info=True)
    return None


def _handle_ack(alert_id: int, chat_id: int) -> str:
    """User tapped 'Took It' — mark alert and open a real trade."""
    logger.info("_handle_ack: alert_id=%s chat_id=%s", alert_id, chat_id)
    try:
        alert = _find_alert(alert_id)
    except Exception:
        logger.exception("_handle_ack: lookup failed for %s", alert_id)
        return f"DB error looking up alert {alert_id}."
    if not alert:
        logger.warning("_handle_ack: alert %s not found", alert_id)
        return "Alert not found."

    alert_id = alert["id"]
    symbol = alert["symbol"]
    logger.info("_handle_ack: found alert %s symbol=%s", alert_id, symbol)

    if alert.get("user_action") == "took":
        return "Already acknowledged this trade."

    # ACK in V2 DB (api/tradesignal_dev.db)
    _ack_v2_alert(alert_id, "took")

    # Also try V1 ACK for backward compatibility
    try:
        from alerting.alert_store import ack_alert, create_active_entry_from_alert
        ack_alert(alert_id, "took")
        create_active_entry_from_alert(alert_id, user_id=alert.get("user_id"))
    except Exception:
        pass

    # Open a real trade — write directly to DB with user_id
    try:
        from db import get_db
        user_id = alert.get("user_id")
        entry_price = alert.get("entry") or alert["price"]
        direction = alert["direction"]
        session_date = alert.get("session_date") or date.today().isoformat()

        # Check if already have open trade for this symbol
        with get_db() as conn:
            existing = conn.execute(
                "SELECT id FROM real_trades WHERE symbol = ? AND status = 'open' AND user_id = ?",
                (symbol, user_id),
            ).fetchone()

        if not existing:
            # Position sizing
            if symbol == "SPY":
                shares = 200
            else:
                shares = int(50000 // entry_price) if entry_price > 0 else 0

            with get_db() as conn:
                conn.execute(
                    """INSERT INTO real_trades (user_id, symbol, direction, shares, entry_price,
                       stop_price, target_price, target_2_price, status, alert_type, alert_id, session_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)""",
                    (user_id, symbol, direction, shares, entry_price,
                     alert.get("stop"), alert.get("target_1"), alert.get("target_2"),
                     alert["alert_type"], alert_id, session_date),
                )
            logger.info("_handle_ack: opened real trade for %s %s @ %.2f (user=%s)", symbol, direction, entry_price, user_id)
    except Exception:
        logger.exception("_handle_ack: real trade creation failed")

    entry = alert.get("entry") or alert["price"]
    return f"\u2705 Trade ACK'd: {symbol} @ ${entry:.2f}"


def _ack_v2_alert(alert_id: int, action: str) -> None:
    """Update user_action in the database."""
    try:
        from db import get_db
        with get_db() as conn:
            conn.execute("UPDATE alerts SET user_action = ? WHERE id = ?", (action, alert_id))
            logger.info("_ack_v2_alert: updated alert %d -> %s in V2 DB", alert_id, action)
    except Exception:
        logger.debug("_ack_v2_alert: failed", exc_info=True)


def _handle_skip(alert_id: int) -> str:
    """User tapped 'Skip' — mark alert as skipped."""
    alert = _find_alert(alert_id)
    if not alert:
        return "Alert not found."

    _ack_v2_alert(alert["id"], "skipped")
    try:
        from alerting.alert_store import ack_alert
        ack_alert(alert["id"], "skipped")
    except Exception:
        pass
    return f"\u274c Skipped {alert['symbol']} alert."


def _handle_exit(alert_id: int, chat_id: int) -> str:
    """User tapped 'Exit' — close the active entry and any open trade.

    Removes active entries for the symbol (stops position updates)
    and closes any open real trade.
    """
    alert = _find_alert(alert_id)
    if not alert:
        return "Alert not found."

    symbol = alert["symbol"]
    exit_price = alert.get("price", 0)

    # Remove active entries for this symbol
    active_deleted = 0
    try:
        from db import get_db
        with get_db() as conn:
            cur = conn.execute(
                "DELETE FROM active_entries WHERE symbol = ?",
                (symbol,),
            )
            active_deleted = cur.rowcount
            conn.commit()
    except Exception as e:
        logger.warning("Exit: failed to clear active entries for %s: %s", symbol, e)

    # Close any open real trade
    try:
        from alerting.real_trade_store import close_real_trade
        from db import get_db
        with get_db() as conn:
            trade = conn.execute(
                "SELECT id, entry_price FROM real_trades WHERE symbol=? AND status='open' ORDER BY opened_at DESC LIMIT 1",
                (symbol,),
            ).fetchone()
        if trade:
            pnl = close_real_trade(trade["id"], exit_price, notes="Exited via Telegram")
            sign = "+" if pnl >= 0 else ""
            return f"\U0001f6d1 Exited {symbol} @ ${exit_price:.2f} | P&L: {sign}${pnl:.2f}"
    except Exception as e:
        logger.debug("Exit: no real trade to close for %s: %s", symbol, e)

    return f"\U0001f6d1 Exited {symbol} | {active_deleted} entries cleared"


def _handle_exit_manual(symbol: str, chat_id: int) -> str:
    """User wants to exit manually (no exit alert) — prompt for price.

    This is triggered by the /exit command. Returns a message asking for the price.
    """
    from db import get_db

    with get_db() as conn:
        trade = conn.execute(
            "SELECT id, entry_price FROM real_trades WHERE symbol=? AND status='open' ORDER BY opened_at DESC LIMIT 1",
            (symbol,),
        ).fetchone()

    if not trade:
        return f"No open trade found for {symbol}."

    return f"_awaiting_exit_price:{trade['id']}"


def _handle_hold(alert_id: int) -> str:
    """User tapped 'Still Holding' — acknowledge but keep position open."""
    return "\U0001f4aa Holding position. You'll get the next exit signal."


# ---------------------------------------------------------------------------
# Bot application builder
# ---------------------------------------------------------------------------

def _build_app(bot_token: str):
    """Build the telegram Application with /start handler and trade ACK callbacks."""
    from telegram import Update
    from telegram.ext import (
        ApplicationBuilder, CommandHandler, CallbackQueryHandler,
        ContextTypes, MessageHandler, filters,
    )

    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "Welcome to TradeCoPilot Bot!\n\n"
                "To link your Telegram to your TradeCoPilot account:\n\n"
                "1. Log in to TradeCoPilot (your web dashboard)\n"
                "2. Go to Settings > Notifications\n"
                "3. Scroll to Telegram DM Alerts\n"
                "4. Click \"Generate Link\"\n"
                "5. Open the link it gives you — it will send "
                "a special /start command back here that connects "
                "your account automatically\n\n"
                "Commands:\n"
                "/exit SYMBOL PRICE — manually exit a trade\n"
                "/trades — list open trades\n\n"
                "Note: Telegram DM alerts require a Pro or Elite subscription."
            )
            return

        token = context.args[0]
        chat_id = update.effective_chat.id
        try:
            result = handle_start(token, chat_id)
        except Exception:
            logger.exception("handle_start failed for chat_id=%s", chat_id)
            result = (
                "Something went wrong linking your account. "
                "Please try generating a new link from Settings > Notifications."
            )
        await update.message.reply_text(result)

    async def exit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /exit SYMBOL PRICE — manually exit an open trade."""
        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage: /exit SYMBOL PRICE\n"
                "Example: /exit AAPL 185.50"
            )
            return

        symbol = context.args[0].upper()
        try:
            exit_price = float(context.args[1])
        except ValueError:
            await update.message.reply_text("Invalid price. Usage: /exit AAPL 185.50")
            return

        from db import init_db, get_db
        from alerting.real_trade_store import close_real_trade

        init_db()

        with get_db() as conn:
            trade = conn.execute(
                "SELECT id FROM real_trades WHERE symbol=? AND status='open' ORDER BY opened_at DESC LIMIT 1",
                (symbol,),
            ).fetchone()

        if not trade:
            await update.message.reply_text(f"No open trade found for {symbol}.")
            return

        pnl = close_real_trade(trade["id"], exit_price, notes="Manual exit via Telegram /exit command")
        sign = "+" if pnl >= 0 else ""
        await update.message.reply_text(
            f"\U0001f4b0 Exited {symbol} @ ${exit_price:.2f} | P&L: {sign}${pnl:.2f}"
        )

    async def trades_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /trades — list open trades."""
        from db import init_db
        from alerting.real_trade_store import get_open_trades

        init_db()
        trades = get_open_trades()
        if not trades:
            await update.message.reply_text("No open trades.")
            return

        lines = ["Open Trades:\n"]
        for t in trades:
            entry = t.get("entry_price", 0)
            symbol = t["symbol"]
            stop = t.get("stop_price")
            stop_str = f" | Stop ${stop:.2f}" if stop else ""
            lines.append(f"  {symbol} @ ${entry:.2f}{stop_str}")
        await update.message.reply_text("\n".join(lines))

    async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks for trade ACK."""
        query = update.callback_query
        await query.answer()

        data = query.data or ""
        chat_id = query.message.chat_id

        try:
            action, alert_id_str = data.split(":", 1)
            alert_id = int(alert_id_str)
        except (ValueError, AttributeError):
            logger.warning("Invalid callback data: %s", data)
            return

        try:
            if action == "ack":
                result = _handle_ack(alert_id, chat_id)
            elif action == "skip":
                result = _handle_skip(alert_id)
            elif action == "exit":
                result = _handle_exit(alert_id, chat_id)
            elif action == "hold":
                result = _handle_hold(alert_id)
            else:
                result = "Unknown action."
        except Exception:
            logger.exception("Callback handler failed: %s", data)
            result = "Something went wrong. Please try again."

        # Edit the original message to show the action taken
        original_text = query.message.text or ""
        badge = {
            "ack": "\n\n\u2705 TOOK IT",
            "skip": "\n\n\u274c SKIPPED",
            "exit": f"\n\n\U0001f4b0 EXITED",
            "hold": "\n\n\U0001f4aa HOLDING",
        }.get(action, "")

        try:
            # After "Took It": keep Exit button. After "Exit"/"Skip": remove all.
            if action == "ack":
                _exit_markup = {
                    "inline_keyboard": [[
                        {"text": "\U0001f6d1 Exit Trade", "callback_data": f"exit:{alert_id}"},
                    ]]
                }
            else:
                _exit_markup = None

            await query.edit_message_text(
                text=original_text + badge,
                reply_markup=_exit_markup,
            )
        except Exception:
            logger.debug("Could not edit original message (may be too old)")

        # Send confirmation as a separate message
        await query.message.reply_text(result)

    app = ApplicationBuilder().token(bot_token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("exit", exit_command))
    app.add_handler(CommandHandler("trades", trades_command))
    app.add_handler(CallbackQueryHandler(callback_handler))
    return app


def start_bot_thread() -> bool:
    """Start the Telegram bot polling in a background daemon thread.

    Returns True if the bot was started, False if dependencies are missing
    or TELEGRAM_BOT_TOKEN is not set.  Safe to call multiple times — only
    the first call starts the bot.
    """
    import threading

    # Guard: only start once
    if getattr(start_bot_thread, "_started", False):
        return True
    start_bot_thread._started = True

    try:
        from telegram import Update  # noqa: F401
        from telegram.ext import ApplicationBuilder  # noqa: F401
    except ImportError:
        logger.warning("python-telegram-bot not installed — bot listener disabled")
        start_bot_thread._started = False
        return False

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        # Fallback: read from alert_config which uses _get_secret (supports Railway)
        try:
            from alert_config import TELEGRAM_BOT_TOKEN
            bot_token = TELEGRAM_BOT_TOKEN
        except Exception:
            pass
    if not bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — bot listener disabled")
        start_bot_thread._started = False
        return False

    def _run():
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            app = _build_app(bot_token)
            logger.info("Telegram bot listener starting (background thread)...")
            loop.run_until_complete(app.initialize())
            loop.run_until_complete(app.start())
            loop.run_until_complete(app.updater.start_polling())
            loop.run_forever()
        except Exception:
            logger.exception("Telegram bot listener crashed")
            start_bot_thread._started = False

    t = threading.Thread(target=_run, daemon=True, name="telegram-bot")
    t.start()
    logger.info("Telegram bot listener thread started")
    return True


def main():
    """Run the Telegram bot using polling (standalone mode)."""
    try:
        from telegram import Update  # noqa: F401
        from telegram.ext import ApplicationBuilder  # noqa: F401
    except ImportError:
        print("Error: python-telegram-bot not installed.")
        print("  pip install python-telegram-bot")
        sys.exit(1)

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("Error: TELEGRAM_BOT_TOKEN environment variable not set.")
        sys.exit(1)

    app = _build_app(bot_token)
    logger.info("TradeCoPilot Telegram bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
