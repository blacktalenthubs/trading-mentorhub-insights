"""LEAP Desk — live long-dated CALL chain + strike recommendation. READ-ONLY.

The scan suggests heuristic strikes (an ITM ~0.8Δ stock-replacement and a target at the
nearest overhead resistance). This turns those into REAL, tradeable strikes: it pulls the
~18-month call chain from the live Robinhood chain (same path as the premium put chain),
then recommends the actual listed strikes to buy — filtered by LIQUIDITY (open interest,
volume, bid/ask spread) and delta, so you never get pointed at a strike with no market.

  • ITM pick    — the liquid strike with delta nearest ~0.80 (stock replacement).
  • TARGET pick — the liquid strike nearest the scan's target price (overhead resistance).

Never places an order. Fails soft: on any broker error returns {available:false} and the
UI falls back to the heuristic strikes. Tiny per-(symbol,target) cache like premium_chain.
"""
from __future__ import annotations

import datetime as _dt
import logging
import threading
import time

logger = logging.getLogger(__name__)

CACHE_TTL = 120.0
_CACHE: dict[str, tuple[float, dict]] = {}
_LOCK = threading.Lock()

LEAP_DTE = 540            # ~18-month target
MIN_LEAP_DTE = 300       # a real LEAP is ≥ ~10mo out; below this it isn't one
MIN_OI = 50              # open interest at/above this = a real market
MAX_SPREAD_PCT = 20.0    # bid/ask spread as % of mark — wider = illiquid
ITM_DELTA = 0.80         # stock-replacement target delta
MONEYNESS = 0.30         # pull strikes within ±30% of price (ITM through OTM target)


def _pick_leap_expiration(exps: list[str], today: _dt.date):
    """The listed expiration closest to ~18mo out, preferring real LEAPs (≥ MIN_LEAP_DTE).
    Falls back to the longest-dated expiration when nothing reaches the LEAP window."""
    dated = []
    for e in exps or []:
        try:
            d = (_dt.date.fromisoformat(e) - today).days
        except Exception:
            continue
        if d > 0:
            dated.append((e, d))
    if not dated:
        return None
    leaps = [x for x in dated if x[1] >= MIN_LEAP_DTE]
    if leaps:
        return min(leaps, key=lambda x: abs(x[1] - LEAP_DTE))
    return max(dated, key=lambda x: x[1])   # longest available


def fetch_leap_chain(symbol: str, target: float | None = None, client=None) -> dict:  # pragma: no cover - network
    sym = symbol.upper()
    key = f"{sym}:{round(target or 0, 2)}"
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < CACHE_TTL:
            return hit[1]
    result = _fetch(sym, target, client)
    with _LOCK:
        _CACHE[key] = (now, result)
    return result


def _spread_pct(bid, ask, mark):
    if not mark or mark <= 0 or not ask or ask <= 0:
        return None
    return round((ask - bid) / mark * 100.0, 1)


def _liquid(r):
    return r["open_interest"] >= MIN_OI and r["ask"] > 0 and (r["spread_pct"] is None or r["spread_pct"] <= MAX_SPREAD_PCT)


def _fetch(sym: str, target, client) -> dict:  # pragma: no cover - network
    from brokers.robinhood import RobinhoodClient, RobinhoodError
    from brokers.robinhood_options import fetch_expirations, fetch_option_greeks

    try:
        if client is None:
            client = RobinhoodClient()
            client.login()
        exps = fetch_expirations(sym, client=client)
        picked = _pick_leap_expiration(exps, _dt.date.today())
        if picked is None:
            return {"available": False, "reason": "no LEAP-dated expiration", "rows": []}
        expiration, dte = picked
        chain = fetch_option_greeks(sym, expiration, option_type="call", moneyness_pct=MONEYNESS, client=client)
    except RobinhoodError as exc:
        logger.warning("leap chain unavailable for %s (%s)", sym, exc)
        return {"available": False, "reason": str(exc), "rows": []}
    except Exception:
        logger.exception("leap chain fetch failed for %s", sym)
        return {"available": False, "reason": "fetch failed", "rows": []}

    price = chain.get("underlying_price") or 0.0
    rows = []
    for r in chain.get("rows", []):
        strike = r.get("strike", 0)
        if strike <= 0:
            continue
        bid, ask = r.get("bid", 0), r.get("ask", 0)
        mark = r.get("mark") or ((bid + ask) / 2 if ask else 0)
        rows.append({
            "strike": round(strike, 2), "bid": round(bid, 2), "ask": round(ask, 2),
            "mark": round(mark, 2), "delta": round(r.get("delta", 0), 3),
            "iv": round(r.get("iv", 0), 3), "volume": int(r.get("volume", 0) or 0),
            "open_interest": int(r.get("open_interest", 0) or 0),
            "spread_pct": _spread_pct(bid, ask, mark),
        })
    rows.sort(key=lambda r: r["strike"])
    for r in rows:
        r["liquid"] = _liquid(r)
    if not rows:
        return {"available": False, "reason": "empty chain", "rows": []}

    liquid = [r for r in rows if r["liquid"]] or rows   # if nothing clears the bar, rank on all

    # ITM pick — delta nearest ~0.80 among liquid ITM-ish strikes.
    itm_pool = [r for r in liquid if 0.6 <= r["delta"] <= 0.92] or liquid
    itm = min(itm_pool, key=lambda r: abs(r["delta"] - ITM_DELTA)) if itm_pool else None
    # Target pick — liquid strike nearest the scan's target price.
    tgt = None
    if target and target > 0:
        tgt = min(liquid, key=lambda r: abs(r["strike"] - target))

    return {
        "available": True, "symbol": sym, "underlying_price": round(price, 2),
        "expiration": expiration, "dte": dte,
        "recommend": {"itm": itm, "target": tgt},
        "rows": rows,
    }
