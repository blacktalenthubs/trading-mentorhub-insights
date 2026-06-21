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
from app.services.scanner import run_scan

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


@router.get("/scan", response_model=List[SignalResultResponse])
@limiter.limit("20/minute")
async def scan(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run daily scanner on user's watchlist."""
    symbols = await _get_user_symbols(user, db)
    if not symbols:
        return []
    # Run CPU-bound scanner in thread pool
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, partial(run_scan, symbols))
    return results


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


def _compute_watchlist_ranks(symbols: List[str]) -> List[dict]:
    """Compute tradeability scores for symbols using yfinance daily data.

    Each symbol gets a score 0-100 from four factors (25 pts each):
    - Volume: today's volume vs 20-day average
    - Level proximity: distance to nearest MA / prior day H/L
    - RSI: extremes (near 30/70) are more tradeable
    - Trend clarity: EMA alignment (5>20>50 or inverse)
    """
    import yfinance as yf

    results: List[dict] = []

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="3mo", interval="1d")
            if df is None or df.empty or len(df) < 20:
                continue

            # Flatten MultiIndex columns (yfinance quirk)
            if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
                df.columns = df.columns.get_level_values(0)

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

            # NEXT-ENTRIES gate: a long candidate must be in an uptrend — price above the
            # 50 EMA. Below it = no trend → SKIP, no matter how oversold (this is what kills
            # the old behaviour of surfacing extended/overbought or falling-knife names).
            if ema50 is None or price < ema50:
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

            # ── Description (buy-zone framing) ──
            signal = _build_next_entry_text(nearest_label, min_dist_pct, rsi_val, stacked)

            results.append({
                "symbol": symbol,
                "score": total,
                "rank": 0,  # filled after sort
                "price": round(price, 2),
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
