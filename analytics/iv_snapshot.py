"""IV-history snapshot — the foundation of the Premium Desk's IV Rank.

IV Rank = where today's implied vol sits inside its own 1-year range:
    (IV_today - IV_52w_low) / (IV_52w_high - IV_52w_low) * 100
High rank = options are expensive relative to this name's own history = a better
moment to SELL premium. The range is what matters, and the range only exists if
we've been recording IV every day — so this job is clock-sensitive: it must start
accumulating history now, and the rank label grows with the window (IVR·30d →
IVR·90d → IVR·1y) until a full 252-session range exists.

What it records, once per weekday, at a CONSISTENT time (IV drifts intraday, but
the daily range is stable — a fixed snapshot time keeps the series comparable):
for each Premium Desk ETF, the ATM implied vol of the option nearest ~30 DTE.
Source is the live Robinhood option chain (brokers/robinhood_options — READ ONLY,
never places an order); charts/Pine can't give real option IV, the broker can.

Stores one row per (symbol, session_date) in `iv_history`. `iv_rank()` computes
the rank + percentile over the rolling window with its sample size, so the UI can
honestly label how much history backs the number.

CLI: `python3 -m analytics.iv_snapshot [--publish] [SYM ...]`  (default: full universe)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics import premium_universe  # noqa: E402

logger = logging.getLogger(__name__)

# Target the option roughly one month out — the sweet spot for premium selling
# (enough theta, past the near-week gamma). Accept anything in the window and pick
# the closest to the target; never pick something expiring inside a few days.
TARGET_DTE = 30
MIN_DTE = 10
MAX_DTE = 55

# Rolling window for the rank. A true "52-week" rank is 252 trading days; until we
# have that many rows the rank is computed over whatever exists and labeled with n.
RANK_WINDOW = 252


def _dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is required for IV snapshot (Postgres history store)")
    return dsn


def _ensure_table(cur) -> None:
    # Self-creating, idempotent — same pattern as etf_finders/market_reports so the
    # job runs standalone with just DATABASE_URL, no migration step.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS iv_history (
            symbol TEXT NOT NULL,
            session_date TEXT NOT NULL,
            atm_iv REAL NOT NULL,
            underlying_price REAL,
            strike REAL,
            expiration TEXT,
            dte INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (symbol, session_date)
        )
    """)


def _pick_expiration(exps: list[str], today: _dt.date) -> tuple[str, int] | None:
    """Nearest listed expiration to TARGET_DTE within [MIN_DTE, MAX_DTE]."""
    best = None
    for e in exps:
        try:
            d = (_dt.date.fromisoformat(e) - today).days
        except ValueError:
            continue
        if d < MIN_DTE or d > MAX_DTE:
            continue
        score = abs(d - TARGET_DTE)
        if best is None or score < best[0]:
            best = (score, e, d)
    if best is None:
        return None
    return best[1], best[2]


def snapshot_symbol(etf: str, client=None, today: _dt.date | None = None) -> dict | None:
    """Return {symbol, atm_iv, underlying_price, strike, expiration, dte} or None.

    ATM IV = the implied vol at the strike closest to the underlying price. We read
    the CALL side (Robinhood's endpoint 400s on type="both"; ATM call IV is the
    standard IV-rank proxy and tracks the ATM put within a fraction of a vol point).
    READ-ONLY.
    """  # pragma: no cover - network
    from brokers.robinhood import RobinhoodError
    from brokers.robinhood_options import fetch_expirations, fetch_option_greeks

    today = today or _dt.date.today()
    try:
        exps = fetch_expirations(etf, client=client)
    except RobinhoodError as exc:
        logger.warning("IV snapshot: no expirations for %s (%s)", etf, exc)
        return None
    picked = _pick_expiration(exps, today)
    if picked is None:
        logger.warning("IV snapshot: no ~%dDTE expiration for %s in %s..%s", TARGET_DTE, etf, MIN_DTE, MAX_DTE)
        return None
    expiration, dte = picked

    try:
        chain = fetch_option_greeks(etf, expiration, option_type="call", near=3, client=client)
    except RobinhoodError as exc:
        logger.warning("IV snapshot: chain fetch failed for %s (%s)", etf, exc)
        return None

    price = chain.get("underlying_price") or 0.0
    rows = [r for r in chain.get("rows", []) if r.get("iv", 0) > 0 and r.get("strike", 0) > 0]
    if not rows or price <= 0:
        logger.warning("IV snapshot: no priced IV rows for %s", etf)
        return None

    # Strike closest to the money → its call IV.
    atm = min(rows, key=lambda r: abs(r["strike"] - price))
    atm_strike = atm["strike"]
    atm_iv = round(atm["iv"] * 100, 2)  # robin_stocks IV is a fraction → %

    return {
        "symbol": etf.upper(), "atm_iv": atm_iv, "underlying_price": round(price, 2),
        "strike": round(atm_strike, 2), "expiration": expiration, "dte": dte,
    }


def store(snaps: list[dict], session_date: str) -> None:  # pragma: no cover - DB
    import psycopg2
    conn = psycopg2.connect(_dsn(), connect_timeout=15)
    cur = conn.cursor()
    _ensure_table(cur)
    for s in snaps:
        cur.execute(
            """INSERT INTO iv_history
                 (symbol, session_date, atm_iv, underlying_price, strike, expiration, dte)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (symbol, session_date) DO UPDATE SET
                 atm_iv = EXCLUDED.atm_iv, underlying_price = EXCLUDED.underlying_price,
                 strike = EXCLUDED.strike, expiration = EXCLUDED.expiration,
                 dte = EXCLUDED.dte, created_at = NOW()""",
            (s["symbol"], session_date, s["atm_iv"], s["underlying_price"],
             s["strike"], s["expiration"], s["dte"]),
        )
    conn.commit(); cur.close(); conn.close()


def iv_rank(symbol: str, window: int = RANK_WINDOW) -> dict | None:  # pragma: no cover - DB
    """Rank + percentile of the latest IV within the trailing `window` sessions.

    Returns {symbol, iv, rank, percentile, n, low, high} or None if no history.
    `rank`  = position of latest IV in [low, high] (0..100).
    `percentile` = share of prior sessions with IV <= latest (0..100).
    `n` = sessions in the window (label the UI honestly: "IVR·<n>d").
    """
    import psycopg2
    conn = psycopg2.connect(_dsn(), connect_timeout=15)
    cur = conn.cursor()
    _ensure_table(cur)
    cur.execute(
        "SELECT atm_iv FROM iv_history WHERE symbol = %s ORDER BY session_date DESC LIMIT %s",
        (symbol.upper(), window),
    )
    vals = [float(r[0]) for r in cur.fetchall() if r[0] is not None]
    cur.close(); conn.close()
    if not vals:
        return None
    cur_iv = vals[0]
    lo, hi = min(vals), max(vals)
    rank = 0.0 if hi <= lo else round((cur_iv - lo) / (hi - lo) * 100, 1)
    pct = round(sum(1 for v in vals if v <= cur_iv) / len(vals) * 100, 1)
    return {"symbol": symbol.upper(), "iv": cur_iv, "rank": rank,
            "percentile": pct, "n": len(vals), "low": round(lo, 2), "high": round(hi, 2)}


def run(etfs: list[str] | None = None, publish: bool = False) -> dict:  # pragma: no cover - network
    from brokers.robinhood import RobinhoodClient
    etfs = etfs or [i.etf for i in premium_universe.load_instruments()]
    today = _dt.date.today()
    date = today.isoformat()
    client = RobinhoodClient()
    client.login()

    snaps: list[dict] = []
    for etf in etfs:
        try:
            s = snapshot_symbol(etf, client=client, today=today)
            if s:
                snaps.append(s)
        except Exception:
            logger.exception("IV snapshot failed for %s", etf)

    if snaps:
        store(snaps, date)

    rep = {"date": date, "count": len(snaps), "rows": snaps}
    if publish and snaps:
        _publish_summary(rep, date)
    return rep


def _publish_summary(rep: dict, date: str) -> None:  # pragma: no cover - DB
    """Mirror the day's snapshot (with live rank) to market_reports for visibility."""
    import psycopg2
    body = dict(rep)
    body["ranks"] = [iv_rank(s["symbol"]) for s in rep["rows"]]
    conn = psycopg2.connect(_dsn(), connect_timeout=15)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS market_reports (
        kind TEXT NOT NULL, session_date TEXT NOT NULL, body TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(), PRIMARY KEY (kind, session_date))""")
    cur.execute(
        "INSERT INTO market_reports (kind, session_date, body) VALUES ('iv_snapshot', %s, %s) "
        "ON CONFLICT (kind, session_date) DO UPDATE SET body = EXCLUDED.body, created_at = NOW()",
        (date, json.dumps(body)),
    )
    conn.commit(); cur.close(); conn.close()


def main():  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Daily ATM ~30-DTE IV snapshot for the Premium Desk universe")
    ap.add_argument("symbols", nargs="*", help="ETF tickers (default: full universe)")
    ap.add_argument("--publish", action="store_true", help="also mirror to market_reports[iv_snapshot]")
    ap.add_argument("--rank", action="store_true", help="print current IV rank per symbol and exit (no snapshot)")
    args = ap.parse_args()
    syms = [s.upper() for s in args.symbols] or premium_universe.etfs()

    if args.rank:
        for s in syms:
            r = iv_rank(s)
            print(f"  {s:<6} " + ("no history" if not r else
                  f"IV {r['iv']:>6.2f}%  rank {r['rank']:>5.1f}  pct {r['percentile']:>5.1f}  "
                  f"[{r['low']}-{r['high']}]  n={r['n']}"))
        return

    rep = run(syms, publish=args.publish)
    print(f"\n=== IV SNAPSHOT {rep['date']} === {rep['count']}/{len(syms)} captured\n")
    for s in rep["rows"]:
        print(f"  {s['symbol']:<6} IV {s['atm_iv']:>6.2f}%  ${s['underlying_price']:>8.2f}  "
              f"strike {s['strike']:>8.2f}  exp {s['expiration']} ({s['dte']}d)")
    if not rep["rows"]:
        print("  (nothing captured — check Robinhood session / chain availability)")


if __name__ == "__main__":
    main()
