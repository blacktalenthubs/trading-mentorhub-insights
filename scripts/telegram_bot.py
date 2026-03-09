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


def _build_app(bot_token: str):
    """Build the telegram Application with /start handler."""
    from telegram import Update
    from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

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

    app = ApplicationBuilder().token(bot_token).build()
    app.add_handler(CommandHandler("start", start_command))
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
