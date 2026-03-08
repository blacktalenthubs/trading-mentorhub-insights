"""Per-user rate limiting using slowapi.

Limits are identified by JWT user ID (falls back to IP for unauthenticated).
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _get_user_key(request: Request) -> str:
    """Extract user ID from JWT for rate-limit keying; fall back to IP."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            from jose import jwt

            from app.config import get_settings

            settings = get_settings()
            token = auth.split(" ", 1)[1]
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
            user_id = payload.get("sub")
            if user_id:
                return f"user:{user_id}"
        except Exception:
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=_get_user_key)
