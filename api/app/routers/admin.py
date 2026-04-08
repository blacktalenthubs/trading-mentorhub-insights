"""Admin endpoints — user management, platform stats."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import Subscription, User
from app.models.watchlist import WatchlistItem
from app.models.alert import Alert

router = APIRouter()


async def _require_admin(user: User = Depends(get_current_user)):
    """Only allow admin users (user_id <= 3 or specific emails)."""
    admin_emails = {"vbolofinde@gmail.com", "segunbolofinde@gmail.com"}
    if user.email not in admin_emails:
        raise HTTPException(403, "Admin access required")
    return user


@router.get("/users")
async def list_users(
    user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all registered users with subscription and watchlist info."""
    result = await db.execute(
        select(User).order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    data = []
    for u in users:
        # Get subscription
        sub = await db.execute(
            select(Subscription).where(Subscription.user_id == u.id)
        )
        sub_row = sub.scalar_one_or_none()

        # Get watchlist count
        wl = await db.execute(
            select(func.count()).select_from(WatchlistItem).where(WatchlistItem.user_id == u.id)
        )
        wl_count = wl.scalar() or 0

        # Get alert count
        alerts = await db.execute(
            select(func.count()).select_from(Alert).where(Alert.user_id == u.id)
        )
        alert_count = alerts.scalar() or 0

        # Trial days remaining
        _trial_days = 0
        _trial_expired = False
        if sub_row and sub_row.trial_ends_at:
            from datetime import datetime, timezone
            _ends = sub_row.trial_ends_at
            if _ends.tzinfo is None:
                _ends = _ends.replace(tzinfo=timezone.utc)
            _remaining = (_ends - datetime.now(timezone.utc)).total_seconds()
            if _remaining > 0:
                _trial_days = max(1, int(_remaining / 86400) + 1)
            else:
                _trial_expired = True

        # Effective tier (accounts for active trial)
        _effective_tier = sub_row.tier if sub_row else "none"
        if _effective_tier == "free" and _trial_days > 0:
            _effective_tier = "trial"

        data.append({
            "id": u.id,
            "email": u.email,
            "display_name": u.display_name,
            "created_at": str(u.created_at),
            "tier": _effective_tier,
            "status": sub_row.status if sub_row else "none",
            "trial_days_left": _trial_days,
            "trial_expired": _trial_expired,
            "telegram_linked": bool(u.telegram_chat_id),
            "watchlist_count": wl_count,
            "alert_count": alert_count,
        })

    return {"total": len(data), "users": data}


@router.get("/stats")
async def platform_stats(
    user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Platform-wide stats for admin dashboard."""
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    pro_users = (await db.execute(
        select(func.count()).select_from(Subscription).where(Subscription.tier == "pro")
    )).scalar() or 0
    total_alerts = (await db.execute(select(func.count()).select_from(Alert))).scalar() or 0
    telegram_linked = (await db.execute(
        select(func.count()).select_from(User).where(User.telegram_chat_id.isnot(None))
    )).scalar() or 0

    # Premium users
    premium_users = (await db.execute(
        select(func.count()).select_from(Subscription).where(Subscription.tier == "premium")
    )).scalar() or 0

    # Active trials
    from datetime import datetime, timezone
    from sqlalchemy import text
    trial_users = (await db.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.tier == "free",
            Subscription.trial_ends_at.isnot(None),
            Subscription.trial_ends_at > datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )).scalar() or 0

    # Signups last 7 days
    signups_7d = (await db.execute(
        text("SELECT COUNT(*) FROM users WHERE created_at >= NOW() - INTERVAL '7 days'")
    )).scalar() or 0

    # Signups last 30 days
    signups_30d = (await db.execute(
        text("SELECT COUNT(*) FROM users WHERE created_at >= NOW() - INTERVAL '30 days'")
    )).scalar() or 0

    # Alerts today
    from datetime import date
    today = date.today().isoformat()
    alerts_today = (await db.execute(
        select(func.count()).select_from(Alert).where(Alert.session_date == today)
    )).scalar() or 0

    # Revenue estimate
    monthly_revenue = (pro_users * 49) + (premium_users * 99)

    return {
        "total_users": total_users,
        "pro_users": pro_users,
        "premium_users": premium_users,
        "free_users": total_users - pro_users - premium_users,
        "trial_users": trial_users,
        "telegram_linked": telegram_linked,
        "total_alerts": total_alerts,
        "alerts_today": alerts_today,
        "signups_7d": signups_7d,
        "signups_30d": signups_30d,
        "monthly_revenue_estimate": monthly_revenue,
    }


@router.put("/users/{user_id}/tier")
async def update_user_tier(
    user_id: int,
    body: dict,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin: change a user's subscription tier."""
    new_tier = body.get("tier", "").lower()
    if new_tier not in ("free", "pro", "premium", "admin"):
        raise HTTPException(400, f"Invalid tier: {new_tier}")

    from app.models.subscription import Subscription
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(404, f"No subscription for user {user_id}")

    sub.tier = new_tier
    sub.status = "active"
    sub.trial_ends_at = None  # Clear trial — they're on a real tier now
    await db.flush()

    return {"user_id": user_id, "tier": new_tier, "status": "active"}
