"""FastAPI dependencies: auth, tier enforcement, usage limits."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.models.user import Subscription, User
from app.tier import get_limits, has_access

settings = get_settings()


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate JWT from Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id: int = int(payload.get("sub", 0))
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await db.execute(
        select(User).options(selectinload(User.subscription)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_user_tier(user: User) -> str:
    """Return the user's effective tier — checks trial expiry."""
    if not user.subscription:
        return "free"
    sub = user.subscription
    # Active paid subscription takes priority
    if sub.status == "active" and sub.tier in ("pro", "premium", "admin"):
        return sub.tier
    # Trial check: free tier with unexpired trial → grant pro
    if sub.tier == "free" and sub.trial_ends_at:
        if datetime.now(timezone.utc) < sub.trial_ends_at.replace(tzinfo=timezone.utc):
            return "pro"
    return "free"


def is_trial_active(user: User) -> bool:
    """Check if user is currently on a trial (not a paid subscription)."""
    if not user.subscription:
        return False
    sub = user.subscription
    if sub.tier in ("pro", "premium"):
        return False  # paid user, not trial
    if sub.trial_ends_at:
        return datetime.now(timezone.utc) < sub.trial_ends_at.replace(tzinfo=timezone.utc)
    return False


def trial_days_remaining(user: User) -> int:
    """Return days left on trial, 0 if expired or no trial."""
    if not user.subscription or not user.subscription.trial_ends_at:
        return 0
    ends = user.subscription.trial_ends_at.replace(tzinfo=timezone.utc)
    remaining = (ends - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        return 0
    return max(1, int(remaining / 86400) + 1)  # ceil to nearest day


def require_tier(minimum: str):
    """Dependency factory — require user tier >= minimum."""
    async def _check(user: User = Depends(get_current_user)) -> User:
        user_tier = get_user_tier(user)
        if not has_access(user_tier, minimum):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "upgrade_required",
                    "required_tier": minimum,
                    "current_tier": user_tier,
                    "message": f"{minimum.title()} subscription required",
                },
            )
        return user
    return _check


# Convenience aliases
require_pro = require_tier("pro")
require_premium = require_tier("premium")


async def require_ai_access(user: User = Depends(get_current_user)) -> User:
    """Hard gate on AI-triggered endpoints.

    When the env var AI_ALLOWED_EMAILS is set (comma-separated list), only
    users whose email matches are allowed to invoke AI features. Every
    other user gets a 403 with upgrade prompt — including COMP, FREE,
    and even PRO/PREMIUM unless explicitly whitelisted.

    When the env var is unset, access falls through to the route's
    existing tier requirement (e.g. require_pro). So removing the env var
    restores normal tier-based access without redeploying.

    Pre-launch use: restrict cost to a single developer email.
    """
    import os
    raw = os.environ.get("AI_ALLOWED_EMAILS", "").strip()
    if not raw:
        return user  # no whitelist configured → let route's own gates decide

    allowed = {e.strip().lower() for e in raw.split(",") if e.strip()}
    user_email = (user.email or "").strip().lower()
    if user_email in allowed:
        return user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": "upgrade_required",
            "required_tier": "pro",
            "current_tier": get_user_tier(user),
            "message": "Upgrade to Pro or Premium to access AI features",
        },
    )


async def check_usage_limit(
    user: User, feature: str, db: AsyncSession,
) -> int:
    """Check daily usage for a feature. Returns remaining uses.

    Raises 429 if over limit. Returns -1 if unlimited.
    """
    user_tier = get_user_tier(user)
    limits = get_limits(user_tier)
    limit_key = f"{feature}_per_day"
    max_uses = limits.get(limit_key)

    # Trial users get reduced AI queries (4/day instead of full Pro 20/day)
    if max_uses and is_trial_active(user) and feature == "ai_queries":
        max_uses = min(max_uses, 4)

    if max_uses is None:
        return -1  # unlimited

    today = date.today().isoformat()
    result = await db.execute(
        text(
            "SELECT usage_count FROM usage_limits "
            "WHERE user_id = :uid AND feature = :f AND usage_date = :d"
        ),
        {"uid": user.id, "f": feature, "d": today},
    )
    row = result.fetchone()
    current = row[0] if row else 0
    remaining = max_uses - current

    if remaining <= 0:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "usage_limit_reached",
                "feature": feature,
                "limit": max_uses,
                "used": current,
                "remaining": 0,
                "tier": user_tier,
                "message": f"Daily limit reached ({max_uses} {feature.replace('_', ' ')}). Upgrade for more.",
            },
        )

    # Increment usage
    await db.execute(
        text(
            "INSERT INTO usage_limits (user_id, feature, usage_date, usage_count) "
            "VALUES (:uid, :f, :d, 1) "
            "ON CONFLICT (user_id, feature, usage_date) "
            "DO UPDATE SET usage_count = usage_limits.usage_count + 1"
        ),
        {"uid": user.id, "f": feature, "d": today},
    )

    return remaining - 1
