"""In-Play Volume Screener service (spec 62) — orchestration + persistence.

Heavy/live imports (yfinance, alpaca-py, analytics fetch) are LAZY so the app
always boots even when a live adapter needs tuning. The scheduler runs sync jobs
that drive the async DB via ``asyncio.run`` (one fresh loop per run).
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, desc, select

from analytics import screener as scr
from app.config import get_settings
from app.database import async_session_factory
from app.models.screener import ScreenerSnapshot, ScreenerUniverse, ScreenerUserSettings

logger = logging.getLogger("screener")
ET = ZoneInfo("America/New_York")
_SNAPSHOT_RETENTION = 50  # keep last N snapshots for debugging

# Market-hours gate lives in analytics.screener (pure, testable).
is_market_open = scr.is_market_open

# In-memory cache of the latest snapshot (FR — fast reads). Short TTL; the
# scheduler writes every ~10 min so a 20s cache is plenty and bounds DB hits.
_CACHE: dict = {"snap": None, "at": None}
_CACHE_TTL_S = 20


# ---------------------------------------------------------------------------
# Persistence (async)
# ---------------------------------------------------------------------------

async def _load_universe() -> list[scr.UniverseRow]:
    async with async_session_factory() as s:
        rows = (await s.execute(select(ScreenerUniverse))).scalars().all()
    return [scr.UniverseRow(r.symbol, r.market_cap, r.last_price, r.avg_dollar_vol, r.sector) for r in rows]


async def _save_universe(rows: list[scr.UniverseRow]) -> None:
    async with async_session_factory() as s:
        await s.execute(delete(ScreenerUniverse))
        for r in rows:
            s.add(ScreenerUniverse(
                symbol=r.symbol, market_cap=r.market_cap, last_price=r.last_price,
                avg_dollar_vol=r.avg_dollar_vol, sector=r.sector,
            ))
        await s.commit()


async def _save_snapshot(entries: list[scr.InPlayEntry], *, market_open: bool, stale: bool, top_n: int) -> None:
    async with async_session_factory() as s:
        s.add(ScreenerSnapshot(
            market_open=market_open, stale=stale, top_n=top_n,
            entries=[e.to_dict() for e in entries],
        ))
        # prune old snapshots
        old = (await s.execute(
            select(ScreenerSnapshot.id).order_by(desc(ScreenerSnapshot.id)).offset(_SNAPSHOT_RETENTION)
        )).scalars().all()
        if old:
            await s.execute(delete(ScreenerSnapshot).where(ScreenerSnapshot.id.in_(old)))
        await s.commit()
    _CACHE["snap"] = None  # invalidate cache on new write


async def _mark_latest_stale() -> None:
    """Degraded-data path (FR-8): flag the most recent snapshot as stale."""
    async with async_session_factory() as s:
        latest = (await s.execute(
            select(ScreenerSnapshot).order_by(desc(ScreenerSnapshot.id)).limit(1)
        )).scalar_one_or_none()
        if latest is not None:
            latest.stale = True
            await s.commit()


async def get_latest_snapshot() -> ScreenerSnapshot | None:
    """Latest snapshot, fronted by a short in-memory cache to bound DB hits (T034)."""
    now = time.monotonic()
    if _CACHE["snap"] is not None and _CACHE["at"] is not None and (now - _CACHE["at"]) < _CACHE_TTL_S:
        return _CACHE["snap"]
    async with async_session_factory() as s:
        snap = (await s.execute(
            select(ScreenerSnapshot).order_by(desc(ScreenerSnapshot.id)).limit(1)
        )).scalar_one_or_none()
    _CACHE["snap"], _CACHE["at"] = snap, now
    return snap


# --- per-user view settings (FR-6) ---

async def get_user_settings(user_id: int) -> dict:
    async with async_session_factory() as s:
        row = await s.get(ScreenerUserSettings, user_id)
    return {"market_cap_floor": row.market_cap_floor, "top_n": row.top_n} if row else {}


async def set_user_settings(user_id: int, *, market_cap_floor=None, top_n=None) -> dict:
    async with async_session_factory() as s:
        row = await s.get(ScreenerUserSettings, user_id)
        if row is None:
            row = ScreenerUserSettings(user_id=user_id)
            s.add(row)
        if market_cap_floor is not None:
            row.market_cap_floor = market_cap_floor
        if top_n is not None:
            row.top_n = top_n
        await s.commit()
        return {"market_cap_floor": row.market_cap_floor, "top_n": row.top_n}


async def universe_rebuilt_at() -> datetime | None:
    async with async_session_factory() as s:
        return (await s.execute(
            select(ScreenerUniverse.rebuilt_at).order_by(desc(ScreenerUniverse.rebuilt_at)).limit(1)
        )).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Live data gather (Layer 2) — the part to validate during market hours
# ---------------------------------------------------------------------------

def _gather_in_play(universe: list[scr.UniverseRow], top_n: int) -> list[scr.InPlayEntry]:
    """Build ranked InPlayEntry list from live intraday data. LAZY live imports.

    Strategy: prune the universe to today's most-active names (Alpaca), then for
    each compute time-normalized RVOL + setup + refine inputs. Bounded by design.
    """
    from analytics.intraday_data import fetch_intraday  # lazy
    from analytics.signal_engine import analyze_symbol, fetch_ohlc  # lazy, read-only

    by_symbol = {u.symbol: u for u in universe}
    candidates = _most_active_symbols(set(by_symbol)) or list(by_symbol)[:120]

    now_et = datetime.now(ET).time()
    frac = scr.session_fraction(now_et)
    entries: list[scr.InPlayEntry] = []
    for sym in candidates:
        u = by_symbol.get(sym)
        if u is None:
            continue
        try:
            intraday = fetch_intraday(sym, period="1d", interval="5m")
            if intraday is None or intraday.empty:
                continue
            today_cum = float(intraday["Volume"].sum())
            avg_daily_vol = (u.avg_dollar_vol / u.last_price) if u.last_price else 0.0
            rvol = scr.relative_volume(today_cum, avg_daily_vol, frac)
            last_price = float(intraday["Close"].iloc[-1])
            first_open = float(intraday["Open"].iloc[0])
            pct_change = ((last_price - first_open) / first_open * 100.0) if first_open else 0.0
            entry = scr.InPlayEntry(
                symbol=sym, last_price=last_price, pct_change=pct_change, rvol=rvol,
                dollar_vol=today_cum * last_price, market_cap=u.market_cap, sector=u.sector,
            )
            _attach_refine(entry, fetch_ohlc(sym, "3mo"), intraday)
            entries.append(entry)
        except Exception:  # one bad symbol must not kill the snapshot
            logger.debug("screener: skipped %s", sym, exc_info=True)

    ranked = scr.rank_in_play(entries, top_n)
    # setup scan (read-only) on the final shortlist only
    scr.scan_setups(ranked, hist_provider=lambda s: _safe_ohlc(s), analyzer=analyze_symbol)
    return ranked


def _safe_ohlc(symbol: str):
    try:
        from analytics.signal_engine import fetch_ohlc
        return fetch_ohlc(symbol, "3mo")
    except Exception:
        return None


def _attach_refine(entry: scr.InPlayEntry, daily, intraday) -> None:
    """Best-effort refine inputs from data already on hand (FR-9 inputs)."""
    try:
        import pandas as pd  # noqa
        close = daily["Close"]
        ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
        delta = close.diff()
        up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        down = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        rs = up / down.replace(0, 1e-9)
        rsi = float(100 - 100 / (1 + rs.iloc[-1]))
        high_20 = float(close.tail(20).max())
        vwap = float((intraday["Close"] * intraday["Volume"]).sum() / max(intraday["Volume"].sum(), 1))
        above_ema50 = entry.last_price > float(ema50)
        entry.refine = {
            "above_ema50": above_ema50,
            "above_vwap": entry.last_price > vwap,
            "rsi": round(rsi, 1),
            "near_20d_high": entry.last_price >= 0.98 * high_20,
            "rs_vs_spy": None,  # TODO: vs-SPY relative strength (Monday validation)
            "atr_pct": None,
        }
        entry.direction = "long" if above_ema50 else "short"
    except Exception:
        entry.refine = {}
        entry.direction = "neutral"


def _most_active_symbols(universe_symbols: set[str]) -> list[str]:
    """Alpaca most-actives ∩ universe (lazy). Empty list → caller falls back."""
    try:
        import os
        from alpaca.data.historical.screener import ScreenerClient
        from alpaca.data.requests import MostActivesRequest
        client = ScreenerClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])
        res = client.get_most_actives(MostActivesRequest(top=100))
        actives = [m.symbol for m in getattr(res, "most_actives", [])]
        return [s for s in actives if s in universe_symbols]
    except Exception:
        logger.warning("screener: most-actives unavailable, falling back to universe head", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Orchestration (async) + sync scheduler wrappers
# ---------------------------------------------------------------------------

async def refresh_in_play() -> None:
    """FR-2/FR-3/FR-8: market-hours gate → gather → persist; degrade on failure."""
    if not is_market_open():
        logger.info("screener: market closed, refresh skipped")
        return
    settings = get_settings()

    # Single-instance guard (T032): if another replica wrote a snapshot within
    # half the refresh interval, skip so we don't double-refresh. Best-effort.
    guard_min = max(1, settings.SCREENER_REFRESH_MINUTES // 2)
    latest = await get_latest_snapshot()
    if latest is not None and latest.captured_at is not None:
        cap = latest.captured_at.replace(tzinfo=None)
        age_min = (datetime.utcnow() - cap).total_seconds() / 60
        if 0 <= age_min < guard_min:
            logger.info("screener: fresh snapshot (%.1fm) — skip duplicate refresh", age_min)
            return

    universe = await _load_universe()
    if not universe:
        logger.warning("screener: empty universe — rebuild needed")
        return
    try:
        entries = await asyncio.to_thread(_gather_in_play, universe, settings.SCREENER_TOP_N)
        await _save_snapshot(entries, market_open=True, stale=False, top_n=settings.SCREENER_TOP_N)
        logger.info("screener: snapshot refreshed (%d entries)", len(entries))
    except Exception:
        logger.exception("screener: refresh failed — marking last snapshot stale")
        await _mark_latest_stale()


async def rebuild_universe() -> None:
    """FR-1/FR-7: rebuild the capped universe (weekly / on demand)."""
    settings = get_settings()
    rows = await asyncio.to_thread(
        scr.build_universe,
        settings.SCREENER_MARKET_CAP_FLOOR, settings.SCREENER_PRICE_FLOOR, settings.SCREENER_DOLLAR_VOL_FLOOR,
    )
    if rows:
        await _save_universe(rows)
        logger.info("screener: universe rebuilt (%d names)", len(rows))
    else:
        logger.warning("screener: universe rebuild returned 0 names — kept previous")


# Sync wrappers for BackgroundScheduler (one fresh event loop per run).
def refresh_in_play_job() -> None:
    asyncio.run(refresh_in_play())


def rebuild_universe_job() -> None:
    asyncio.run(rebuild_universe())
