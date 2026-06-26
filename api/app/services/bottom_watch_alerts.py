"""Global Bottom-Watch level alerts — push an in-app notification to ALL users when a
notable name hits a critical daily level:

  • reclaim_30  — daily RSI crossed back ABOVE 30 (the oversold turn → long-term entry)
  • oversold_30 — daily RSI crossed BELOW 30 (washed out; watch for the reclaim)
  • at_200ma    — pulled back to the 200-day MA while weak (institutional dip-buy floor)

This is a GLOBAL market signal, not per-user: the universe is the union of every
watchlist symbol, and the push goes to every registered device. Runs from the API's
BackgroundScheduler (which already has the data fetch + the APNs push), so it never
touches the triage worker. Deduped once per symbol/event/session-day via the cache.
RTH-only. Never raises — it's a background job.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import text

from app.cache import cache_get, cache_set
from app.services.push_service import send_push_sync

logger = logging.getLogger(__name__)

_UNIVERSE_MAX = 150
_DEDUP_TTL = 72_000   # ~20h — one push per symbol/event/session day
_CLOSES_TTL = 1_500   # 25 min — share the daily-close fetch across the scan


def _rsi_and_levels(closes: list[float]):
    """(rsi, rsi_prev, near_200) from a list of daily closes, or None if not computable."""
    import pandas as pd
    s = pd.Series(closes, dtype="float64")
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(com=13, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(com=13, min_periods=14).mean()
    rsi_series = 100 - 100 / (1 + gain / loss)
    rsi = float(rsi_series.iloc[-1])
    if rsi != rsi:  # NaN
        return None
    rsi_prev = (float(rsi_series.iloc[-2])
                if len(rsi_series) >= 2 and rsi_series.iloc[-2] == rsi_series.iloc[-2] else None)
    close = float(s.iloc[-1])
    ema200 = float(s.ewm(span=200, adjust=False).mean().iloc[-1]) if len(s) >= 200 else None
    near_200 = ema200 is not None and abs(close - ema200) / ema200 <= 0.02
    return rsi, rsi_prev, near_200


def _events(sym: str, rsi: float, rsi_prev, near_200: bool):
    """The critical-level events to push for this symbol (event_key, title, body)."""
    out = []
    if rsi_prev is not None and rsi_prev < 30 <= rsi:
        out.append(("reclaim_30", f"📈 {sym} reclaimed 30 RSI",
                    f"Oversold turn — long-term entry zone (RSI {rsi:.0f})."))
    elif rsi_prev is not None and rsi_prev >= 30 > rsi:
        out.append(("oversold_30", f"⚠️ {sym} is oversold (RSI {rsi:.0f})",
                    "Washed out — watch for the 30 reclaim."))
    if near_200 and rsi < 45:
        out.append(("at_200ma", f"🎯 {sym} at its 200-day MA",
                    f"Institutional floor + weak (RSI {rsi:.0f}) — dip-buy zone."))
    return out


def scan_bottom_watch(sync_session_factory) -> None:
    """RTH-only global scan → in-app push on a new critical level. Never raises."""
    try:
        from analytics.market_hours import is_market_hours
        if not is_market_hours():
            return
        from app.routers.market import _fetch_daily_closes

        session_date = datetime.utcnow().strftime("%Y-%m-%d")
        with sync_session_factory() as db:
            symbols = [r[0].upper() for r in db.execute(
                text("SELECT DISTINCT symbol FROM watchlist")).all()][:_UNIVERSE_MAX]
            tokens = [r[0] for r in db.execute(text(
                "SELECT token FROM device_tokens WHERE platform = 'ios' AND token IS NOT NULL "
                "UNION SELECT apns_token FROM users WHERE apns_enabled = true "
                "AND apns_token IS NOT NULL AND apns_token <> ''")).all() if r[0]]
        if not symbols or not tokens:
            return

        fired = 0
        for sym in symbols:
            try:
                ck = f"bw_closes:{sym}"
                closes = cache_get(ck)
                if closes is None:
                    closes = _fetch_daily_closes(sym, sym.endswith("-USD"))
                    cache_set(ck, closes, _CLOSES_TTL)
                if not closes or len(closes) < 30:
                    continue
                rl = _rsi_and_levels(closes)
                if rl is None:
                    continue
                rsi, rsi_prev, near_200 = rl
                for ev, title, body in _events(sym, rsi, rsi_prev, near_200):
                    dk = f"bw_fired:{sym}:{ev}:{session_date}"
                    if cache_get(dk):
                        continue
                    cache_set(dk, True, _DEDUP_TTL)
                    send_push_sync(tokens, title, body,
                                   data={"symbol": sym, "kind": "bottom_watch", "event": ev},
                                   thread_id="bottom_watch")
                    fired += 1
            except Exception:
                continue
        if fired:
            logger.info("bottom-watch: pushed %d level alert(s) to %d device(s)", fired, len(tokens))
    except Exception:
        logger.exception("bottom-watch scan failed")
