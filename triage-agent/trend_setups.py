"""Trend Setups briefing — post-close triage job (SELF-CONTAINED).

Classifies the curated master watchlist into three actionable buckets using the
validated 20-EMA trend engine, and persists the result as JSON to `market_reports`
(kind=trend_setups) so the app renders it as cards.

  • ready_now   — above a RISING 20 EMA, ADX-confirmed, WITHIN the entry band (~2.5%)
                  of the 20. Entry = the 20-EMA LEVEL (a limit), stop just below.
                  (Backtest: entering AT the line ≈ 4.5× the R of chasing the close.)
  • extended    — same strong trend, but farther above the 20 → wait for a pullback.
  • rolling_off — below the 20 (lost the line) → not a trend entry.

This is a FORK of analytics/trend_scan_report.py — the triage image ships only its
own *.py (COPY *.py), so the logic is duplicated here on purpose. Keep in sync.
Read-only: never creates alerts, never touches delivery.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

ENTRY_BAND_PCT = 2.5   # within this % of the 20 = "ready to buy the line"
ADX_MIN = 20.0
SLOPE_BARS = 5


def _watchlist(dsn):
    """The curated master account (platform universe), NOT the union of all users."""
    import psycopg2
    con = psycopg2.connect(dsn); cur = con.cursor()
    cur.execute("SELECT id FROM users WHERE lower(email)=lower('master@busytradersdesk')")
    row = cur.fetchone()
    if row:
        cur.execute("SELECT DISTINCT UPPER(symbol) FROM watchlist "
                    "WHERE user_id=%s AND symbol IS NOT NULL AND symbol<>''", (row[0],))
    else:
        cur.execute("SELECT DISTINCT UPPER(symbol) FROM watchlist WHERE symbol IS NOT NULL AND symbol<>''")
    syms = [r[0] for r in cur.fetchall() if r[0] and "-" not in r[0]]
    con.close()
    return syms


def _adx(h, l, c, n=14):
    import numpy as np, pandas as pd
    up = h.diff(); dn = -l.diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0); minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(plus, index=h.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    mdi = 100 * pd.Series(minus, index=h.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    return (100 * (pdi - mdi).abs() / (pdi + mdi)).ewm(alpha=1 / n, adjust=False).mean()


def _row(sym, df):
    import numpy as np
    if df is None or len(df) < 60:
        return None
    h, l, c = df["High"], df["Low"], df["Close"]
    e20 = c.ewm(span=20).mean(); e50 = c.ewm(span=50).mean(); adx = _adx(h, l, c)
    cl = float(c.iloc[-1]); m20 = float(e20.iloc[-1]); m50 = float(e50.iloc[-1]); a = float(adx.iloc[-1])
    if m20 <= 0 or np.isnan(m20) or np.isnan(a):
        return None
    rising20 = m20 > float(e20.iloc[-1 - SLOPE_BARS])
    above20 = cl > m20
    dist = (cl - m20) / m20 * 100.0
    return {
        "symbol": sym, "price": round(cl, 2), "ema20": round(m20, 2), "ema50": round(m50, 2),
        "adx": round(a, 0), "dist_pct": round(dist, 1),
        "stop": round(min(float(l.iloc[-1]), m20 * 0.995), 2),
        "rising20": rising20, "above20": above20,
    }


def build(syms, data):
    ready, extended, rolling = [], [], []
    for s in syms:
        try:
            df = data[s].dropna()
        except Exception:
            continue
        r = _row(s, df)
        if r is None:
            continue
        trend = r["rising20"] and r["above20"] and r["adx"] >= ADX_MIN
        if trend and r["dist_pct"] <= ENTRY_BAND_PCT:
            ready.append(r)
        elif trend:
            extended.append(r)
        elif not r["above20"]:
            rolling.append(r)
    ready.sort(key=lambda x: -x["adx"])
    extended.sort(key=lambda x: -x["adx"])
    rolling.sort(key=lambda x: x["dist_pct"])
    return {
        "kind": "trend_setups", "entry_band_pct": ENTRY_BAND_PCT,
        "ready_now": ready, "extended": extended, "rolling_off": rolling,
        "counts": {"ready": len(ready), "extended": len(extended), "rolling": len(rolling)},
    }


def run_trend_setups(send: bool = False) -> None:
    """Fetch the master universe, classify, persist to market_reports. Never raises."""
    import yfinance as yf
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print(json.dumps({"error": "no DATABASE_URL"})); return
    try:
        syms = _watchlist(dsn)
    except Exception as e:
        print(json.dumps({"error": f"watchlist: {e}"})); return
    if not syms:
        print(json.dumps({"detail": "empty watchlist"})); return
    data = yf.download(syms, period="6mo", interval="1d", progress=False,
                       auto_adjust=False, group_by="ticker", threads=True)
    rep = build(syms, data)
    try:
        import pytz
        et = datetime.now(pytz.timezone("America/New_York"))
    except Exception:
        et = datetime.utcnow()
    try:
        from reports_store import publish
        publish("trend_setups", et, json.dumps(rep), send=send)
        print(json.dumps({"published": True, "counts": rep["counts"]}))
    except Exception as e:
        print(json.dumps({"published": False, "error": str(e), "counts": rep["counts"]}))


if __name__ == "__main__":
    run_trend_setups(send="--send" in sys.argv)
