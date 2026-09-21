"""Put-seller scan over the MASTER watchlist → market_reports → Today page.

Same shape as volume_signal_scan.py (a standalone daily job, NOT the live alert
pipeline): fetch each name's daily + weekly bars, run the put-seller engine, and publish
the hits to market_reports(kind='putsell_signals') so they show on the Today page.

Surfaces two things the trader asked for:
  1. Every name currently UNDER 40 WEEKLY RSI — the oversold watchlist to hunt.
  2. Which of those (or any name) is firing a put-sell trigger NOW, with the strike.

Triggers (from analytics.putsell_signals): Daily RSI reversal · Weekly RSI reversal ·
50 SMA bounce · 200 SMA bounce. Prints; --telegram / --publish. Timing only — verify IV.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics.putsell_signals import detect_putsell  # noqa: E402


def _daily(sym):  # pragma: no cover - network
    from analytics.market_data import fetch_ohlc
    df = fetch_ohlc(sym, period="14mo", interval="1d")
    return None if df is None or df.empty else df.dropna()


def _weekly(sym):  # pragma: no cover - network
    from analytics.market_data import fetch_ohlc
    df = fetch_ohlc(sym, period="5y", interval="1wk")
    return None if df is None or df.empty else df.dropna()


def check(sym: str) -> dict | None:  # pragma: no cover - network
    d, w = _daily(sym), _weekly(sym)
    s = detect_putsell(d, w, sym)
    if s is None:
        return None
    return {
        "sym": s.symbol,
        "price": s.price,
        "rsi_d": s.rsi_d,
        "rsi_w": s.rsi_w,
        "weekly_oversold": s.weekly_oversold,
        "triggers": s.triggers,
        "fired": s.fired,
        "strike": s.strike,
        "dte": s.dte,
    }


def scan(symbols) -> dict:  # pragma: no cover - network
    rows = []
    for s in symbols:
        try:
            r = check(s)
            if r:
                rows.append(r)
        except Exception:
            pass
    # Live triggers first, then the most-oversold weekly RSI at the top of the watchlist.
    rows.sort(key=lambda r: (0 if r["fired"] else 1, r["rsi_w"]))
    return {"rows": rows, "scanned": len(symbols)}


def _print(rep):
    fired = [r for r in rep["rows"] if r["fired"]]
    watch = [r for r in rep["rows"] if not r["fired"]]
    print(f"\n=== PUT-SELLER SCAN === scanned {rep['scanned']} · "
          f"{len(fired)} firing · {len(watch)} on the weekly-oversold watch\n")
    for r in rep["rows"]:
        tag = "🔴 SELL PUT" if r["fired"] else "  watch   "
        why = " · ".join(r["triggers"]) if r["triggers"] else f"weekly RSI {r['rsi_w']}"
        strike = f"  → PUT ≤ {r['strike']:.2f} (~{r['dte']}d)" if r["fired"] else ""
        print(f"  {tag} {r['sym']:<7} RSI d{r['rsi_d']:>5}/w{r['rsi_w']:>5}  "
              f"${r['price']:>9.2f}  {why}{strike}")


def _telegram(rep, date):
    fired = [r for r in rep["rows"] if r["fired"]]
    out = [f"<b>PUT-SELLER · {date}</b>  ({len(fired)} firing · {len(rep['rows'])} watched)"]
    for r in fired:
        out.append(f"  🔴 {r['sym']} — {' · '.join(r['triggers'])} · sell PUT ≤ {r['strike']} (~{r['dte']}d)")
    watch = [r for r in rep["rows"] if not r["fired"]]
    if watch:
        out.append("  <i>weekly-oversold watch:</i> " + ", ".join(f"{r['sym']}({r['rsi_w']})" for r in watch[:20]))
    return "\n".join(out)


def publish(rep, session_date):  # pragma: no cover - DB
    import json
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=15)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO market_reports (kind, session_date, body, created_at) "
        "VALUES ('putsell_signals', %s, %s, NOW()) "
        "ON CONFLICT (kind, session_date) DO UPDATE SET body = EXCLUDED.body, created_at = NOW()",
        (session_date, json.dumps(rep)),
    )
    conn.commit(); cur.close(); conn.close()


def main():  # pragma: no cover
    ap = argparse.ArgumentParser(description="Put-seller scan (oversold reversals + SMA bounces) over the master watchlist")
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--universe", action="store_true")
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()
    if args.universe:
        from analytics.swing_setups_report import _watchlist
        symbols = _watchlist(os.environ["DATABASE_URL"])
    else:
        symbols = [s.upper() for s in args.symbols] or ["IWM", "SPY", "QQQ", "SOXL", "NBIS", "AAOI", "MU"]
    date = _dt.date.today().isoformat()
    rep = scan(symbols)
    _print(rep)
    if args.publish:
        publish(rep, date); print("published: putsell_signals", date, file=sys.stderr)
    if args.telegram:
        from analytics.minervini_scan import _send_to_telegram
        _send_to_telegram(_telegram(rep, date))


if __name__ == "__main__":
    main()
