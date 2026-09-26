"""LEAP Desk universe — the names we hunt LEAP entries on.

A LEAP (long-dated ITM call, ~12-24mo) is a stock-replacement bet on a STRONG company
caught deeply oversold. So the universe is two buckets:

  • INDEX ETFs — SPY/QQQ/IWM/… — inherently diversified/quality, so they SKIP the
    per-company fundamentals gate and are treated as elite (you can't have a "broken
    fundamentals" index). An index at a rare oversold is a generational buy.
  • QUALITY STOCKS — large/mega-cap names strong enough to warrant a 1-2yr call. These
    still pass the fundamentals gate (revenue growth, margins, profitability, analyst
    consensus) in leap_scan — the gate is what separates "quality on sale" from a value
    trap that also prints RSI < 30.

Tune with env LEAP_UNIVERSE_CSV (comma-separated) to override the stock list entirely;
the index set always stays in. Fundamentals come from the symbol_fundamentals table
(nightly Finnhub refresh) — a name with no fundamentals row is scored as "warming".
"""
from __future__ import annotations

import os

# Broad index / index-style ETFs — always LEAP-eligible, no fundamentals gate.
INDEX_ETFS: set[str] = {"SPY", "QQQ", "IWM", "DIA", "MDY", "RSP"}

# Curated quality large/mega-caps — the "strong company" bucket (still gated on fundamentals).
_DEFAULT_STOCKS: set[str] = {
    # Mega-cap tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "AVGO", "ORCL", "NFLX", "ADBE",
    "CRM", "AMD", "QCOM", "TXN", "CSCO", "INTU", "NOW", "IBM",
    # Semis / AI infrastructure
    "LRCX", "AMAT", "KLAC", "ASML", "MU", "ARM", "ANET", "MRVL", "TSM",
    "PLTR", "CRWD", "PANW", "SNOW", "DDOG", "NET",
    # Consumer / platforms
    "ABNB", "COST", "HD", "NKE", "SBUX", "DIS", "V", "MA", "UBER", "BKNG", "LULU",
    # Healthcare / other quality
    "LLY", "UNH", "ISRG",
}

_csv = os.environ.get("LEAP_UNIVERSE_CSV", "").strip()
_STOCKS: set[str] = (
    {s.strip().upper() for s in _csv.split(",") if s.strip()} if _csv else _DEFAULT_STOCKS
)

UNIVERSE: list[str] = sorted(INDEX_ETFS | _STOCKS)


def is_index(sym: str) -> bool:
    """Index ETFs skip the fundamentals gate and get elite quality treatment."""
    return sym.upper() in INDEX_ETFS
