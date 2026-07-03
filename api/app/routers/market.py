"""Market data endpoints with Redis/memory caching."""

from __future__ import annotations

import asyncio
import logging
import sys
from functools import partial
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Request

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_get, cache_set
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.watchlist import WatchlistItem
from app.rate_limit import limiter
from app.schemas.market import (
    CatalystItem,
    GroupPremarketSummary,
    GroupSymbolQuote,
    MarketStatusResponse,
    OHLCBar,
    OptionsFlowItem,
    PriorDayResponse,
    SectorRotationItem,
)

# Add project root so analytics is importable
_root = str(Path(__file__).resolve().parents[3])
if _root not in sys.path:
    sys.path.insert(0, _root)

from analytics.market_hours import is_market_hours, is_premarket, get_session_phase  # noqa: E402
from analytics.intraday_data import fetch_intraday, fetch_prior_day  # noqa: E402

router = APIRouter()

# Cache TTLs (seconds)
_INTRADAY_TTL = 180  # 3 min — matches monitor interval
_PRIOR_DAY_TTL = 3600  # 1 hour — stale after close


@router.get("/status", response_model=MarketStatusResponse)
async def market_status(user: User = Depends(get_current_user)):
    return MarketStatusResponse(
        is_open=is_market_hours(),
        is_premarket=is_premarket(),
        session_phase=get_session_phase(),
    )


@router.get("/prices")
async def live_prices(user: User = Depends(get_current_user)):
    """Get latest prices for user's watchlist symbols. Polled by frontend every 15s."""
    loop = asyncio.get_event_loop()

    from app.database import get_db as get_db_dep
    from sqlalchemy import select
    from app.models.watchlist import WatchlistItem

    # Get user's symbols
    async for db in get_db_dep():
        result = await db.execute(
            select(WatchlistItem.symbol).where(WatchlistItem.user_id == user.id)
        )
        symbols = [r[0] for r in result.all()]
        break

    if not symbols:
        return {"prices": {}}

    def _fetch_prices(syms):
        import yfinance as yf
        prices = {}
        for sym in syms:
            try:
                t = yf.Ticker(sym)
                fi = t.fast_info
                price = round(float(fi.last_price), 2)
                prev = float(fi.previous_close) if hasattr(fi, 'previous_close') and fi.previous_close else price
                change = round(((price - prev) / prev) * 100, 2) if prev else 0
                prices[sym] = {"price": price, "change_pct": change}
            except Exception:
                pass
        return prices

    prices = await loop.run_in_executor(None, partial(_fetch_prices, symbols))
    return {"prices": prices}


def _fetch_and_serialize_intraday(symbol: str) -> List[dict]:
    df = fetch_intraday(symbol)
    if df.empty:
        return []
    # Drop bars with any missing OHLC. A NaN survives round() and serializes to
    # JSON null, which makes lightweight-charts throw "Value is null" and takes
    # down the whole chart on a single bad bar.
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if df.empty:
        return []
    return [
        {
            "timestamp": str(ts),
            "open": round(row["Open"], 2),
            "high": round(row["High"], 2),
            "low": round(row["Low"], 2),
            "close": round(row["Close"], 2),
            "volume": round(row["Volume"], 0),
        }
        for ts, row in df.iterrows()
    ]


@router.get("/intraday/{symbol}", response_model=List[OHLCBar])
@limiter.limit("20/minute")
async def intraday(
    request: Request,
    symbol: str,
    user: User = Depends(get_current_user),
):
    """Get today's 5-min intraday bars for a symbol (cached)."""
    key = f"intraday:{symbol.upper()}"
    cached = cache_get(key)
    if cached is not None:
        return cached

    loop = asyncio.get_event_loop()
    bars = await loop.run_in_executor(
        None, partial(_fetch_and_serialize_intraday, symbol.upper())
    )
    if bars:
        cache_set(key, bars, _INTRADAY_TTL)
    return bars


def _spark_closes(symbol: str, n: int = 16) -> List[float]:
    """~n evenly-spaced intraday closes for a sparkline. Reuses the per-symbol
    intraday cache (a charted symbol is instant); fetches + caches on miss."""
    key = f"intraday:{symbol.upper()}"
    bars = cache_get(key)
    if bars is None:
        bars = _fetch_and_serialize_intraday(symbol.upper())
        if bars:
            cache_set(key, bars, _INTRADAY_TTL)
    closes = [b["close"] for b in (bars or []) if b.get("close") is not None]
    if len(closes) <= n:
        return closes
    step = len(closes) / n
    return [closes[min(len(closes) - 1, int(i * step))] for i in range(n)]


@router.get("/sparklines")
async def sparklines(user: User = Depends(get_current_user)):
    """~16 recent intraday closes per watchlist symbol → the watchlist panel's
    sparklines. Reuses the per-symbol intraday cache; the whole response is cached
    ~2 min per user, and the (cold) fetch is bounded-parallel so it can't hang."""
    ckey = f"spark:{user.id}"
    cached = cache_get(ckey)
    if cached is not None:
        return cached

    from app.database import get_db as get_db_dep
    from sqlalchemy import select
    from app.models.watchlist import WatchlistItem

    symbols: List[str] = []
    async for db in get_db_dep():
        rows = await db.execute(select(WatchlistItem.symbol).where(WatchlistItem.user_id == user.id))
        symbols = [r[0] for r in rows.all()][:60]
        break
    if not symbols:
        return {"sparklines": {}}

    def _all(syms: List[str]) -> dict:
        from concurrent.futures import ThreadPoolExecutor
        out: dict = {}
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(_spark_closes, s): s for s in syms}
            for fut, s in futs.items():
                try:
                    cl = fut.result(timeout=8)
                    if cl:
                        out[s.upper()] = cl
                except Exception:
                    pass
        return out

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, partial(_all, symbols))
    payload = {"sparklines": result}
    cache_set(ckey, payload, 120)
    return payload


@router.get("/prior-day/{symbol}", response_model=Optional[PriorDayResponse])
@limiter.limit("20/minute")
async def prior_day(
    request: Request,
    symbol: str,
    user: User = Depends(get_current_user),
):
    """Get prior completed day's data for a symbol (cached)."""
    key = f"prior_day:{symbol.upper()}"
    cached = cache_get(key)
    if cached is not None:
        return PriorDayResponse(**cached) if cached else None

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, partial(fetch_prior_day, symbol.upper()))
    if not data:
        cache_set(key, {}, _PRIOR_DAY_TTL)
        return None
    cache_set(key, data, _PRIOR_DAY_TTL)
    return PriorDayResponse(**data)


# ── Options Flow ─────────────────────────────────────────────────────

_OPTIONS_FLOW_TTL = 180  # 3 min — same as monitor interval


def _fetch_options_flow(symbols: List[str]) -> List[dict]:
    """Scan nearest 2 expiries for unusual options activity."""
    import yfinance as yf

    results: List[dict] = []

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            expirations = ticker.options
            if not expirations:
                continue

            # Only scan nearest 2 expiration dates
            for expiry in expirations[:2]:
                try:
                    chain = ticker.option_chain(expiry)
                except Exception:
                    continue

                for opt_type, df in [("CALL", chain.calls), ("PUT", chain.puts)]:
                    if df.empty:
                        continue
                    for _, row in df.iterrows():
                        vol = int(row.get("volume", 0) or 0)
                        oi = int(row.get("openInterest", 0) or 0)
                        if oi <= 0 or vol <= 500:
                            continue
                        ratio = round(vol / oi, 2)
                        if ratio < 3.0:
                            continue

                        # Unusual activity detected
                        iv = row.get("impliedVolatility")
                        results.append(
                            {
                                "symbol": symbol,
                                "type": opt_type,
                                "strike": round(float(row["strike"]), 2),
                                "expiry": expiry,
                                "volume": vol,
                                "open_interest": oi,
                                "volume_oi_ratio": ratio,
                                "last_price": (
                                    round(float(row["lastPrice"]), 2)
                                    if row.get("lastPrice") is not None
                                    else None
                                ),
                                "implied_vol": (
                                    round(float(iv), 4) if iv is not None else None
                                ),
                                "sentiment": "BULLISH" if opt_type == "CALL" else "BEARISH",
                            }
                        )
        except Exception:
            # yfinance failure for this symbol — skip it
            continue

    # Sort by volume/OI ratio descending
    results.sort(key=lambda x: x["volume_oi_ratio"], reverse=True)
    return results


@router.get("/options-flow", response_model=List[OptionsFlowItem])
@limiter.limit("10/minute")
async def options_flow(
    request: Request,
    symbols: str = "SPY,QQQ,AAPL,NVDA,TSLA",
    user: User = Depends(get_current_user),
):
    """Scan options chains for unusual volume activity (cached 3 min)."""
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        return []

    key = f"options_flow:{','.join(sorted(sym_list))}"
    cached = cache_get(key)
    if cached is not None:
        return cached

    loop = asyncio.get_event_loop()
    items = await loop.run_in_executor(None, partial(_fetch_options_flow, sym_list))
    cache_set(key, items, _OPTIONS_FLOW_TTL)
    return items


# ── Sector Rotation ────────────────────────────────────────────────

_SECTOR_ROTATION_TTL = 300  # 5 min

_SECTOR_ETFS = {
    "XLK": "Tech",
    "XLE": "Energy",
    "XLF": "Financials",
    "XLV": "Healthcare",
    "XLI": "Industrials",
    "XLY": "Consumer Disc",
    "XLP": "Consumer Staples",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLC": "Communication",
}


def _fetch_sector_rotation() -> List[dict]:
    """Compute 1d/5d/20d % changes for sector ETFs."""
    import yfinance as yf

    results: List[dict] = []
    symbols = list(_SECTOR_ETFS.keys())

    for symbol in symbols:
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="1mo")
            if hist.empty or len(hist) < 2:
                continue

            current = float(hist["Close"].iloc[-1])
            prev_1d = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
            prev_5d = float(hist["Close"].iloc[-6]) if len(hist) >= 6 else float(hist["Close"].iloc[0])
            prev_20d = float(hist["Close"].iloc[0]) if len(hist) >= 20 else float(hist["Close"].iloc[0])

            change_1d = round(((current - prev_1d) / prev_1d) * 100, 2)
            change_5d = round(((current - prev_5d) / prev_5d) * 100, 2)
            change_20d = round(((current - prev_20d) / prev_20d) * 100, 2)

            if change_1d > 0.5:
                flow = "INFLOW"
            elif change_1d < -0.5:
                flow = "OUTFLOW"
            else:
                flow = "NEUTRAL"

            results.append({
                "symbol": symbol,
                "name": _SECTOR_ETFS[symbol],
                "price": round(current, 2),
                "change_1d": change_1d,
                "change_5d": change_5d,
                "change_20d": change_20d,
                "flow": flow,
            })
        except Exception:
            continue

    results.sort(key=lambda x: x["change_1d"], reverse=True)
    return results


@router.get("/sector-rotation", response_model=List[SectorRotationItem])
async def sector_rotation():
    """Sector ETF rotation heatmap — 1d/5d/20d changes (cached 5 min, public)."""
    key = "sector_rotation"
    cached = cache_get(key)
    if cached is not None:
        return cached

    loop = asyncio.get_event_loop()
    items = await loop.run_in_executor(None, _fetch_sector_rotation)
    if items:
        cache_set(key, items, _SECTOR_ROTATION_TTL)
    return items


# ── Catalysts Calendar ────────────────────────────────────────────

_CATALYSTS_TTL = 3600  # 1 hour — catalysts don't change frequently


def _fetch_catalysts(symbols: List[str], max_days: int = 7) -> List[dict]:
    """Get upcoming earnings/dividend catalysts for symbols via yfinance."""
    import yfinance as yf
    from datetime import date, datetime

    today = date.today()
    results: List[dict] = []

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)

            # --- Earnings date ---
            try:
                cal = ticker.calendar
                # ticker.calendar can be a DataFrame, dict, or None
                earnings_dates: list = []
                timing = "Unknown"

                if cal is not None:
                    import pandas as pd

                    if isinstance(cal, pd.DataFrame):
                        # DataFrame with row index like "Earnings Date"
                        if "Earnings Date" in cal.index:
                            raw = cal.loc["Earnings Date"]
                            # Could be a Series (multiple columns) or scalar
                            if hasattr(raw, "tolist"):
                                earnings_dates = [v for v in raw.tolist() if v is not None]
                            elif raw is not None:
                                earnings_dates = [raw]
                    elif isinstance(cal, dict):
                        # Dict with "Earnings Date" key
                        raw = cal.get("Earnings Date") or cal.get("earningsDate")
                        if raw is not None:
                            if isinstance(raw, list):
                                earnings_dates = [v for v in raw if v is not None]
                            else:
                                earnings_dates = [raw]
                        # Timing info
                        raw_timing = cal.get("Earnings Average") or cal.get("earningsTimestamp")
                        if raw_timing is not None:
                            timing = "Unknown"

                    # Also try ticker.info for timing hint
                    try:
                        info = ticker.info or {}
                        eh = info.get("earningsTimestamp")
                        ehS = info.get("earningsTimestampStart")
                        ehE = info.get("earningsTimestampEnd")
                        if eh or ehS:
                            ts = eh or ehS
                            if isinstance(ts, (int, float)):
                                dt = datetime.fromtimestamp(ts)
                                # Before 12pm = Before Open, after = After Close
                                timing = "Before Open" if dt.hour < 12 else "After Close"
                    except Exception:
                        pass

                for ed in earnings_dates:
                    try:
                        if isinstance(ed, datetime):
                            ed_date = ed.date()
                        elif isinstance(ed, date):
                            ed_date = ed
                        elif isinstance(ed, str):
                            ed_date = datetime.fromisoformat(ed.replace("Z", "+00:00")).date()
                        elif isinstance(ed, (int, float)):
                            ed_date = datetime.fromtimestamp(ed).date()
                        else:
                            continue

                        days_away = (ed_date - today).days
                        if 0 <= days_away <= max_days:
                            results.append({
                                "symbol": symbol,
                                "event": "EARNINGS",
                                "date": ed_date.isoformat(),
                                "days_away": days_away,
                                "timing": timing,
                            })
                            break  # Only report the nearest earnings date
                    except Exception:
                        continue
            except Exception:
                pass

            # --- Ex-Dividend date ---
            try:
                info = ticker.info or {}
                ex_div = info.get("exDividendDate")
                if ex_div is not None:
                    if isinstance(ex_div, (int, float)):
                        ex_date = datetime.fromtimestamp(ex_div).date()
                    elif isinstance(ex_div, datetime):
                        ex_date = ex_div.date()
                    elif isinstance(ex_div, date):
                        ex_date = ex_div
                    elif isinstance(ex_div, str):
                        ex_date = datetime.fromisoformat(ex_div.replace("Z", "+00:00")).date()
                    else:
                        ex_date = None

                    if ex_date is not None:
                        days_away = (ex_date - today).days
                        if 0 <= days_away <= max_days:
                            results.append({
                                "symbol": symbol,
                                "event": "EX_DIVIDEND",
                                "date": ex_date.isoformat(),
                                "days_away": days_away,
                            })
            except Exception:
                pass

        except Exception:
            # yfinance failure for this symbol — skip it
            continue

    # Sort by days_away ascending
    results.sort(key=lambda x: x["days_away"])
    return results


@router.get("/catalysts", response_model=List[CatalystItem])
async def catalysts(symbols: str = ""):
    """Upcoming earnings/dividend catalysts within 7 days (cached 1 hour, public)."""
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        return []

    key = f"catalysts:{','.join(sorted(sym_list))}"
    cached = cache_get(key)
    if cached is not None:
        return cached

    loop = asyncio.get_event_loop()
    items = await loop.run_in_executor(None, partial(_fetch_catalysts, sym_list))
    cache_set(key, items, _CATALYSTS_TTL)
    return items


# =====================================================================
# Premarket sector heat — per watchlist group, batched yfinance fetch.
# =====================================================================

_GROUPS_PREMARKET_TTL = 60  # 1 min — fresh enough for premarket window


def _fetch_quotes_batch(symbols: list[str]) -> dict[str, dict]:
    """Batch fetch latest price + prior close for many symbols via yfinance.

    Returns {symbol: {last, prev_close, volume}}. Symbols with no data are
    omitted. yfinance batch keeps this to a single HTTP round-trip.
    """
    import pandas as pd
    import yfinance as yf

    out: dict[str, dict] = {}
    if not symbols:
        return out

    # period=2d so we always have a prior close even if today hasn't traded yet.
    # prepost=True picks up premarket / aftermarket bars when present.
    try:
        data = yf.download(
            tickers=symbols,
            period="2d",
            interval="1d",
            prepost=True,
            progress=False,
            group_by="ticker",
            threads=False,  # yfinance threading is flaky; serial is fine for ~30 symbols
            auto_adjust=False,
        )
    except Exception:
        return out

    if data is None or len(data) == 0:
        return out

    for sym in symbols:
        try:
            # Single-symbol download returns flat columns; multi-symbol → MultiIndex.
            if len(symbols) == 1:
                df = data
            else:
                if sym not in data.columns.get_level_values(0):
                    continue
                df = data[sym]
            if df is None or df.empty or len(df) < 2:
                continue
            close = df["Close"].dropna()
            vol = df["Volume"].dropna() if "Volume" in df else pd.Series(dtype=float)
            if len(close) < 2:
                continue
            last = float(close.iloc[-1])
            prev_close = float(close.iloc[-2])
            volume = float(vol.iloc[-1]) if len(vol) > 0 else None
            if prev_close <= 0:
                continue
            out[sym] = {"last": last, "prev_close": prev_close, "volume": volume}
        except Exception:
            continue
    return out


def _summarize_group(
    group, items: list, quotes: dict[str, dict]
) -> GroupPremarketSummary:
    """Aggregate per-group: avg gap, breadth, top/bottom movers."""
    item_quotes: list[GroupSymbolQuote] = []
    breadth_green = 0
    breadth_total = 0
    gap_sum = 0.0

    for it in items:
        q = quotes.get(it.symbol)
        if q is None:
            item_quotes.append(GroupSymbolQuote(symbol=it.symbol))
            continue
        last = q["last"]
        prev = q["prev_close"]
        gap_pct = round((last - prev) / prev * 100, 2) if prev > 0 else None
        item_quotes.append(
            GroupSymbolQuote(
                symbol=it.symbol,
                last_price=round(last, 2),
                prior_close=round(prev, 2),
                gap_pct=gap_pct,
                volume=q.get("volume"),
            )
        )
        if gap_pct is not None:
            gap_sum += gap_pct
            breadth_total += 1
            if gap_pct > 0:
                breadth_green += 1

    movers = [q for q in item_quotes if q.gap_pct is not None]
    top = max(movers, key=lambda q: q.gap_pct) if movers else None
    bottom = min(movers, key=lambda q: q.gap_pct) if movers else None
    avg_gap = round(gap_sum / breadth_total, 2) if breadth_total > 0 else None

    return GroupPremarketSummary(
        group_id=group.id,
        name=group.name,
        color=group.color,
        sort_order=group.sort_order,
        item_count=len(items),
        avg_gap_pct=avg_gap,
        breadth_green=breadth_green,
        breadth_total=breadth_total,
        top_mover=top,
        bottom_mover=bottom,
        items=item_quotes,
    )


@router.get("/groups/premarket-summary", response_model=List[GroupPremarketSummary])
async def groups_premarket_summary(
    user: User = Depends(get_current_user),
):
    """Per-watchlist-group premarket aggregation.

    For each of the user's WatchlistGroups, computes:
      - avg gap % across constituents
      - breadth (count of green symbols / total)
      - top mover and bottom mover
      - per-symbol last/prev_close/gap_pct rows for drill-in

    Sorted by abs(avg_gap_pct) DESC so the most active sectors float to top.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.database import async_session_factory
    from app.models.watchlist import WatchlistGroup, WatchlistItem

    cache_key = f"groups_premarket:{user.id}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    # Load user's groups + items. Fall back to the admin's groups when the
    # user has none — 2026-06-01 public-access launch. Lets brand-new users
    # see sector premarket data immediately without having to seed their own
    # watchlist first. Admin user is resolved the same way as /watchlist/sectors.
    db: AsyncSession
    async with async_session_factory() as db:
        groups_result = await db.execute(
            select(WatchlistGroup)
            .where(WatchlistGroup.user_id == user.id)
            .order_by(WatchlistGroup.sort_order, WatchlistGroup.id)
        )
        groups = list(groups_result.scalars().all())
        source_user_id = user.id
        if not groups:
            from app.dependencies import ADMIN_EMAILS
            from app.models.user import User as _User
            admin_id = (
                await db.execute(
                    select(_User.id).where(_User.email.in_(ADMIN_EMAILS)).order_by(_User.id).limit(1)
                )
            ).scalar_one_or_none()
            if admin_id is None:
                return []
            groups_result = await db.execute(
                select(WatchlistGroup)
                .where(WatchlistGroup.user_id == admin_id)
                .order_by(WatchlistGroup.sort_order, WatchlistGroup.id)
            )
            groups = list(groups_result.scalars().all())
            if not groups:
                return []
            source_user_id = admin_id

        items_result = await db.execute(
            select(WatchlistItem)
            .where(WatchlistItem.user_id == source_user_id)
            .where(WatchlistItem.group_id.is_not(None))
        )
        all_items = list(items_result.scalars().all())

    # Bucket items by group_id.
    items_by_group: dict[int, list] = {}
    for it in all_items:
        items_by_group.setdefault(it.group_id, []).append(it)

    # Batch fetch quotes for all symbols at once (one HTTP round-trip).
    all_symbols = sorted({it.symbol for it in all_items})
    loop = asyncio.get_event_loop()
    quotes = await loop.run_in_executor(None, partial(_fetch_quotes_batch, all_symbols))

    summaries = [
        _summarize_group(g, items_by_group.get(g.id, []), quotes) for g in groups
    ]
    # Sort by abs(avg_gap_pct) DESC; groups with no data sink to bottom.
    summaries.sort(
        key=lambda s: abs(s.avg_gap_pct) if s.avg_gap_pct is not None else -1,
        reverse=True,
    )

    cache_set(cache_key, summaries, _GROUPS_PREMARKET_TTL)
    return summaries


@router.post("/groups/sector-brief/test")
async def fire_sector_brief_test(
    user: User = Depends(get_current_user),
):
    """Manually fire the premarket sector brief to the current user's Telegram.

    Bypasses the 9:00 ET cron — useful for testing the format and pipeline
    without waiting for the scheduled run. Only sends to YOUR chat_id, not
    other users.
    """
    from app.services.sector_brief import build_user_sector_brief
    from alerting.notifier import _send_telegram_to

    if not user.telegram_chat_id:
        return {"sent": False, "reason": "no telegram_chat_id on this user"}

    body = await build_user_sector_brief(user.id)
    if not body:
        return {"sent": False, "reason": "no groups or no premarket data"}

    ok = _send_telegram_to(body, user.telegram_chat_id, parse_mode="HTML")
    return {"sent": ok, "preview": body}


# ── SPY Regime Gauge (Feature 3) ─────────────────────────────────────
# Polled every ~60s by the Trading page top strip. Gives the busy user
# one-glance "is today engageable" context.
#
# Bias label decision tree:
#   inside_day AND |slope| < 0.05%  →  "INSIDE DAY · WAIT · scalp edges"
#   slope >= +0.05% AND price > VWAP →  "LONG BIAS"
#   slope <= -0.05% AND price < VWAP →  "STAND DOWN"
#   else                              →  "NEUTRAL"

_SPY_REGIME_TTL = 30  # server-side cache TTL in seconds; clients poll ~60s


@router.get("/spy-regime")
@limiter.limit("60/minute")
async def spy_regime(request: Request, user: User = Depends(get_current_user)):
    """Returns the live SPY regime snapshot for the Trading page top strip.

    Server caches the computed snapshot for 30s — 60s client poll means
    typical worst-case 2 Alpaca calls/min/server regardless of user count.
    """
    cached = cache_get("spy_regime")
    if cached is not None:
        return cached

    loop = asyncio.get_event_loop()
    snapshot = await loop.run_in_executor(None, _compute_spy_regime)
    cache_set("spy_regime", snapshot, _SPY_REGIME_TTL)
    return snapshot


@router.get("/btc-regime")
@limiter.limit("60/minute")
async def btc_regime(request: Request, user: User = Depends(get_current_user)):
    """Live BTC regime snapshot — the crypto market gate (24/7). Same shape as
    /spy-regime; drives the BTC banner chip and gates ETH/alt buys."""
    cached = cache_get("btc_regime")
    if cached is not None:
        return cached

    loop = asyncio.get_event_loop()
    snapshot = await loop.run_in_executor(None, _compute_btc_regime)
    cache_set("btc_regime", snapshot, _SPY_REGIME_TTL)
    return snapshot


def _spy_prior_levels(bars, last_date) -> tuple:
    """PDH/PDL of the most recent COMPLETED RTH session — cached per that date.

    During RTH today's session is in progress, so 'prior' = yesterday. After the
    4pm ET close today is COMPLETE, so the levels ROLL FORWARD to today's low —
    instead of showing yesterday's level all evening until the next open. The
    cache key is the session date used, so it rolls automatically at the close
    and never carries a stale level across the day boundary.

    Derived from Alpaca's RTH bars (reliable in prod); yfinance fetch_prior_day
    is the dev/local fallback. Returns (pdh, pdl, source). Feeds inside-day too.
    """
    from datetime import datetime as _dt
    from analytics.intraday_data import ET

    dates = sorted({ts.date() for ts in bars.index})
    if not dates:
        return None, None, "none"
    # cur_date = the CURRENT open session (passed by the regime). prior_date = the
    # trading session BEFORE it — the PDL rolls at the OPEN (9:30), not the prior
    # close (#267), so a weak close holds through after-hours + premarket until the
    # new session opens. Use the DAILY bars (full history) to find the session-
    # before; the 5m window may not reach back that far (e.g. premarket, cur=yday).
    cur_date = last_date
    daily = None
    try:
        from analytics.intraday_data import _fetch_alpaca_bars as _fab_daily
        daily = _fab_daily("SPY", interval="1d", hours_back=24 * 40)
    except Exception:
        daily = None
    prior_date = None
    if daily is not None and not daily.empty:
        _before = sorted({ts.date() for ts in daily.index if ts.date() < cur_date})
        if _before:
            prior_date = _before[-1]
    if prior_date is None:  # daily unavailable → fall back to the intraday dates
        _before = [d for d in dates if d < cur_date]
        prior_date = _before[-1] if _before else (dates[-2] if len(dates) >= 2 else dates[-1])

    key = f"spy_levels:SPY:{prior_date.isoformat()}"
    cached = cache_get(key)
    if isinstance(cached, dict) and cached.get("pdl") is not None:
        return cached.get("pdh"), cached.get("pdl"), "cache"

    pdh = pdl = None
    src = "alpaca_daily"
    # PRIMARY (#260): the COMPLETED DAILY bar for prior_date. A daily bar's high/low
    # IS the RTH session high/low — no extended-hours prints. The old path read 5m
    # bars and leaked a pre/after-hours low (749.74, BELOW the real 751.76 RTH low),
    # so SPY read as above its PDL and the weak-tape gate never bit. At the close we
    # already know the day's PDH/PDL — just take the daily bar. Alpaca daily is
    # cloud-safe (yfinance is blocked on Railway).
    try:
        if daily is not None and not daily.empty:
            drow = daily[daily.index.date == prior_date]
            if len(drow):
                pdh = float(drow["High"].iloc[-1])
                pdl = float(drow["Low"].iloc[-1])
    except Exception:
        pdh = pdl = None
    # FALLBACK: RTH-filtered 5m bars if the daily bar was missing for that date.
    if pdl is None:
        src = "alpaca_5m"
        pbars = bars[bars.index.date == prior_date]
        rth = pbars.between_time("09:30", "16:00")
        use = rth if len(rth) else pbars
        if len(use):
            pdh = float(use["High"].max())
            pdl = float(use["Low"].min())
    if pdl is None:  # Alpaca lacked the session (dev/local) → yfinance
        src = "yfinance"
        from analytics.intraday_data import fetch_prior_day
        prior = fetch_prior_day("SPY") or {}
        pdh = float(prior["high"]) if prior.get("high") is not None else None
        pdl = float(prior["low"]) if prior.get("low") is not None else None
    try:
        logger.info("SPY prior-levels: date=%s src=%s -> pdh=%s pdl=%s", prior_date, src, pdh, pdl)
    except Exception:
        pass
    if pdl is not None:
        cache_set(key, {"pdh": pdh, "pdl": pdl}, 8 * 3600)
    return pdh, pdl, src


def _rsi(closes: list, period: int = 14):
    """Wilder's RSI on a close series. None if not enough data."""
    if len(closes) < period + 1:
        return None
    import pandas as pd
    s = pd.Series([float(c) for c in closes])
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    ag, al = float(avg_gain.iloc[-1]), float(avg_loss.iloc[-1])
    if al == 0:
        return 100.0 if ag > 0 else None
    rs = ag / al
    return 100.0 - 100.0 / (1.0 + rs)


def _fetch_yf_daily_closes(product: str, n: int = 250) -> list:
    """Daily closes from yfinance — the gate's fallback when Alpaca is 401/down in
    prod. Without a fallback the SPY 8/21 read returns None and the day-trade-long
    gate FAILS OPEN (every long flows in a weak tape). yfinance is unreliable on
    some cloud hosts; returns [] gracefully when it can't fetch (no worse than the
    Alpaca-only path it backstops)."""
    try:
        import yfinance as yf
        df = yf.download(product, period="1y", interval="1d", progress=False, auto_adjust=False)
        if df is None or df.empty:
            return []
        col = df["Close"]
        closes = [float(x) for x in (col.iloc[:, 0] if hasattr(col, "columns") else col).dropna()]
        return closes[-n:] if closes else []
    except Exception:
        return []


def _fetch_daily_closes(product: str, is_crypto: bool, n: int = 250) -> list:
    """A YEAR of DAILY closes (last bar ~= today's running close). Wilder's RSI
    needs a long warmup to match TradingView — feeding only a few recent bars
    (e.g. just a selloff) reads artificially oversold. Alpaca daily for stocks,
    Coinbase daily for crypto. Coinbase caps at 300 candles/request. For stocks,
    fall back to yfinance when Alpaca is empty/unauthorized so the regime gate keeps
    working (otherwise it fails open and longs flow in a weak tape)."""
    try:
        if is_crypto:
            from analytics.intraday_data import _fetch_coinbase_candles
            df = _fetch_coinbase_candles(product, granularity=86400, num_candles=min(n, 300))
            if df is None or df.empty:
                return []
            return [float(x) for x in df["Close"].tail(n)]
        from analytics.intraday_data import _fetch_alpaca_bars
        df = _fetch_alpaca_bars(product, interval="1d", hours_back=24 * 370)  # ~1yr
        if df is not None and not df.empty:
            return [float(x) for x in df["Close"].tail(n)]
        return _fetch_yf_daily_closes(product, n)  # Alpaca down → keep the gate alive
    except Exception:
        return _fetch_yf_daily_closes(product, n) if not is_crypto else []


def _spy_below_8_and_21() -> Optional[bool]:
    """Is SPY trading below EITHER its daily 8-EMA or 21-EMA right now?

    The day-trade-long gate (agreed spec, v2-routing-notices-patterns.md, 2026-05-05):
    HEALTHY = SPY above BOTH the 8 AND 21; WEAK = SPY below the 8 OR the 21. The
    moment SPY loses either short-term EMA the tape is no longer cleanly trending,
    so equity longs are suppressed except the exempt names. Cached 60s. Returns
    True/False, or None when data is unavailable (caller fails open — never block
    on missing data).
    """
    cached = cache_get("spy_trend_8_21")
    if isinstance(cached, bool):
        return cached
    try:
        import pandas as pd
        from analytics.intraday_data import fetch_latest_price
        closes = _fetch_daily_closes("SPY", False)
        if len(closes) < 22:
            return None
        s = pd.Series(closes, dtype="float64")
        ema8 = float(s.ewm(span=8, adjust=False).mean().iloc[-1])
        ema21 = float(s.ewm(span=21, adjust=False).mean().iloc[-1])
        price = fetch_latest_price("SPY") or float(closes[-1])
        below = bool(price < ema8 or price < ema21)
        cache_set("spy_trend_8_21", below, 60)
        return below
    except Exception:
        return None


# Need ample warmup or Wilder's RSI is skewed by the recent window.
_RSI_MIN_BARS = 50


def _daily_rsi(product: str, is_crypto: bool, period: int = 14):
    """Daily RSI(14) for the regime banner — context, not a gate. Cached 5 min.
    Returns None (no badge) rather than a wrong value when there aren't enough
    daily bars to warm up. Zones: <= 30 oversold, >= 70 overbought."""
    key = f"daily_rsi:{product}"
    cached = cache_get(key)
    if isinstance(cached, dict):
        return cached.get("rsi")
    closes = _fetch_daily_closes(product, is_crypto)
    rsi = _rsi(closes, period) if len(closes) >= _RSI_MIN_BARS else None
    cache_set(key, {"rsi": rsi}, 300)
    return rsi


def _regime_dict(today_bars, pdh, pdl, pdl_src, label, rsi=None, below_trend=None) -> dict:
    """Shared regime computation from ONE session's bars + prior levels —
    used by both SPY (Alpaca) and BTC (Coinbase). Computes session VWAP/slope,
    inside-day, below_pdl, and the bias label. `label` is the market name for
    the log + bias text (e.g. "SPY", "BTC")."""
    typical = (today_bars["High"] + today_bars["Low"] + today_bars["Close"]) / 3.0
    pv = typical * today_bars["Volume"]
    cum_pv = pv.cumsum()
    cum_vol = today_bars["Volume"].cumsum().replace(0, float("nan"))
    vwap_series = (cum_pv / cum_vol).dropna()
    if len(vwap_series) == 0:
        return {"status": "unavailable", "reason": "vwap math failed"}

    last_vwap = float(vwap_series.iloc[-1])
    last_price = float(today_bars["Close"].iloc[-1])

    # Slope as % over the last ~30 minutes (6 × 5m bars).
    look = min(6, len(vwap_series) - 1)
    slope_pct = 0.0
    if look > 0 and vwap_series.iloc[-1 - look] != 0:
        prev = float(vwap_series.iloc[-1 - look])
        slope_pct = (last_vwap - prev) / prev * 100.0

    today_open = float(today_bars["Open"].iloc[0])
    today_high = float(today_bars["High"].max())
    today_low = float(today_bars["Low"].min())
    inside_day = bool(
        pdh is not None and pdl is not None
        and today_high < pdh and today_low > pdl
    )
    below_pdl = bool(pdl is not None and last_price < pdl)

    # Headline regime. When the caller passes `below_trend` (SPY → its daily 8/21
    # EMA read), use it so the banner matches the alert gate EXACTLY, per the agreed
    # spec (v2-routing-notices-patterns.md, 2026-05-05): below the 8 OR the 21 = not
    # cleanly trending → WEAK (day-trade longs gated, shorts flow); above BOTH the 8
    # AND 21 = trending → HEALTHY; None (no data) → HEALTHY.
    # When below_trend is omitted (BTC), keep the prior PDL-based binary unchanged.
    logging.getLogger(__name__).info(
        "%s regime: price=%.2f below_trend=%s pdl=%s (src=%s) below_pdl=%s",
        label, last_price, below_trend, pdl, pdl_src, below_pdl,
    )
    if below_trend is not None:
        weak = below_trend is True
        weak_why = "below its 8 or 21 EMA (not trending; day-trade longs gated)"
        ok_why = "trading above its 8 & 21 EMA"
    else:
        weak = below_pdl
        weak_why = "below its prior-day low (dips get knifed; longs gated)"
        ok_why = "holding above its prior-day low"
    if weak:
        bias = "WEAK"
        bias_label = f"WEAK — {label} {weak_why}"
        bias_color = "red"
    else:
        bias = "HEALTHY"
        bias_label = f"HEALTHY — {label} {ok_why}"
        bias_color = "green"

    # RSI context (daily) — informs sizing, not a gate. <= 30 oversold,
    # >= 70 overbought (standard 30/70 bands).
    rsi_zone = None
    if rsi is not None:
        rsi_zone = "oversold" if rsi <= 30 else "overbought" if rsi >= 70 else "neutral"

    return {
        "status": "ok",
        "price": round(last_price, 2),
        "vwap": round(last_vwap, 2),
        "vwap_slope_pct": round(slope_pct, 3),
        "today_open": round(today_open, 2),
        "pdh": pdh,
        "pdl": pdl,
        "below_pdl": below_pdl,
        "below_8_21": below_trend,
        "inside_day": inside_day,
        "rsi": round(rsi, 1) if rsi is not None else None,
        "rsi_zone": rsi_zone,
        "bias": bias,
        "bias_label": bias_label,
        "bias_color": bias_color,
        "last_bar_time": today_bars.index[-1].isoformat(),
    }


def _regime_or_last_good(key: str, fresh: dict) -> dict:
    """ALWAYS try to return usable data. On a successful compute, stash it as
    the 'last good' snapshot; on a failed one (data outage), return the last
    good snapshot marked stale rather than going blind — the gate keeps working
    on slightly-old data instead of failing open. Only truly returns
    'unavailable' when there is no last-good to fall back to."""
    if fresh.get("status") == "ok":
        cache_set(f"{key}_lastgood", fresh, 6 * 3600)
        return fresh
    last = cache_get(f"{key}_lastgood")
    if isinstance(last, dict) and last.get("status") == "ok":
        return {**last, "stale": True}
    return fresh


def _compute_spy_regime() -> dict:
    """SPY regime (stocks) — last-good fallback so it almost never goes blind."""
    return _regime_or_last_good("spy_regime", _spy_regime_fresh())


def _spy_regime_fresh() -> dict:
    from analytics.intraday_data import _fetch_alpaca_bars, fetch_intraday

    bars = None
    try:
        bars = _fetch_alpaca_bars("SPY", interval="5m", hours_back=48)
    except Exception:
        bars = None
    if bars is None or len(bars) == 0:
        # Alpaca down → try yfinance intraday (works sometimes from cloud).
        try:
            bars = fetch_intraday("SPY", period="2d", interval="5m")
        except Exception:
            bars = None
    if bars is None or len(bars) == 0:
        return {"status": "unavailable", "reason": "no SPY bars"}

    # #267 — reflect the TRUE session state, RTH-only. The "current session" is the
    # most recent one whose RTH 9:30 OPEN has passed. Outside RTH it stays the just-
    # closed session, so its CLOSE (never a 4am print) drives the regime and a weak
    # close HOLDS through after-hours + premarket. The PDL is the session BEFORE it,
    # and only rolls at the next OPEN (see _spy_prior_levels). So: SPY closes below
    # its PDL Tuesday -> stays WEAK premarket Wed -> rolls to Tue's low at Wed's open.
    from datetime import datetime as _dt
    from analytics.intraday_data import ET as _ET
    now_et = _dt.now(_ET).replace(tzinfo=None)
    rth_all = bars.between_time("09:30", "16:00")
    if len(rth_all) == 0:
        return {"status": "unavailable", "reason": "no RTH bars"}
    rth_dates = sorted({ts.date() for ts in rth_all.index})
    cur_date = next(
        (d for d in reversed(rth_dates) if now_et >= _dt(d.year, d.month, d.day, 9, 30)),
        rth_dates[-1],
    )
    today_bars = rth_all[rth_all.index.date == cur_date]
    if len(today_bars) == 0:
        return {"status": "unavailable", "reason": "no current-session bars"}

    pdh, pdl, src = _spy_prior_levels(bars, cur_date)
    return _regime_dict(today_bars, pdh, pdl, src, "SPY", rsi=_daily_rsi("SPY", False),
                        below_trend=_spy_below_8_and_21())


def _crypto_prior_levels(product: str, last_date) -> tuple:
    """Prior-day PDH/PDL for a crypto product — taken straight from the last
    COMPLETED Coinbase daily candle (iloc[-2]; iloc[-1] is the in-progress day),
    which matches what the chart plots. We do NOT use fetch_prior_day's crypto
    path: its iloc[-2 vs -1] 'market hours' logic is meaningless for a 24/7
    market and returned the wrong candle (e.g. 59448 vs the chart's 59073),
    making inside-day false and producing phantom below-PDL blocks. Cached 1h
    (the UTC day boundary is fuzzy vs the ET intraday date)."""
    key = f"crypto_levels:{product}:{last_date.isoformat()}"
    cached = cache_get(key)
    if isinstance(cached, dict) and cached.get("pdl") is not None:
        return cached.get("pdh"), cached.get("pdl"), "cache"
    pdh = pdl = None
    try:
        from analytics.intraday_data import _fetch_coinbase_candles
        d = _fetch_coinbase_candles(product, granularity=86400, num_candles=5)
        if d is not None and len(d) >= 2:
            prior = d.iloc[-2]  # last fully-completed daily candle
            pdh = float(prior["High"])
            pdl = float(prior["Low"])
    except Exception:
        pass
    if pdl is not None:
        cache_set(key, {"pdh": pdh, "pdl": pdl}, 3600)
    return pdh, pdl, "coinbase"


def _compute_btc_regime() -> dict:
    """BTC regime (crypto, 24/7) — last-good fallback so it almost never blinds.
    BTC is the crypto 'index': it gates ETH/alt buys but is itself exempt, and
    runs around the clock so the gate flow can be validated before equity open.
    """
    return _regime_or_last_good("btc_regime", _btc_regime_fresh())


def _btc_regime_fresh() -> dict:
    # fetch_intraday_crypto chains Alpaca → Coinbase → yfinance (robust). PDH/PDL
    # come from the Coinbase daily candle directly (see _crypto_prior_levels).
    from analytics.intraday_data import fetch_intraday_crypto

    try:
        today_bars = fetch_intraday_crypto("BTC-USD", "5m")  # already today-only
    except Exception:
        return {"status": "unavailable", "reason": "data fetch failed"}
    if today_bars is None or len(today_bars) == 0:
        return {"status": "unavailable", "reason": "no BTC bars"}

    last_date = today_bars.index[-1].date()
    pdh, pdl, src = _crypto_prior_levels("BTC-USD", last_date)
    return _regime_dict(today_bars, pdh, pdl, src, "BTC", rsi=_daily_rsi("BTC-USD", True))


# ── Premarket Gap Board ──────────────────────────────────────────────

def _pmgaps_sync_session_factory():
    """Standalone sync session factory (independent of app.state)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.config import get_settings
    url = get_settings().DATABASE_URL
    if url.startswith("sqlite"):
        url = url.replace("+aiosqlite", "")
    else:
        for suffix in ("+asyncpg", "+psycopg2", "+psycopg"):
            url = url.replace(suffix, "")
    engine = create_engine(url, pool_pre_ping=True)
    return engine, sessionmaker(bind=engine)


@router.get("/premarket-gaps")
async def premarket_gaps(user: User = Depends(get_current_user)):
    """Latest premarket gap snapshot — stocks gapping pre-bell (clean + momentum
    buckets) with PM volume, key levels, and a news catalyst. Read-only; the
    snapshot is produced by the premarket cron / refresh."""
    from datetime import datetime, timedelta
    from sqlalchemy import select, desc
    from app.database import get_db as get_db_dep
    from app.models.premarket_gap import PremarketGapSnapshot

    async for db in get_db_dep():
        row = (await db.execute(
            select(PremarketGapSnapshot).order_by(desc(PremarketGapSnapshot.captured_at)).limit(1)
        )).scalar_one_or_none()
        if row is None:
            return {"captured_at": None, "entries": [], "stale": False}
        stale = (datetime.utcnow() - row.captured_at) > timedelta(hours=6)
        return {
            "captured_at": row.captured_at.isoformat() + "Z",
            "entries": row.entries or [],
            "stale": stale,
        }


@router.post("/premarket-gaps/refresh", status_code=200)
async def refresh_premarket_gaps_now(user: User = Depends(get_current_user)):
    """Manual premarket gap scan — same code path as the cron, synchronous,
    returns the scan summary (so the UI can show 'blocked' vs 'refreshed')."""
    import logging

    def _run() -> dict:
        from analytics.premarket_gaps import refresh_premarket_gaps
        engine, factory = _pmgaps_sync_session_factory()
        try:
            return refresh_premarket_gaps(factory)
        finally:
            engine.dispose()

    try:
        summary = await asyncio.to_thread(_run)
    except Exception:
        logging.getLogger(__name__).exception("Manual premarket gaps refresh failed")
        return {"status": "error", "gappers": 0, "snapshot_id": None}
    return {"status": "ok", **summary}


# ── Bottom Watch — watchlist ranked by daily RSI (oversold bottom-fishing) ──────
_BOTTOM_WATCH_TTL = 300       # 5 min — RSI is daily, the rank barely moves intraday
_BOTTOM_WATCH_MAX = 120       # the screener_universe (~120 notable/liquid names)


def _bottom_state(rsi: float, rsi_prev, near_200: bool) -> tuple[str, str]:
    """Classify a symbol's bottom-fishing state. ONLY the actionable states make
    the board (user 2026-06-30): RSI <= 33 (cooling near / below 30) OR at the
    200-MA. 'Cooling above the zone' and 'approaching' are DROPPED (empty state) —
    they don't do much; below 33 is where we start paying attention. Less data,
    fast to scan. The caller filters out the empty-state rows."""
    if rsi_prev is not None and rsi_prev < 30 <= rsi:
        return "reclaimed_30", "Reclaimed 30 → BUY"
    if rsi < 30:
        return "oversold", "Oversold — watch the reclaim"
    if rsi <= 33:
        return "buy_zone", "In the 30–33 buy zone"
    if near_200:
        return "at_200ma", "At the 200-MA"
    return "", ""   # not on the board — cooling above the zone


# Fundamentals — "is it worth buying even oversold?" (P/E, EPS, analyst rating + target,
# market cap, sector). yfinance .info is slow + cloud-blocked, so it is WARMED IN THE
# BACKGROUND (never blocks the board) and cached 12h — fundamentals barely move.
_FUND_TTL = 12 * 3600
_fund_inflight: set = set()


def _fund_fetch(sym: str) -> dict:
    out: dict = {}
    try:
        import yfinance as yf
        info = yf.Ticker(sym).info or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        tgt = info.get("targetMeanPrice")
        out = {
            "pe": round(float(info["trailingPE"]), 1) if info.get("trailingPE") else None,
            "eps": round(float(info["trailingEps"]), 2) if info.get("trailingEps") else None,
            "mkt_cap": info.get("marketCap"),
            "rec": info.get("recommendationKey"),
            "target_upside_pct": (round((tgt - price) / price * 100, 1)
                                  if tgt and price else None),
            "sector": info.get("sector"),
        }
    except Exception:
        out = {}
    cache_set(f"fund:{sym}", out, _FUND_TTL)
    return out


async def _warm_fund(sym: str) -> None:
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _fund_fetch, sym)
    finally:
        _fund_inflight.discard(sym)


@router.get("/bottom-watch")
async def bottom_watch(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The broad universe ranked by daily RSI(14), lowest first — for catching the
    bottom in washed-out (mega-)caps. ONLY actionable rows make the board: RSI <= 33
    (cooling near / below 30) OR at the 200-MA. Each row carries the RSI, distance to
    the 200-MA, and a STATE: reclaimed_30 (the turn is in) · oversold (<30) · buy_zone
    (30–33) · at_200ma. 'Cooling above the zone' is excluded (less data, fast to scan).
    Powers the Today 'Bottom Watch' board. Cached 5 min."""
    # GLOBAL universe — the broad market scan set (screener_universe, ~120 notable/liquid
    # names, rebuilt periodically), NOT the user's watchlist. The whole point is to surface
    # oversold names you AREN'T already watching, so the board is the same for everyone.
    key = "bottom_watch:global"
    base = cache_get(key)
    if base is not None:
        return _attach_fundamentals(base)

    from sqlalchemy import text
    rows = (await db.execute(text(
        "SELECT symbol FROM screener_universe ORDER BY market_cap DESC NULLS LAST LIMIT :n"
    ), {"n": _BOTTOM_WATCH_MAX})).all()
    symbols = [r[0].upper() for r in rows]
    loop = asyncio.get_running_loop()

    async def _one(sym: str):
        # Use market.py's own daily-close fetch (Alpaca → yfinance fallback, #461) +
        # compute RSI inline — fetch_prior_day computes many fragile fields and returns
        # None if any fail, which silently emptied the board in prod.
        try:
            closes = await loop.run_in_executor(
                None, _fetch_daily_closes, sym, sym.endswith("-USD")
            )
        except Exception:
            return None
        if not closes or len(closes) < 30:
            return None
        import pandas as pd
        s = pd.Series(closes, dtype="float64")
        delta = s.diff()
        gain = delta.clip(lower=0).ewm(com=13, min_periods=14).mean()
        loss = (-delta.clip(upper=0)).ewm(com=13, min_periods=14).mean()
        rsi_series = 100 - 100 / (1 + gain / loss)
        rsi = float(rsi_series.iloc[-1])
        if rsi != rsi:  # NaN guard
            return None
        rsi_prev = float(rsi_series.iloc[-2]) if len(rsi_series) >= 2 and rsi_series.iloc[-2] == rsi_series.iloc[-2] else None
        close = float(s.iloc[-1])
        ema200 = float(s.ewm(span=200, adjust=False).mean().iloc[-1]) if len(s) >= 200 else None
        dist = round((close - ema200) / ema200 * 100, 2) if ema200 else None
        near_200 = ema200 is not None and abs(close - ema200) / ema200 <= 0.02
        state, label = _bottom_state(rsi, rsi_prev, near_200)
        return {
            "symbol": sym,
            "rsi": round(rsi, 1),
            "rsi_prev": round(rsi_prev, 1) if rsi_prev is not None else None,
            "dist_200ma_pct": dist,
            "near_200ma": near_200,
            "state": state,
            "state_label": label,
        }

    # Only actionable rows make the board — RSI <= 33 (cooling near/below 30) or at
    # the 200-MA. Empty-state rows (cooling above the zone) are dropped.
    results = [r for r in await asyncio.gather(*[_one(s) for s in symbols]) if r and r["state"]]
    results.sort(key=lambda x: x["rsi"])
    cache_set(key, results, _BOTTOM_WATCH_TTL)
    return _attach_fundamentals(results)


def _attach_fundamentals(base: list) -> list:
    """Merge each row with its cached fundamentals; kick off a background warm for any
    cache miss. Runs on EVERY request (outside the 5-min board cache) so the P/E etc.
    fill in within a refresh or two of first sight, without ever blocking the board."""
    out = []
    for row in base:
        sym = row["symbol"]
        f = cache_get(f"fund:{sym}")
        if f is None and sym not in _fund_inflight:
            _fund_inflight.add(sym)
            try:
                asyncio.get_running_loop().create_task(_warm_fund(sym))
            except RuntimeError:
                _fund_inflight.discard(sym)
        out.append({**row, "fund": (f or None)})
    return out
