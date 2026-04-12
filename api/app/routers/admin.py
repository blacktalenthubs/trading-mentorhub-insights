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


@router.get("/attribution")
async def signup_attribution(
    days: int = 30,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Signups grouped by attribution source/medium/campaign for the last N days."""
    from sqlalchemy import text

    # By source
    by_source = await db.execute(text(
        f"SELECT COALESCE(attribution_source, 'direct') AS source, COUNT(*) AS count "
        f"FROM users WHERE created_at >= NOW() - INTERVAL '{int(days)} days' "
        f"GROUP BY source ORDER BY count DESC"
    ))
    sources = [{"source": r[0], "count": r[1]} for r in by_source.all()]

    # By medium
    by_medium = await db.execute(text(
        f"SELECT COALESCE(attribution_medium, 'direct') AS medium, COUNT(*) AS count "
        f"FROM users WHERE created_at >= NOW() - INTERVAL '{int(days)} days' "
        f"GROUP BY medium ORDER BY count DESC"
    ))
    mediums = [{"medium": r[0], "count": r[1]} for r in by_medium.all()]

    # By campaign (only non-null)
    by_campaign = await db.execute(text(
        f"SELECT attribution_campaign AS campaign, COUNT(*) AS count "
        f"FROM users WHERE created_at >= NOW() - INTERVAL '{int(days)} days' "
        f"AND attribution_campaign IS NOT NULL "
        f"GROUP BY campaign ORDER BY count DESC LIMIT 20"
    ))
    campaigns = [{"campaign": r[0], "count": r[1]} for r in by_campaign.all()]

    total = (await db.execute(text(
        f"SELECT COUNT(*) FROM users WHERE created_at >= NOW() - INTERVAL '{int(days)} days'"
    ))).scalar() or 0

    return {
        "days": days,
        "total_signups": total,
        "by_source": sources,
        "by_medium": mediums,
        "by_campaign": campaigns,
    }


@router.post("/backfill-ai-alerts")
async def backfill_ai_alerts(
    days: int = 7,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """One-time backfill: duplicate historical AI alerts for each user watching
    the symbol, so they show up in each user's Trade Review + replay.

    Problem context: before the per-user fix, AI alerts were recorded only for
    _first_uid. Now we create one row per watcher. This endpoint backfills the
    historical gap. Idempotent — skips if a row for (user_id, alert_type,
    symbol, created_at) already exists.
    """
    from sqlalchemy import text

    inserted_total = 0
    # For each AI alert in the last N days, find all users watching that symbol
    # and insert a duplicate row (preserving all fields except user_id + id).
    result = await db.execute(text(f"""
        WITH source AS (
            SELECT a.id, a.symbol, a.alert_type, a.direction, a.price, a.entry,
                   a.stop, a.target_1, a.target_2, a.confidence, a.message,
                   a.score, a.session_date, a.created_at, a.user_id AS orig_uid
            FROM alerts a
            WHERE a.created_at >= NOW() - INTERVAL '{int(days)} days'
              AND a.alert_type LIKE 'ai_%'
        )
        SELECT s.*, w.user_id AS watcher_uid
        FROM source s
        JOIN watchlist_items w ON w.symbol = s.symbol
        WHERE w.user_id != s.orig_uid
          AND NOT EXISTS (
              SELECT 1 FROM alerts a2
              WHERE a2.user_id = w.user_id
                AND a2.symbol = s.symbol
                AND a2.alert_type = s.alert_type
                AND a2.created_at = s.created_at
          )
    """))
    rows = result.all()

    for r in rows:
        await db.execute(text("""
            INSERT INTO alerts (
                user_id, symbol, alert_type, direction, price, entry,
                stop, target_1, target_2, confidence, message, score,
                session_date, created_at
            ) VALUES (
                :uid, :sym, :atype, :dir, :price, :entry,
                :stop, :t1, :t2, :conf, :msg, :score,
                :sd, :ca
            )
        """), {
            "uid": r.watcher_uid,
            "sym": r.symbol,
            "atype": r.alert_type,
            "dir": r.direction,
            "price": r.price,
            "entry": r.entry,
            "stop": r.stop,
            "t1": r.target_1,
            "t2": r.target_2,
            "conf": r.confidence,
            "msg": r.message,
            "score": r.score,
            "sd": r.session_date,
            "ca": r.created_at,
        })
        inserted_total += 1

    await db.commit()
    return {"inserted": inserted_total, "days": days}


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
