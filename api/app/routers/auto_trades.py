"""Public AI Auto-Pilot API — Spec 35 Phase 3.

All endpoints are public (no auth). This is the marketing asset —
anyone can audit the AI's live paper trading record.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.database import get_db
from app.models.auto_trade import AIAutoTrade

router = APIRouter()

# Symbols excluded from the public report (kept private / noisy)
EXCLUDED_SYMBOLS = ("BTC-USD",)


# ── Response schemas ─────────────────────────────────────────────────


class AutoTradeSummary(BaseModel):
    id: int
    symbol: str
    direction: str
    setup_type: Optional[str] = None
    conviction: Optional[str] = None
    entry_price: float
    stop_price: Optional[float] = None
    target_1_price: Optional[float] = None
    target_2_price: Optional[float] = None
    shares: float
    status: str
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl_dollars: Optional[float] = None
    pnl_percent: Optional[float] = None
    r_multiple: Optional[float] = None
    opened_at: datetime
    closed_at: Optional[datetime] = None
    session_date: str
    market: Optional[str] = None
    alert_id: Optional[int] = None


class Stats(BaseModel):
    total_trades: int
    open_trades: int
    closed_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl_dollars: float
    total_pnl_percent: float   # sum of per-trade P&L % — comparable since notional is fixed
    avg_win_pct: float
    avg_loss_pct: float
    best_trade_pct: Optional[float] = None
    worst_trade_pct: Optional[float] = None
    total_notional_invested: float


class PatternRow(BaseModel):
    setup_type: Optional[str]
    trades: int
    wins: int
    win_rate: float
    avg_pnl_pct: float


class SymbolRow(BaseModel):
    symbol: str
    trades: int
    wins: int
    win_rate: float
    avg_pnl_pct: float


class EquityPoint(BaseModel):
    date: str
    cumulative_pnl_pct: float
    cumulative_pnl_dollars: float
    trades_closed: int


# ── Helpers ──────────────────────────────────────────────────────────


def _is_win(t: AIAutoTrade) -> bool:
    return (t.pnl_dollars or 0) > 0


def _to_summary(t: AIAutoTrade) -> AutoTradeSummary:
    return AutoTradeSummary(
        id=t.id,
        symbol=t.symbol,
        direction=t.direction,
        setup_type=t.setup_type,
        conviction=t.conviction,
        entry_price=t.entry_price,
        stop_price=t.stop_price,
        target_1_price=t.target_1_price,
        target_2_price=t.target_2_price,
        shares=t.shares,
        status=t.status,
        exit_price=t.exit_price,
        exit_reason=t.exit_reason,
        pnl_dollars=t.pnl_dollars,
        pnl_percent=t.pnl_percent,
        r_multiple=t.r_multiple,
        opened_at=t.opened_at,
        closed_at=t.closed_at,
        session_date=t.session_date,
        market=t.market,
        alert_id=t.alert_id,
    )


# ── Endpoints (all public) ───────────────────────────────────────────


@router.get("/stats", response_model=Stats)
async def stats(
    days: int = Query(default=30, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate stats for the last N days (default 30)."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = await db.execute(
        select(AIAutoTrade)
        .where(AIAutoTrade.session_date >= cutoff)
        .where(AIAutoTrade.symbol.notin_(EXCLUDED_SYMBOLS))
    )
    trades = list(result.scalars().all())

    closed = [t for t in trades if t.status != "open"]
    opens = [t for t in trades if t.status == "open"]
    wins = [t for t in closed if _is_win(t)]
    losses = [t for t in closed if not _is_win(t)]

    win_pcts = [t.pnl_percent or 0 for t in wins]
    loss_pcts = [t.pnl_percent or 0 for t in losses]
    closed_pcts = [t.pnl_percent or 0 for t in closed]

    return Stats(
        total_trades=len(trades),
        open_trades=len(opens),
        closed_trades=len(closed),
        wins=len(wins),
        losses=len(losses),
        win_rate=round((len(wins) / len(closed) * 100) if closed else 0.0, 2),
        total_pnl_dollars=round(sum(t.pnl_dollars or 0 for t in closed), 2),
        total_pnl_percent=round(sum(closed_pcts), 4),
        avg_win_pct=round(sum(win_pcts) / len(win_pcts), 4) if win_pcts else 0.0,
        avg_loss_pct=round(sum(loss_pcts) / len(loss_pcts), 4) if loss_pcts else 0.0,
        best_trade_pct=max(closed_pcts) if closed_pcts else None,
        worst_trade_pct=min(closed_pcts) if closed_pcts else None,
        total_notional_invested=round(sum(t.notional_at_entry or 0 for t in trades), 2),
    )


@router.get("/recent", response_model=list[AutoTradeSummary])
async def recent_closed(
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Most recent closed trades — used for the public trade table."""
    result = await db.execute(
        select(AIAutoTrade)
        .where(AIAutoTrade.status != "open")
        .where(AIAutoTrade.symbol.notin_(EXCLUDED_SYMBOLS))
        .order_by(AIAutoTrade.closed_at.desc())
        .limit(limit)
    )
    return [_to_summary(t) for t in result.scalars().all()]


@router.get("/open", response_model=list[AutoTradeSummary])
async def open_positions(db: AsyncSession = Depends(get_db)):
    """Currently open AI Auto-Pilot positions — live transparency."""
    result = await db.execute(
        select(AIAutoTrade)
        .where(AIAutoTrade.status == "open")
        .where(AIAutoTrade.symbol.notin_(EXCLUDED_SYMBOLS))
        .order_by(AIAutoTrade.opened_at.desc())
    )
    return [_to_summary(t) for t in result.scalars().all()]


@router.get("/equity-curve", response_model=list[EquityPoint])
async def equity_curve(
    days: int = Query(default=90, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Daily cumulative P&L (percent + dollars) for chart rendering."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = await db.execute(
        select(AIAutoTrade)
        .where(AIAutoTrade.session_date >= cutoff)
        .where(AIAutoTrade.status != "open")
        .where(AIAutoTrade.symbol.notin_(EXCLUDED_SYMBOLS))
        .order_by(AIAutoTrade.closed_at.asc())  # equity curve
    )
    closed = list(result.scalars().all())

    # Group by session_date (day of close)
    by_day: dict[str, list] = {}
    for t in closed:
        day = (t.closed_at.date().isoformat() if t.closed_at else t.session_date)
        by_day.setdefault(day, []).append(t)

    points: list[EquityPoint] = []
    cum_pct = 0.0
    cum_dollars = 0.0
    for day in sorted(by_day.keys()):
        day_trades = by_day[day]
        cum_pct += sum(t.pnl_percent or 0 for t in day_trades)
        cum_dollars += sum(t.pnl_dollars or 0 for t in day_trades)
        points.append(EquityPoint(
            date=day,
            cumulative_pnl_pct=round(cum_pct, 4),
            cumulative_pnl_dollars=round(cum_dollars, 2),
            trades_closed=len(day_trades),
        ))
    return points


@router.get("/by-pattern", response_model=list[PatternRow])
async def by_pattern(
    days: int = Query(default=90, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Win rate + avg P&L grouped by AI setup type."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = await db.execute(
        select(AIAutoTrade)
        .where(AIAutoTrade.session_date >= cutoff)
        .where(AIAutoTrade.status != "open")
        .where(AIAutoTrade.symbol.notin_(EXCLUDED_SYMBOLS))
    )
    closed = list(result.scalars().all())

    buckets: dict[Optional[str], list] = {}
    for t in closed:
        buckets.setdefault(t.setup_type, []).append(t)

    rows: list[PatternRow] = []
    for setup, trades in buckets.items():
        wins = sum(1 for t in trades if _is_win(t))
        pcts = [t.pnl_percent or 0 for t in trades]
        rows.append(PatternRow(
            setup_type=setup,
            trades=len(trades),
            wins=wins,
            win_rate=round((wins / len(trades) * 100) if trades else 0.0, 2),
            avg_pnl_pct=round(sum(pcts) / len(pcts), 4) if pcts else 0.0,
        ))
    rows.sort(key=lambda r: r.trades, reverse=True)
    return rows


@router.get("/by-symbol", response_model=list[SymbolRow])
async def by_symbol(
    days: int = Query(default=90, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Win rate + avg P&L grouped by symbol."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    result = await db.execute(
        select(AIAutoTrade)
        .where(AIAutoTrade.session_date >= cutoff)
        .where(AIAutoTrade.status != "open")
        .where(AIAutoTrade.symbol.notin_(EXCLUDED_SYMBOLS))
    )
    closed = list(result.scalars().all())

    buckets: dict[str, list] = {}
    for t in closed:
        buckets.setdefault(t.symbol, []).append(t)

    rows: list[SymbolRow] = []
    for sym, trades in buckets.items():
        wins = sum(1 for t in trades if _is_win(t))
        pcts = [t.pnl_percent or 0 for t in trades]
        rows.append(SymbolRow(
            symbol=sym,
            trades=len(trades),
            wins=wins,
            win_rate=round((wins / len(trades) * 100) if trades else 0.0, 2),
            avg_pnl_pct=round(sum(pcts) / len(pcts), 4) if pcts else 0.0,
        ))
    rows.sort(key=lambda r: r.trades, reverse=True)
    return rows


class PublicSignalRow(BaseModel):
    """Public view of an AI signal with its auto-trade outcome (if closed)."""
    id: int
    symbol: str
    alert_type: str
    direction: str
    entry: Optional[float] = None
    stop: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    confidence: Optional[str] = None
    fired_at: Optional[str] = None
    # Outcome from the matched auto-trade (if any)
    auto_trade_status: Optional[str] = None  # "open" | "closed_t1" | "closed_t2" | "closed_stop" | "closed_eod"
    exit_price: Optional[float] = None
    pnl_percent: Optional[float] = None
    r_multiple: Optional[float] = None


@router.get("/all-ai-alerts", response_model=list[PublicSignalRow])
async def all_ai_alerts(
    days: int = Query(default=7, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Public — every distinct AI LONG/SHORT signal in the last N days,
    deduped across per-user copies, joined with auto-trade outcomes.

    No user data leaked. This is the marketing audit asset — anyone
    can verify every signal AI fired and how it played out.
    """
    from sqlalchemy import text
    result = await db.execute(text(f"""
        WITH dedup_alerts AS (
            SELECT MIN(id) AS id, symbol, alert_type, direction,
                   entry, stop, target_1, target_2, confidence,
                   DATE_TRUNC('minute', created_at) AS fired_at
            FROM alerts
            WHERE alert_type IN ('ai_day_long', 'ai_day_short')
              AND symbol NOT IN ('BTC-USD')
              AND created_at >= NOW() - INTERVAL '{int(days)} days'
            GROUP BY symbol, alert_type, direction, entry, stop, target_1, target_2,
                     confidence, DATE_TRUNC('minute', created_at)
        )
        SELECT a.id, a.symbol, a.alert_type, a.direction, a.entry, a.stop,
               a.target_1, a.target_2, a.confidence, a.fired_at,
               t.status, t.exit_price, t.pnl_percent, t.r_multiple
        FROM dedup_alerts a
        LEFT JOIN ai_auto_trades t ON t.alert_id = a.id
        ORDER BY a.fired_at DESC
        LIMIT 500
    """))
    rows = result.fetchall()
    return [PublicSignalRow(
        id=r[0],
        symbol=r[1],
        alert_type=r[2],
        direction=r[3],
        entry=r[4],
        stop=r[5],
        target_1=r[6],
        target_2=r[7],
        confidence=r[8],
        fired_at=r[9].isoformat() if r[9] else None,
        auto_trade_status=r[10],
        exit_price=r[11],
        pnl_percent=r[12],
        r_multiple=r[13],
    ) for r in rows]


@router.get("/{trade_id}", response_model=AutoTradeSummary)
async def get_trade(
    trade_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Single trade detail — used by shareable permalinks."""
    result = await db.execute(
        select(AIAutoTrade).where(AIAutoTrade.id == trade_id)
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Trade not found")
    return _to_summary(t)


# ── Social cards (shareable P&L images for TikTok / IG / YouTube) ───────


@router.get("/card/daily", response_class=HTMLResponse)
async def daily_card(
    day: Optional[str] = Query(default=None, description="YYYY-MM-DD (defaults to today)"),
    w: int = Query(default=1080, description="Width px"),
    h: int = Query(default=1920, description="Height px (9:16 = 1920)"),
    db: AsyncSession = Depends(get_db),
):
    """Self-contained HTML card with today's AI trading stats — screenshot-ready
    for TikTok (1080x1920), Instagram Reels, or YouTube Shorts.

    Public. Safe to share. BTC excluded (matches public-report policy).
    """
    target_day = day or date.today().isoformat()

    # Today's closed trades
    closed_res = await db.execute(
        select(AIAutoTrade)
        .where(AIAutoTrade.session_date == target_day)
        .where(AIAutoTrade.status != "open")
        .where(AIAutoTrade.symbol.notin_(EXCLUDED_SYMBOLS))
    )
    closed = list(closed_res.scalars().all())

    open_res = await db.execute(
        select(AIAutoTrade)
        .where(AIAutoTrade.session_date == target_day)
        .where(AIAutoTrade.status == "open")
        .where(AIAutoTrade.symbol.notin_(EXCLUDED_SYMBOLS))
    )
    opens = list(open_res.scalars().all())

    wins = [t for t in closed if (t.pnl_dollars or 0) > 0]
    losses = [t for t in closed if (t.pnl_dollars or 0) <= 0 and t.status != "open"]
    total_pnl = round(sum((t.pnl_dollars or 0) for t in closed), 2)
    total_pnl_pct = round(sum((t.pnl_percent or 0) for t in closed), 2)
    win_rate = round((len(wins) / len(closed) * 100), 1) if closed else 0.0

    best = max(closed, key=lambda t: t.pnl_dollars or 0, default=None)
    worst = min(closed, key=lambda t: t.pnl_dollars or 0, default=None)

    # Formatted strings
    pnl_color = "#22c55e" if total_pnl >= 0 else "#ef4444"
    pnl_sign = "+" if total_pnl >= 0 else ""
    pnl_dollars_s = f"{pnl_sign}${abs(total_pnl):,.2f}" if total_pnl < 0 else f"{pnl_sign}${total_pnl:,.2f}"
    pnl_pct_s = f"{pnl_sign}{total_pnl_pct:.2f}%"

    best_row = ""
    if best and (best.pnl_dollars or 0) > 0:
        best_row = (
            f'<div class="trade-row best">'
            f'<div class="sym">{best.symbol}</div>'
            f'<div class="dir">{best.direction}</div>'
            f'<div class="pnl">+${best.pnl_dollars:,.2f}</div>'
            f'<div class="pct">+{best.pnl_percent or 0:.2f}%</div>'
            f'</div>'
        )

    # Day label
    try:
        day_label = datetime.strptime(target_day, "%Y-%m-%d").strftime("%b %d, %Y").upper()
    except Exception:
        day_label = target_day

    html = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width={w}"/>
<title>AI Trading — {day_label}</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", system-ui, sans-serif; }}
  html, body {{ width: {w}px; height: {h}px; background: #0a0a0f; color: #fff; overflow: hidden; }}
  .card {{
    width: {w}px; height: {h}px;
    padding: 90px 80px;
    background: radial-gradient(ellipse at top, #1a1a2e 0%, #0a0a0f 55%);
    display: flex; flex-direction: column; justify-content: space-between;
  }}
  .brand {{ display: flex; align-items: center; gap: 20px; }}
  .brand-dot {{ width: 28px; height: 28px; border-radius: 50%; background: linear-gradient(135deg, #22d3ee, #8b5cf6); }}
  .brand-name {{ font-size: 42px; font-weight: 700; letter-spacing: -1px; }}
  .brand-url {{ font-size: 26px; color: #9ca3af; margin-top: 4px; }}

  .date-tag {{ font-size: 32px; letter-spacing: 4px; color: #9ca3af; margin-top: 30px; }}
  .headline {{ font-size: 72px; font-weight: 800; line-height: 1.05; letter-spacing: -2px; margin-top: 40px; }}

  .pnl-block {{ margin-top: 50px; }}
  .pnl-label {{ font-size: 34px; color: #9ca3af; letter-spacing: 2px; }}
  .pnl-amount {{ font-size: 180px; font-weight: 900; letter-spacing: -6px; line-height: 1; margin-top: 10px; color: {pnl_color}; }}
  .pnl-pct {{ font-size: 54px; font-weight: 700; color: {pnl_color}; margin-top: 8px; }}

  .stats {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 24px; margin-top: 70px; }}
  .stat {{ background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 24px; padding: 30px; text-align: center; }}
  .stat-value {{ font-size: 62px; font-weight: 800; letter-spacing: -2px; }}
  .stat-label {{ font-size: 24px; color: #9ca3af; margin-top: 6px; letter-spacing: 1px; }}

  .best-block {{ margin-top: 50px; }}
  .best-title {{ font-size: 28px; color: #9ca3af; letter-spacing: 3px; margin-bottom: 20px; }}
  .trade-row {{ display: flex; align-items: center; padding: 24px 30px; background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.25); border-radius: 20px; gap: 20px; }}
  .trade-row .sym {{ font-size: 42px; font-weight: 800; flex: 1; }}
  .trade-row .dir {{ font-size: 26px; background: rgba(34,197,94,0.2); color: #22c55e; padding: 8px 18px; border-radius: 100px; font-weight: 700; }}
  .trade-row .pnl {{ font-size: 44px; font-weight: 800; color: #22c55e; }}
  .trade-row .pct {{ font-size: 28px; color: #22c55e; opacity: 0.8; }}

  .footer {{ margin-top: auto; display: flex; justify-content: space-between; align-items: center; padding-top: 40px; border-top: 1px solid rgba(255,255,255,0.08); }}
  .cta {{ font-size: 30px; color: #9ca3af; }}
  .cta strong {{ color: #fff; }}
  .handle {{ font-size: 26px; color: #22d3ee; font-weight: 600; }}
</style>
</head>
<body>
  <div class="card">
    <div>
      <div class="brand">
        <div class="brand-dot"></div>
        <div>
          <div class="brand-name">TradeCoPilot</div>
          <div class="brand-url">tradingwithai.ai</div>
        </div>
      </div>
      <div class="date-tag">{day_label}</div>
      <div class="headline">AI Paper Trading<br/>Results</div>

      <div class="pnl-block">
        <div class="pnl-label">TODAY'S P&amp;L</div>
        <div class="pnl-amount">{pnl_dollars_s}</div>
        <div class="pnl-pct">{pnl_pct_s}</div>
      </div>

      <div class="stats">
        <div class="stat">
          <div class="stat-value">{len(closed)}</div>
          <div class="stat-label">CLOSED</div>
        </div>
        <div class="stat">
          <div class="stat-value">{win_rate:.0f}%</div>
          <div class="stat-label">WIN RATE</div>
        </div>
        <div class="stat">
          <div class="stat-value">{len(opens)}</div>
          <div class="stat-label">OPEN</div>
        </div>
      </div>

      {"<div class='best-block'><div class='best-title'>BEST TRADE</div>" + best_row + "</div>" if best_row else ""}
    </div>

    <div class="footer">
      <div class="cta">Live audit at <strong>tradingwithai.ai/track-record</strong></div>
      <div class="handle">@tradewithai</div>
    </div>
  </div>
</body></html>"""
    return HTMLResponse(content=html)
