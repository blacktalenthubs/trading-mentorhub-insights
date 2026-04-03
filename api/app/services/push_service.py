"""APNs push notification delivery using token-based auth (p8 key).

Environment variables:
    APNS_KEY_ID      — 10-character key ID from Apple Developer portal
    APNS_TEAM_ID     — Apple Developer Team ID
    APNS_KEY_PATH    — Path to the .p8 private key file
    APNS_TOPIC       — Bundle ID (e.g. com.aicopilottrader.app)
    APNS_USE_SANDBOX — Set to "1" for development/TestFlight
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

# Lazy-loaded client (module-level singleton)
_apns_client = None


def _get_client():
    """Lazily initialize the APNs client. Returns None if not configured."""
    global _apns_client
    if _apns_client is not None:
        return _apns_client

    key_id = os.environ.get("APNS_KEY_ID", "")
    team_id = os.environ.get("APNS_TEAM_ID", "")
    key_path = os.environ.get("APNS_KEY_PATH", "")

    if not all([key_id, team_id, key_path]):
        logger.info("APNs not configured — push notifications disabled")
        return None

    try:
        from aioapns import APNs, ConnectionError  # noqa: F811

        use_sandbox = os.environ.get("APNS_USE_SANDBOX", "0") == "1"
        _apns_client = APNs(
            key=key_path,
            key_id=key_id,
            team_id=team_id,
            topic=os.environ.get("APNS_TOPIC", "com.aicopilottrader.app"),
            use_sandbox=use_sandbox,
        )
        logger.info("APNs client initialized (sandbox=%s)", use_sandbox)
        return _apns_client
    except Exception:
        logger.exception("Failed to initialize APNs client")
        return None


async def send_push(
    device_token: str,
    title: str,
    body: str,
    badge: Optional[int] = None,
    data: Optional[dict] = None,
    thread_id: Optional[str] = None,
) -> bool:
    """Send a single push notification via APNs. Returns True on success."""
    client = _get_client()
    if client is None:
        return False

    try:
        from aioapns import NotificationRequest

        alert = {"title": title, "body": body}
        aps: dict = {"alert": alert, "sound": "default"}
        if badge is not None:
            aps["badge"] = badge
        if thread_id:
            aps["thread-id"] = thread_id

        payload: dict = {"aps": aps}
        if data:
            payload.update(data)

        request = NotificationRequest(
            device_token=device_token,
            message=payload,
        )
        response = await client.send_notification(request)

        if not response.is_successful:
            logger.warning(
                "APNs delivery failed for token=%s…: %s",
                device_token[:12], response.description,
            )
            return False

        logger.info("APNs push sent to token=%s…", device_token[:12])
        return True
    except Exception:
        logger.exception("APNs send error for token=%s…", device_token[:12])
        return False


async def send_push_to_user(
    device_tokens: List[str],
    title: str,
    body: str,
    badge: Optional[int] = None,
    data: Optional[dict] = None,
    thread_id: Optional[str] = None,
) -> int:
    """Send push to all of a user's devices. Returns count of successful deliveries."""
    sent = 0
    for token in device_tokens:
        if await send_push(token, title, body, badge=badge, data=data, thread_id=thread_id):
            sent += 1
    return sent


def send_push_sync(
    device_tokens: List[str],
    title: str,
    body: str,
    data: Optional[dict] = None,
    thread_id: Optional[str] = None,
) -> int:
    """Synchronous wrapper for use in background threads (APScheduler).

    Creates a new event loop to run the async push delivery.
    """
    if not device_tokens:
        return 0

    client = _get_client()
    if client is None:
        return 0

    import asyncio

    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            send_push_to_user(device_tokens, title, body, data=data, thread_id=thread_id)
        )
        loop.close()
        return result
    except Exception:
        logger.exception("sync push wrapper failed")
        return 0
