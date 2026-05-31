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
from app.models.screener import ScreenerAlertLog, ScreenerSnapshot, ScreenerUniverse, ScreenerUserSettings

logger = logging.getLogger("screener")
ET = ZoneInfo("America/New_York")
_SNAPSHOT_RETENTION = 50  # keep last N snapshots for debugging

# Market-hours gate lives in analytics.screener (pure, testable).
is_market_open = scr.is_market_open

# In-memory cache of the latest snapshot per kind (fast reads, bounds DB hits).
_CACHE: dict = {}  # kind -> {"snap": ScreenerSnapshot|None, "at": monotonic}
_CACHE_TTL_S = 20

# The app's main event loop (set at startup). Scheduler jobs run on worker threads;
# the async Postgres engine is bound to THIS loop, so cross-loop asyncio.run() fails.
_MAIN_LOOP = None


def set_main_loop(loop) -> None:
    global _MAIN_LOOP
    _MAIN_LOOP = loop


def _run(coro) -> None:
    """Run an async coroutine from a sync scheduler thread on the main loop."""
    if _MAIN_LOOP is not None and _MAIN_LOOP.is_running():
        asyncio.run_coroutine_threadsafe(coro, _MAIN_LOOP).result()
    else:
        asyncio.run(coro)  # fallback for local/tests (no running app loop)


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


async def _save_snapshot(entries, *, kind: str = "in_play", market_open: bool = False, stale: bool = False, top_n: int = 30) -> None:
    async with async_session_factory() as s:
        s.add(ScreenerSnapshot(
            kind=kind, market_open=market_open, stale=stale, top_n=top_n,
            entries=[e.to_dict() for e in entries],
        ))
        # prune old snapshots of THIS kind only
        old = (await s.execute(
            select(ScreenerSnapshot.id).where(ScreenerSnapshot.kind == kind)
            .order_by(desc(ScreenerSnapshot.id)).offset(_SNAPSHOT_RETENTION)
        )).scalars().all()
        if old:
            await s.execute(delete(ScreenerSnapshot).where(ScreenerSnapshot.id.in_(old)))
        await s.commit()
    _CACHE.pop(kind, None)  # invalidate this kind's cache


async def _mark_latest_stale(kind: str = "in_play") -> None:
    """Degraded-data path (FR-8): flag the most recent snapshot of a kind as stale."""
    async with async_session_factory() as s:
        latest = (await s.execute(
            select(ScreenerSnapshot).where(ScreenerSnapshot.kind == kind)
            .order_by(desc(ScreenerSnapshot.id)).limit(1)
        )).scalar_one_or_none()
        if latest is not None:
            latest.stale = True
            await s.commit()


async def get_latest_snapshot(kind: str = "in_play") -> ScreenerSnapshot | None:
    """Latest snapshot of a kind, fronted by a short per-kind in-memory cache."""
    now = time.monotonic()
    c = _CACHE.get(kind)
    if c and (now - c["at"]) < _CACHE_TTL_S:
        return c["snap"]
    async with async_session_factory() as s:
        snap = (await s.execute(
            select(ScreenerSnapshot).where(ScreenerSnapshot.kind == kind)
            .order_by(desc(ScreenerSnapshot.id)).limit(1)
        )).scalar_one_or_none()
    _CACHE[kind] = {"snap": snap, "at": now}
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
        # A/B/C grade — same scale as TV alerts: rvol (volume ratio) + intraday VWAP slope.
        from analytics.alert_grade import compute_grade
        vwap_series = (intraday["Close"] * intraday["Volume"]).cumsum() / intraday["Volume"].cumsum()
        slope = (((float(vwap_series.iloc[-1]) - float(vwap_series.iloc[-7])) / float(vwap_series.iloc[-7])) * 100
                 if len(vwap_series) >= 7 and float(vwap_series.iloc[-7]) != 0 else 0.0)
        entry.vwap_slope = slope
        entry.grade = compute_grade(entry.rvol, slope)
    except Exception:
        entry.refine = {}
        entry.direction = "neutral"
        entry.vwap_slope = None
        entry.grade = "C"


def _fetch_most_actives(top: int = 100) -> list[str]:
    """Raw Alpaca most-actives symbols by volume (lazy, Railway-friendly)."""
    try:
        import os
        from alpaca.data.historical.screener import ScreenerClient
        from alpaca.data.requests import MostActivesRequest
        client = ScreenerClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])
        res = client.get_most_actives(MostActivesRequest(top=top))
        return [m.symbol for m in getattr(res, "most_actives", [])]
    except Exception:
        logger.warning("screener: most-actives unavailable", exc_info=True)
        return []


def _most_active_symbols(universe_symbols: set[str]) -> list[str]:
    """Most-actives ∩ universe (in-play prune). Empty → caller falls back."""
    return [s for s in _fetch_most_actives(100) if s in universe_symbols]


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


# ---------------------------------------------------------------------------
# Swing screener — market-wide daily-bar setups. NO market-hours gate: daily
# bars don't change intraday, so setups stay valid all week (incl. weekends).
# ---------------------------------------------------------------------------

def _fetch_daily_consolidated(symbol: str, period: str = "1y"):
    """Daily bars with CONSOLIDATED volume (yfinance) for swing grading.

    The swing A/B/C grade is volume_ratio = today's vol / 20-day avg. Alpaca's
    free ``feed="iex"`` reports only IEX-exchange volume (~2-3% of total, and an
    unstable share day-to-day), so grading off it is noisy — a true 2.2x RVOL
    name (Grade A) collapses to sub-1.3 (Grade C). Swing runs once/day on ~140
    names, low enough frequency that yfinance's consolidated daily bars are safe
    here (unlike intraday polling, which is why Alpaca is primary elsewhere).
    Falls back to the Alpaca path PER SYMBOL only if yfinance fails, so a Yahoo
    hiccup degrades that one grade rather than dropping the name.
    """
    try:
        import yfinance as yf  # lazy
        df = yf.Ticker(symbol).history(period=period, auto_adjust=False)
        if df is not None and not df.empty and "Volume" in df.columns:
            return df[["Open", "High", "Low", "Close", "Volume"]]
    except Exception:
        logger.debug("swing: yfinance daily failed for %s — falling back to Alpaca/IEX",
                     symbol, exc_info=True)
    from analytics.market_data import fetch_ohlc  # lazy fallback (IEX volume)
    return fetch_ohlc(symbol, period)


def _intraday_session_frac() -> float:
    """Fraction of the RTH session elapsed right now (0 before open, 1 after close)."""
    return scr.session_fraction(datetime.now(ET).time())


def _project_volume_to_close(daily, frac: float):
    """Scale the last (forming) bar's volume up to a full-session estimate so the
    swing grade isn't understated when scanning mid-session (e.g. the 3:30 PM run).
    No-op outside market hours (frac 0 or 1) — those bars are already complete."""
    if daily is None or daily.empty or frac <= 0 or frac >= 1:
        return daily
    daily = daily.copy()
    daily.loc[daily.index[-1], "Volume"] = float(daily["Volume"].iloc[-1]) / frac
    return daily


def _gather_swing(intraday: bool = False) -> list[scr.SwingCandidate]:
    """Scan the curated MEGA-CAP list on daily bars (independent of the dynamic
    universe build). Daily bars use CONSOLIDATED volume so the A/B/C grade
    reflects real relative volume, not Alpaca's thin IEX slice. ``intraday=True``
    (the 3:30 PM close run) reads today's forming bar and projects its volume to
    a full-session estimate."""
    frac = _intraday_session_frac() if intraday else 1.0
    spy = _fetch_daily_consolidated("SPY", "1y")
    spy_ret = (((float(spy["Close"].iloc[-1]) / float(spy["Close"].iloc[-21])) - 1) * 100
               if spy is not None and len(spy) > 21 else 0.0)
    cands: list[scr.SwingCandidate] = []
    for u in scr.mega_cap_rows():
        try:
            daily = _fetch_daily_consolidated(u.symbol, "1y")
            if intraday:
                daily = _project_volume_to_close(daily, frac)
            c = scr.swing_signals(daily, spy_ret, symbol=u.symbol, market_cap=u.market_cap, sector=u.sector)
            if c and c.setup:
                cands.append(c)
        except Exception:
            logger.debug("swing: skipped %s", u.symbol, exc_info=True)
    return scr.rank_swing(cands, get_settings().SCREENER_TOP_N)


async def _alert_a_grade(cands: list[scr.SwingCandidate], kind: str, slot: str = "am") -> None:
    """Ping the Telegram group for each NEW A-grade swing setup (once per symbol/day).
    Group-only (constitution); reuses notifier._send_telegram without modifying it.
    Toggle with SWING_ALERTS_ENABLED=false."""
    import os
    if os.environ.get("SWING_ALERTS_ENABLED", "true").strip().lower() in ("false", "0", "no", "off"):
        return
    a_grade = [c for c in cands if c.setup and getattr(c, "grade", "C") == "A"]
    if not a_grade:
        return
    session_date = datetime.now(ET).date().isoformat()
    cap_label = "Small-cap" if kind == "swing_small" else "Mega-cap"
    # Morning (yesterday's settled bar) and close (today's near-final bar) are
    # different signals — dedup them independently so each can fire once per day.
    dedup_kind = f"{kind}:{slot}"[:16]
    slot_label = "into close" if slot == "pm" else "morning"
    try:
        from alerting.notifier import _send_telegram
    except Exception:
        logger.warning("swing alert: notifier unavailable", exc_info=True)
        return
    async with async_session_factory() as s:
        for c in a_grade:
            if await s.get(ScreenerAlertLog, (c.symbol, dedup_kind, session_date)) is not None:
                continue  # already alerted this symbol in this slot today
            st = c.setup
            msg = (
                f"📈 Swing A-setup ({cap_label} · {slot_label}) — {c.symbol} ${c.last_price:.2f}\n"
                f"{st['pattern']} · stop ${st['stop']} / target ${st['target']}\n"
                f"Vol {c.vol_ratio:.1f}x · close {round(c.close_strength * 100)}% · RS {c.rs_vs_spy:+.1f} · busytradersdesk.com"
            )
            try:
                await asyncio.to_thread(_send_telegram, msg)
            except Exception:
                logger.exception("swing alert: send failed for %s", c.symbol)
            s.add(ScreenerAlertLog(symbol=c.symbol, kind=dedup_kind, session_date=session_date))
        await s.commit()
    logger.info("swing alert: %d A-grade %s (%s) setups sent", len(a_grade), kind, slot)


async def refresh_swing(alert: bool = False, slot: str = "am") -> None:
    """Scan mega-caps on daily bars for Trend + MA-defense swing setups; persist.
    Always writes a snapshot (even 0 setups). ``alert=True`` (scheduled runs only)
    pings the group for new A-grade setups. ``slot="pm"`` reads today's forming bar
    (the 3:30 PM close run) and alerts under a separate dedup namespace."""
    try:
        cands = await asyncio.to_thread(_gather_swing, slot == "pm")
        await _save_snapshot(cands, kind="swing", market_open=True, top_n=get_settings().SCREENER_TOP_N)
        if alert:
            await _alert_a_grade(cands, "swing", slot)
        logger.info("swing: snapshot refreshed (%d setups)", len(cands))
    except Exception:
        logger.exception("swing: refresh failed — marking last snapshot stale")
        await _mark_latest_stale("swing")


async def get_latest_swing() -> ScreenerSnapshot | None:
    return await get_latest_snapshot("swing")


async def list_snapshots(kind: str, limit: int = 20) -> list[dict]:
    """Recent runs of a kind (newest first) for the history selector."""
    async with async_session_factory() as s:
        rows = (await s.execute(
            select(ScreenerSnapshot.id, ScreenerSnapshot.captured_at, ScreenerSnapshot.entries)
            .where(ScreenerSnapshot.kind == kind).order_by(desc(ScreenerSnapshot.id)).limit(limit)
        )).all()
    return [{"id": r.id, "captured_at": r.captured_at, "count": len(r.entries or [])} for r in rows]


async def get_snapshot(snapshot_id: int) -> ScreenerSnapshot | None:
    async with async_session_factory() as s:
        return await s.get(ScreenerSnapshot, snapshot_id)


# --- Small-cap / recent-IPO swing (dynamic universe via Alpaca most-actives) ---

_SMALL_PRICE_FLOOR = 2.0           # skip sub-$2 micro-junk
_SMALL_DOLLAR_VOL_FLOOR = 20e6     # liquidity / institutional-interest gate


def _gather_swing_small(intraday: bool = False) -> list[scr.SwingCandidate]:
    """Scan today's most-active NON-mega names defending the 20/50 EMA. Quality-gated
    on price + dollar volume so it surfaces real small-cap momentum, not penny shells.
    ``intraday=True`` reads the forming bar and projects its volume to full-session."""
    # Curated small/mid + recent-IPO pool only. (Alpaca most-actives isn't cap-aware,
    # so it leaks mega caps like GOOG into "small" — dynamic discovery needs a
    # market-cap source, e.g. Polygon/FMP. Tracked as a follow-up.)
    frac = _intraday_session_frac() if intraday else 1.0
    pool = list(scr.SMALL_CAP_UNIVERSE)
    spy = _fetch_daily_consolidated("SPY", "1y")
    spy_ret = (((float(spy["Close"].iloc[-1]) / float(spy["Close"].iloc[-21])) - 1) * 100
               if spy is not None and len(spy) > 21 else 0.0)
    cands: list[scr.SwingCandidate] = []
    for sym in pool[:150]:
        try:
            daily = _fetch_daily_consolidated(sym, "6mo")
            if daily is None or daily.empty or len(daily) < 50:
                continue
            if intraday:
                daily = _project_volume_to_close(daily, frac)
            last = float(daily["Close"].iloc[-1])
            if last < _SMALL_PRICE_FLOOR:
                continue
            if last * float(daily["Volume"].iloc[-1]) < _SMALL_DOLLAR_VOL_FLOOR:
                continue
            c = scr.swing_signals(daily, spy_ret, symbol=sym, small_cap=True)
            if c and c.setup:
                cands.append(c)
        except Exception:
            logger.debug("swing-small: skipped %s", sym, exc_info=True)
    return scr.rank_swing(cands, get_settings().SCREENER_TOP_N)


async def refresh_swing_small(alert: bool = False, slot: str = "am") -> None:
    """Scan small-cap / IPO names for 20/50 EMA-hold setups; persist. ``alert=True``
    (scheduled only) pings the group for new A-grade setups. ``slot="pm"`` reads the
    forming bar (3:30 PM close run) and alerts under a separate dedup namespace."""
    try:
        cands = await asyncio.to_thread(_gather_swing_small, slot == "pm")
        await _save_snapshot(cands, kind="swing_small", market_open=True, top_n=get_settings().SCREENER_TOP_N)
        if alert:
            await _alert_a_grade(cands, "swing_small", slot)
        logger.info("swing-small: snapshot refreshed (%d setups)", len(cands))
    except Exception:
        logger.exception("swing-small: refresh failed")
        await _mark_latest_stale("swing_small")


# Sync wrappers for BackgroundScheduler — run on the app's main loop (where the
# async DB engine lives), NOT a fresh asyncio.run() loop.
def refresh_in_play_job() -> None:
    _run(refresh_in_play())


def rebuild_universe_job() -> None:
    _run(rebuild_universe())


def refresh_swing_job() -> None:
    _run(refresh_swing(alert=True))          # 7:30 AM morning run (yesterday's settled bar)


def refresh_swing_small_job() -> None:
    _run(refresh_swing_small(alert=True))    # 7:40 AM morning run


def refresh_swing_close_job() -> None:
    _run(refresh_swing(alert=True, slot="pm"))        # 3:30 PM run → today's near-final bar


def refresh_swing_small_close_job() -> None:
    _run(refresh_swing_small(alert=True, slot="pm"))  # 3:35 PM run → today's near-final bar


async def bootstrap() -> None:
    """One-shot self-populate on deploy: build the universe if it's empty, then run
    an initial swing scan if no swing snapshot exists yet. Idempotent across restarts
    (skips once the universe/snapshot are present)."""
    try:
        if not await _load_universe():
            logger.info("screener: bootstrap — building universe")
            await rebuild_universe()
        if await get_latest_snapshot("swing") is None:
            logger.info("screener: bootstrap — initial swing scan")
            await refresh_swing()
        if await get_latest_snapshot("swing_small") is None:
            logger.info("screener: bootstrap — initial small-cap swing scan")
            await refresh_swing_small()
        logger.info("screener: bootstrap complete")
    except Exception:
        logger.exception("screener: bootstrap failed")


def bootstrap_job() -> None:
    _run(bootstrap())
