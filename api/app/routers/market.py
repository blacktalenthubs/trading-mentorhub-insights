"""Market data endpoints with Redis/memory caching."""

from __future__ import annotations

import asyncio
import sys
from functools import partial
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Request

from app.cache import cache_get, cache_set
from app.dependencies import get_current_user
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.market import CatalystItem, MarketStatusResponse, OHLCBar, OptionsFlowItem, PriorDayResponse, SectorRotationItem

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
