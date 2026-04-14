"""Symbol resolver — probe Alpaca for equity vs crypto data to canonicalize user input.

On watchlist add we need to figure out: when a user types "BCH", do they mean
the Chilean bank ADR (equity) or Bitcoin Cash (crypto)? Probe both Alpaca
endpoints, return a structured answer for the router.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Literal, Optional

import requests

logger = logging.getLogger(__name__)

ResolveKind = Literal["equity", "crypto", "ambiguous", "unknown"]


@dataclass
class SymbolOption:
    symbol: str          # canonical form to store (e.g. "BCH" or "BCH-USD")
    kind: str            # "equity" | "crypto"
    display_name: str    # rough human label ("BCH equity" / "BCH-USD crypto")
    last_price: Optional[float] = None


@dataclass
class ResolveResult:
    kind: ResolveKind
    canonical: Optional[str]           # set when kind in ("equity", "crypto")
    options: list[SymbolOption]        # populated on "ambiguous"
    resolved_from: Optional[str] = None  # original user input (if differed from canonical)


def _alpaca_headers() -> Optional[dict[str, str]]:
    key = os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_SECRET_KEY", "")
    if not key or not secret:
        return None
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}


def _probe_equity(symbol: str) -> Optional[float]:
    """Return last close if Alpaca has equity data for the symbol, else None."""
    headers = _alpaca_headers()
    if not headers:
        return None
    try:
        r = requests.get(
            f"https://data.alpaca.markets/v2/stocks/{symbol}/bars/latest",
            headers=headers,
            params={"feed": "iex"},
            timeout=5,
        )
        if r.status_code != 200:
            return None
        bar = r.json().get("bar")
        return float(bar["c"]) if bar else None
    except Exception:
        return None


def _probe_crypto(symbol: str) -> Optional[float]:
    """Return last close if Alpaca crypto has data for `{SYM}/USD`, else None.

    `symbol` is the bare ticker like BCH or BTC (no suffix).
    """
    headers = _alpaca_headers()
    if not headers:
        return None
    alpaca_sym = f"{symbol}/USD"
    try:
        r = requests.get(
            "https://data.alpaca.markets/v1beta3/crypto/us/latest/bars",
            headers=headers,
            params={"symbols": alpaca_sym},
            timeout=5,
        )
        if r.status_code != 200:
            return None
        bar = r.json().get("bars", {}).get(alpaca_sym)
        return float(bar["c"]) if bar else None
    except Exception:
        return None


def resolve_symbol(user_input: str) -> ResolveResult:
    """Resolve a user-entered symbol to the canonical form.

    Probes Alpaca equity and crypto endpoints. Rules:
    - If user input already ends with "-USD", only probe crypto (assume intent).
    - Otherwise, probe both and report.
    """
    raw = user_input.upper().strip()
    if not raw:
        return ResolveResult(kind="unknown", canonical=None, options=[])

    # Explicit crypto suffix — skip equity probe
    if raw.endswith("-USD"):
        bare = raw.replace("-USD", "")
        crypto_price = _probe_crypto(bare)
        if crypto_price is not None:
            return ResolveResult(
                kind="crypto",
                canonical=raw,
                options=[],
                resolved_from=raw,
            )
        return ResolveResult(kind="unknown", canonical=None, options=[])

    # Probe both
    equity_price = _probe_equity(raw)
    crypto_price = _probe_crypto(raw)

    equity_opt = (
        SymbolOption(symbol=raw, kind="equity",
                     display_name=f"{raw} (equity)", last_price=equity_price)
        if equity_price is not None else None
    )
    crypto_opt = (
        SymbolOption(symbol=f"{raw}-USD", kind="crypto",
                     display_name=f"{raw}-USD (crypto)", last_price=crypto_price)
        if crypto_price is not None else None
    )

    if equity_opt and crypto_opt:
        return ResolveResult(
            kind="ambiguous",
            canonical=None,
            options=[crypto_opt, equity_opt],  # crypto first (more common intent)
            resolved_from=raw,
        )
    if crypto_opt:
        return ResolveResult(
            kind="crypto",
            canonical=f"{raw}-USD",
            options=[],
            resolved_from=raw,
        )
    if equity_opt:
        return ResolveResult(
            kind="equity",
            canonical=raw,
            options=[],
            resolved_from=raw,
        )

    return ResolveResult(kind="unknown", canonical=None, options=[])
