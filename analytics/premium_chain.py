"""Premium Desk S4 — live put chain for the trade-detail view. READ-ONLY.

The feed (S3) shows an illustrative credit; the detail view needs the REAL quote to
compute contracts, collateral, return on capital and the 30% / 50% exit math. This
fetches the ~30-DTE put chain around the money (bid / ask / mark / delta / IV per strike)
so the user picks a strike and sees true numbers.

Data source: ALPACA primary (2026-10-03) — an API-key feed with no expiring session, so
the chain stays FRESH without the periodic Robinhood re-mint. Falls back to Robinhood only
if Alpaca is unavailable (keys unset / plan without options) and a Robinhood session exists.
Never places an order. Fails soft: on any error the endpoint returns {available: false} and
the UI falls back to the illustrative estimate.

A tiny per-symbol in-process cache (CACHE_TTL) keeps repeated detail opens from hammering
the source; option quotes don't move enough intra-minute to matter for sizing.
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

CACHE_TTL = 60.0  # seconds
_CACHE: dict[str, tuple[float, dict]] = {}
_LOCK = threading.Lock()

# Keep this many strikes each side of the money — enough to pick a comfortable OTM put.
NEAR = 8
# The Premium Desk sells ~30 DTE, but we request a WIDE expiration band and then pick the
# expiration nearest DTE_TARGET. A tight 21-45 band missed monthly-only ETFs (e.g. on Oct 3 the
# nearest AMZU expirations were ~14d and ~49d — both outside 21-45 → empty chain). 7-70 catches
# weeklies and the surrounding monthlies so there's always something to pick from.
DTE_TARGET = 30
DTE_LO = 7
DTE_HI = 70


def fetch_put_chain(symbol: str, client=None) -> dict:  # pragma: no cover - network
    """{available, underlying_price, expiration, dte, rows[], source} for the ~30-DTE put chain.

    rows: [{strike, bid, ask, mark, delta, iv, theta, oi, volume}] sorted by strike.
    `available` is False (with a `reason`) when no source is reachable or the chain is empty.
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
    """Alpaca first (durable key, always fresh); Robinhood only as a fallback."""
    res = _fetch_alpaca(sym)
    if res.get("available"):
        return res
    rh = _fetch_robinhood(sym, client)
    if rh.get("available"):
        return rh
    # Neither worked — surface the more informative reason. Prefer Alpaca's unless it is
    # merely "keys not set" (then the Robinhood reason is the one the operator should see).
    if res.get("reason") and "keys not set" not in res.get("reason", ""):
        return res
    return rh if rh.get("reason") else res


# ─────────────────────────────────────────────────────────────────────────────
# Alpaca (primary) — API key, no session expiry.
# ─────────────────────────────────────────────────────────────────────────────

def _occ_parse(occ: str):
    """Parse an OCC option symbol → (expiration_iso, type 'P'/'C', strike). None if malformed.

    OCC = <root><YYMMDD><C|P><strike*1000, 8 digits>. The last 15 chars are fixed-width, so
    the variable-length root doesn't matter.
    """
    try:
        s = (occ or "").strip()
        if len(s) < 15:
            return None
        tail = s[-15:]
        yy, mm, dd = tail[0:2], tail[2:4], tail[4:6]
        otype = tail[6]
        strike = int(tail[7:15]) / 1000.0
        return (f"20{yy}-{mm}-{dd}", otype, strike)
    except Exception:
        return None


def _underlying_price(sym: str, key: str, secret: str) -> float:
    """Live underlying price — Alpaca latest trade, falling back to the last daily close."""
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockLatestTradeRequest
        c = StockHistoricalDataClient(api_key=key, secret_key=secret)
        t = c.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=sym))
        px = float(getattr(t[sym], "price", 0) or 0)
        if px > 0:
            return px
    except Exception:
        pass
    try:
        from analytics.market_data import fetch_ohlc
        df = fetch_ohlc(sym, period="5d", interval="1d")
        if df is not None and not df.empty:
            return float(df["Close"].iloc[-1])
    except Exception:
        pass
    return 0.0


def _fetch_alpaca(sym: str) -> dict:  # pragma: no cover - network
    key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not secret:
        return {"available": False, "reason": "alpaca keys not set", "rows": []}
    try:
        from alpaca.data.historical.option import OptionHistoricalDataClient
        from alpaca.data.requests import OptionChainRequest
        from alpaca.trading.enums import ContractType
        _feed = None
        try:
            from alpaca.data.enums import OptionsFeed
            _feed = (OptionsFeed.OPRA if os.environ.get("ALPACA_OPTIONS_FEED", "").lower() == "opra"
                     else OptionsFeed.INDICATIVE)
        except Exception:
            _feed = None

        price = _underlying_price(sym, key, secret)
        if price <= 0:
            return {"available": False, "reason": "no underlying price", "rows": []}

        today = _dt.date.today()
        req = OptionChainRequest(
            underlying_symbol=sym,
            feed=_feed,
            type=ContractType.PUT,
            strike_price_gte=round(price * 0.75, 2),
            strike_price_lte=round(price * 1.05, 2),
            expiration_date_gte=today + _dt.timedelta(days=DTE_LO),
            expiration_date_lte=today + _dt.timedelta(days=DTE_HI),
        )
        oc = OptionHistoricalDataClient(api_key=key, secret_key=secret)
        chain = oc.get_option_chain(req)
    except Exception as exc:
        logger.warning("alpaca put chain unavailable for %s (%s)", sym, exc)
        return {"available": False, "reason": f"alpaca: {exc}", "rows": []}

    raw = chain if isinstance(chain, dict) else (getattr(chain, "data", {}) or {})
    return _build_from_chain(raw, price)


def _build_from_chain(raw: dict, price: float, today: "_dt.date | None" = None) -> dict:
    """Pure: group Alpaca put snapshots by expiration, pick the ~30-DTE one, build sized rows.

    Separated from the network call so the parsing is unit-testable against fake snapshots.
    """
    today = today or _dt.date.today()
    n_raw = len(raw or {})
    by_exp: dict[str, list] = {}
    for occ, snap in (raw or {}).items():
        parsed = _occ_parse(occ)
        if parsed is None:
            continue
        exp, otype, strike = parsed
        if otype != "P" or strike <= 0:
            continue
        by_exp.setdefault(exp, []).append((strike, snap))
    if not by_exp:
        # Distinguish a window miss (contracts came back but no usable puts) from genuine
        # no-coverage (0 contracts) so the UI message tells us which it is.
        reason = "empty chain" if n_raw == 0 else f"no ~30d puts ({n_raw} contracts in window)"
        return {"available": False, "reason": reason, "rows": []}

    def _dte(exp_iso: str) -> int:
        try:
            y, m, d = int(exp_iso[0:4]), int(exp_iso[5:7]), int(exp_iso[8:10])
            return (_dt.date(y, m, d) - today).days
        except Exception:
            return 10_000

    best_exp = min(by_exp.keys(), key=lambda e: abs(_dte(e) - DTE_TARGET))
    dte = _dte(best_exp)

    rows = []
    for strike, snap in by_exp[best_exp]:
        q = getattr(snap, "latest_quote", None)
        g = getattr(snap, "greeks", None)
        bid = float(getattr(q, "bid_price", 0) or 0) if q else 0.0
        ask = float(getattr(q, "ask_price", 0) or 0) if q else 0.0
        mark = (bid + ask) / 2 if ask else bid
        delta = float(getattr(g, "delta", 0) or 0) if g else 0.0
        theta = float(getattr(g, "theta", 0) or 0) if g else 0.0
        iv = float(getattr(snap, "implied_volatility", 0) or 0)
        rows.append({
            "strike": round(strike, 2),
            "bid": round(bid, 2), "ask": round(ask, 2), "mark": round(mark, 2),
            "delta": round(delta, 3), "iv": round(iv * 100, 1), "theta": round(theta, 3),
            # Alpaca option snapshots carry no OI / daily volume — left 0 (quotes + greeks
            # drive the sizing; liquidity is still visible as the bid/ask spread).
            "oi": 0, "volume": 0,
        })
    rows.sort(key=lambda x: x["strike"])
    # Trim to NEAR strikes each side of the money so the detail list stays tight.
    if len(rows) > 2 * NEAR + 1 and price > 0:
        nidx = min(range(len(rows)), key=lambda i: abs(rows[i]["strike"] - price))
        rows = rows[max(0, nidx - NEAR):nidx + NEAR + 1]
    if not rows:
        return {"available": False, "reason": "empty chain", "rows": []}
    return {"available": True, "underlying_price": round(price, 2),
            "expiration": best_exp, "dte": dte, "rows": rows, "source": "alpaca"}


# ─────────────────────────────────────────────────────────────────────────────
# Robinhood (fallback) — only used if Alpaca is unavailable and a session exists.
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_robinhood(sym: str, client) -> dict:  # pragma: no cover - network
    from brokers.robinhood import RobinhoodError
    from brokers.robinhood_options import fetch_expirations, fetch_option_greeks
    from analytics.iv_snapshot import _pick_expiration

    try:
        if client is None:
            from brokers.robinhood import RobinhoodClient
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
            "expiration": expiration, "dte": dte, "rows": rows, "source": "robinhood"}
