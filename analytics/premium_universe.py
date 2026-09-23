"""Premium Desk universe — what the desk scores for selling premium.

Two worlds, one config:
  - DIRECT names (leverage 1×): the mega-cap stocks themselves (GOOGL, AAPL, …) plus
    the broad index ETFs (SPY, QQQ). Sell a cash-secured put straight on the stock — e.g.
    the GOOGL 340 put — no leveraged wrapper.
  - LEVERAGED ETFs (2× / 3×): the single-stock 2× ETFs and the 3× index ETFs. Same theme,
    fatter premium, more risk.

Everything downstream (IV snapshot, scoring, feed) iterates `UNIVERSE`, so adding a name is
a one-line edit here. `leverage` is the direct-vs-leveraged discriminator the UI filters on;
`kind` is a descriptive tag ("stock" | "index" | "single"). We sell options on the ticker in
`etf` (its own chain / IV / RSI); `underlying` is the theme it tracks (the ETF's parent, or
itself for a direct stock).

Extensible by design — the eventual goal is any liquid optionable name; this is the baseline.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    etf: str            # the optionable ticker we sell puts ON (chain + IV live here)
    underlying: str     # the theme it tracks (parent mega-cap, or itself for a direct stock)
    theme: str          # human label for the UI
    leverage: float     # 1.0 = direct; 2.0 / 3.0 = leveraged
    kind: str           # "stock" | "index" | "single"
    issuer: str = ""    # for ETFs: GraniteShares / Direxion / ProShares


# --- Direct mega-cap stocks (leverage 1×) — sell the put on the stock itself ----------
_STOCKS = [
    Instrument("GOOGL", "GOOGL", "Alphabet", 1.0, "stock"),
    Instrument("AAPL", "AAPL", "Apple", 1.0, "stock"),
    Instrument("MSFT", "MSFT", "Microsoft", 1.0, "stock"),
    Instrument("NVDA", "NVDA", "Nvidia", 1.0, "stock"),
    Instrument("AMZN", "AMZN", "Amazon", 1.0, "stock"),
    Instrument("META", "META", "Meta", 1.0, "stock"),
    Instrument("TSLA", "TSLA", "Tesla", 1.0, "stock"),
    Instrument("AVGO", "AVGO", "Broadcom", 1.0, "stock"),
    Instrument("NFLX", "NFLX", "Netflix", 1.0, "stock"),
    Instrument("AMD", "AMD", "AMD", 1.0, "stock"),
    Instrument("QCOM", "QCOM", "Qualcomm", 1.0, "stock"),
    Instrument("CRM", "CRM", "Salesforce", 1.0, "stock"),
    Instrument("ORCL", "ORCL", "Oracle", 1.0, "stock"),
    Instrument("MU", "MU", "Micron", 1.0, "stock"),
    Instrument("PLTR", "PLTR", "Palantir", 1.0, "stock"),
]

# --- Direct broad index ETFs (leverage 1×) — classic CSP underlyings ------------------
_INDEX = [
    Instrument("SPY", "SPX", "S&P 500", 1.0, "index", "State Street"),
    Instrument("QQQ", "NDX", "Nasdaq-100", 1.0, "index", "Invesco"),
]

# --- Single-stock leveraged ETFs (2×) -------------------------------------------------
_SINGLE = [
    Instrument("NVDL", "NVDA", "Nvidia 2×", 2.0, "single", "GraniteShares"),
    Instrument("TSLL", "TSLA", "Tesla 2×", 2.0, "single", "Direxion"),
    Instrument("GGLL", "GOOGL", "Alphabet 2×", 2.0, "single", "Direxion"),
    Instrument("AAPU", "AAPL", "Apple 2×", 2.0, "single", "Direxion"),
    Instrument("MSFU", "MSFT", "Microsoft 2×", 2.0, "single", "Direxion"),
    Instrument("METU", "META", "Meta 2×", 2.0, "single", "Direxion"),
    Instrument("AMZU", "AMZN", "Amazon 2×", 2.0, "single", "Direxion"),
]

# --- Leveraged index ETFs (3×) — deepest, most liquid option chains -------------------
_LEV_INDEX = [
    Instrument("SOXL", "SOX", "Semis 3×", 3.0, "index", "Direxion"),
    Instrument("TQQQ", "QQQ", "Nasdaq-100 3×", 3.0, "index", "ProShares"),
]

UNIVERSE: list[Instrument] = [*_STOCKS, *_INDEX, *_SINGLE, *_LEV_INDEX]

BY_ETF: dict[str, Instrument] = {i.etf: i for i in UNIVERSE}


def etfs() -> list[str]:
    """Every optionable ticker in the STATIC defaults, in config order."""
    return [i.etf for i in UNIVERSE]


symbols = etfs  # clearer alias now that the universe holds stocks too


def get(etf: str) -> Instrument | None:
    return BY_ETF.get(etf.upper())


# --- DB-backed, editable universe -----------------------------------------------------
# The list above is the SEED, not the source of truth. In production the universe lives in
# a `premium_universe` table so names can be added/removed WITHOUT a code deploy (edit the
# rows; an admin UI can come later). load_instruments() is what the scan + IV snapshot
# iterate: it self-seeds the table from the defaults on first run, then reads it, and falls
# back to the static defaults on any DB issue — so tests and local runs (no DATABASE_URL)
# just get the defaults and it's never empty.
_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS premium_universe (
  symbol TEXT PRIMARY KEY, underlying TEXT, theme TEXT, leverage REAL, kind TEXT,
  issuer TEXT, enabled INTEGER DEFAULT 1, added_at TEXT
)
"""


def load_instruments() -> list[Instrument]:
    """The live universe: DB rows if present, else the static defaults. Never raises."""
    import os
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return list(UNIVERSE)
    try:
        import datetime as _dt
        import psycopg2
        conn = psycopg2.connect(dsn, connect_timeout=15)
        cur = conn.cursor()
        cur.execute(_TABLE_DDL)
        cur.execute("SELECT COUNT(*) FROM premium_universe")
        if (cur.fetchone() or [0])[0] == 0:
            # Seed once from the code defaults so there's an editable starting set.
            now = _dt.datetime.utcnow().isoformat()
            for i in UNIVERSE:
                cur.execute(
                    "INSERT INTO premium_universe (symbol, underlying, theme, leverage, kind, issuer, enabled, added_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,1,%s) ON CONFLICT (symbol) DO NOTHING",
                    (i.etf, i.underlying, i.theme, i.leverage, i.kind, i.issuer, now),
                )
            conn.commit()
        cur.execute("SELECT symbol, underlying, theme, leverage, kind, issuer FROM premium_universe WHERE enabled = 1")
        rows = cur.fetchall()
        cur.close(); conn.close()
        if not rows:
            return list(UNIVERSE)
        return [Instrument(r[0], r[1] or r[0], r[2] or r[0], float(r[3] or 1.0), r[4] or "stock", r[5] or "") for r in rows]
    except Exception:
        return list(UNIVERSE)


def load_map() -> dict[str, Instrument]:
    """symbol → Instrument for the live universe (metadata lookup in the scan)."""
    return {i.etf: i for i in load_instruments()}
