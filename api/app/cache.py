"""Redis cache for market data — deduplicates yfinance fetches across users.

Falls back to in-memory TTL cache if Redis is unavailable.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger("cache")

_redis_client = None
_memory_store: dict[str, tuple[float, Any]] = {}


def _get_redis():
    """Lazy-init Redis connection; returns None if unavailable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    from app.config import get_settings

    settings = get_settings()
    if not settings.REDIS_URL:
        logger.info("No REDIS_URL configured — using in-memory cache")
        return None

    try:
        import redis

        _redis_client = redis.Redis.from_url(
            settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2
        )
        _redis_client.ping()
        logger.info("Redis cache connected")
        return _redis_client
    except Exception:
        logger.warning("Redis unavailable — falling back to in-memory cache")
        _redis_client = None
        return None


def cache_get(key: str) -> Optional[Any]:
    """Get a value from cache. Returns None on miss."""
    r = _get_redis()
    if r:
        try:
            val = r.get(key)
            return json.loads(val) if val else None
        except Exception:
            pass

    # In-memory fallback
    entry = _memory_store.get(key)
    if entry and entry[0] > time.time():
        return entry[1]
    return None


def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> None:
    """Store a value in cache with TTL."""
    r = _get_redis()
    if r:
        try:
            r.setex(key, ttl_seconds, json.dumps(value))
            return
        except Exception:
            pass

    # In-memory fallback
    _memory_store[key] = (time.time() + ttl_seconds, value)


def cache_delete_pattern(pattern: str) -> None:
    """Delete keys matching a pattern (Redis only; no-op for memory)."""
    r = _get_redis()
    if r:
        try:
            keys = r.keys(pattern)
            if keys:
                r.delete(*keys)
        except Exception:
            pass
