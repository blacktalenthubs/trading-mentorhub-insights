"""Volume-profile scan over the MASTER watchlist → market_reports → UI.

Same shape as daily_structural_scan.py (a standalone daily job, NOT the live alert
pipeline): fetch each name, run the validated volume-profile engine, and publish the
hits to market_reports(kind='volume_signals') so they show in the app for evaluation.

Setups (from analytics.volume_profile_signals):
  POC reclaim / VAL bounce / VAH breakout / VWAP reclaim (long) + VWAP loss (short).
Support signals require an open-and-hold above the level; each carries a 20/50/200 SMA
confluence tag. Shorts only for the short universe. Prints; --telegram / --publish.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics.volume_profile_signals import detect_signals  # noqa: E402

try:
    from alert_config import SHORT_UNIVERSE
except Exception:
    SHORT_UNIVERSE = {"SPY", "QQQ", "SMH", "DRAM"}

KIND_LABEL = {
    "poc_reclaim":  "POC reclaim",
    "val_bounce":   "VAL bounce",
    "vah_breakout": "VAH breakout",
    "vwap_reclaim": "VWAP reclaim",
    "vwap_loss":    "VWAP loss",
}


def _daily(sym):  # pragma: no cover - network
    from analytics.market_data import fetch_ohlc
    df = fetch_ohlc(sym, period="14mo", interval="1d")
    return None if df is None or df.empty else df.dropna()


def check(sym: str, df) -> list[dict]:
    if df is None or len(df) < 40:
        return []
    rows = []
    for s in detect_signals(df, sym, short_ok=sym in SHORT_UNIVERSE):
        stop = round(s.level * (0.985 if s.direction == "long" else 1.015), 2)
        risk = abs(s.price - stop)
        rows.append({
            "sym": sym,
            "signal": s.kind,
            "label": KIND_LABEL.get(s.kind, s.kind),
            "direction": s.direction,
            "price": round(s.price, 2),
            "level": round(s.level, 2),
            "level_name": s.level_name,
            "stop": stop,
            "risk_pct": round(risk / s.price * 100, 1) if s.price else 0.0,
            "confluence": s.confluence,
        })
    # Put/call SELLING lives in the dedicated put-seller scan now (analytics/putsell_scan.py
    # -> the "Put sellers" section) so there's ONE put-selling surface. This scan is
    # directional VP setups only (POC / value area / VWAP).
    return rows


def scan(symbols) -> dict:
    rows = []
    for s in symbols:
        try:
            rows += check(s, _daily(s))
        except Exception:
            pass
    # Confluence setups first, then lowest risk.
    rows.sort(key=lambda r: (0 if r["confluence"] else 1, r["risk_pct"]))
    return {"rows": rows, "scanned": len(symbols)}


def _print(rep):
    print(f"\n=== VOLUME-SIGNAL SCAN === scanned {rep['scanned']} · {len(rep['rows'])} setups\n")
    for r in rep["rows"]:
        conf = f"  ⭐ {', '.join(r['confluence'])}" if r["confluence"] else ""
        print(f"  {r['sym']:<7} {r['label']:<13} {r['direction']:<5} "
              f"{r['level_name']} @ {r['level']:>9.2f}  close {r['price']:>9.2f} (risk {r['risk_pct']}%){conf}")


def _telegram(rep, date):
    out = [f"<b>VOLUME SIGNALS · {date}</b>  ({len(rep['rows'])} setups)"]
    for r in rep["rows"]:
        conf = f" · ⭐ {', '.join(r['confluence'])}" if r["confluence"] else ""
        out.append(f"  {r['sym']} — {r['label']} ({r['direction']}) · {r['level_name']} {r['level']}{conf}")
    return "\n".join(out)


def publish(rep, session_date):  # pragma: no cover - DB
    import json
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=15)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO market_reports (kind, session_date, body, created_at) "
        "VALUES ('volume_signals', %s, %s, NOW()) "
        "ON CONFLICT (kind, session_date) DO UPDATE SET body = EXCLUDED.body, created_at = NOW()",
        (session_date, json.dumps(rep)),
    )
    conn.commit(); cur.close(); conn.close()


def main():  # pragma: no cover
    ap = argparse.ArgumentParser(description="Volume-profile scan (POC/VA/VWAP setups) over the master watchlist")
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--universe", action="store_true")
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()
    if args.universe:
        from analytics.swing_setups_report import _watchlist
        symbols = _watchlist(os.environ["DATABASE_URL"])
    else:
        symbols = [s.upper() for s in args.symbols] or ["NBIS", "AAOI", "DRAM", "QQQ", "AAPL", "MU"]
    date = _dt.date.today().isoformat()
    rep = scan(symbols)
    _print(rep)
    if args.publish:
        publish(rep, date); print("published: volume_signals", date, file=sys.stderr)
    if args.telegram:
        from analytics.minervini_scan import _send_to_telegram
        _send_to_telegram(_telegram(rep, date))


if __name__ == "__main__":
    main()
