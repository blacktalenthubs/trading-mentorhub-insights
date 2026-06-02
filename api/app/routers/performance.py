"""Performance analytics — win rate by strategy, time of day, etc."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import ADMIN_EMAILS, get_current_user
from app.models.alert import Alert
from app.models.user import User
from app.rate_limit import limiter
from sqlalchemy import select

router = APIRouter()


async def _scope_uid(user: User, db: AsyncSession) -> int:
    """2026-06-01 public-access launch — read-only Performance reports fall
    back to the first admin's user_id when the caller has zero alert rows.
    Brand-new users see the founder's track record until they accumulate
    their own data. Mirrors _history_user_id in alerts.py.
    """
    exists = await db.execute(
        select(Alert.id).where(Alert.user_id == user.id).limit(1)
    )
    if exists.scalar_one_or_none() is not None:
        return user.id
    admin_id = (await db.execute(
        select(User.id).where(User.email.in_(ADMIN_EMAILS)).order_by(User.id).limit(1)
    )).scalar_one_or_none()
    return admin_id if admin_id is not None else user.id


@router.get("/by-strategy")
@limiter.limit("20/minute")
async def performance_by_strategy(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Win rate and average R:R per alert strategy type."""
    scope_uid = await _scope_uid(user, db)
    result = await db.execute(
        text("""
            WITH outcomes AS (
                SELECT
                    a.alert_type,
                    a.direction,
                    a.id as alert_id,
                    a.entry,
                    a.stop,
                    a.target_1,
                    a.user_action,
                    a.confidence,
                    a.score,
                    a.confluence_score,
                    -- Check if there's a T1 hit, T2 hit, or stop hit after this alert
                    (SELECT COUNT(*) FROM alerts t1
                     WHERE t1.user_id = a.user_id AND t1.symbol = a.symbol
                     AND t1.alert_type = 'target_1_hit'
                     AND t1.session_date = a.session_date
                     AND t1.created_at > a.created_at) as t1_hits,
                    (SELECT COUNT(*) FROM alerts t2
                     WHERE t2.user_id = a.user_id AND t2.symbol = a.symbol
                     AND t2.alert_type = 'target_2_hit'
                     AND t2.session_date = a.session_date
                     AND t2.created_at > a.created_at) as t2_hits,
                    (SELECT COUNT(*) FROM alerts sl
                     WHERE sl.user_id = a.user_id AND sl.symbol = a.symbol
                     AND sl.alert_type = 'stop_loss_hit'
                     AND sl.session_date = a.session_date
                     AND sl.created_at > a.created_at) as stop_hits
                FROM alerts a
                WHERE a.user_id = :uid
                AND a.direction IN ('BUY', 'SHORT')
                AND a.alert_type NOT IN ('target_1_hit', 'target_2_hit', 'stop_loss_hit',
                                         'auto_stop_out', 'vwap_loss', 'vwap_reclaim')
            )
            SELECT
                alert_type,
                COUNT(*) as total,
                SUM(CASE WHEN t1_hits > 0 OR t2_hits > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN stop_hits > 0 AND t1_hits = 0 THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN t1_hits = 0 AND stop_hits = 0 THEN 1 ELSE 0 END) as no_outcome,
                SUM(CASE WHEN t2_hits > 0 THEN 1 ELSE 0 END) as t2_wins,
                ROUND(AVG(score), 0) as avg_score,
                ROUND(AVG(confluence_score), 1) as avg_confluence
            FROM outcomes
            GROUP BY alert_type
            HAVING COUNT(*) >= 2
            ORDER BY
                CAST(SUM(CASE WHEN t1_hits > 0 OR t2_hits > 0 THEN 1 ELSE 0 END) AS FLOAT)
                / CAST(COUNT(*) AS FLOAT) DESC
        """),
        {"uid": scope_uid},
    )
    rows = result.fetchall()

    strategies = []
    for row in rows:
        total = row[1]
        wins = row[2]
        losses = row[3]
        no_outcome = row[4]
        t2_wins = row[5]
        resolved = wins + losses
        win_rate = round((wins / resolved * 100) if resolved > 0 else 0, 1)

        strategies.append({
            "alert_type": row[0],
            "total": total,
            "wins": wins,
            "losses": losses,
            "no_outcome": no_outcome,
            "t2_wins": t2_wins,
            "win_rate": win_rate,
            "avg_score": int(row[6] or 0),
            "avg_confluence": float(row[7] or 0),
        })

    return strategies


@router.get("/by-hour")
@limiter.limit("20/minute")
async def performance_by_hour(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Win rate by hour of day."""
    scope_uid = await _scope_uid(user, db)
    result = await db.execute(
        text("""
            WITH outcomes AS (
                SELECT
                    a.id,
                    a.created_at,
                    (SELECT COUNT(*) FROM alerts t1
                     WHERE t1.user_id = a.user_id AND t1.symbol = a.symbol
                     AND t1.alert_type = 'target_1_hit'
                     AND t1.session_date = a.session_date
                     AND t1.created_at > a.created_at) as t1_hits,
                    (SELECT COUNT(*) FROM alerts sl
                     WHERE sl.user_id = a.user_id AND sl.symbol = a.symbol
                     AND sl.alert_type = 'stop_loss_hit'
                     AND sl.session_date = a.session_date
                     AND sl.created_at > a.created_at) as stop_hits
                FROM alerts a
                WHERE a.user_id = :uid
                AND a.direction IN ('BUY', 'SHORT')
                AND a.alert_type NOT IN ('target_1_hit', 'target_2_hit', 'stop_loss_hit',
                                         'auto_stop_out', 'vwap_loss', 'vwap_reclaim')
            )
            SELECT
                CAST(strftime('%H', created_at) AS INTEGER) as hour,
                COUNT(*) as total,
                SUM(CASE WHEN t1_hits > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN stop_hits > 0 AND t1_hits = 0 THEN 1 ELSE 0 END) as losses
            FROM outcomes
            GROUP BY hour
            HAVING COUNT(*) >= 2
            ORDER BY hour
        """),
        {"uid": scope_uid},
    )
    rows = result.fetchall()

    return [
        {
            "hour": row[0],
            "total": row[1],
            "wins": row[2],
            "losses": row[3],
            "win_rate": round((row[2] / (row[2] + row[3]) * 100) if (row[2] + row[3]) > 0 else 0, 1),
        }
        for row in rows
    ]


@router.get("/summary")
@limiter.limit("20/minute")
async def performance_summary(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Overall performance summary."""
    scope_uid = await _scope_uid(user, db)
    result = await db.execute(
        text("""
            SELECT
                COUNT(*) as total_alerts,
                SUM(CASE WHEN direction = 'BUY' THEN 1 ELSE 0 END) as buys,
                SUM(CASE WHEN direction = 'SHORT' THEN 1 ELSE 0 END) as shorts,
                SUM(CASE WHEN alert_type = 'target_1_hit' THEN 1 ELSE 0 END) as t1_hits,
                SUM(CASE WHEN alert_type = 'target_2_hit' THEN 1 ELSE 0 END) as t2_hits,
                SUM(CASE WHEN alert_type = 'stop_loss_hit' THEN 1 ELSE 0 END) as stops,
                COUNT(DISTINCT session_date) as trading_days,
                COUNT(DISTINCT symbol) as symbols_traded
            FROM alerts
            WHERE user_id = :uid
        """),
        {"uid": scope_uid},
    )
    row = result.fetchone()
    if not row:
        return {"total_alerts": 0}

    return {
        "total_alerts": row[0],
        "buys": row[1],
        "shorts": row[2],
        "t1_hits": row[3],
        "t2_hits": row[4],
        "stops": row[5],
        "trading_days": row[6],
        "symbols_traded": row[7],
    }


# ── Weekly pattern report (spec 61 follow-up) ───────────────────────
# Aggregates the past Mon-Fri of alert fires by pattern with the two
# quality signals that drove the v2 gates: volume_ratio + vwap_slope_pct.
# Plus top/bottom 10 individual fires by volume so the user can spot
# both the best signals and the noise still slipping through.

from datetime import date, datetime, timedelta  # noqa: E402
from typing import Optional  # noqa: E402

from fastapi import Query  # noqa: E402
from app.models.alert_type_config import (  # noqa: E402
    ALERT_TYPE_CATALOG, OBSOLETE_ALERT_TYPES, describe_alert_type,
)


def _week_bounds(week_param: Optional[str]) -> tuple[date, date]:
    """Returns (monday, friday) for the requested week. If week_param is
    a YYYY-MM-DD string, we anchor to the Monday of THAT week. Otherwise
    we use the current week.
    """
    if week_param:
        try:
            anchor = datetime.strptime(week_param, "%Y-%m-%d").date()
        except ValueError:
            anchor = date.today()
    else:
        anchor = date.today()
    monday = anchor - timedelta(days=anchor.weekday())  # weekday(): Mon=0
    friday = monday + timedelta(days=4)
    return monday, friday


@router.get("/weekly")
@limiter.limit("20/minute")
async def weekly_pattern_report(
    request: Request,
    week: Optional[str] = Query(None, description="YYYY-MM-DD anchor; defaults to this week's Monday"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pattern leaderboard + top/bottom 10 individual fires for the
    week (Mon-Fri inclusive). Excludes OBSOLETE alert types so the
    deprecated pullback_long etc. don't pollute the breakdown.

    The same query runs across whatever data the user has for that week
    — no auth-scope leak: every WHERE filters on alerts.user_id = :uid.
    """
    monday, friday = _week_bounds(week)
    # Inclusive end-of-Friday in UTC-ish terms — query uses session_date
    # which is local ET so this is safe.
    start_iso = monday.isoformat()
    end_iso = friday.isoformat()

    scope_uid = await _scope_uid(user, db)
    obsolete_list = list(OBSOLETE_ALERT_TYPES)
    label_map = {row[0]: row[1] for row in ALERT_TYPE_CATALOG}

    # Pattern aggregates — fires, avg vol, avg slope, % above quality gates,
    # PLUS real-outcome stats from analytics/alert_outcomes.py.
    agg_rows = (await db.execute(text("""
        SELECT
            alert_type,
            COUNT(*) AS fires,
            AVG(volume_ratio) AS avg_vol,
            AVG(vwap_slope_pct) AS avg_slope,
            SUM(CASE
                WHEN volume_ratio >= 2.0 AND vwap_slope_pct >= 0.05 THEN 1
                ELSE 0
            END) AS gates_passed,
            SUM(CASE WHEN real_outcome IS NOT NULL THEN 1 ELSE 0 END) AS graded,
            SUM(CASE WHEN real_outcome = 'worked' THEN 1 ELSE 0 END) AS worked,
            AVG(mfe_r) AS avg_mfe_r
        FROM alerts
        WHERE user_id = :uid
          AND session_date BETWEEN :a AND :b
          AND (:no_obsolete OR NOT (alert_type = ANY(:obsolete)))
        GROUP BY alert_type
    """), {
        "uid": scope_uid,
        "a": start_iso,
        "b": end_iso,
        "no_obsolete": False,
        "obsolete": obsolete_list,
    })).all()

    patterns = []
    for at, fires, avg_vol, avg_slope, gates_passed, graded, worked, avg_mfe in agg_rows:
        if at in OBSOLETE_ALERT_TYPES:
            continue
        graded_n = int(graded or 0)
        worked_n = int(worked or 0)
        patterns.append({
            "alert_type": at,
            "label": label_map.get(at, at),
            "description": describe_alert_type(at),
            "fires": int(fires or 0),
            "avg_vol_ratio": round(float(avg_vol), 2) if avg_vol is not None else None,
            "avg_vwap_slope_pct": round(float(avg_slope), 3) if avg_slope is not None else None,
            "pct_above_gates": round(int(gates_passed or 0) / fires * 100, 1) if fires else 0.0,
            "graded": graded_n,
            "real_worked_pct": round(worked_n / graded_n * 100, 1) if graded_n else None,
            "avg_mfe_r": round(float(avg_mfe), 2) if avg_mfe is not None else None,
        })
    patterns.sort(key=lambda p: -p["fires"])

    # Top 10 by volume (highest conviction fires).
    top_rows = (await db.execute(text("""
        SELECT id, symbol, alert_type, direction, created_at, volume_ratio,
               vwap_slope_pct, entry, stop, target_1
        FROM alerts
        WHERE user_id = :uid
          AND session_date BETWEEN :a AND :b
          AND volume_ratio IS NOT NULL
          AND NOT (alert_type = ANY(:obsolete))
        ORDER BY volume_ratio DESC
        LIMIT 10
    """), {"uid": scope_uid, "a": start_iso, "b": end_iso, "obsolete": obsolete_list})).all()

    # Bottom 10 by volume (noise still slipping through gates).
    bottom_rows = (await db.execute(text("""
        SELECT id, symbol, alert_type, direction, created_at, volume_ratio,
               vwap_slope_pct, entry, stop, target_1
        FROM alerts
        WHERE user_id = :uid
          AND session_date BETWEEN :a AND :b
          AND volume_ratio IS NOT NULL
          AND NOT (alert_type = ANY(:obsolete))
        ORDER BY volume_ratio ASC
        LIMIT 10
    """), {"uid": scope_uid, "a": start_iso, "b": end_iso, "obsolete": obsolete_list})).all()

    def _to_fire(r) -> dict:
        (aid, sym, at, dirn, ts, vol, slope, entry, stop, t1) = r
        return {
            "id": aid,
            "symbol": sym,
            "alert_type": at,
            "label": label_map.get(at, at),
            "description": describe_alert_type(at),
            "direction": dirn,
            "created_at": ts.isoformat() + "Z" if ts else None,
            "volume_ratio": float(vol) if vol is not None else None,
            "vwap_slope_pct": float(slope) if slope is not None else None,
            "entry": float(entry) if entry is not None else None,
            "stop": float(stop) if stop is not None else None,
            "target_1": float(t1) if t1 is not None else None,
        }

    # Top-line totals.
    total_fires = sum(p["fires"] for p in patterns)
    unique_symbols = (await db.execute(text("""
        SELECT COUNT(DISTINCT symbol)
        FROM alerts
        WHERE user_id = :uid
          AND session_date BETWEEN :a AND :b
          AND NOT (alert_type = ANY(:obsolete))
    """), {"uid": scope_uid, "a": start_iso, "b": end_iso, "obsolete": obsolete_list})).scalar() or 0

    return {
        "week_start": start_iso,
        "week_end": end_iso,
        "total_fires": total_fires,
        "unique_symbols": int(unique_symbols),
        "patterns": patterns,
        "top_volume": [_to_fire(r) for r in top_rows],
        "bottom_volume": [_to_fire(r) for r in bottom_rows],
    }
