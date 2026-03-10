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


def _format_email_body(signal: AlertSignal) -> str:
    """Build the plain-text email body for an alert."""
    now = datetime.now().strftime("%I:%M %p ET")
    label = signal.alert_type.value.replace("_", " ").title()
    lines = [
        f"Symbol:  {signal.symbol}",
        f"Signal:  {signal.direction} - {label}",
        f"Price:   ${signal.price:.2f}",
    ]

    if signal.score > 0:
        score_line = f"Score:   {signal.score_label} ({signal.score}/100)"
        v2 = getattr(signal, "score_v2", 0)
        if v2 and v2 != signal.score:
            v2_label = getattr(signal, "score_v2_label", "")
            score_line += f" | v2: {v2_label} ({v2}/100)"
        lines.append(score_line)
        _factors = getattr(signal, "score_factors", None)
        if _factors:
            _fl = {"ma": "MA", "vol": "Vol", "conf": "Conf", "vwap": "VWAP",
                   "rr": "R:R", "confluence": "Cnfl", "mtf": "MTF",
                   "consolidation": "Multi"}
            _fb = [f"{_fl.get(k, k)}+{v}" for k, v in _factors.items() if v]
            if _fb:
                lines.append(f"         {' '.join(_fb)}")

    if signal.entry is not None:
        lines.append(f"Entry:   ${signal.entry:.2f}")
    if signal.stop is not None:
        lines.append(f"Stop:    ${signal.stop:.2f}")
        if signal.entry is not None:
            risk = signal.entry - signal.stop
            risk_pct = risk / signal.entry * 100 if signal.entry > 0 else 0
            lines[-1] += f" (-${risk:.2f}, {risk_pct:.1f}%)"
    if signal.target_1 is not None:
        base = signal.entry or signal.price
        risk = base - signal.stop if signal.stop else 0
        reward1 = signal.target_1 - base
        r1_mult = f"{reward1 / risk:.1f}R" if risk > 0 else "+${reward1:.2f}"
        lines.append(f"T1:      ${signal.target_1:.2f} (+${reward1:.2f}, {r1_mult})")
    if signal.target_2 is not None:
        base = signal.entry or signal.price
        risk = base - signal.stop if signal.stop else 0
        reward2 = signal.target_2 - base
        r2_mult = f"{reward2 / risk:.1f}R" if risk > 0 else "+${reward2:.2f}"
        lines.append(f"T2:      ${signal.target_2:.2f} (+${reward2:.2f}, {r2_mult})")

    lines.append(f"Time:    {now}")

    if signal.message:
        lines.append(f"\n{signal.message}")

    if getattr(signal, "narrative", ""):
        lines.append(f"\nTHESIS:\n{signal.narrative}")

    return "\n".join(lines)


def _get_app_url() -> str:
    """Return the public-facing app URL, ignoring localhost values."""
    _default = "https://tradecopilot.streamlit.app"
    url = os.environ.get("APP_URL", "") or _default
    if "localhost" in url or "127.0.0.1" in url:
        return _default
    return url.rstrip("/")


def _format_sms_body(signal: AlertSignal) -> str:
    """Build a concise SMS/Telegram message optimised for at-a-glance action.

    Output uses HTML formatting for Telegram (clickable links, bold headers).
    """
    import html as _html

    label = signal.alert_type.value.replace("_", " ").title()

    if signal.direction == "SELL":
        # SELL signals: compact 2-3 line format
        parts = [f"<b>EXIT ZONE {_html.escape(signal.symbol)} ${signal.price:.2f}</b>"]
        parts.append(_html.escape(label))
        if signal.message:
            hint = signal.message.split("|")[0].strip()
            if hint:
                parts.append(_html.escape(hint))
        return "\n".join(parts)[:400]

    if signal.direction == "NOTICE":
        # Informational alerts (key level touches) — not actionable
        parts = [f"<b>MARKET UPDATE {_html.escape(signal.symbol)} ${signal.price:.2f}</b>"]
        parts.append(_html.escape(label))
        if signal.entry is not None:
            parts.append(f"Key Level ${signal.entry:.2f}")
        if signal.message:
            hint = signal.message.split("|")[0].strip()
            if hint:
                parts.append(_html.escape(hint))
        return "\n".join(parts)[:400]

    # BUY / SHORT signals: entry, targets, score on first line
    _prefix = "POTENTIAL SHORT" if signal.direction == "SHORT" else "POTENTIAL ENTRY"
    score_tag = ""
    if signal.score > 0:
        v2 = getattr(signal, "score_v2", 0)
        v2_label = getattr(signal, "score_v2_label", "")
        if v2 and v2 != signal.score:
            score_tag = f" — {signal.score_label} ({signal.score}) v2:{v2_label} ({v2})"
        else:
            score_tag = f" — {signal.score_label} ({signal.score})"
    parts = [f"<b>{_prefix} {_html.escape(signal.symbol)} ${signal.price:.2f}{_html.escape(score_tag)}</b>"]
    parts.append(_html.escape(label))

    # Potential Entry | Stop
    if signal.entry is not None and signal.stop is not None:
        parts.append(f"Potential Entry ${signal.entry:.2f} | Stop ${signal.stop:.2f}")

    # T1 | T2
    t_bits = []
    if signal.target_1 is not None:
        t_bits.append(f"T1 ${signal.target_1:.2f}")
    if signal.target_2 is not None:
        t_bits.append(f"T2 ${signal.target_2:.2f}")
    if t_bits:
        parts.append(" | ".join(t_bits))

    # Vol + VWAP (compact context)
    ctx = []
    if signal.volume_label:
        ctx.append(f"Vol: {_html.escape(signal.volume_label.split(' (')[0])}")
    if signal.vwap_position:
        ctx.append(_html.escape(signal.vwap_position.replace("VWAP", "").strip()))
    if ctx:
        parts.append(" | ".join(ctx))

    # Day pattern + MA context (compact tags)
    tags = []
    if getattr(signal, "day_pattern", "") in ("inside", "outside"):
        tags.append(f"{signal.day_pattern.upper()} DAY")
    if getattr(signal, "ma_defending", ""):
        tags.append(f"Def {_html.escape(signal.ma_defending)}")
    if getattr(signal, "ma_rejected_by", ""):
        tags.append(f"Res {_html.escape(signal.ma_rejected_by)}")
    if tags:
        parts.append(" | ".join(tags))

    # Score breakdown omitted — A+ (100) in header is sufficient for Telegram.
    # Full factor breakdown available in email and dashboard.

    # Signal context — phase, VWAP, confluence, hourly targets
    if signal.message:
        parts.append(_html.escape(signal.message))

    # AI thesis — first sentence only (Telegram char limit)
    if getattr(signal, "narrative", ""):
        import re
        sentences = re.split(r"\.(?:\s|$)", signal.narrative, maxsplit=1)
        if sentences and sentences[0].strip():
            parts.append(_html.escape(sentences[0].strip()) + ".")

    # Deep link to AI Coach for further analysis (clickable HTML link)
    _app_url = _get_app_url()
    _alert_type_val = signal.alert_type.value
    _link = (
        f"{_app_url}/AI_Coach"
        f"?symbol={quote(signal.symbol)}&alert={quote(_alert_type_val)}"
    )
    parts.append(f'<a href="{_link}">Analyze in AI Coach</a>')

    # Telegram message limit is 4096 chars; truncate safely
    return "\n".join(parts)[:4000]


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
        f"[TRADE ALERT] {dir_label} {signal.symbol} "
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

    # SMS limit is 160 chars; MMS can do more but not all gateways support it
    truncated = body[:160]

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
    """Send SMS alert. Tries: Telegram → email gateway → Twilio."""
    body = _format_sms_body(signal)

    # Prefer Telegram (free, instant, reliable)
    if TELEGRAM_BOT_TOKEN:
        logger.info("Notification channel: Telegram (chat_id=%s)", TELEGRAM_CHAT_ID or "<missing>")
        return _send_telegram(body)

    # Fallback: email-to-SMS gateway
    if SMS_GATEWAY_TO:
        return _send_sms_via_email_gateway(body)

    # Fallback: Twilio
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not ALERT_SMS_TO:
        logger.warning("SMS not configured — skipping (set SMS_GATEWAY_TO or Twilio vars)")
        return False

    try:
        from twilio.rest import Client

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        if TWILIO_USE_WHATSAPP:
            from_num = f"whatsapp:{TWILIO_FROM_NUMBER}"
            to_num = f"whatsapp:{ALERT_SMS_TO}"
            channel = "WhatsApp"
        else:
            from_num = TWILIO_FROM_NUMBER
            to_num = ALERT_SMS_TO
            channel = "SMS"

        client.messages.create(body=body, from_=from_num, to=to_num)
        logger.info("%s sent to %s: %s", channel, to_num, body[:50])
        return True
    except Exception:
        logger.exception("Failed to send %s", "WhatsApp" if TWILIO_USE_WHATSAPP else "SMS")
        return False


# Exit signals always Tier 1 (time-critical)
_TIER1_ALERT_TYPES = {
    AlertType.STOP_LOSS_HIT,
    AlertType.AUTO_STOP_OUT,
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
            ]]
        }

    if signal.direction == "SELL":
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
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        body = _format_sms_body(signal)
        buttons = _build_trade_buttons(signal, alert_id)
        sms_sent = _send_telegram_to(body, TELEGRAM_CHAT_ID, reply_markup=buttons)
    else:
        sms_sent = send_sms(signal)

    return email_sent, sms_sent
