"""Alert event bus — delivers real-time alerts to connected SSE clients."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Dict, List

logger = logging.getLogger("alert_bus")

# Per-user asyncio queues for SSE delivery
_user_queues: Dict[int, List[asyncio.Queue]] = defaultdict(list)


def subscribe(user_id: int) -> asyncio.Queue:
    """Create a new SSE subscription queue for a user."""
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _user_queues[user_id].append(q)
    logger.info("SSE subscribe: user=%d (total=%d)", user_id, len(_user_queues[user_id]))
    return q


def unsubscribe(user_id: int, q: asyncio.Queue) -> None:
    """Remove a subscription queue."""
    queues = _user_queues.get(user_id, [])
    if q in queues:
        queues.remove(q)
    if not queues:
        _user_queues.pop(user_id, None)
    logger.info("SSE unsubscribe: user=%d", user_id)


def publish(user_id: int, alert_data: dict) -> None:
    """Push an alert to all of a user's connected SSE clients."""
    queues = _user_queues.get(user_id, [])
    payload = json.dumps(alert_data)
    for q in queues:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("SSE queue full for user=%d, dropping alert", user_id)


def publish_all(alert_data: dict) -> None:
    """Broadcast an alert to all connected users."""
    payload = json.dumps(alert_data)
    for user_id, queues in _user_queues.items():
        for q in queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass
