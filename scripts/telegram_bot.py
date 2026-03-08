#!/usr/bin/env python3
"""Telegram bot handler for deep-link token verification.

Listens for /start <token> messages and links the user's Telegram chat_id
to their TradeCoPilot account via the telegram_link_tokens table.

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

    init_db()

    with get_db() as conn:
        row = conn.execute(
            """SELECT user_id, expires_at, used
               FROM telegram_link_tokens WHERE token = ?""",
            (token,),
        ).fetchone()

    if not row:
        return "Invalid link token. Please generate a new one from Settings."

    if row["used"]:
        return "This link has already been used."

    if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        return "This link has expired. Please generate a new one from Settings."

    user_id = row["user_id"]

    # Mark token as used
    with get_db() as conn:
        conn.execute(
            "UPDATE telegram_link_tokens SET used = 1 WHERE token = ?",
            (token,),
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
    return (
        "Your Telegram account is now linked to TradeCoPilot! "
        "You'll receive DM alerts here for your watchlist signals."
    )


def main():
    """Run the Telegram bot using polling."""
    try:
        from telegram import Update
        from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
    except ImportError:
        print("Error: python-telegram-bot not installed.")
        print("  pip install python-telegram-bot")
        sys.exit(1)

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        print("Error: TELEGRAM_BOT_TOKEN environment variable not set.")
        sys.exit(1)

    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "Welcome to TradeCoPilot Bot!\n\n"
                "To link your account, use the link from Settings > Notifications."
            )
            return

        token = context.args[0]
        chat_id = update.effective_chat.id
        result = handle_start(token, chat_id)
        await update.message.reply_text(result)

    app = ApplicationBuilder().token(bot_token).build()
    app.add_handler(CommandHandler("start", start_command))

    logger.info("TradeCoPilot Telegram bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
