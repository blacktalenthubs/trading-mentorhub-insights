"""Notification delivery — email (SMTP) and SMS (Twilio)."""

from __future__ import annotations

import logging
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from urllib.parse import quote

from analytics.intraday_rules import AlertSignal, AlertType
from alert_config import (
    ALERT_EMAIL_FROM,
    ALERT_EMAIL_TO,
    ALERT_SMS_TO,
    SMS_GATEWAY_TO,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER,
    TWILIO_USE_WHATSAPP,
)

logger = logging.getLogger(__name__)


def _get_app_url() -> str:
    """Return the public-facing app URL, ignoring localhost values."""
    _default = "https://tradecopilot.streamlit.app"
    url = os.environ.get("APP_URL", "") or _default
    if "localhost" in url or "127.0.0.1" in url:
        return _default
    return url.rstrip("/")


def _format_sms_body(signal: AlertSignal) -> str | None:
    """Build a concise SMS/Telegram message. Returns None to skip Telegram.

    Output uses HTML formatting for Telegram (clickable links, bold headers).
    """
    import html as _html

    label = signal.alert_type.value.replace("_", " ").title()

    # NOTICE — send to Telegram (useful context: inside day, weekly tests, resistance zones)
    if signal.direction == "NOTICE":
        import html as _html_n
        _notice_msg = signal.message.split(" — ")[0] if signal.message else label
        return (
            f"<b>NOTICE — {_html_n.escape(signal.symbol)} ${signal.price:.2f}</b>\n"
            f"{_notice_msg}"
        )

    # SELL — route by type: stops → alert, resistance → NOTICE, targets → suppressed
    if signal.direction == "SELL":
        _exit_types = {"stop_loss_hit", "auto_stop_out"}
        _resistance_notice_types = {
            "weekly_high_resistance":  "Rejected at weekly high",
            "ma_resistance":           "Rejected at MA resistance",
            "resistance_prior_high":   "Rejected at prior high",
            "monthly_high_resistance": "Rejected at monthly high",
        }

        if signal.alert_type.value in _exit_types:
            import html as _html2
            return (
                f"<b>STOPPED OUT — {_html2.escape(signal.symbol)}</b>\n"
                f"Stop ${signal.price:.2f} hit\n"
                f"Trade invalidated — exit"
            )

        if signal.alert_type.value in _resistance_notice_types:
            import html as _html_res
            _res_label = _resistance_notice_types[signal.alert_type.value]
            _detail = signal.message.split(" — ")[0] if signal.message else _res_label
            return (
                f"<b>NOTICE — {_html_res.escape(signal.symbol)} ${signal.price:.2f}</b>\n"
                f"{_detail}\n"
                f"Watch for rejection or breakout"
            )

        return None  # T1/T2 suppressed — monitor sends these with Exit buttons

    # SWING alerts — labeled "SWING LONG" / "SWING EXIT" in Telegram
    if signal.alert_type.value.startswith("swing_"):
        import html as _html_swing
        _sym = _html_swing.escape(signal.symbol)

        # Swing EXIT alerts
        if signal.alert_type.value in ("swing_target_hit", "swing_stopped_out",
                                        "swing_rsi_target", "swing_pdl_close",
                                        "swing_ma_invalidated"):
            _exit_label = {
                "swing_target_hit": "TARGET REACHED",
                "swing_stopped_out": "STOP REACHED",
                "swing_rsi_target": "RSI TARGET",
                "swing_pdl_close": "CLOSED BELOW PDL",
                "swing_ma_invalidated": "MA INVALIDATED",
            }.get(signal.alert_type.value, "EXIT")
            _msg = signal.message.replace("[SWING] ", "") if signal.message else _exit_label
            return (
                f"<b>SWING EXIT — {_sym} ${signal.price:.2f}</b>\n"
                f"{_msg}"
            )

        # Swing RSI zone notices (oversold/overbought)
        if signal.alert_type.value in ("swing_rsi_oversold", "swing_rsi_overbought"):
            _msg = signal.message.replace("[SWING] ", "") if signal.message else label
            return (
                f"<b>SWING NOTICE — {_sym} ${signal.price:.2f}</b>\n"
                f"{_msg}"
            )

        # Swing BUY entries
        parts = [f"<b>SWING LONG {_sym} ${signal.price:.2f}</b>"]
        _levels = []
        if signal.entry is not None:
            _levels.append(f"Entry ${signal.entry:.2f}")
        if signal.stop is not None:
            _levels.append(f"Stop ${signal.stop:.2f} (daily close)")
        if signal.target_1 is not None:
            _levels.append(f"T1 ${signal.target_1:.2f}")
        if signal.target_2 is not None:
            _levels.append(f"T2 ${signal.target_2:.2f}")
        if _levels:
            parts.append(" · ".join(_levels))

        _reason = signal.message.replace("[SWING] ", "") if signal.message else label
        _conviction = "HIGH" if signal.score >= 75 else ("MEDIUM" if signal.score >= 55 else "LOW")
        parts.append(f"Setup: {_reason}")
        parts.append(f"Conviction: {_conviction}")
        return "\n".join(parts)[:4000]

    # VWAP reclaim — send as NOTICE (awareness, not entry pressure)
    # First VWAP reclaim from below is a momentum shift signal
    if signal.direction == "BUY" and signal.alert_type.value == "vwap_reclaim":
        import html as _html_vwap
        return (
            f"<b>NOTICE — {_html_vwap.escape(signal.symbol)} ${signal.price:.2f}</b>\n"
            f"VWAP reclaimed from below — momentum shifting bullish\n"
            f"Watch for pullback to VWAP for entry"
        )

    # SHORT filter — only structural daily-level shorts reach Telegram as SHORT
    # Key intraday levels (VWAP loss, session low, morning low) → send as NOTICE
    # Other intraday shorts → suppress entirely
    if signal.direction == "SHORT":
        _STRUCTURAL_SHORT_TYPES = {
            "pdh_failed_breakout",       # rejection at PDH
            "support_breakdown",         # break of PDL / double bottom low
            "session_high_double_top",   # daily double top rejection
            "ema_rejection_short",       # rejection at key DAILY EMA (50/100/200)
        }
        _NOTICE_SHORT_TYPES = {
            "vwap_loss":                "VWAP lost",
            "session_low_breakdown":    "Session low broken",
            "morning_low_breakdown":    "Morning low broken",
        }
        if signal.alert_type.value in _NOTICE_SHORT_TYPES:
            import html as _html_notice
            _notice_label = _NOTICE_SHORT_TYPES[signal.alert_type.value]
            return (
                f"<b>NOTICE — {_html_notice.escape(signal.symbol)} ${signal.price:.2f}</b>\n"
                f"{_notice_label} — watch for continuation or reclaim"
            )
        if signal.alert_type.value not in _STRUCTURAL_SHORT_TYPES:
            return None  # suppress remaining non-structural shorts

    # LONG (BUY) and SHORT only — minimal format for entry evaluation
    _dir = "SHORT" if signal.direction == "SHORT" else "LONG"
    # Use message prefix (e.g. "EMA50 REJECTION") when available for specificity
    _reason = signal.message.split(" — ")[0] if signal.message and " — " in signal.message else label

    parts = [f"<b>{_dir} {_html.escape(signal.symbol)} ${signal.price:.2f}</b>"]

    # Levels
    # BUG-2 fix: show both structural entry and current price when they differ
    _levels = []
    if signal.entry is not None:
        # If current price is >0.5% above entry, show both so trader knows the gap
        _entry_gap = abs(signal.price - signal.entry) / signal.entry if signal.entry > 0 else 0
        if _entry_gap > 0.005:
            _levels.append(f"Entry ${signal.entry:.2f} (now ${signal.price:.2f})")
        else:
            _levels.append(f"Entry ${signal.entry:.2f}")
    if signal.stop is not None:
        _levels.append(f"Stop ${signal.stop:.2f}")
    if signal.target_1 is not None:
        _levels.append(f"T1 ${signal.target_1:.2f}")
    if signal.target_2 is not None:
        _levels.append(f"T2 ${signal.target_2:.2f}")
    if _levels:
        parts.append(" · ".join(_levels))

    # Reason + Conviction
    _conviction = "HIGH" if signal.score >= 75 else ("MEDIUM" if signal.score >= 55 else "LOW")
    parts.append(f"Reason: {_reason}")
    parts.append(f"Conviction: {_conviction}")

    # Telegram message limit is 4096 chars; truncate safely
    return "\n".join(parts)[:4000]


def _format_email_body(signal: AlertSignal) -> str:
    """Build a concise plain-text email body — same format as Telegram."""
    import re

    # Reuse the Telegram formatter and strip HTML tags
    body = _format_sms_body(signal)
    if body is None:
        # Fallback for suppressed types (SELL/NOTICE)
        label = signal.alert_type.value.replace("_", " ").title()
        return f"{signal.direction} {signal.symbol} ${signal.price:.2f}\n{label}"

    return re.sub(r"<[^>]+>", "", body)


def send_plain_email(email_to: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns True on success."""
    if not SMTP_USER or not SMTP_PASSWORD or not email_to:
        logger.warning("Email not configured — skipping plain email")
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = ALERT_EMAIL_FROM
    msg["To"] = email_to

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(ALERT_EMAIL_FROM, [email_to], msg.as_string())
        logger.info("Plain email sent to %s: %s", email_to, subject)
        return True
    except Exception:
        logger.exception("Failed to send plain email to %s", email_to)
        return False


def send_email_to(signal: AlertSignal, email_to: str) -> bool:
    """Send an alert email to an explicit recipient. Returns True on success."""
    if not SMTP_USER or not SMTP_PASSWORD or not email_to:
        logger.warning("Email not configured — skipping")
        return False

    from ui_theme import display_direction
    dir_label, _ = display_direction(signal.direction)
    subject = (
        f"[PATTERN ALERT] {dir_label} {signal.symbol} "
        f"- {signal.alert_type.value.replace('_', ' ').title()} @ ${signal.price:.2f}"
    )
    body = _format_email_body(signal)

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = ALERT_EMAIL_FROM
    msg["To"] = email_to

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(ALERT_EMAIL_FROM, [email_to], msg.as_string())
        logger.info("Email sent to %s: %s", email_to, subject)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", email_to)
        return False


def send_email(signal: AlertSignal) -> bool:
    """Send an alert email to the global ALERT_EMAIL_TO. Returns True on success."""
    return send_email_to(signal, ALERT_EMAIL_TO)


def _send_telegram_to(
    body: str, chat_id: str, reply_markup: dict | None = None, parse_mode: str | None = None,
) -> bool:
    """Send a message via Telegram Bot API to an explicit chat_id.

    *reply_markup* — optional InlineKeyboardMarkup dict for interactive buttons.
    *parse_mode* — "HTML" or "Markdown". Auto-detected if body contains HTML tags.
    """
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        logger.warning(
            "Telegram not configured — missing %s",
            "TELEGRAM_BOT_TOKEN" if not TELEGRAM_BOT_TOKEN else "chat_id",
        )
        return False

    import json
    import urllib.request

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Auto-detect HTML if body contains tags; callers can also pass parse_mode explicitly
    _mode = parse_mode
    if _mode is None and ("<b>" in body or "<a " in body or "<i>" in body):
        _mode = "HTML"
    payload: dict = {
        "chat_id": chat_id,
        "text": body,
    }
    if _mode:
        payload["parse_mode"] = _mode
    if reply_markup:
        payload["reply_markup"] = reply_markup  # kept as dict for JSON body

    # Use JSON content-type for reliable inline-keyboard delivery;
    # form-urlencoded can mangle nested JSON with emoji characters.
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
    )

    try:
        resp = urllib.request.urlopen(req, timeout=10)
        resp_body = resp.read().decode("utf-8", errors="replace")
        logger.info(
            "Telegram sent to %s (status=%s): %s",
            chat_id, resp.status, resp_body[:200],
        )
        return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error(
            "Telegram API error %s for chat_id=%s: %s",
            e.code, chat_id, error_body,
        )
        return False
    except Exception:
        logger.exception("Failed to send Telegram message to chat_id=%s", chat_id)
        return False


def _send_telegram(body: str) -> bool:
    """Send a message via Telegram Bot API to the global TELEGRAM_CHAT_ID."""
    return _send_telegram_to(body, TELEGRAM_CHAT_ID)


def _send_sms_via_email_gateway(body: str) -> bool:
    """Send SMS via carrier email-to-SMS gateway (e.g. number@txt.att.net).

    Truncates to 160 chars (SMS limit). No Subject header — gateways may
    prepend it to the message body, wasting precious characters.
    """
    if not SMS_GATEWAY_TO or not SMTP_USER or not SMTP_PASSWORD:
        return False

    # Strip HTML tags (body may contain Telegram HTML formatting)
    import re
    plain = re.sub(r"<[^>]+>", "", body)

    # SMS limit is 160 chars; MMS can do more but not all gateways support it
    truncated = plain[:160]

    msg = MIMEText(truncated)
    msg["From"] = ALERT_EMAIL_FROM
    msg["To"] = SMS_GATEWAY_TO
    # No Subject — carrier gateways prepend it to the body

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(ALERT_EMAIL_FROM, [SMS_GATEWAY_TO], msg.as_string())
        logger.info("SMS (email gateway) sent to %s: %s", SMS_GATEWAY_TO, truncated[:50])
        return True
    except Exception:
        logger.exception("Failed to send SMS via email gateway")
        return False


def send_sms(signal: AlertSignal) -> bool:
    """Send alert via all configured channels (Telegram + Twilio)."""
    body = _format_sms_body(signal)
    if body is None:
        # Signal type suppressed (SELL/SHORT/NOTICE)
        return False

    sent_any = False

    # Telegram (primary)
    if TELEGRAM_BOT_TOKEN:
        logger.info("Notification channel: Telegram (chat_id=%s)", TELEGRAM_CHAT_ID or "<missing>")
        if _send_telegram(body):
            sent_any = True

    # Email-to-SMS gateway (always send alongside Telegram)
    if SMS_GATEWAY_TO:
        if _send_sms_via_email_gateway(body):
            sent_any = True

    if not sent_any:
        logger.warning("No notification channel delivered — check Telegram/SMS config")

    return sent_any


# Exit signals always Tier 1 (time-critical)
_TIER1_ALERT_TYPES = {
    AlertType.STOP_LOSS_HIT,
    AlertType.TARGET_1_HIT,
    AlertType.TARGET_2_HIT,
}


def _build_trade_buttons(signal: AlertSignal, alert_id: int | None) -> dict | None:
    """Build InlineKeyboardMarkup for trade ACK buttons.

    BUY/SHORT signals get "Took It" + "Skip" buttons.
    SELL signals get "Exited" + "Still Holding" buttons.
    NOTICE signals get no buttons.
    """
    if alert_id is None:
        return None

    if signal.direction in ("BUY", "SHORT"):
        return {
            "inline_keyboard": [[
                {"text": "\u2705 Took It", "callback_data": f"ack:{alert_id}"},
                {"text": "\u274c Skip", "callback_data": f"skip:{alert_id}"},
                {"text": "\U0001f6d1 Exit", "callback_data": f"exit:{alert_id}"},
            ]]
        }

    if signal.direction == "SELL":
        # T1/stop alerts get a single Exit button
        _exit_types = {"target_1_hit", "target_2_hit", "stop_loss_hit", "auto_stop_out"}
        if signal.alert_type.value in _exit_types:
            return {
                "inline_keyboard": [[
                    {"text": "\U0001f6d1 Exit Trade", "callback_data": f"exit:{alert_id}"},
                ]]
            }
        return {
            "inline_keyboard": [[
                {"text": "\U0001f4b0 Exited", "callback_data": f"exit:{alert_id}"},
                {"text": "\U0001f4aa Still Holding", "callback_data": f"hold:{alert_id}"},
            ]]
        }

    return None


def notify_user(
    signal: AlertSignal, prefs: dict, alert_id: int | None = None,
) -> tuple[bool, bool]:
    """Send notifications to a specific user based on their preferences.

    *alert_id* — if provided, BUY/SELL Telegram messages include inline
    buttons for trade acknowledgement (Took It / Skip / Exited).

    Returns (email_sent, telegram_sent).
    """
    email_sent = False
    telegram_sent = False

    if prefs.get("email_enabled"):
        email_to = prefs.get("notification_email", "")
        if email_to:
            email_sent = send_email_to(signal, email_to)

    if prefs.get("telegram_enabled"):
        chat_id = prefs.get("telegram_chat_id", "")
        if chat_id:
            body = _format_sms_body(signal)
            if body is not None:
                buttons = _build_trade_buttons(signal, alert_id)
                telegram_sent = _send_telegram_to(body, chat_id, reply_markup=buttons)
        else:
            logger.warning("notify_user: telegram_enabled but chat_id empty")
    else:
        logger.debug("notify_user: telegram_enabled=False, skipping")

    return email_sent, telegram_sent


def notify(signal: AlertSignal, alert_id: int | None = None) -> tuple[bool, bool]:
    """Send notifications for an alert signal (global fallback).

    Both email and Telegram are sent for ALL signals.
    If *alert_id* is provided, BUY/SELL Telegram messages include inline
    buttons for trade acknowledgement (Took It / Skip / Exited).

    Returns (email_sent, sms_sent).
    """
    email_sent = send_email(signal)
    sms_sent = False

    body = _format_sms_body(signal)
    if body is not None:
        # Telegram (with buttons if alert_id provided)
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            buttons = _build_trade_buttons(signal, alert_id)
            if _send_telegram_to(body, TELEGRAM_CHAT_ID, reply_markup=buttons):
                sms_sent = True

        # Email-to-SMS gateway (always send alongside Telegram)
        if SMS_GATEWAY_TO:
            if _send_sms_via_email_gateway(body):
                sms_sent = True

    return email_sent, sms_sent
