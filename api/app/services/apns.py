"""iOS APNs push notification sender — Capacitor mobile app integration.

Spec 2026-05-26 — Stage 2 of mobile rollout. Sends a native iOS push
notification when an alert fires, alongside the existing Telegram dispatch.

Activation requires four env vars from Apple Developer Portal:
  APNS_AUTH_KEY      — multiline contents of AuthKey_<KEYID>.p8 file
  APNS_KEY_ID        — 10-char key identifier
  APNS_TEAM_ID       — 10-char Apple Developer team ID
  APNS_BUNDLE_ID     — iOS app bundle identifier (e.g. com.aicopilottrader.app)
  APNS_USE_SANDBOX   — "1" for development APNs, "0" or unset for production

If any required var is missing, send_apns_push() returns False gracefully.
Lets us ship the code now and activate when the Apple account is funded.

Uses `aioapns` library (pip install aioapns). Falls back to a clean log
message if the library isn't installed yet, so production stays stable.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def apns_configured() -> bool:
    """True if all required env vars are present to actually send pushes."""
    return all(
        os.environ.get(k)
        for k in ("APNS_AUTH_KEY", "APNS_KEY_ID", "APNS_TEAM_ID", "APNS_BUNDLE_ID")
    )


async def send_apns_push(
    device_token: str,
    title: str,
    body: str,
    payload: Optional[dict] = None,
) -> bool:
    """Send a single APNs push to one device. Returns True on success.

    Gracefully no-ops if APNs isn't configured (missing env vars) or the
    `aioapns` library isn't installed. Logs the reason in both cases so we
    can see in Railway logs why it didn't fire.
    """
    if not device_token or len(device_token) < 32:
        logger.info("APNs skip: invalid device_token")
        return False
    if not apns_configured():
        logger.info("APNs skip: not configured (set APNS_* env vars)")
        return False

    try:
        from aioapns import APNs, NotificationRequest, PushType
    except ImportError:
        logger.info("APNs skip: aioapns library not installed (pip install aioapns)")
        return False

    use_sandbox = os.environ.get("APNS_USE_SANDBOX", "0") == "1"
    try:
        client = APNs(
            key=os.environ["APNS_AUTH_KEY"],
            key_id=os.environ["APNS_KEY_ID"],
            team_id=os.environ["APNS_TEAM_ID"],
            topic=os.environ["APNS_BUNDLE_ID"],
            use_sandbox=use_sandbox,
        )
        message = {
            "aps": {
                "alert": {"title": title, "body": body},
                "sound": "default",
                "badge": 1,
            }
        }
        if payload:
            message["data"] = payload  # custom fields for deep-link routing
        request = NotificationRequest(
            device_token=device_token,
            message=message,
            push_type=PushType.ALERT,
        )
        result = await client.send_notification(request)
        ok = result.is_successful
        if not ok:
            logger.warning(
                "APNs send failed: status=%s description=%s",
                result.status, result.description,
            )
        return ok
    except Exception:
        logger.exception("APNs send raised an exception")
        return False


def build_alert_push(symbol: str, alert_type: str, direction: str, entry: Optional[float]) -> tuple[str, str]:
    """Format a TV alert into (title, body) for APNs notification."""
    # Strip 'tv_' prefix + format alert_type for human reading
    clean_type = alert_type.replace("tv_", "").replace("_", " ").title()
    title = f"{direction} · {symbol}"
    body = f"{clean_type}" + (f" · ${entry:.2f}" if entry else "")
    return title, body
