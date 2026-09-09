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
    client: RobinhoodClient | None = None,
) -> list[dict]:
    """Return option rows (strike, greeks, quote) for `symbol` at `expiration_date`.

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
    rows.sort(key=lambda r: (r["type"], r["strike"]))
    return rows
