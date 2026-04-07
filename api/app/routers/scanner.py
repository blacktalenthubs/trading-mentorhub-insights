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

            # ── Volume factor (0-25) ──
            vol_avg_20 = float(volume.iloc[-20:].mean()) if len(volume) >= 20 else float(volume.mean())
            vol_today = float(volume.iloc[-1])
            if vol_avg_20 > 0:
                vol_ratio = vol_today / vol_avg_20
                volume_score = min(25, int(vol_ratio * 12.5))  # 2x avg = 25
            else:
                volume_score = 0

            # ── MAs ──
            ema5 = float(close.ewm(span=5).mean().iloc[-1])
            ema20 = float(close.ewm(span=20).mean().iloc[-1])
            ema50 = float(close.ewm(span=50).mean().iloc[-1]) if len(close) >= 50 else None
            sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
            prior_high = float(df["High"].iloc[-2]) if len(df) >= 2 else None
            prior_low = float(df["Low"].iloc[-2]) if len(df) >= 2 else None

            # ── Level proximity (0-25) ──
            levels: List[Tuple[str, float]] = [
                ("20EMA", ema20),
            ]
            if ema50 is not None:
                levels.append(("50EMA", ema50))
            if sma200 is not None:
                levels.append(("200SMA", sma200))
            if prior_high is not None:
                levels.append(("Prior High", prior_high))
            if prior_low is not None:
                levels.append(("Prior Low", prior_low))

            nearest_label = ""
            nearest_price_val = 0.0
            min_dist_pct = 999.0
            for label, level_price in levels:
                dist_pct = abs(price - level_price) / price * 100
                if dist_pct < min_dist_pct:
                    min_dist_pct = dist_pct
                    nearest_label = label
                    nearest_price_val = level_price

            # Closer = higher score. 0% distance = 25, 5%+ = 0
            level_score = max(0, min(25, int(25 * (1 - min_dist_pct / 5))))
            nearest_level_str = f"{nearest_label} at ${nearest_price_val:.2f}"

            # ── RSI factor (0-25) ──
            delta = close.diff()
            gain = delta.clip(lower=0)
            loss = (-delta.clip(upper=0))
            avg_gain = gain.ewm(com=13, min_periods=14).mean()
            avg_loss = loss.ewm(com=13, min_periods=14).mean()
            rs = avg_gain / avg_loss
            rsi_series = 100 - (100 / (1 + rs))
            rsi_val = float(rsi_series.iloc[-1]) if len(rsi_series) >= 14 else 50.0

            # Extremes (near 30 or 70) are tradeable; middle (45-55) is not
            dist_from_center = abs(rsi_val - 50)
            # 0 at center (dist=0), 25 at extremes (dist=20+)
            rsi_score = min(25, int(dist_from_center * 1.25))

            # ── Trend clarity (0-25) ──
            if ema50 is not None:
                bullish_aligned = ema5 > ema20 > ema50
                bearish_aligned = ema5 < ema20 < ema50
                if bullish_aligned or bearish_aligned:
                    trend_score = 25
                elif (ema5 > ema20 and ema20 < ema50) or (ema5 < ema20 and ema20 > ema50):
                    trend_score = 8  # mixed
                else:
                    trend_score = 15  # partially aligned
            else:
                # Only have ema5 and ema20
                trend_score = 20 if ema5 > ema20 or ema5 < ema20 else 5

            total = volume_score + level_score + rsi_score + trend_score

            # ── Signal description ──
            signal = _build_signal_text(
                price, nearest_label, nearest_price_val, min_dist_pct,
                rsi_val, ema5, ema20, ema50,
            )

            results.append({
                "symbol": symbol,
                "score": total,
                "rank": 0,  # filled after sort
                "price": round(price, 2),
                "factors": {
                    "volume": volume_score,
                    "level_proximity": level_score,
                    "rsi": rsi_score,
                    "trend": trend_score,
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


def _build_signal_text(
    price: float,
    nearest_label: str,
    nearest_price: float,
    dist_pct: float,
    rsi: float,
    ema5: float,
    ema20: float,
    ema50: float | None,
) -> str:
    """Generate a 1-line signal description."""
    parts: List[str] = []

    # Level proximity
    if dist_pct < 1.0:
        direction = "support" if price > nearest_price else "resistance"
        parts.append(f"Approaching {nearest_label} {direction}")
    elif dist_pct < 2.0:
        parts.append(f"Near {nearest_label}")

    # RSI
    if rsi <= 32:
        parts.append("oversold")
    elif rsi >= 68:
        parts.append("overbought")

    # Trend
    if ema50 is not None:
        if ema5 > ema20 > ema50:
            parts.append("strong uptrend")
        elif ema5 < ema20 < ema50:
            parts.append("strong downtrend")

    if not parts:
        if rsi < 45:
            parts.append("leaning bearish")
        elif rsi > 55:
            parts.append("leaning bullish")
        else:
            parts.append("consolidating")

    return " — ".join(parts).capitalize()


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
