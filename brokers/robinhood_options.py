"""Read-only options analytics from Robinhood — chain + greeks, NO execution.

Pure analysis: fetch the option chain for a symbol/expiration with greeks
(delta / theta / gamma / vega / IV) and the quote. This module NEVER places an
order — it only calls read endpoints. It reuses RobinhoodClient's login, so it
rides the same stored session pickle as the daily import.

The installed robin_stocks namespaces options under robin_stocks.robinhood and
exposes find_options_by_expiration(inputSymbols, expirationDate, optionType).
"""
from __future__ import annotations

import logging

from brokers.robinhood import RobinhoodClient, RobinhoodError, _f

logger = logging.getLogger(__name__)


def fetch_option_greeks(
    symbol: str,
    expiration_date: str,
    option_type: str = "both",
    moneyness_pct: float = 0.15,
    client: RobinhoodClient | None = None,
) -> dict:
    """Return {underlying_price, rows} for `symbol` at `expiration_date`.

    Robinhood returns the ENTIRE chain (every strike ever listed), so we fetch
    the live underlying price and keep only strikes within `moneyness_pct` of it
    (default ±15%) — the relevant, near-the-money contracts. 0 = no filter.

    option_type: "call" | "put" | "both". READ-ONLY — no order is ever placed.
    `client` is injectable for tests. Raises RobinhoodError on failure.
    """
    try:
        import robin_stocks.robinhood as rh
    except ImportError as exc:
        raise RobinhoodError("robin_stocks is not installed") from exc

    if client is None:
        client = RobinhoodClient()
        client.login()

    # Live underlying price — the anchor for the moneyness filter.
    price = 0.0
    try:
        lp = rh.get_latest_price([symbol]) or []
        price = _f(lp[0]) if lp else 0.0
    except Exception:
        price = 0.0

    try:
        raw = rh.find_options_by_expiration(
            [symbol], expirationDate=expiration_date, optionType=option_type
        ) or []
    except Exception as exc:
        # Never echo the exception body — it can carry request/session details.
        raise RobinhoodError(f"option chain fetch failed: {type(exc).__name__}") from exc

    rows: list[dict] = []
    for o in raw:
        if not isinstance(o, dict):
            continue
        rows.append({
            "symbol": (o.get("chain_symbol") or symbol).upper(),
            "type": o.get("type") or "",
            "expiration": o.get("expiration_date") or expiration_date,
            "strike": _f(o.get("strike_price")),
            "bid": _f(o.get("bid_price")),
            "ask": _f(o.get("ask_price")),
            "mark": _f(o.get("mark_price") or o.get("adjusted_mark_price")),
            "delta": _f(o.get("delta")),
            "theta": _f(o.get("theta")),
            "gamma": _f(o.get("gamma")),
            "vega": _f(o.get("vega")),
            "iv": _f(o.get("implied_volatility")),
            "volume": _f(o.get("volume")),
            "open_interest": _f(o.get("open_interest")),
        })
    # Keep only strikes near the money (unless disabled or price unknown).
    if price > 0 and moneyness_pct and moneyness_pct > 0:
        lo, hi = price * (1 - moneyness_pct), price * (1 + moneyness_pct)
        rows = [r for r in rows if lo <= r["strike"] <= hi]

    rows.sort(key=lambda r: (r["type"], r["strike"]))
    return {"underlying_price": round(price, 2), "rows": rows}
