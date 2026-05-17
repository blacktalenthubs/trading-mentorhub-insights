"""V2-minimal config shim.

The original `config.py` (Streamlit-era, ~150 LOC) was deleted as part of
Spec 49. This shim retains only the symbols still consumed by V2-live code:
`db.py` (DB_PATH + admin/watchlist seeds) and `analytics/intel_hub.py`
(MEGA_CAP + categorize_symbol).

- `is_crypto_alert_symbol` was moved to `alert_config.py` in Phase A; this
  shim re-exports it for the small number of V2-live importers that still
  point here (`analytics/market_data.py`, `analytics/market_hours.py`).
  Those importers should be migrated to `from alert_config import ...` in a
  follow-up commit; doing so here would scope-creep this cleanup.

Long-term: consolidate this shim into `alert_config.py`. That refactor is
deferred to a future spec.
"""

from __future__ import annotations

import os

# Re-export from the new home so existing V2 importers keep working.
from alert_config import (  # noqa: F401  (re-export)
    CRYPTO_ALERT_SYMBOLS,
    is_crypto_alert_symbol,
)

# --- DB ---------------------------------------------------------------
# Local-dev SQLite path. Production uses DATABASE_URL → Railway Postgres
# and never touches DB_PATH at runtime.
# Resolve relative to THIS file (the trade-analytics root) so it works
# regardless of where uvicorn / pytest / streamlit was invoked from.
_TA_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(_TA_ROOT, "data", "trades.db"))

# --- Admin seeding (used by db.py at first-boot) -----------------------
DEFAULT_ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
DEFAULT_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me-on-first-login")

# --- Default watchlist -------------------------------------------------
# Seed list for a fresh user account. Operator can override via env var.
DEFAULT_WATCHLIST: tuple[str, ...] = tuple(
    s.strip().upper()
    for s in os.environ.get(
        "DEFAULT_WATCHLIST",
        "SPY,QQQ,AAPL,MSFT,NVDA,TSLA,AMZN,GOOGL,META,AMD",
    ).split(",")
    if s.strip()
)

# --- Symbol categorization (used by intel_hub) --------------------------
# Operator-curated mega-cap list. Adjust as the market evolves.
MEGA_CAP: frozenset[str] = frozenset({
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "TSLA",
    "BRK.B", "AVGO", "LLY", "JPM", "V", "MA", "WMT", "XOM", "UNH", "ORCL",
})


def categorize_symbol(symbol: str) -> str:
    """Coarse market-cap bucket: 'mega_cap' | 'other'.

    The V1 version had finer-grained buckets (large/mid/small/etc.); V2
    only needs the binary "mega vs. not" distinction for intel_hub
    edge-scoring. Restore the full taxonomy here if a future spec needs it.
    """
    if not symbol:
        return "other"
    return "mega_cap" if symbol.upper() in MEGA_CAP else "other"


# --- Trade-import helpers (parsers/) ---------------------------------
# Used by parsers/parser_1099.py + parsers/parser_statement.py for PDF
# tax/brokerage import flows behind the React /trades page.

# Holding period thresholds (calendar days). Used by classify_holding_period
# to bucket realized trades into "day" / "swing" / "position" / "investment".
DAY_TRADE_MAX = 0     # bought + sold same day
SWING_TRADE_MAX = 30  # held ≤ 30 days
# Beyond SWING_TRADE_MAX up to ~365 days = "position"; beyond ~365 = "investment".


def classify_holding_period(days_held: int) -> str:
    """Bucket a holding period in days into a trade-style label.

    Returns one of: 'day', 'swing', 'position', 'investment'.
    """
    if days_held is None or days_held < 0:
        return "day"
    if days_held <= DAY_TRADE_MAX:
        return "day"
    if days_held <= SWING_TRADE_MAX:
        return "swing"
    if days_held <= 365:
        return "position"
    return "investment"


# Crude asset-type heuristics used by the brokerage-statement parsers.
# Option contract descriptions usually contain CALL/PUT and a strike; ETF
# symbols are checked against a small known list before falling through.
_KNOWN_ETFS: frozenset[str] = frozenset({
    "SPY", "QQQ", "DIA", "IWM", "VOO", "VTI", "VEA", "VWO", "AGG", "BND",
    "GLD", "SLV", "USO", "TLT", "HYG", "LQD", "EEM", "EFA", "XLK", "XLF",
    "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "AIQ", "SOXX",
    "ARKK", "ARKW", "TQQQ", "SQQQ", "UPRO", "SPXU",
})


def detect_asset_type(symbol: str, description: str = "") -> str:
    """Coarse asset-type bucket: 'option' | 'etf' | 'stock' | 'crypto' | 'other'.

    Used by trade-import parsers to categorize executed transactions. This
    is a best-effort heuristic; the V1 original may have had a finer
    taxonomy (futures, mutual fund, etc.) — restore from git history if a
    consumer needs more granularity.
    """
    desc = (description or "").upper()
    sym = (symbol or "").upper()
    if not sym:
        return "other"
    # Option contracts almost always say CALL or PUT in the description.
    if " CALL" in desc or " PUT" in desc or "CALL " in desc or "PUT " in desc:
        return "option"
    # yfinance-style crypto tickers end with -USD.
    if sym.endswith("-USD"):
        return "crypto"
    if sym in _KNOWN_ETFS:
        return "etf"
    return "stock"


# --- CUSIP → symbol map (used by parsers/parser_1099.py) ---------------
# The V1 original maintained a hand-curated CUSIP → ticker mapping for
# 1099 imports that surface CUSIPs but not tickers. This shim starts
# empty; the parser will fall back to using whatever symbol field the
# 1099 row exposes. Restore the original dict from git history if you
# need richer CUSIP coverage.
CUSIP_TO_SYMBOL: dict[str, str] = {}


# --- Recurring account allowlist (used by parsers/parser_statement.py) -
# Account numbers (or labels) treated as "recurring" (e.g., the user's
# own brokerage account vs. an external mirror). The V1 original was a
# small operator-curated list; defaulting to empty keeps the parser
# functional but treats everything as non-recurring.
RECURRING_ACCOUNT: frozenset[str] = frozenset(
    s.strip() for s in os.environ.get("RECURRING_ACCOUNT", "").split(",") if s.strip()
)
