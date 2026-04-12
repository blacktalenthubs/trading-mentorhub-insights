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
from datetime import date, datetime

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
            # Clear V2 users table too
            try:
                with get_db() as conn:
                    conn.execute(
                        "UPDATE users SET telegram_chat_id = NULL WHERE id = ?",
                        (prev["user_id"],),
                    )
            except Exception:
                pass

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

    # Also update V2 users table (FastAPI reads telegram_chat_id from here)
    try:
        with get_db() as conn:
            result = conn.execute(
                "UPDATE users SET telegram_chat_id = ?, telegram_enabled = 1 WHERE id = ?",
                (str(chat_id), user_id),
            )
            rows_updated = result.rowcount if hasattr(result, 'rowcount') else -1
            logger.info(
                "V2 users table update: user_id=%s chat_id=%s rows_updated=%s",
                user_id, chat_id, rows_updated,
            )
            if rows_updated == 0:
                logger.warning(
                    "V2 users table update: NO ROWS MATCHED for user_id=%s — "
                    "user may not exist in V2 users table",
                    user_id,
                )
    except Exception:
        logger.exception("V2 users table update FAILED for user_id=%s", user_id)

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
    The ID could be an alert ID or a real_trade ID — try both.
    """
    alert = _find_alert(alert_id)
    symbol = None
    exit_price = 0

    if alert:
        symbol = alert["symbol"]
        exit_price = alert.get("price", 0)
    else:
        # Try looking up as a real_trade ID
        try:
            from db import get_db
            with get_db() as conn:
                trade = conn.execute(
                    "SELECT symbol, entry_price FROM real_trades WHERE id = ?",
                    (alert_id,),
                ).fetchone()
                if trade:
                    symbol = trade["symbol"]
                    exit_price = trade["entry_price"]  # fallback — will use current price below
        except Exception:
            pass

    if not symbol:
        return "Alert not found."

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

    # Close ALL open real trades for this symbol (not just one)
    try:
        from alerting.real_trade_store import close_real_trade
        from db import get_db
        with get_db() as conn:
            open_trades = conn.execute(
                "SELECT id, entry_price FROM real_trades WHERE symbol=? AND status='open' ORDER BY opened_at DESC",
                (symbol,),
            ).fetchall()
        if open_trades:
            total_pnl = 0.0
            closed_count = 0
            for ot in open_trades:
                try:
                    pnl = close_real_trade(ot["id"], exit_price, notes="Exited via Telegram")
                    total_pnl += pnl
                    closed_count += 1
                except Exception as _e:
                    logger.warning("Exit: failed to close trade %d: %s", ot["id"], _e)
            sign = "+" if total_pnl >= 0 else ""
            if closed_count > 1:
                return f"\U0001f6d1 Exited {closed_count}x {symbol} @ ${exit_price:.2f} | Total P&L: {sign}${total_pnl:.2f}"
            return f"\U0001f6d1 Exited {symbol} @ ${exit_price:.2f} | P&L: {sign}${total_pnl:.2f}"
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
# AI Telegram Commands — /spy, /eth, /btc, /levels, /scan
# ---------------------------------------------------------------------------

# Symbol shortcuts
_SYMBOL_MAP = {
    "eth": "ETH-USD", "btc": "BTC-USD", "sol": "SOL-USD",
    "doge": "DOGE-USD", "ada": "ADA-USD",
}

def _resolve_symbol(text: str) -> str | None:
    """Convert command text to symbol. /spy → SPY, /eth → ETH-USD."""
    parts = text.strip().lstrip("/").split()
    if not parts:
        return None
    raw = parts[0].lower()
    if not raw or not raw.isalpha():
        return None
    return _SYMBOL_MAP.get(raw, raw.upper())


def _get_user_from_chat_id(chat_id: int) -> dict | None:
    """Look up user by telegram chat_id."""
    try:
        from db import get_db
        with get_db() as conn:
            row = conn.execute(
                "SELECT id, email FROM users WHERE telegram_chat_id = ?",
                (str(chat_id),),
            ).fetchone()
            if row:
                return {"id": row["id"], "email": row["email"]}
    except Exception:
        pass
    # Try V2 DB
    try:
        from db import get_db
        with get_db() as conn:
            row = conn.execute(
                "SELECT user_id FROM user_notification_prefs WHERE telegram_chat_id = ?",
                (str(chat_id),),
            ).fetchone()
            if row:
                return {"id": row["user_id"]}
    except Exception:
        pass
    return None


def _ai_analyze_symbol(symbol: str) -> str:
    """Run AI analysis on a symbol — same as AI Coach, returns formatted text."""
    try:
        from analytics.intraday_data import fetch_intraday, fetch_intraday_crypto, fetch_prior_day
        from config import is_crypto_alert_symbol
        from alert_config import ANTHROPIC_API_KEY, CLAUDE_MODEL

        is_crypto = is_crypto_alert_symbol(symbol)
        api_key = ANTHROPIC_API_KEY
        if not api_key:
            return "AI not configured. Contact support."

        # Fetch data
        bars_df = fetch_intraday_crypto(symbol) if is_crypto else fetch_intraday(symbol, period="1d", interval="5m")
        if bars_df is None or (hasattr(bars_df, "empty") and bars_df.empty):
            return f"No data available for {symbol}."

        prior_day = fetch_prior_day(symbol, is_crypto=is_crypto)

        # Build context — data only, AI decides
        current = float(bars_df.iloc[-1]["Close"])
        parts = [
            f"Analyze {symbol} at ${current:.2f}. Is there a day trade entry?\n",
            "Reply with: CHART READ (1 sentence) + ACTION (Direction/Entry/Stop/T1/T2/Conviction).\n"
            "If no trade, say WAIT with what to watch for.\n"
            "Entry = key level, not current price. Stop = structural support.\n"
            "MAXIMUM 60 WORDS. Plain text.\n",
        ]

        # Key levels
        if prior_day:
            levels = []
            for key, label in [
                ("high", "PDH"), ("low", "PDL"), ("close", "PriorClose"),
                ("ma50", "50MA"), ("ma100", "100MA"), ("ma200", "200MA"),
                ("ema20", "20EMA"), ("ema50", "50EMA"),
            ]:
                val = prior_day.get(key)
                if val and val > 0:
                    levels.append(f"{label}=${val:.2f}")
            rsi = prior_day.get("rsi14")
            if rsi:
                levels.append(f"RSI={rsi:.1f}")
            pw_high = prior_day.get("prior_week_high")
            pw_low = prior_day.get("prior_week_low")
            if pw_high:
                levels.append(f"WeekHi=${pw_high:.2f}")
            if pw_low:
                levels.append(f"WeekLo=${pw_low:.2f}")
            parts.append("[LEVELS] " + "  ".join(levels))

        # Session levels
        session_high = float(bars_df["High"].max())
        session_low = float(bars_df["Low"].min())
        import pandas as pd
        tp = (bars_df["High"] + bars_df["Low"] + bars_df["Close"]) / 3
        vwap = float((tp * bars_df["Volume"]).sum() / bars_df["Volume"].sum()) if bars_df["Volume"].sum() > 0 else current
        parts.append(f"[SESSION] High=${session_high:.2f} Low=${session_low:.2f} VWAP=${vwap:.2f}")

        # Last 15 bars
        lines = ["[5-MIN BARS]"]
        for _, r in bars_df.tail(15).iterrows():
            lines.append(f"O={float(r['Open']):.2f} H={float(r['High']):.2f} L={float(r['Low']):.2f} C={float(r['Close']):.2f} V={float(r['Volume']):.0f}")
        parts.append("\n".join(lines))

        prompt = "\n\n".join(parts)

        # Call Claude
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=200,
            system=[{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"Analyze {symbol} now."}],
            timeout=10.0,
        )
        return response.content[0].text.strip()

    except Exception as e:
        logger.exception("AI analyze failed for %s", symbol)
        return f"Analysis failed for {symbol}. Try again."


def _get_key_levels(symbol: str) -> str:
    """Get key levels for a symbol — no AI call, instant."""
    try:
        from analytics.intraday_data import fetch_intraday, fetch_intraday_crypto, fetch_prior_day
        from config import is_crypto_alert_symbol

        is_crypto = is_crypto_alert_symbol(symbol)
        prior_day = fetch_prior_day(symbol, is_crypto=is_crypto)
        bars_df = fetch_intraday_crypto(symbol) if is_crypto else fetch_intraday(symbol, period="1d", interval="5m")

        if not prior_day:
            return f"No data for {symbol}."

        lines = [f"<b>📊 {symbol} Key Levels</b>"]

        for key, label in [("high", "PDH"), ("low", "PDL"), ("close", "Prior Close")]:
            val = prior_day.get(key)
            if val and val > 0:
                lines.append(f"{label}: ${val:.2f}")

        for key, label in [("ma50", "50MA"), ("ma100", "100MA"), ("ma200", "200MA")]:
            val = prior_day.get(key)
            if val and val > 0:
                lines.append(f"{label}: ${val:.2f}")

        if bars_df is not None and not (hasattr(bars_df, "empty") and bars_df.empty):
            session_high = float(bars_df["High"].max())
            session_low = float(bars_df["Low"].min())
            import pandas as pd
            tp = (bars_df["High"] + bars_df["Low"] + bars_df["Close"]) / 3
            vol_sum = bars_df["Volume"].sum()
            vwap = float((tp * bars_df["Volume"]).sum() / vol_sum) if vol_sum > 0 else float(bars_df.iloc[-1]["Close"])
            lines.append(f"Session Hi: ${session_high:.2f}")
            lines.append(f"Session Lo: ${session_low:.2f}")
            lines.append(f"VWAP: ${vwap:.2f}")

        rsi = prior_day.get("rsi14")
        if rsi:
            lines.append(f"RSI: {rsi:.1f}")

        return "\n".join(lines)

    except Exception:
        logger.exception("Key levels failed for %s", symbol)
        return f"Could not fetch levels for {symbol}."


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

    # --- AI symbol command handler ---
    async def ai_symbol_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /spy, /eth, /btc, etc. — AI chart analysis."""
        symbol = _resolve_symbol(update.message.text)
        if not symbol:
            await update.message.reply_text("Usage: /spy, /eth, /btc, /aapl, etc.")
            return

        # Check user is linked
        user = _get_user_from_chat_id(update.effective_chat.id)
        if not user:
            await update.message.reply_text(
                "Account not linked. Go to Settings > Notifications > Telegram to connect."
            )
            return

        # Rate limit check
        remaining = -1  # default unlimited
        try:
            from db import get_db, init_db
            from api.app.tier import get_limits
            init_db()
            user_id = user["id"]
            tier = "free"
            try:
                with get_db() as conn:
                    sub = conn.execute(
                        "SELECT tier FROM subscriptions WHERE user_id = ? AND status = 'active'",
                        (user_id,),
                    ).fetchone()
                    if sub:
                        tier = sub["tier"]
            except Exception:
                pass

            limits = get_limits(tier)
            max_cmds = limits.get("telegram_commands_per_day")
            if max_cmds is not None:
                today = date.today().isoformat()
                with get_db() as conn:
                    row = conn.execute(
                        "SELECT usage_count FROM usage_limits WHERE user_id = ? AND feature = ? AND usage_date = ?",
                        (user_id, "telegram_command", today),
                    ).fetchone()
                    current = row["usage_count"] if row else 0
                    if current >= max_cmds:
                        await update.message.reply_text(
                            f"Daily command limit reached ({max_cmds}/{max_cmds}).\n"
                            f"Upgrade to Pro for 50 commands/day.\n"
                            f"→ https://www.tradesignalwithai.com/billing"
                        )
                        return
                    # Increment
                    conn.execute(
                        "INSERT INTO usage_limits (user_id, feature, usage_date, usage_count) "
                        "VALUES (?, ?, ?, 1) "
                        "ON CONFLICT (user_id, feature, usage_date) "
                        "DO UPDATE SET usage_count = usage_limits.usage_count + 1",
                        (user_id, "telegram_command", today),
                    )
                    remaining = max_cmds - current - 1
        except Exception:
            remaining = -1  # skip limit on error
            logger.debug("Rate limit check failed, allowing command")

        await update.message.reply_text(f"Analyzing {symbol}...")

        # Run AI analysis
        analysis = _ai_analyze_symbol(symbol)
        current_price = ""
        try:
            from analytics.intraday_data import fetch_intraday, fetch_intraday_crypto
            from config import is_crypto_alert_symbol
            is_crypto = is_crypto_alert_symbol(symbol)
            bars = fetch_intraday_crypto(symbol) if is_crypto else fetch_intraday(symbol, period="1d", interval="5m")
            if bars is not None and not (hasattr(bars, "empty") and bars.empty):
                current_price = f" ${float(bars.iloc[-1]['Close']):.2f}"
        except Exception:
            pass

        _remaining_text = f"\n\n<i>{remaining} queries remaining today</i>" if isinstance(remaining, int) and remaining >= 0 else ""
        msg = f"<b>📊 {symbol}{current_price}</b>\n\n{analysis}{_remaining_text}"
        await update.message.reply_html(msg)

    # --- /levels command handler ---
    async def levels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /levels spy — show key levels, no AI call."""
        if not context.args:
            await update.message.reply_text("Usage: /levels spy, /levels eth")
            return
        symbol = _resolve_symbol(context.args[0])
        if not symbol:
            await update.message.reply_text("Invalid symbol.")
            return
        msg = _get_key_levels(symbol)
        await update.message.reply_html(msg)

    # --- /scan command handler ---
    async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /scan — trigger AI scan on user's watchlist."""
        user = _get_user_from_chat_id(update.effective_chat.id)
        if not user:
            await update.message.reply_text("Account not linked.")
            return

        await update.message.reply_text("Scanning your watchlist...")

        try:
            from db import get_db
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT symbol FROM watchlist WHERE user_id = ?",
                    (user["id"],),
                ).fetchall()
            symbols = [r["symbol"] for r in rows] if rows else []
            if not symbols:
                await update.message.reply_text("No symbols on your watchlist.")
                return

            results = []
            for sym in symbols[:10]:  # max 10
                analysis = _ai_analyze_symbol(sym)
                # Extract first line as summary
                first_line = analysis.split("\n")[0][:80]
                results.append(f"<b>{sym}</b>: {first_line}")

            msg = "<b>📊 Watchlist Scan</b>\n\n" + "\n\n".join(results)
            await update.message.reply_html(msg)
        except Exception:
            logger.exception("Scan command failed")
            await update.message.reply_text("Scan failed. Try again.")

    app = ApplicationBuilder().token(bot_token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("exit", exit_command))
    app.add_handler(CommandHandler("trades", trades_command))
    app.add_handler(CommandHandler("levels", levels_command))
    app.add_handler(CommandHandler("scan", scan_command))
    # AI symbol commands — register common symbols + catch-all
    _common_symbols = ["spy", "eth", "btc", "aapl", "tsla", "nvda", "meta",
                       "pltr", "qqq", "amd", "googl", "amzn", "msft", "sol"]
    for _sym in _common_symbols:
        app.add_handler(CommandHandler(_sym, ai_symbol_command))
    app.add_handler(CallbackQueryHandler(callback_handler))
    return app


def _get_bot_token() -> str | None:
    """Resolve the Telegram bot token from env or alert_config."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        try:
            from alert_config import TELEGRAM_BOT_TOKEN
            bot_token = TELEGRAM_BOT_TOKEN
        except Exception:
            pass
    return bot_token


# ---------------------------------------------------------------------------
# Webhook mode (production — eliminates 409 polling conflicts)
# ---------------------------------------------------------------------------

_webhook_app = None


def get_webhook_path() -> str:
    """Return the webhook URL path (for registering the FastAPI route)."""
    bot_token = _get_bot_token()
    if not bot_token:
        return "/telegram/webhook/disabled"
    return f"/telegram/webhook/{bot_token[-10:]}"


async def setup_webhook(webhook_base_url: str) -> bool:
    """Set up Telegram webhook. Call from FastAPI lifespan."""
    global _webhook_app

    logger.info("setup_webhook: starting with base_url=%s", webhook_base_url)

    bot_token = _get_bot_token()
    if not bot_token:
        logger.warning("setup_webhook: no TELEGRAM_BOT_TOKEN — skipping")
        return False

    try:
        webhook_path = f"/telegram/webhook/{bot_token[-10:]}"
        webhook_url = f"{webhook_base_url.rstrip('/')}{webhook_path}"

        app = _build_app(bot_token)
        await app.initialize()

        await app.bot.set_webhook(
            url=webhook_url,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
        )

        await app.start()
        _webhook_app = app

        logger.info("setup_webhook: registered %s", webhook_url)
        return True
    except Exception:
        logger.exception("setup_webhook: failed")
        return False


async def process_webhook_update(update_data: dict) -> None:
    """Process an incoming webhook update from Telegram."""
    if _webhook_app is None:
        logger.warning("Webhook update received but bot not initialized")
        return

    from telegram import Update
    update = Update.de_json(update_data, _webhook_app.bot)
    await _webhook_app.process_update(update)


async def shutdown_webhook() -> None:
    """Clean shutdown — remove webhook and stop the app."""
    global _webhook_app
    if _webhook_app is not None:
        try:
            await _webhook_app.bot.delete_webhook()
            await _webhook_app.stop()
            await _webhook_app.shutdown()
        except Exception:
            logger.exception("shutdown_webhook: error")
        _webhook_app = None


# ---------------------------------------------------------------------------
# Polling mode (local dev only — no public URL available)
# ---------------------------------------------------------------------------

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
            logger.info("Telegram bot listener starting (polling, local dev)...")
            loop.run_until_complete(app.initialize())
            loop.run_until_complete(app.start())
            # drop_pending_updates=True but do NOT delete webhook
            # (production uses webhook mode with the same bot token)
            loop.run_until_complete(app.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query"],
            ))
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
