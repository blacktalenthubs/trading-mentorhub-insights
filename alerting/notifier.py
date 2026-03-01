"""Notification delivery — email (SMTP) and SMS (Twilio)."""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

from analytics.intraday_rules import AlertSignal
from alert_config import (
    ALERT_EMAIL_FROM,
    ALERT_EMAIL_TO,
    ALERT_SMS_TO,
    SMS_GATEWAY_TO,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER,
    TWILIO_USE_WHATSAPP,
)

logger = logging.getLogger(__name__)


def _format_email_body(signal: AlertSignal) -> str:
    """Build the plain-text email body for an alert."""
    now = datetime.now().strftime("%I:%M %p ET")
    lines = [
        f"Symbol:  {signal.symbol}",
        f"Signal:  {signal.direction} - {signal.alert_type.value.replace('_', ' ').title()}",
        f"Price:   ${signal.price:.2f}",
    ]

    if signal.entry is not None:
        lines.append(f"Entry:   ${signal.entry:.2f}")
    if signal.stop is not None:
        lines.append(f"Stop:    ${signal.stop:.2f}")
        if signal.entry is not None:
            risk = signal.entry - signal.stop
            lines[-1] += f" (-${risk:.2f}/share)"
    if signal.target_1 is not None:
        reward = signal.target_1 - (signal.entry or signal.price)
        lines.append(f"T1:      ${signal.target_1:.2f} (+${reward:.2f}, 1R)")
    if signal.target_2 is not None:
        reward = signal.target_2 - (signal.entry or signal.price)
        lines.append(f"T2:      ${signal.target_2:.2f} (+${reward:.2f}, 2R)")

    lines.append(f"Time:    {now}")

    if signal.message:
        lines.append(f"\n{signal.message}")

    return "\n".join(lines)


def _format_sms_body(signal: AlertSignal) -> str:
    """Build an enhanced SMS/WhatsApp message with context."""
    label = signal.alert_type.value.replace("_", " ").title()
    parts = [f"{signal.direction} {signal.symbol} ${signal.price:.2f}"]
    parts.append(label)

    # Session phase context
    if signal.session_phase:
        parts[-1] += f" ({signal.session_phase.replace('_', ' ')})"

    # Context line: SPY + Volume + VWAP
    context_bits = []
    if signal.spy_trend:
        context_bits.append(f"SPY: {signal.spy_trend}")
    if signal.volume_label:
        context_bits.append(f"Vol: {signal.volume_label.split(' (')[0]}")
    if signal.vwap_position:
        context_bits.append(f"VWAP: {signal.vwap_position.replace('VWAP', '').strip()}")
    if context_bits:
        parts.append(" | ".join(context_bits))

    if signal.stop is not None and signal.target_1 is not None:
        parts.append(f"Stop ${signal.stop:.2f} T1 ${signal.target_1:.2f}")

    # Score
    if signal.score > 0:
        parts.append(f"Score: {signal.score_label} ({signal.score}/100)")

    return "\n".join(parts)[:320]


def send_email(signal: AlertSignal) -> bool:
    """Send an alert email via SMTP. Returns True on success."""
    if not SMTP_USER or not SMTP_PASSWORD or not ALERT_EMAIL_TO:
        logger.warning("Email not configured — skipping")
        return False

    subject = (
        f"[TRADE ALERT] {signal.direction} {signal.symbol} "
        f"- {signal.alert_type.value.replace('_', ' ').title()} @ ${signal.price:.2f}"
    )
    body = _format_email_body(signal)

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = ALERT_EMAIL_FROM
    msg["To"] = ALERT_EMAIL_TO

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(ALERT_EMAIL_FROM, [ALERT_EMAIL_TO], msg.as_string())
        logger.info("Email sent: %s", subject)
        return True
    except Exception:
        logger.exception("Failed to send email")
        return False


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
    """Send SMS alert. Uses email-to-SMS gateway if configured, falls back to Twilio."""
    body = _format_sms_body(signal)

    # Prefer email-to-SMS gateway (free, no Twilio needed)
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


def notify(signal: AlertSignal) -> tuple[bool, bool]:
    """Send notifications for an alert signal.

    Email is sent for ALL signals.
    SMS is sent only for BUY signals.

    Returns (email_sent, sms_sent).
    """
    email_sent = send_email(signal)
    sms_sent = False
    if signal.direction == "BUY":
        sms_sent = send_sms(signal)
    return email_sent, sms_sent
