"""Scanner endpoints: scan watchlist, premarket, active entries."""

from __future__ import annotations

import asyncio
import time
from functools import partial
from typing import Dict, List, Tuple

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.alert import ActiveEntry
from app.models.user import User
from app.models.watchlist import WatchlistItem
from app.rate_limit import limiter
from app.schemas.scanner import (
    ActiveEntryResponse,
    SignalResultResponse,
    WatchlistRankItem,
)
from app.services.scanner import meets_entry, run_scan
from app.services.screener_service import get_latest_snapshot

router = APIRouter()

# ── Watchlist rank cache (user_id -> (timestamp, results)) ──────────
_rank_cache: Dict[int, Tuple[float, List[dict]]] = {}
_RANK_CACHE_TTL = 180  # 3 minutes


async def _get_user_symbols(user: User, db: AsyncSession) -> List[str]:
    result = await db.execute(
        select(WatchlistItem.symbol)
        .where(WatchlistItem.user_id == user.id)
        .order_by(WatchlistItem.id)
    )
    return [row[0] for row in result.all()]


# Screener snapshot kind -> the `source` tag exposed on scan results. Conviction
# is listed first so it wins when a symbol appears in both snapshots.
_IDEA_SOURCES: List[Tuple[str, str]] = [
    ("conviction", "conviction"),
    ("swing", "long_term"),
]
# Cap the extra scan load. Snapshots are pre-ranked best-first, so the cap keeps
# the strongest ideas; without it a busy market could add ~60 yfinance fetches
# to every 3-minute Today scan.
_MAX_IDEA_SYMBOLS = 20


async def _gather_idea_symbols(exclude: set[str]) -> Dict[str, str]:
    """Symbols from the latest conviction + swing screener snapshots, each mapped
    to its source tag.

    Read-only: reads the global snapshots, never mutates the watchlist. Excludes
    anything already on the user's watchlist, dedupes across kinds (conviction
    wins), and caps the total so the scan stays fast.
    """
    source_by_symbol: Dict[str, str] = {}
    for kind, source in _IDEA_SOURCES:
        if len(source_by_symbol) >= _MAX_IDEA_SYMBOLS:
            break
        snap = await get_latest_snapshot(kind)
        if snap is None or not snap.entries:
            continue
        for entry in snap.entries:
            if len(source_by_symbol) >= _MAX_IDEA_SYMBOLS:
                break
            sym = str(entry.get("symbol") or "").strip().upper()
            if not sym or sym in exclude or sym in source_by_symbol:
                continue
            source_by_symbol[sym] = source
    return source_by_symbol


@router.get("/scan", response_model=List[SignalResultResponse])
@limiter.limit("20/minute")
async def scan(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run the daily scanner on the user's watchlist PLUS the strongest conviction
    and long-term (swing) ideas.

    Watchlist names always appear (unchanged behaviour). Idea-sourced names are
    run through the exact same signal engine and only kept when they clear the same
    entry gate as watchlist names (`meets_entry`), so they show up in Today only
    when actually at entry. Each result is tagged with `source` for UI badging.
    Computed live on every call, so it auto-tracks the latest snapshots + prices.
    """
    symbols = await _get_user_symbols(user, db)
    watchlist_set = {s.strip().upper() for s in symbols}
    idea_source = await _gather_idea_symbols(exclude=watchlist_set)

    all_symbols = symbols + list(idea_source.keys())
    if not all_symbols:
        return []

    # Run CPU-bound scanner in thread pool
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, partial(run_scan, all_symbols))

    # Tag origin + drop idea-sourced names that aren't at entry today. Watchlist
    # names are always kept (unchanged behaviour).
    tagged: List[dict] = []
    for r in results:
        sym = str(r.get("symbol") or "").strip().upper()
        source = idea_source.get(sym, "watchlist")
        r["source"] = source
        if source != "watchlist" and not meets_entry(r):
            continue
        tagged.append(r)
    return tagged


@router.get("/active-entries", response_model=List[ActiveEntryResponse])
async def active_entries(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get active entries for the user's current session."""
    result = await db.execute(
        select(ActiveEntry)
        .where(ActiveEntry.user_id == user.id, ActiveEntry.status == "active")
        .order_by(ActiveEntry.created_at.desc())
    )
    return result.scalars().all()


# ── Watchlist ranking ────────────────────────────────────────────────


def _daily_bars(symbol: str):
    """~1y of daily bars [Open, High, Low, Close, Volume], naive ET index.
    Alpaca FIRST (reliable server-side — yfinance silently empties on Railway);
    yfinance fallback for local dev / an Alpaca gap. ~1y so the 50/100/200 EMA
    stack actually computes (3mo only ever yielded the 50)."""
    from analytics.intraday_data import _fetch_alpaca_bars, _fetch_alpaca_crypto_bars
    is_crypto = symbol.upper().endswith("-USD")
    hours = 24 * 400
    try:
        df = (_fetch_alpaca_crypto_bars(symbol, interval="1d", hours_back=hours)
              if is_crypto else
              _fetch_alpaca_bars(symbol, interval="1d", hours_back=hours))
        if df is not None and len(df) >= 60:
            return df
    except Exception:
        pass
    try:
        import yfinance as yf
        df = yf.Ticker(symbol).history(period="1y", interval="1d")
        if df is not None and not df.empty:
            if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
                df.columns = df.columns.get_level_values(0)
            return df
    except Exception:
        pass
    return None


def _compute_watchlist_ranks(symbols: List[str]) -> List[dict]:
    """Compute tradeability scores for symbols using daily bars (Alpaca→yfinance).

    Each symbol gets a score 0-100 from four factors (25 pts each):
    - Volume: today's volume vs 20-day average
    - Level proximity: distance to nearest MA / prior day H/L
    - RSI: extremes (near 30/70) are more tradeable
    - Trend clarity: EMA alignment (5>20>50 or inverse)
    """
    results: List[dict] = []

    for symbol in symbols:
        try:
            df = _daily_bars(symbol)
            if df is None or len(df) < 20:
                continue

            close = df["Close"]
            volume = df["Volume"]
            price = float(close.iloc[-1])

            # ── MAs: slow stack (50>100>200 = trend gate) + fast EMAs (pullback supports) ──
            ema8   = float(close.ewm(span=8).mean().iloc[-1])
            ema21  = float(close.ewm(span=21).mean().iloc[-1])
            ema50  = float(close.ewm(span=50).mean().iloc[-1])  if len(close) >= 50  else None
            ema100 = float(close.ewm(span=100).mean().iloc[-1]) if len(close) >= 100 else None
            ema200 = float(close.ewm(span=200).mean().iloc[-1]) if len(close) >= 200 else None
            prior_low = float(df["Low"].iloc[-2]) if len(df) >= 2 else None

            # ── RSI (Wilder) ──
            delta = close.diff()
            avg_gain = delta.clip(lower=0).ewm(com=13, min_periods=14).mean()
            avg_loss = (-delta.clip(upper=0)).ewm(com=13, min_periods=14).mean()
            rs = avg_gain / avg_loss
            rsi_series = 100 - (100 / (1 + rs))
            rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) >= 14 else 50.0

            if ema50 is None:
                continue
            # LOSING TREND (risk band): below the 50 EMA = the trend broke. Capture the RECENT
            # breakdowns (within ~12% below the 50) as bucket "losing" — the exit-watch side —
            # and skip the deep long-dead names. Everything past here is an uptrend long.
            if price < ema50:
                if price >= ema50 * 0.88:
                    db = (ema50 - price) / ema50 * 100.0
                    results.append({
                        "symbol": symbol, "score": 0, "rank": 0, "price": round(price, 2),
                        "bucket": "losing",
                        "factors": {"trend": 0, "pullback": 0, "rsi_room": 0},
                        "nearest_level": f"50 EMA at ${ema50:.2f}",
                        "rsi": round(rsi_val, 1),
                        "signal": _build_losing_text(db, rsi_val, ema200 is not None and price < ema200),
                    })
                continue

            # ── Pullback to support (0-40): nearest RISING MA / prior low BELOW price.
            # Sitting ON a support = the dip-buy zone; extended above it = not yet. ──
            supports = [(lbl, v) for lbl, v in
                        [("8 EMA", ema8), ("21 EMA", ema21), ("50 EMA", ema50), ("prior low", prior_low)]
                        if v is not None and v <= price]
            if supports:
                nearest_label, nearest_price_val = min(supports, key=lambda x: price - x[1])
                min_dist_pct = (price - nearest_price_val) / price * 100.0
                pullback_score = max(0, min(40, int(40 * (1 - min_dist_pct / 4.0))))  # 0%→40, 4%+→0
            else:
                nearest_label, nearest_price_val, min_dist_pct, pullback_score = "8 EMA", ema8, 999.0, 0

            # ── RSI room (0-20): cooled into the buy zone (40-55) = best; overbought = none. ──
            if 40 <= rsi_val <= 55:
                rsi_score = 20
            elif rsi_val < 40:
                rsi_score = 14          # deeper pullback — still a dip
            elif rsi_val <= 62:
                rsi_score = 10
            else:
                rsi_score = 0           # >62 extended — wait for the pullback

            # ── Trend quality (0-40): the slow stack — same engine as the alert gate. ──
            stacked = (ema100 is not None and ema200 is not None and ema50 > ema100 > ema200)
            trend_score = 40 if stacked else 20

            total = trend_score + pullback_score + rsi_score
            nearest_level_str = f"{nearest_label} at ${nearest_price_val:.2f}"

            # ── Bucket: coiling (pulled back to a support, RSI has room) = the BUY zone,
            # vs leader (running above the EMAs / RSI hot) = strong uptrend but extended —
            # watch for the pullback or trim, don't chase. Same gate, opposite end. ──
            is_coiling = min_dist_pct <= 2.5 and rsi_val <= 62
            bucket = "coiling" if is_coiling else "leader"
            signal = (_build_next_entry_text(nearest_label, min_dist_pct, rsi_val, stacked)
                      if is_coiling else
                      _build_leader_text(nearest_label, min_dist_pct, rsi_val, stacked))

            results.append({
                "symbol": symbol,
                "score": total,
                "rank": 0,  # filled after sort
                "price": round(price, 2),
                "bucket": bucket,
                "factors": {
                    "trend": trend_score,
                    "pullback": pullback_score,
                    "rsi_room": rsi_score,
                },
                "nearest_level": nearest_level_str,
                "rsi": round(rsi_val, 1),
                "signal": signal,
            })
        except Exception:
            # Skip symbols that fail (delisted, no data, etc.)
            continue

    # Sort by score descending and assign ranks
    results.sort(key=lambda x: x["score"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    return results


def _build_next_entry_text(nearest_label: str, dist_pct: float, rsi: float, stacked: bool) -> str:
    """1-line 'next entry' read — where a long is coiling, in buy-zone framing."""
    parts: List[str] = []
    if dist_pct < 0.8:
        parts.append(f"At the {nearest_label} — buy zone")
    elif dist_pct < 2.5:
        parts.append(f"Pulling back to the {nearest_label}")
    else:
        parts.append("Riding above support")

    if rsi <= 40:
        parts.append(f"RSI {rsi:.0f} reset")
    elif rsi <= 55:
        parts.append(f"RSI {rsi:.0f}, room")
    elif rsi > 62:
        parts.append(f"RSI {rsi:.0f} extended")

    parts.append("stacked uptrend" if stacked else "uptrend forming")
    return " · ".join(parts)


def _build_leader_text(nearest_label: str, dist_pct: float, rsi: float, stacked: bool) -> str:
    """1-line 'leader' read — strong uptrend but extended; watch for a pullback / trim."""
    parts: List[str] = []
    if rsi >= 70:
        parts.append(f"RSI {rsi:.0f} — extended, trim zone")
    elif rsi > 62:
        parts.append(f"RSI {rsi:.0f} — running hot")
    else:
        parts.append(f"{dist_pct:.0f}% above the {nearest_label} — extended")
    parts.append("strong uptrend · wait for the pullback" if stacked else "uptrend")
    return " · ".join(parts)


def _build_losing_text(dist_below: float, rsi: float, below_200: bool) -> str:
    """1-line 'losing trend' read — broke the 50 EMA; the exit / trim watch (risk band)."""
    parts: List[str] = [f"Lost the 50 EMA · {dist_below:.0f}% below"]
    if below_200:
        parts.append("under the 200 too")
    if rsi < 40:
        parts.append(f"RSI {rsi:.0f} weak")
    return " · ".join(parts)


@router.get("/watchlist-rank", response_model=List[WatchlistRankItem])
@limiter.limit("20/minute")
async def watchlist_rank(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rank watchlist symbols by tradeability score (cached 3 min)."""
    symbols = await _get_user_symbols(user, db)
    if not symbols:
        return []

    # Check cache
    now = time.time()
    cached = _rank_cache.get(user.id)
    if cached and (now - cached[0]) < _RANK_CACHE_TTL:
        # Return cached if symbols haven't changed
        cached_symbols = {r["symbol"] for r in cached[1]}
        if cached_symbols == set(symbols):
            return cached[1]

    # Compute in thread pool (yfinance is blocking)
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(
        None, partial(_compute_watchlist_ranks, symbols)
    )

    # Update cache
    _rank_cache[user.id] = (now, results)
    return results
