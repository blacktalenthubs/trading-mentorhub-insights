"""Premium Desk S4 — live put chain for the trade-detail view. READ-ONLY.

The feed (S3) shows an illustrative credit; the detail view needs the REAL quote to
compute contracts, collateral, return on capital and the 30% / 50% exit math. This
fetches the ~30-DTE put chain around the money from the live Robinhood chain (bid / ask
/ mark / delta / IV per strike) so the user picks a strike and sees true numbers.

Never places an order. Fails soft: on any broker error the endpoint returns
{available: false} and the UI falls back to the illustrative estimate.

A tiny per-symbol in-process cache (CACHE_TTL) keeps repeated detail opens from hammering
the broker; option quotes don't move enough intra-minute to matter for sizing.
"""
from __future__ import annotations

import datetime as _dt
import logging
import threading
import time

logger = logging.getLogger(__name__)

CACHE_TTL = 60.0  # seconds
_CACHE: dict[str, tuple[float, dict]] = {}
_LOCK = threading.Lock()

# Keep this many strikes each side of the money — enough to pick a comfortable OTM put.
NEAR = 8


def fetch_put_chain(symbol: str, client=None) -> dict:  # pragma: no cover - network
    """{available, underlying_price, expiration, dte, rows[]} for the ~30-DTE put chain.

    rows: [{strike, bid, ask, mark, delta, iv, theta, oi, volume}] sorted by strike.
    `available` is False (with a `reason`) when the broker is off or the chain is empty.
    """
    sym = symbol.upper()
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(sym)
        if hit and now - hit[0] < CACHE_TTL:
            return hit[1]

    result = _fetch(sym, client)
    with _LOCK:
        _CACHE[sym] = (now, result)
    return result


def _fetch(sym: str, client) -> dict:  # pragma: no cover - network
    from brokers.robinhood import RobinhoodClient, RobinhoodError
    from brokers.robinhood_options import fetch_expirations, fetch_option_greeks
    from analytics.iv_snapshot import _pick_expiration

    try:
        if client is None:
            client = RobinhoodClient()
            client.login()
        exps = fetch_expirations(sym, client=client)
        picked = _pick_expiration(exps, _dt.date.today())
        if picked is None:
            return {"available": False, "reason": "no ~30-DTE expiration", "rows": []}
        expiration, dte = picked
        chain = fetch_option_greeks(sym, expiration, option_type="put", near=NEAR, client=client)
    except RobinhoodError as exc:
        logger.warning("put chain unavailable for %s (%s)", sym, exc)
        return {"available": False, "reason": str(exc), "rows": []}
    except Exception:
        logger.exception("put chain fetch failed for %s", sym)
        return {"available": False, "reason": "fetch failed", "rows": []}

    price = chain.get("underlying_price") or 0.0
    rows = []
    for r in chain.get("rows", []):
        if r.get("strike", 0) <= 0:
            continue
        mark = r.get("mark") or ((r.get("bid", 0) + r.get("ask", 0)) / 2 if r.get("ask") else 0)
        rows.append({
            "strike": round(r["strike"], 2),
            "bid": round(r.get("bid", 0), 2), "ask": round(r.get("ask", 0), 2),
            "mark": round(mark, 2),
            "delta": round(r.get("delta", 0), 3), "iv": round(r.get("iv", 0) * 100, 1),
            "theta": round(r.get("theta", 0), 3),
            "oi": int(r.get("open_interest", 0)), "volume": int(r.get("volume", 0)),
        })
    rows.sort(key=lambda x: x["strike"])
    if not rows:
        return {"available": False, "reason": "empty chain", "rows": []}
    return {"available": True, "underlying_price": round(price, 2),
            "expiration": expiration, "dte": dte, "rows": rows}
