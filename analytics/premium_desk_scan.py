"""Premium Desk scan (S2 rails) — score the universe, publish the ranked feed.

Standalone job, same shape as support_scan / volume_signal_scan: for each ETF in the
premium universe, pull daily + weekly bars, read its IV rank from iv_history, run the
S2 scoring engine, and publish the ranked candidates to market_reports(kind='premium_desk')
for the S3 feed to render.

Reads the freshest available iv_history row (today's 15:55 snapshot once it exists, else
the prior session's — IV rank barely moves session to session, so the feed stays live all
day). Timing/analytics only; verify the live chain in-broker before selling. NO orders.

CLI: `python3 -m analytics.premium_desk_scan [--publish]`
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics import premium_universe  # noqa: E402
from analytics.premium_score import rank, score_candidate  # noqa: E402


def _daily(sym):  # pragma: no cover - network
    from analytics.market_data import fetch_ohlc
    df = fetch_ohlc(sym, period="14mo", interval="1d")
    return None if df is None or df.empty else df.dropna()


def _weekly(sym):  # pragma: no cover - network
    from analytics.market_data import fetch_ohlc
    df = fetch_ohlc(sym, period="5y", interval="1wk")
    return None if df is None or df.empty else df.dropna()


def _earnings_days(underlying: str) -> int | None:  # pragma: no cover - network
    """Days to the underlying's next earnings (None if unknown). Best-effort — the
    #1 premium-selling landmine: never be short a put through an earnings event.
    Finnhub when a key is set, else the yfinance calendar (already our price source)."""
    import datetime as _d
    import os as _os
    today = _d.date.today()

    # Finnhub path — only when the key exists (avoids per-call "disabled" log spam).
    if _os.environ.get("FINNHUB_API_KEY"):
        try:
            from analytics.earnings_fetcher import fetch_upcoming_earnings
            up = fetch_upcoming_earnings(underlying)
            if up and up.next_earnings_date:
                d = (up.next_earnings_date - today).days
                if d >= 0:
                    return d
        except Exception:
            pass

    # yfinance fallback — needs no key.
    try:
        import yfinance as yf
        cal = yf.Ticker(underlying).calendar
        dates = []
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            dates = ed if isinstance(ed, list) else ([ed] if ed else [])
        elif cal is not None and hasattr(cal, "loc"):  # legacy DataFrame form
            try:
                dates = [cal.loc["Earnings Date"].iloc[0]]
            except Exception:
                dates = []
        for e in dates:
            ed = e.date() if hasattr(e, "date") else e
            if isinstance(ed, _d.date):
                d = (ed - today).days
                if d >= 0:
                    return d
    except Exception:
        pass
    return None


def scan(etfs=None) -> dict:  # pragma: no cover - network
    from analytics.iv_snapshot import iv_rank
    insts = [premium_universe.get(e) for e in etfs] if etfs else premium_universe.UNIVERSE
    insts = [i for i in insts if i is not None]
    cands = []
    for inst in insts:
        try:
            try:
                iv = iv_rank(inst.etf)
            except Exception:
                iv = None  # no DB / no history yet → scored as warming
            c = score_candidate(_daily(inst.etf), _weekly(inst.etf), inst.etf, iv, theme=inst.theme)
            if c:
                # Earnings on the UNDERLYING (the ETF has none); warn if it lands in the DTE window.
                ed = _earnings_days(inst.underlying)
                c.earnings_days = ed
                c.earnings_warn = ed is not None and ed <= c.dte
                cands.append(c)
        except Exception:
            pass
    ranked = rank(cands)
    rows = [_row(c) for c in ranked]
    return {"rows": rows, "scanned": len(insts),
            "tiers": {t: sum(1 for c in ranked if c.tier == t) for t in ("low", "med", "high")}}


def _row(c) -> dict:
    return {
        "sym": c.symbol, "theme": c.theme, "price": c.price, "score": c.score,
        "tier": c.tier, "qualifies": c.qualifies, "side": c.side,
        "strike": c.strike, "dte": c.dte,
        "iv": c.iv, "iv_rank": c.iv_rank, "iv_pct": c.iv_pct, "iv_n": c.iv_n,
        "iv_warming": c.iv_warming, "rsi_d": c.rsi_d, "rsi_w": c.rsi_w,
        "above_200": c.above_200, "above_50": c.above_50, "above_20": c.above_20,
        "reclaim": c.reclaim, "rationale": c.rationale,
        "exp_move_pct": c.exp_move_pct, "exp_move_usd": c.exp_move_usd,
        "strike_cushion_pct": c.strike_cushion_pct,
        "sma20": c.sma20, "sma50": c.sma50, "sma200": c.sma200,
        "floor_dist_pct": c.floor_dist_pct,
        "earnings_days": c.earnings_days, "earnings_warn": c.earnings_warn,
    }


def publish(rep, session_date):  # pragma: no cover - DB
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=15)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS market_reports (
        kind TEXT NOT NULL, session_date TEXT NOT NULL, body TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(), PRIMARY KEY (kind, session_date))""")
    cur.execute(
        "INSERT INTO market_reports (kind, session_date, body) VALUES ('premium_desk', %s, %s) "
        "ON CONFLICT (kind, session_date) DO UPDATE SET body = EXCLUDED.body, created_at = NOW()",
        (session_date, json.dumps(rep)),
    )
    conn.commit(); cur.close(); conn.close()


def _print(rep):
    t = rep["tiers"]
    print(f"\n=== PREMIUM DESK === scanned {rep['scanned']} · "
          f"{t['low']} low · {t['med']} med · {t['high']} high\n")
    for r in rep["rows"]:
        gate = "✓" if r["qualifies"] else "·"
        print(f"  {gate} [{r['tier']:>4}] {r['sym']:<6} score {r['score']:>5.1f}  "
              f"IVR {r['iv_rank']:>5.1f}{'*' if r['iv_warming'] else ' '}  "
              f"RSI d{r['rsi_d']:>4.0f}/w{r['rsi_w']:>4.0f}  "
              f"put ≤ {r['strike']:>8.2f}  — {' · '.join(r['rationale'])}")


def main():  # pragma: no cover
    ap = argparse.ArgumentParser(description="Premium Desk scan — score + rank the leveraged-ETF universe")
    ap.add_argument("symbols", nargs="*", help="ETF tickers (default: full universe)")
    ap.add_argument("--publish", action="store_true", help="publish to market_reports[premium_desk]")
    args = ap.parse_args()
    etfs = [s.upper() for s in args.symbols] or None
    rep = scan(etfs)
    _print(rep)
    if args.publish:
        publish(rep, _dt.date.today().isoformat())
        print("published: premium_desk", _dt.date.today().isoformat(), file=sys.stderr)


if __name__ == "__main__":
    main()
