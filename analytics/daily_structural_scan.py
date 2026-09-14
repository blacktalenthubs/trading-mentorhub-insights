"""Daily-structural scan over the MASTER watchlist — the swing/oversold reclaims that
only need daily data (so they can cover all ~150 names cheaply, unlike the intraday
scanner's curated 52). Three rules, mirroring the live scanner's daily logic:

  • RSI-30 turn  — RSI reclaimed 30 (prev < 30 → 30-35) OR held it (prev ≥ 30, 30-32, up)
  • 150 SMA reclaim — daily close reclaimed (prev ≤ 150 < close) or is holding just above
  • 200 SMA reclaim — same on the 200

Entry = the close; stop = the MA (or session low for RSI). Prints; --telegram / --publish.
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HOLD_PCT = 1.5   # "holding just above" the MA within this % counts as a reclaim/hold


def _daily(sym):  # pragma: no cover - network
    from analytics.market_data import fetch_ohlc
    df = fetch_ohlc(sym, period="14mo", interval="1d")
    return None if df is None or df.empty else df.dropna()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, 1e-9)
    return 100 - 100 / (1 + rs)


def check(sym: str, df: pd.DataFrame) -> list[dict]:
    if df is None or len(df) < 210:
        return []
    close = df["Close"].astype(float)
    c = float(close.iloc[-1])
    pc = float(close.iloc[-2])
    lo5 = float(df["Low"].astype(float).tail(5).min())
    out = []

    def _emit(rule, level, stop):
        risk = c - stop
        if risk <= 0:
            return
        out.append({"sym": sym, "rule": rule, "close": round(c, 2), "entry": round(c, 2),
                    "stop": round(stop, 2), "level": round(level, 2),
                    "risk_pct": round(risk / c * 100, 1)})

    # RSI-30 (watch bar — looser than the live entry): reclaimed 30 (prev<30 → 30-35)
    # OR sitting at 30-32 having NOT lost 30 (prev>=30). "turning up" noted when it is.
    rsi = _rsi(close)
    r, rp = float(rsi.iloc[-1]), float(rsi.iloc[-2])
    if rp < 30 and 30 <= r <= 35:
        _emit(f"RSI-30 reclaim ({r:.0f})", c, min(lo5, c * 0.97))
    elif rp >= 30 and 30 <= r <= 32:
        _emit(f"RSI-30 at line ({r:.0f}{', up' if r > rp else ''})", c, min(lo5, c * 0.97))

    # 150 / 200 SMA reclaim or hold
    for p in (150, 200):
        ma = float(close.rolling(p).mean().iloc[-1])
        if ma <= 0:
            continue
        reclaim = pc <= ma < c
        hold = c >= ma and (c - ma) / ma * 100 <= HOLD_PCT
        if reclaim or hold:
            _emit(f"{p} SMA {'reclaim' if reclaim else 'hold'}", ma, ma * 0.985)
    return out


def scan(symbols) -> dict:
    rows = []
    for s in symbols:
        try:
            rows += check(s, _daily(s))
        except Exception:
            pass
    rows.sort(key=lambda r: r["risk_pct"])
    return {"rows": rows, "scanned": len(symbols)}


def _print(rep):
    print(f"\n=== DAILY-STRUCTURAL SCAN === scanned {rep['scanned']} · {len(rep['rows'])} setups\n")
    for r in rep["rows"]:
        print(f"  {r['sym']:<7} {r['rule']:<20} close {r['close']:>9.2f}  stop {r['stop']:>9.2f}  (risk {r['risk_pct']}%)")


def _telegram(rep, date):
    out = [f"<b>DAILY STRUCTURAL · {date}</b>  ({len(rep['rows'])} setups)"]
    for r in rep["rows"]:
        out.append(f"  {r['sym']} — {r['rule']} · close {r['close']}, stop {r['stop']} (risk {r['risk_pct']}%)")
    return "\n".join(out)


def publish(rep, session_date):  # pragma: no cover - DB
    import json
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=15)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO market_reports (kind, session_date, body, created_at) "
        "VALUES ('daily_structural', %s, %s, NOW()) "
        "ON CONFLICT (kind, session_date) DO UPDATE SET body = EXCLUDED.body, created_at = NOW()",
        (session_date, json.dumps(rep)),
    )
    conn.commit(); cur.close(); conn.close()


def main():  # pragma: no cover
    ap = argparse.ArgumentParser(description="Daily-structural scan (RSI-30 + 150/200 reclaim) over the master watchlist")
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--universe", action="store_true")
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()
    if args.universe:
        from analytics.swing_setups_report import _watchlist
        symbols = _watchlist(os.environ["DATABASE_URL"])
    else:
        symbols = [s.upper() for s in args.symbols] or ["CRDO", "INTC", "PYPL", "NBIS", "MU"]
    import datetime as _dt
    date = _dt.date.today().isoformat()
    rep = scan(symbols)
    _print(rep)
    if args.publish:
        publish(rep, date); print("published: daily_structural", date, file=sys.stderr)
    if args.telegram:
        from analytics.minervini_scan import _send_to_telegram
        _send_to_telegram(_telegram(rep, date))


if __name__ == "__main__":
    main()
