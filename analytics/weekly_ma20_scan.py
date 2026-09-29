"""Weekly rising-20-SMA scan — stocks in a WEEKLY uptrend that have pulled back to (and are
holding) their 20-week SMA. The 20-week SMA (~100 trading days) is a major swing/position
trend line: a *rising* 20w with price sitting on it is the classic pullback-in-uptrend entry.

Two conditions, both required:
  • RISING 20w SMA — the 20w SMA now is above the 20w SMA `SLOPE_WKS` weeks ago (uptrend).
  • AT the line — the last weekly close is within `NEAR_PCT` of the 20w SMA and holding ABOVE
    it (support), OR a fresh reclaim (prior week's close below, this week back above).

Computed by resampling clean DAILY bars to weekly (yfinance weekly VOLUME is wrong, but the
daily closes it's built from are fine; resampling sidesteps the weekly quirks entirely).
Entry = the weekly close; stop = the 20w SMA (a weekly close below it invalidates the swing).

Prints; --telegram / --publish → market_reports kind='weekly_ma20_setups'.

    python3 -m analytics.weekly_ma20_scan AAPL MSFT NVDA
    python3 -m analytics.weekly_ma20_scan --universe --publish
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SMA_WKS = 20      # the weekly SMA length
SLOPE_WKS = 4     # "rising" = 20w SMA now > 20w SMA this many weeks ago
NEAR_PCT = 1.5    # "at the line" = last weekly close within this % of the 20w SMA (tight — a
                  # genuine pullback hugging the line, not a name already extended above it)
STOP_PCT = 1.0    # stop this % below the 20w SMA


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, 1e-9)
    return 100 - 100 / (1 + rs)


def _weekly(sym: str):  # pragma: no cover - network
    """Clean weekly bars from resampled DAILY data (~3y so the 20w SMA + slope have room)."""
    from analytics.market_data import fetch_ohlc
    df = fetch_ohlc(sym, period="3y", interval="1d")
    if df is None or df.empty:
        return None
    df = df.dropna()
    wk = df.resample("W-FRI").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    ).dropna()
    return wk if not wk.empty else None


def check(sym: str, wk: pd.DataFrame) -> dict | None:
    if wk is None or len(wk) < SMA_WKS + SLOPE_WKS + 1:
        return None
    close = wk["Close"].astype(float)
    sma = close.rolling(SMA_WKS).mean()
    ma = float(sma.iloc[-1])
    ma_prev = float(sma.iloc[-1 - SLOPE_WKS])
    if ma <= 0 or pd.isna(ma) or pd.isna(ma_prev):
        return None

    rising = ma > ma_prev
    if not rising:
        return None

    c = float(close.iloc[-1])
    pc = float(close.iloc[-2])
    dist_pct = (c - ma) / ma * 100.0

    reclaim = pc <= ma < c                       # prior week below, now back above
    holding = c >= ma and dist_pct <= NEAR_PCT   # sitting on/just above the line
    if not (reclaim or holding):
        return None

    rsi_w = float(_rsi(close).iloc[-1])
    slope_pct = (ma - ma_prev) / ma_prev * 100.0
    stop = ma * (1 - STOP_PCT / 100.0)
    risk_pct = (c - stop) / c * 100.0 if c > stop else 0.0
    return {
        "sym": sym,
        "close": round(c, 2),
        "sma20w": round(ma, 2),
        "dist_pct": round(dist_pct, 1),
        "status": "reclaim" if reclaim else "holding",
        "slope_pct": round(slope_pct, 1),       # how strongly the 20w is rising (over SLOPE_WKS)
        "rsi_w": round(rsi_w, 0),
        "entry": round(c, 2),
        "stop": round(stop, 2),
        "risk_pct": round(risk_pct, 1),
    }


def scan(symbols) -> dict:
    rows = []
    for s in symbols:
        try:
            r = check(s, _weekly(s))
            if r:
                rows.append(r)
        except Exception:
            pass
    # closest to the line first (best pullback entries), then strongest uptrend
    rows.sort(key=lambda r: (abs(r["dist_pct"]), -r["slope_pct"]))
    return {"rows": rows, "scanned": len(symbols)}


def _print(rep):
    print(f"\n=== WEEKLY RISING 20-SMA === scanned {rep['scanned']} · {len(rep['rows'])} setups\n")
    for r in rep["rows"]:
        print(f"  {r['sym']:<7} {r['status']:<8} close {r['close']:>9.2f}  20wSMA {r['sma20w']:>9.2f}"
              f"  ({r['dist_pct']:+.1f}%)  slope +{r['slope_pct']}%  RSIw {r['rsi_w']:.0f}")


def _telegram(rep, date):
    out = [f"<b>WEEKLY RISING 20-SMA · {date}</b>  ({len(rep['rows'])} setups)"]
    for r in rep["rows"]:
        out.append(f"  {r['sym']} — {r['status']} the 20w SMA {r['sma20w']} "
                   f"({r['dist_pct']:+.1f}%), rising +{r['slope_pct']}% · close {r['close']}, stop {r['stop']}")
    return "\n".join(out)


def publish(rep, session_date):  # pragma: no cover - DB
    import json
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=15)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO market_reports (kind, session_date, body, created_at) "
        "VALUES ('weekly_ma20_setups', %s, %s, NOW()) "
        "ON CONFLICT (kind, session_date) DO UPDATE SET body = EXCLUDED.body, created_at = NOW()",
        (session_date, json.dumps(rep)),
    )
    conn.commit(); cur.close(); conn.close()


def main():  # pragma: no cover
    ap = argparse.ArgumentParser(description="Weekly rising-20-SMA scan over the master watchlist")
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--universe", action="store_true")
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()

    import datetime as _dt
    date = _dt.date.today().isoformat()
    if args.universe or not args.symbols:
        from analytics.swing_setups_report import _watchlist
        syms = _watchlist(os.environ["DATABASE_URL"])
    else:
        syms = [s.upper() for s in args.symbols]

    rep = scan(syms)
    _print(rep)
    if args.publish:
        publish(rep, date)
        print(f"\npublished weekly_ma20_setups · {date} · {len(rep['rows'])} setups")
    if args.telegram:
        from analytics.minervini_scan import _send_to_telegram
        _send_to_telegram(_telegram(rep, date))


if __name__ == "__main__":
    main()
