"""Admin endpoints — user management, platform stats."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import Subscription, User
from app.models.watchlist import WatchlistItem
from app.models.alert import Alert

router = APIRouter()


async def _require_admin(user: User = Depends(get_current_user)):
    """Only allow admin users — emails listed in dependencies.ADMIN_EMAILS."""
    from app.dependencies import is_admin_user
    if not is_admin_user(user):
        raise HTTPException(403, "Admin access required")
    return user


def _is_test_account(email: str) -> bool:
    """Heuristic for automated smoke/QA accounts (not real registrations). The DB
    is dominated by smoke-<ts>@smoketest.* and qa.* accounts (wl=0) created by CI
    — the admin wants the real signups, so these are flagged + hidden by default."""
    e = (email or "").lower()
    return (
        "@smoketest." in e
        or e.startswith("smoke-")
        or e.startswith("qa.")
        or "+test" in e
        or e.endswith(("@example.com", "@test.com"))
    )


@router.get("/users")
async def list_users(
    include_test: bool = Query(default=False, description="Include smoke/QA test accounts (hidden by default)"),
    user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List REAL registered users with subscription + watchlist info. Automated
    smoke/QA accounts are hidden by default (pass include_test=true to show them).
    Also returns test_hidden = how many were filtered out."""
    result = await db.execute(
        select(User).order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    data = []
    test_hidden = 0
    for u in users:
        is_test = _is_test_account(u.email)
        if not include_test and is_test:
            test_hidden += 1
            continue
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
            "is_test": is_test,
        })

    return {"total": len(data), "users": data, "test_hidden": test_hidden}


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


@router.get("/user-debug")
async def user_debug(
    email: str,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Diagnose a specific user's tier + Telegram rate limit state.
    Use when a user reports getting more/fewer alerts than expected.
    """
    from sqlalchemy import text
    from datetime import date

    # Find user
    result = await db.execute(
        select(User).where(User.email == email.lower())
        .options(selectinload(User.subscription))  # type: ignore
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail=f"No user with email {email}")

    # Resolve tier + trial
    from app.dependencies import get_user_tier as _gut, is_trial_active, trial_days_remaining
    from app.tier import get_limits
    tier = _gut(user)
    limits = get_limits(tier)
    trial_active = is_trial_active(user)
    trial_days = trial_days_remaining(user)

    # In-memory rate limit counters (may be 0 if worker recently restarted)
    today = date.today().isoformat()
    try:
        from analytics.ai_day_scanner import (
            _user_delivered_count, _user_limit_notified,
            _user_wait_count, _user_wait_limit_notified,
        )
        ai_delivered = _user_delivered_count.get((user.id, today), 0)
        limit_notified = (user.id, today) in _user_limit_notified
        wait_delivered = _user_wait_count.get((user.id, today), 0)
        wait_limit_notified = (user.id, today) in _user_wait_limit_notified
    except Exception:
        ai_delivered = None
        limit_notified = None
        wait_delivered = None
        wait_limit_notified = None

    # DB-backed alert counts today (reflects actual records, not memory)
    alerts_today = (await db.execute(text("""
        SELECT COUNT(*) FROM alerts
        WHERE user_id = :uid AND session_date = :d
          AND alert_type IN ('ai_day_long', 'ai_day_short', 'ai_resistance', 'ai_exit_signal')
    """), {"uid": user.id, "d": today})).scalar() or 0

    wait_alerts_today = (await db.execute(text("""
        SELECT COUNT(*) FROM alerts
        WHERE user_id = :uid AND session_date = :d
          AND alert_type = 'ai_scan_wait'
    """), {"uid": user.id, "d": today})).scalar() or 0

    rule_alerts_today = (await db.execute(text("""
        SELECT COUNT(*) FROM alerts
        WHERE user_id = :uid AND session_date = :d
          AND alert_type NOT LIKE 'ai_%'
    """), {"uid": user.id, "d": today})).scalar() or 0

    sub_info = None
    if user.subscription:
        sub = user.subscription
        sub_info = {
            "tier": sub.tier,
            "status": sub.status,
            "trial_ends_at": sub.trial_ends_at.isoformat() if sub.trial_ends_at else None,
        }

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "telegram_enabled": user.telegram_enabled,
            "telegram_chat_id": user.telegram_chat_id,
        },
        "subscription": sub_info,
        "resolved_tier": tier,
        "trial_active": trial_active,
        "trial_days_left": trial_days,
        "limits": {
            "ai_scan_alerts_per_day": limits.get("ai_scan_alerts_per_day"),
            "ai_wait_alerts_per_day": limits.get("ai_wait_alerts_per_day"),
            "visible_alerts": limits.get("visible_alerts"),
            "telegram_alerts": limits.get("telegram_alerts"),
        },
        "today_stats": {
            "ai_actionable_alerts_in_db": alerts_today,
            "ai_wait_alerts_in_db": wait_alerts_today,
            "rule_alerts_in_db": rule_alerts_today,
            "ai_telegram_delivered_counter": ai_delivered,
            "limit_reached_notified": limit_notified,
            "ai_wait_telegram_delivered_counter": wait_delivered,
            "wait_limit_reached_notified": wait_limit_notified,
        },
    }


@router.post("/watchlists/cleanup")
async def cleanup_watchlists(
    dry_run: bool = True,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Re-resolve every watchlist symbol through the Alpaca validator.

    - Crypto-only match (e.g. SOL → SOL-USD): rewrite canonical form
    - Unknown (e.g. APPL typo, XYZ garbage): delete row
    - Equity-only / already canonical: no-op

    Pass dry_run=false to apply changes. Default is dry_run=true so you can
    inspect the diff first.
    """
    from sqlalchemy import text
    from app.services.symbol_resolver import resolve_symbol

    rows = (await db.execute(
        select(WatchlistItem.id, WatchlistItem.user_id, WatchlistItem.symbol)
    )).all()

    rewrites: list[dict] = []  # {id, user_id, from, to}
    deletes: list[dict] = []   # {id, user_id, symbol, reason}
    noops = 0

    for row in rows:
        wid, uid, sym = row.id, row.user_id, row.symbol
        res = resolve_symbol(sym)
        if res.kind == "unknown":
            deletes.append({"id": wid, "user_id": uid, "symbol": sym,
                            "reason": "no data (delisted/typo)"})
        elif res.canonical and res.canonical != sym:
            rewrites.append({"id": wid, "user_id": uid,
                             "from": sym, "to": res.canonical})
        else:
            noops += 1

    applied = False
    if not dry_run:
        for r in rewrites:
            # Check if canonical already exists for user (avoid unique collision)
            exists = (await db.execute(
                select(WatchlistItem).where(
                    WatchlistItem.user_id == r["user_id"],
                    WatchlistItem.symbol == r["to"],
                )
            )).scalar_one_or_none()
            if exists:
                # Duplicate — delete the bad one rather than rename
                await db.execute(text(
                    "DELETE FROM watchlist WHERE id = :id"
                ), {"id": r["id"]})
                r["action"] = "deleted (duplicate of canonical)"
            else:
                await db.execute(text(
                    "UPDATE watchlist SET symbol = :s WHERE id = :id"
                ), {"s": r["to"], "id": r["id"]})
                r["action"] = "renamed"
        for d in deletes:
            await db.execute(text(
                "DELETE FROM watchlist WHERE id = :id"
            ), {"id": d["id"]})
        await db.commit()
        applied = True

    return {
        "dry_run": dry_run,
        "applied": applied,
        "total_rows": len(rows),
        "rewrites": rewrites,
        "deletes": deletes,
        "unchanged": noops,
    }


@router.get("/watchlists")
async def all_watchlists(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return every user's watchlist — for cross-user analysis.

    Output: list of { user_id, email, display_name, tier, symbols[] } sorted
    by most symbols first. Also includes a `symbol_popularity` map showing
    how many users watch each symbol.
    """
    # Users + subscriptions
    users_rows = (await db.execute(
        select(User).options(selectinload(User.subscription))  # type: ignore
    )).scalars().all()

    # All watchlist rows in one query
    wl_rows = (await db.execute(
        select(WatchlistItem.user_id, WatchlistItem.symbol)
    )).all()

    user_symbols: dict[int, list[str]] = {}
    popularity: dict[str, int] = {}
    for uid, sym in wl_rows:
        user_symbols.setdefault(uid, []).append(sym)
        popularity[sym] = popularity.get(sym, 0) + 1

    result = []
    for u in users_rows:
        tier = "free"
        if u.subscription:
            tier = u.subscription.tier or "free"
        symbols = sorted(user_symbols.get(u.id, []))
        result.append({
            "user_id": u.id,
            "email": u.email,
            "display_name": u.display_name,
            "tier": tier,
            "symbol_count": len(symbols),
            "symbols": symbols,
        })

    # Sort: users with most symbols first
    result.sort(key=lambda r: r["symbol_count"], reverse=True)

    # Popularity: most-watched first
    pop_sorted = sorted(
        [{"symbol": s, "watchers": c} for s, c in popularity.items()],
        key=lambda r: r["watchers"],
        reverse=True,
    )

    return {
        "users": result,
        "symbol_popularity": pop_sorted,
        "total_users": len(result),
        "total_distinct_symbols": len(popularity),
    }


@router.get("/recent-ai-alerts")
async def recent_ai_alerts(
    days: int = 1,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List recent AI LONG/SHORT alerts (DEDUPED across users by alert_type+symbol+
    minute) to show how many distinct AI signals fired. Default last 1 day."""
    from sqlalchemy import text

    # DEDUP across the per-user copies — group by (symbol, alert_type, created_at minute)
    # so a signal fired to N users counts as ONE row.
    result = await db.execute(text(f"""
        SELECT
            MIN(id) AS id,
            symbol,
            alert_type,
            direction,
            entry,
            stop,
            target_1,
            target_2,
            confidence,
            message,
            DATE_TRUNC('minute', created_at) AS minute,
            COUNT(*) AS user_copies
        FROM alerts
        WHERE alert_type IN ('ai_day_long', 'ai_day_short')
          AND created_at >= NOW() - INTERVAL '{int(days)} days'
        GROUP BY symbol, alert_type, direction, entry, stop, target_1, target_2,
                 confidence, message, DATE_TRUNC('minute', created_at)
        ORDER BY minute DESC
        LIMIT 200
    """))
    rows = result.fetchall()
    return [{
        "id": r[0],
        "symbol": r[1],
        "alert_type": r[2],
        "direction": r[3],
        "entry": r[4],
        "stop": r[5],
        "target_1": r[6],
        "target_2": r[7],
        "confidence": r[8],
        "message": (r[9] or "")[:200],
        "fired_at": r[10].isoformat() if r[10] else None,
        "user_copies": r[11],
    } for r in rows]


@router.get("/alert-debug")
async def alert_debug(
    alert_id: int,
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return full details for a single alert by ID — diagnose missed Telegrams."""
    from sqlalchemy import text

    row = await db.execute(text("""
        SELECT id, user_id, symbol, alert_type, direction, price, entry,
               stop, target_1, target_2, confidence, score, message,
               session_date, created_at, user_action
        FROM alerts WHERE id = :id
    """), {"id": alert_id})
    a = row.fetchone()
    if not a:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    # Look up corresponding auto-trade if there is one
    auto_row = await db.execute(text("""
        SELECT id, status, entry_price, stop_price, target_1_price, target_2_price,
               shares, exit_price, exit_reason, pnl_dollars, pnl_percent, r_multiple,
               opened_at, closed_at, setup_type, conviction
        FROM ai_auto_trades WHERE alert_id = :id
    """), {"id": alert_id})
    auto = auto_row.fetchone()

    # Look up the user
    user_row = await db.execute(text(
        "SELECT email, telegram_enabled, telegram_chat_id FROM users WHERE id = :uid"
    ), {"uid": a[1]})
    u = user_row.fetchone()

    return {
        "alert": {
            "id": a[0],
            "user_id": a[1],
            "user_email": u[0] if u else None,
            "user_telegram_enabled": bool(u[1]) if u else None,
            "user_telegram_linked": bool(u[2]) if u else None,
            "symbol": a[2],
            "alert_type": a[3],
            "direction": a[4],
            "price": a[5],
            "entry": a[6],
            "stop": a[7],
            "target_1": a[8],
            "target_2": a[9],
            "confidence": a[10],
            "score": a[11],
            "message": a[12],
            "session_date": a[13],
            "created_at": a[14].isoformat() if a[14] else None,
            "user_action": a[15],
        },
        "auto_trade": {
            "id": auto[0],
            "status": auto[1],
            "entry_price": auto[2],
            "stop_price": auto[3],
            "target_1_price": auto[4],
            "target_2_price": auto[5],
            "shares": auto[6],
            "exit_price": auto[7],
            "exit_reason": auto[8],
            "pnl_dollars": auto[9],
            "pnl_percent": auto[10],
            "r_multiple": auto[11],
            "opened_at": auto[12].isoformat() if auto[12] else None,
            "closed_at": auto[13].isoformat() if auto[13] else None,
            "setup_type": auto[14],
            "conviction": auto[15],
        } if auto else None,
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
        JOIN watchlist w ON w.symbol = s.symbol
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
    if new_tier not in ("free", "comp", "pro", "premium", "admin"):
        raise HTTPException(400, f"Invalid tier: {new_tier}")

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


@router.post("/run-weekly-retro")
async def run_weekly_retro_now(
    admin: User = Depends(_require_admin),
):
    """Fire the AI Friday retrospective on demand. Useful for previewing
    Friday's message earlier in the week, or re-running if Friday's cron
    misfired. Idempotency rules still apply — same user can't be retro'd
    twice on the same calendar day.
    """
    from app.main import app as _app
    from analytics.ai_weekly_retro import send_weekly_retros

    sync_session_factory = _app.state.sync_session_factory
    summary = send_weekly_retros(sync_session_factory)
    return summary


@router.post("/backfill-real-outcomes")
async def backfill_real_outcomes(
    days: int = 7,
    admin: User = Depends(_require_admin),
):
    """One-shot: backfill real_outcome / mfe_r / mae_r for alerts from the
    last N days (default 7). Pulls Alpaca session bars per (symbol, date)
    and walks each alert's window.

    Run after the nightly cron is in place, or any time you want to
    re-compute history (e.g., after fixing the classifier logic).
    Idempotent — only touches rows where real_outcome IS NULL.
    """
    from datetime import date as _date, timedelta as _td
    from app.main import app as _app
    from analytics.alert_outcomes import compute_outcomes_for_session

    sync_session_factory = _app.state.sync_session_factory

    today = _date.today()
    summaries = []
    for d in range(days):
        target = today - _td(days=d)
        # Skip weekends — no equities session.
        if target.weekday() >= 5:
            continue
        summaries.append(compute_outcomes_for_session(sync_session_factory, target))

    total_updated = sum(s["alerts_updated"] for s in summaries)
    return {"days_scanned": len(summaries), "total_updated": total_updated, "per_day": summaries}


@router.get("/traffic")
async def traffic_stats(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Site traffic — page views + unique visitors over time.

    Backed by the `site_visits` table (logged by the frontend on every route
    change via POST /api/v1/public/track). "Today" is UTC for simplicity.
    """
    from sqlalchemy import text

    async def _scalar(sql: str) -> int:
        return (await db.execute(text(sql))).scalar() or 0

    visits_today = await _scalar(
        "SELECT COUNT(*) FROM site_visits WHERE created_at >= CURRENT_DATE")
    visits_7d = await _scalar(
        "SELECT COUNT(*) FROM site_visits WHERE created_at >= NOW() - INTERVAL '7 days'")
    visits_30d = await _scalar(
        "SELECT COUNT(*) FROM site_visits WHERE created_at >= NOW() - INTERVAL '30 days'")
    uniq_today = await _scalar(
        "SELECT COUNT(DISTINCT visitor_id) FROM site_visits WHERE created_at >= CURRENT_DATE")
    uniq_7d = await _scalar(
        "SELECT COUNT(DISTINCT visitor_id) FROM site_visits WHERE created_at >= NOW() - INTERVAL '7 days'")
    uniq_30d = await _scalar(
        "SELECT COUNT(DISTINCT visitor_id) FROM site_visits WHERE created_at >= NOW() - INTERVAL '30 days'")
    logged_in_7d = await _scalar(
        "SELECT COUNT(*) FROM site_visits WHERE user_id IS NOT NULL "
        "AND created_at >= NOW() - INTERVAL '7 days'")

    top_rows = (await db.execute(text(
        "SELECT path, COUNT(*) AS n, COUNT(DISTINCT visitor_id) AS u "
        "FROM site_visits WHERE created_at >= NOW() - INTERVAL '7 days' "
        "GROUP BY path ORDER BY n DESC LIMIT 12"
    ))).fetchall()
    top_paths = [{"path": r[0], "views": r[1], "visitors": r[2]} for r in top_rows]

    trend_rows = (await db.execute(text(
        "SELECT created_at::date AS d, COUNT(*) AS n, COUNT(DISTINCT visitor_id) AS u "
        "FROM site_visits WHERE created_at >= NOW() - INTERVAL '14 days' "
        "GROUP BY d ORDER BY d"
    ))).fetchall()
    daily = [{"date": str(r[0]), "views": r[1], "visitors": r[2]} for r in trend_rows]

    return {
        "visits_today": visits_today,
        "visits_7d": visits_7d,
        "visits_30d": visits_30d,
        "unique_today": uniq_today,
        "unique_7d": uniq_7d,
        "unique_30d": uniq_30d,
        "logged_in_7d": logged_in_7d,
        "anon_7d": max(0, visits_7d - logged_in_7d),
        "top_paths": top_paths,
        "daily": daily,
    }


@router.get("/alert-health")
async def alert_health(
    admin: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Alert-engine health — what fired vs got suppressed, today + last 7d.

    Each fired signal fans out to ~one row per subscribed user, so raw row
    counts are inflated; the "fired_signals" numbers de-fan-out via DISTINCT on
    (symbol, alert_type, direction, session_date).
    """
    from datetime import date
    from sqlalchemy import text

    today = date.today().isoformat()

    delivered_rows_today = (await db.execute(text(
        "SELECT COUNT(*) FROM alerts WHERE session_date = :d AND suppressed_reason IS NULL"
    ), {"d": today})).scalar() or 0
    suppressed_rows_today = (await db.execute(text(
        "SELECT COUNT(*) FROM alerts WHERE session_date = :d AND suppressed_reason IS NOT NULL"
    ), {"d": today})).scalar() or 0
    fired_signals_today = (await db.execute(text(
        "SELECT COUNT(*) FROM (SELECT DISTINCT symbol, alert_type, direction FROM alerts "
        "WHERE session_date = :d AND suppressed_reason IS NULL) t"
    ), {"d": today})).scalar() or 0

    type_rows = (await db.execute(text(
        "SELECT alert_type, COUNT(*) AS fired FROM (SELECT DISTINCT symbol, alert_type, "
        "direction, session_date FROM alerts WHERE created_at >= NOW() - INTERVAL '7 days' "
        "AND suppressed_reason IS NULL) t GROUP BY alert_type ORDER BY fired DESC LIMIT 15"
    ))).fetchall()
    by_type = [{"alert_type": r[0], "fired_7d": r[1]} for r in type_rows]

    dir_rows = (await db.execute(text(
        "SELECT direction, COUNT(*) AS fired FROM (SELECT DISTINCT symbol, alert_type, "
        "direction, session_date FROM alerts WHERE session_date = :d "
        "AND suppressed_reason IS NULL) t GROUP BY direction ORDER BY fired DESC"
    ), {"d": today})).fetchall()
    by_direction = [{"direction": r[0], "fired": r[1]} for r in dir_rows]

    supp_rows = (await db.execute(text(
        "SELECT suppressed_reason, COUNT(*) AS n FROM alerts "
        "WHERE created_at >= NOW() - INTERVAL '7 days' AND suppressed_reason IS NOT NULL "
        "GROUP BY suppressed_reason ORDER BY n DESC LIMIT 10"
    ))).fetchall()
    suppressed_reasons = [{"reason": r[0], "rows": r[1]} for r in supp_rows]

    daily_rows = (await db.execute(text(
        "SELECT session_date, COUNT(*) AS fired FROM (SELECT DISTINCT symbol, alert_type, "
        "direction, session_date FROM alerts WHERE created_at >= NOW() - INTERVAL '14 days' "
        "AND suppressed_reason IS NULL) t GROUP BY session_date ORDER BY session_date"
    ))).fetchall()
    daily = [{"date": str(r[0]), "fired": r[1]} for r in daily_rows]

    return {
        "delivered_rows_today": delivered_rows_today,
        "suppressed_rows_today": suppressed_rows_today,
        "fired_signals_today": fired_signals_today,
        "by_type": by_type,
        "by_direction": by_direction,
        "suppressed_reasons": suppressed_reasons,
        "daily": daily,
    }
