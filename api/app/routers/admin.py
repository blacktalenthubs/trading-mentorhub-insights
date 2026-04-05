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

        data.append({
            "id": u.id,
            "email": u.email,
            "display_name": u.display_name,
            "created_at": str(u.created_at),
            "tier": sub_row.tier if sub_row else "none",
            "status": sub_row.status if sub_row else "none",
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

    return {
        "total_users": total_users,
        "pro_users": pro_users,
        "free_users": total_users - pro_users,
        "telegram_linked": telegram_linked,
        "total_alerts": total_alerts,
    }
