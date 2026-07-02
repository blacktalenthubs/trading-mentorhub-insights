"""Premarket signals for the Focus list — triage job (SELF-CONTAINED).

The TV pines are RTH-anchored and don't run premarket, so premarket signals come from
here: for every FOCUS symbol, compute the same key levels + fire the level rules on the
live premarket price, then publish to market_reports kind=premarket_signals (a SEPARATE
premarket feed). Read-only; per-user push is a later layer.

FORK of analytics/premarket_signals.py — the triage image ships only its own *.py
(COPY *.py). Keep in sync.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

TOL_PCT = 0.3
PROX_PCT = 1.5   # price must be AT the level now (within this % above it) — not 5% past it
PM_TYPES = {
    "cml_reclaim", "cml_held", "staged_pdl_held", "staged_pwl_held", "staged_pml_held",
    "staged_pdh_break", "staged_pwh_break", "weekly_10w_held", "weekly_30w_held",
}


def _focus_symbols(dsn):
    """Union of every user's FOCUS list — the platform focus universe."""
    import psycopg2
    con = psycopg2.connect(dsn); cur = con.cursor()
    cur.execute("SELECT DISTINCT UPPER(symbol) FROM watchlist "
                "WHERE focus=true AND symbol IS NOT NULL AND symbol<>''")
    syms = [r[0] for r in cur.fetchall() if r[0] and "-" not in r[0]]
    con.close()
    return syms


# ── forked engine (mirror analytics/premarket_signals.py) ───────────────────
def compute_levels(daily, weekly=None):
    import pandas as pd  # noqa
    if daily is None or len(daily) < 25:
        return {}
    h, l, c = daily["High"], daily["Low"], daily["Close"]
    idx = daily.index
    lv = {"prior_close": float(c.iloc[-1]), "pdh": float(h.iloc[-1]), "pdl": float(l.iloc[-1])}
    last = idx[-1]
    cur_month = (idx.year == last.year) & (idx.month == last.month)
    if cur_month.any():
        lv["cml"] = float(l[cur_month].min())
    wk = idx.isocalendar()
    last_wk = (wk.year.iloc[-1], wk.week.iloc[-1])
    prior_wk_mask = ~((wk.year == last_wk[0]) & (wk.week == last_wk[1])).values
    if prior_wk_mask.any():
        recent = daily[prior_wk_mask].tail(5)
        lv["pwh"] = float(recent["High"].max()); lv["pwl"] = float(recent["Low"].min())
    prior_month = (idx.year * 12 + idx.month) == (last.year * 12 + last.month - 1)
    if prior_month.any():
        lv["pml"] = float(l[prior_month].min())
    if weekly is not None and len(weekly) >= 30:
        wc = weekly["Close"]
        lv["w10"] = float(wc.rolling(10).mean().iloc[-1])
        lv["w30"] = float(wc.rolling(30).mean().iloc[-1])
    return lv


def _held(price, low, level, tol):
    return level > 0 and level <= price <= level * (1 + PROX_PCT / 100.0) and low <= level * (1 + tol / 100.0)


def _reclaim(price, low, level, tol):
    return level > 0 and low < level * (1 - tol / 100.0) and level <= price <= level * (1 + PROX_PCT / 100.0)


def evaluate(levels, pm_price, pm_low, pm_high, enabled, tol=TOL_PCT):
    en = set(enabled or [])
    out = []

    def emit(atype, level, why):
        if atype in en:
            out.append({"alert_type": atype, "direction": "BUY", "entry": round(pm_price, 2),
                        "level": round(level, 2), "stop": round(level * 0.997, 2), "note": why})

    cml = levels.get("cml")
    if cml:
        if _reclaim(pm_price, pm_low, cml, tol):
            emit("cml_reclaim", cml, "undercut & reclaimed the current-month low premarket")
        elif _held(pm_price, pm_low, cml, tol):
            emit("cml_held", cml, "tagged & held the current-month low premarket")
    for k, atype, label in (("pdl", "staged_pdl_held", "prior-day low"),
                            ("pwl", "staged_pwl_held", "prior-week low"),
                            ("pml", "staged_pml_held", "prior-month low"),
                            ("w10", "weekly_10w_held", "10-week MA"),
                            ("w30", "weekly_30w_held", "30-week MA")):
        lvl = levels.get(k)
        if lvl and _held(pm_price, pm_low, lvl, tol):
            emit(atype, lvl, f"tagged & held the {label} premarket")
    for k, atype, label in (("pdh", "staged_pdh_break", "prior-day high"),
                            ("pwh", "staged_pwh_break", "prior-week high")):
        lvl = levels.get(k)
        if lvl and lvl < pm_price <= lvl * (1 + PROX_PCT / 100.0) and pm_low <= lvl:
            emit(atype, lvl, f"broke the {label} premarket")
    return out


def run(send: bool = False) -> None:
    import warnings
    warnings.filterwarnings("ignore")
    import pytz
    import yfinance as yf

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print(json.dumps({"error": "no DATABASE_URL"})); return
    syms = _focus_symbols(dsn)
    if not syms:
        print(json.dumps({"detail": "no focus symbols"})); return
    et = datetime.now(pytz.timezone("America/New_York"))

    daily = yf.download(syms, period="6mo", interval="1d", progress=False, auto_adjust=False, group_by="ticker", threads=True)
    weekly = yf.download(syms, period="2y", interval="1wk", progress=False, auto_adjust=False, group_by="ticker", threads=True)
    pm = yf.download(syms, period="1d", interval="5m", prepost=True, progress=False, auto_adjust=False, group_by="ticker", threads=True)

    signals = []
    for s in syms:
        try:
            dd = daily[s].dropna(); wk = weekly[s].dropna(); pmd = pm[s].dropna()
        except Exception:
            continue
        # Drop TODAY's partial daily bar — levels (PDL/CML/PWL…) must come from
        # COMPLETED sessions, else every level looks trivially "tagged" by premarket.
        dd = dd[dd.index.date < et.date()]
        wk = wk[wk.index.date < et.date()]
        if len(dd) < 25 or len(pmd) == 0:
            continue
        idx = pmd.index.tz_convert("America/New_York") if pmd.index.tz else pmd.index
        tdy = pmd[idx.date == et.date()]
        if len(tdy) == 0:
            continue
        pm_low = float(tdy["Low"].min()); pm_high = float(tdy["High"].max()); pm_price = float(tdy["Close"].iloc[-1])
        levels = compute_levels(dd, wk if len(wk) >= 30 else None)
        pc = levels.get("prior_close")
        gap = (pm_price - pc) / pc * 100 if pc else 0.0
        for sig in evaluate(levels, pm_price, pm_low, pm_high, PM_TYPES):
            signals.append({**sig, "symbol": s, "price": round(pm_price, 2), "gap_pct": round(gap, 1)})

    signals.sort(key=lambda x: -abs(x.get("gap_pct", 0)))
    body = json.dumps({"kind": "premarket_signals", "signals": signals,
                       "count": len(signals), "asof": et.strftime("%H:%M ET")})
    try:
        from reports_store import publish
        publish("premarket_signals", et, body, send=send)
        print(json.dumps({"published": True, "count": len(signals),
                          "signals": [f"{s['symbol']}:{s['alert_type']}" for s in signals]}))
    except Exception as e:
        print(json.dumps({"published": False, "error": str(e), "count": len(signals),
                          "signals": [f"{s['symbol']}:{s['alert_type']}" for s in signals]}))


if __name__ == "__main__":
    run(send="--send" in sys.argv)
