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
    """Build a compact SMS message (target: 160 chars)."""
    parts = [f"{signal.direction} {signal.symbol} ${signal.price:.2f}"]

    label = signal.alert_type.value.replace("_", " ").title()
    parts.append(label)

    if signal.stop is not None and signal.target_1 is not None:
        parts.append(f"Stop ${signal.stop:.2f} T1 ${signal.target_1:.2f}")

    if signal.entry and signal.stop:
        risk = signal.entry - signal.stop
        if risk > 0 and signal.target_1:
            reward = signal.target_1 - signal.entry
            rr = reward / risk
            parts.append(f"R:R 1:{rr:.0f}")

    return "\n".join(parts)[:160]


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


def send_sms(signal: AlertSignal) -> bool:
    """Send via Twilio WhatsApp (default) or SMS. Returns True on success."""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not ALERT_SMS_TO:
        logger.warning("Twilio not configured — skipping")
        return False

    body = _format_sms_body(signal)

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
