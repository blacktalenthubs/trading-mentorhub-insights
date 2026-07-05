"""Performance analytics — win rate by strategy, time of day, etc."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import ADMIN_EMAILS, get_current_user
from app.models.alert import Alert
from app.models.user import User
from app.rate_limit import limiter
from sqlalchemy import select

router = APIRouter()


async def _scope_uid(user: User, db: AsyncSession) -> int:
    """Scope Performance reports to the caller's OWN user_id — always.

    Per-user routing (#253): the old admin fallback (showing a brand-new user the
    founder's track record when they have zero alerts) is REMOVED — it leaked one
    user's performance into another's dashboard. No alerts → an honest empty
    report. Mirrors the same fix in alerts.py _history_user_id.
    """
    _ = db  # kept for signature compatibility
    return user.id


@router.get("/report")
@limiter.limit("60/minute")
async def performance_report(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Precomputed alert-outcome report — the pattern leaderboard + date-grouped alerts the
    Performance page renders. Read from market_reports[kind=performance], published by the
    offline scorer (analytics/performance_report.py; nightly on the triage worker). Outcomes
    are scored against price OFFLINE — nothing is fetched in-request (yfinance is blocked on
    this service). Platform-wide (every alert's outcome, same for all users). Fails soft."""
    return await _scoped_report(db, user.id)


async def _scoped_report(db: AsyncSession, user_id: int) -> dict:
    """The latest performance blob, scoped to a user's watchlist symbols (fallback = all)."""
    import json as _json
    row = (await db.execute(text(
        "SELECT body, session_date, created_at FROM market_reports "
        "WHERE kind = 'performance' ORDER BY session_date DESC LIMIT 1"
    ))).fetchone()
    if not row:
        return {"as_of": None, "alerts": []}
    body = _json.loads(row[0]) if isinstance(row[0], str) else row[0]
    wl = (await db.execute(
        text("SELECT DISTINCT upper(symbol) FROM watchlist WHERE user_id = :uid"),
        {"uid": user_id},
    )).fetchall()
    syms = {r[0] for r in wl}
    alerts = body.get("alerts", []) or []
    scoped = [a for a in alerts if str(a.get("symbol", "")).upper() in syms] if syms else alerts
    body["alerts"] = scoped
    return {"as_of": str(row[1]), "generated_at": str(row[2]),
            "watchlist_scoped": bool(syms), "watchlist_count": len(syms), **body}


@router.post("/share")
@limiter.limit("10/minute")
async def performance_share(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Snapshot the caller's (watchlist-scoped) performance under a random token so it can be
    viewed logged-out at /public/performance/{token}. Stable snapshot — the link shows what the
    user shared, not a live feed.

    Returns BOTH the token and the full canonical `url`. The URL is built server-side against
    PUBLIC_BASE_URL (the canonical app host) rather than the browser's window.location.origin —
    otherwise a user browsing on a legacy/transition domain (e.g. tradingwithai.ai) would mint
    links on a host that drops logged-out visitors on the marketing landing page instead of the
    report."""
    import json as _json
    import secrets
    data = await _scoped_report(db, user.id)
    token = secrets.token_urlsafe(9)
    await db.execute(text(
        "CREATE TABLE IF NOT EXISTS share_links ("
        " token TEXT PRIMARY KEY, kind TEXT NOT NULL, user_id INTEGER,"
        " payload TEXT NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT NOW())"
    ))
    await db.execute(text(
        "INSERT INTO share_links (token, kind, user_id, payload) "
        "VALUES (:t, 'performance', :u, :p)"
    ), {"t": token, "u": user.id, "p": _json.dumps(data, default=str)})
    await db.commit()
    base = get_settings().PUBLIC_BASE_URL.rstrip("/")
    return {"token": token, "url": f"{base}/public/performance/{token}"}


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


# ── Strategy Analysis — real forward returns, swing-vs-day, AI keep/stop ──
# Aggregates ALL alerts globally (patterns are system-wide) over a lookback
# window using the close-to-close forward returns (ret_eod_pct / ret_eow_pct)
# computed by analytics/forward_returns.py. Classifies each pattern Swing/Day/
# Avoid and, for admins, generates a cached AI keep/stop/promote briefing.

from fastapi import HTTPException  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402

import json  # noqa: E402

from app.dependencies import is_admin_user  # noqa: E402
from app.models.strategy_analysis import StrategyAnalysisCache  # noqa: E402
from app.models.strategy_week_ai import StrategyWeekAICache  # noqa: E402
from analytics.strategy_analysis import (  # noqa: E402
    aggregate_patterns, attach_ai_verdicts, generate_ai_verdicts,
)

_SYNTHETIC_ALERT_TYPES = [
    "target_1_hit", "target_2_hit", "stop_loss_hit",
    "auto_stop_out", "vwap_loss", "vwap_reclaim",
]


async def _strategy_patterns_window(
    db: AsyncSession, start_iso: str, end_iso: str, min_sample: int,
) -> list[dict]:
    """Aggregate the classified pattern leaderboard over a session-date window
    (inclusive), global across all users.
    """
    excluded = list(OBSOLETE_ALERT_TYPES) + _SYNTHETIC_ALERT_TYPES
    label_map = {row[0]: row[1] for row in ALERT_TYPE_CATALOG}

    rows = (await db.execute(text("""
        SELECT alert_type, ret_eod_pct, ret_eow_pct
        FROM alerts
        WHERE session_date BETWEEN :start AND :end
          AND direction IN ('BUY', 'LONG')
          AND ret_eod_pct IS NOT NULL
          AND NOT (alert_type = ANY(:excluded))
    """), {"start": start_iso, "end": end_iso, "excluded": excluded})).all()

    bundle = [
        {"alert_type": at, "ret_eod_pct": eod, "ret_eow_pct": eow}
        for (at, eod, eow) in rows
    ]
    return aggregate_patterns(bundle, label_map=label_map, describe=describe_alert_type, min_sample=min_sample)


async def _strategy_patterns(db: AsyncSession, lookback: int) -> list[dict]:
    """Legacy lookback path (back-compat) — last `lookback` days to today."""
    start_iso = (date.today() - timedelta(days=lookback)).isoformat()
    return await _strategy_patterns_window(db, start_iso, date.today().isoformat(), min_sample=8)


async def _recent_graded_days(db: AsyncSession, limit: int = 14) -> list[str]:
    """Recent session dates that have at least one graded (EOD) alert — powers
    the Daily view's day picker + default day. Newest first.
    """
    rows = (await db.execute(text("""
        SELECT DISTINCT session_date FROM alerts
        WHERE ret_eod_pct IS NOT NULL
        ORDER BY session_date DESC
        LIMIT :limit
    """), {"limit": limit})).all()
    return [r[0] for r in rows]


async def _week_ai_verdicts(db: AsyncSession, week_start: str):
    """(verdicts_dict, narrative, generated_at_iso) from the weekly AI cache."""
    cache = (await db.execute(
        select(StrategyWeekAICache).where(StrategyWeekAICache.week_start == week_start)
    )).scalar_one_or_none()
    if cache is None:
        return {}, None, None
    verdicts = {}
    if cache.verdicts_json:
        try:
            verdicts = json.loads(cache.verdicts_json)
        except (ValueError, TypeError):
            verdicts = {}
    return verdicts, cache.narrative, (cache.generated_at.isoformat() if cache.generated_at else None)


@router.get("/strategy-analysis")
@limiter.limit("10/minute")
async def strategy_analysis(
    request: Request,
    period: Optional[str] = Query(None, description="day | week (recency views); omit for legacy lookback"),
    date_param: Optional[str] = Query(None, alias="date", description="anchor day/week as YYYY-MM-DD"),
    lookback: int = Query(90, ge=7, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pattern leaderboard by real forward returns, classified Swing/Day/Avoid
    with keep/stop/promote. Recency-first:
      ?period=day[&date=]  → a single trading day (rule engine only).
      ?period=week[&date=] → the Mon-Fri rollup + on-demand AI verdicts.
    Legacy ?lookback= still works when period is omitted.
    """
    # Daily — rule engine only (no AI). Few fires/day, so a low min_sample.
    if period == "day":
        days = await _recent_graded_days(db)
        day = date_param if (date_param and date_param in days) else (days[0] if days else date.today().isoformat())
        patterns = await _strategy_patterns_window(db, day, day, min_sample=3)
        patterns.sort(key=lambda p: (p["avg_ret_eod"] is None, -(p["avg_ret_eod"] or 0.0)))
        return {
            "period": "day", "date": day, "available_days": days,
            "patterns": patterns, "ai_summary": None, "agreement_pct": None, "generated_at": None,
        }

    # Weekly — Mon-Fri rollup + cached AI verdicts.
    if period == "week":
        monday, friday = _week_bounds(date_param)
        patterns = await _strategy_patterns_window(db, monday.isoformat(), friday.isoformat(), min_sample=5)
        verdicts, narrative, gen_at = await _week_ai_verdicts(db, monday.isoformat())
        agreement_pct = attach_ai_verdicts(patterns, verdicts)
        return {
            "period": "week", "week_start": monday.isoformat(), "week_end": friday.isoformat(),
            "patterns": patterns, "ai_summary": narrative,
            "agreement_pct": agreement_pct, "generated_at": gen_at,
        }

    # Legacy lookback path (back-compat).
    patterns = await _strategy_patterns(db, lookback)
    cache = (await db.execute(
        select(StrategyAnalysisCache).where(StrategyAnalysisCache.lookback_days == lookback)
    )).scalar_one_or_none()
    verdicts = {}
    if cache and cache.verdicts_json:
        try:
            verdicts = json.loads(cache.verdicts_json)
        except (ValueError, TypeError):
            verdicts = {}
    agreement_pct = attach_ai_verdicts(patterns, verdicts)
    return {
        "lookback_days": lookback,
        "patterns": patterns,
        "ai_summary": cache.narrative if cache else None,
        "agreement_pct": agreement_pct,
        "generated_at": cache.generated_at.isoformat() if cache else None,
    }


@router.post("/strategy-analysis/refresh")
@limiter.limit("4/minute")
async def refresh_strategy_analysis(
    request: Request,
    period: Optional[str] = Query(None, description="week (recency view); omit for legacy lookback"),
    date_param: Optional[str] = Query(None, alias="date"),
    lookback: int = Query(90, ge=7, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate + cache the AI's independent per-pattern verdicts (admin only —
    the LLM call is the only cost; the rule engine is free). On-demand only,
    never scheduled. AI lives on the WEEKLY rollup; the Daily view is rule-only.
    """
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Admin only")

    # Weekly path — write the per-week AI cache.
    if period == "week":
        monday, friday = _week_bounds(date_param)
        wk = monday.isoformat()
        patterns = await _strategy_patterns_window(db, wk, friday.isoformat(), min_sample=5)
        ai = await run_in_threadpool(generate_ai_verdicts, patterns)
        if not ai or not ai.get("verdicts"):
            raise HTTPException(status_code=502, detail="AI analysis unavailable")
        summary = ai.get("summary", "")
        verdicts_json = json.dumps(ai["verdicts"])
        existing = (await db.execute(
            select(StrategyWeekAICache).where(StrategyWeekAICache.week_start == wk)
        )).scalar_one_or_none()
        if existing:
            existing.narrative = summary
            existing.verdicts_json = verdicts_json
            existing.generated_at = datetime.utcnow()
        else:
            db.add(StrategyWeekAICache(week_start=wk, narrative=summary,
                                       verdicts_json=verdicts_json, generated_at=datetime.utcnow()))
        await db.commit()
        agreement_pct = attach_ai_verdicts(patterns, ai["verdicts"])
        return {
            "period": "week", "week_start": wk, "week_end": friday.isoformat(),
            "patterns": patterns, "ai_summary": summary,
            "agreement_pct": agreement_pct, "generated_at": datetime.utcnow().isoformat(),
        }

    # Legacy lookback path (back-compat).
    patterns = await _strategy_patterns(db, lookback)
    ai = await run_in_threadpool(generate_ai_verdicts, patterns)
    if not ai or not ai.get("verdicts"):
        raise HTTPException(status_code=502, detail="AI analysis unavailable")
    summary = ai.get("summary", "")
    verdicts_json = json.dumps(ai["verdicts"])
    existing = (await db.execute(
        select(StrategyAnalysisCache).where(StrategyAnalysisCache.lookback_days == lookback)
    )).scalar_one_or_none()
    if existing:
        existing.narrative = summary
        existing.verdicts_json = verdicts_json
        existing.generated_at = datetime.utcnow()
    else:
        db.add(StrategyAnalysisCache(lookback_days=lookback, narrative=summary,
                                     verdicts_json=verdicts_json, generated_at=datetime.utcnow()))
    await db.commit()
    agreement_pct = attach_ai_verdicts(patterns, ai["verdicts"])
    return {
        "lookback_days": lookback,
        "patterns": patterns,
        "ai_summary": summary,
        "agreement_pct": agreement_pct,
        "generated_at": datetime.utcnow().isoformat(),
    }
