"""Performance analytics — win rate by strategy, time of day, etc."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.rate_limit import limiter

router = APIRouter()


@router.get("/by-strategy")
@limiter.limit("20/minute")
async def performance_by_strategy(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Win rate and average R:R per alert strategy type."""
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
        {"uid": user.id},
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
        {"uid": user.id},
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
        {"uid": user.id},
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
