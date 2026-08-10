"""Swing Setups briefing — a READ-ONLY daily report (not an alert source).

The MERGED swing finder (user 2026-08-08: "trend setups and swing setups should be
ONE thing"). Runs the finalized swing book (analytics/swing_quality.py) across the
MASTER watchlist universe and buckets every qualifying name by the pattern it hit, so a
busy trader sees — in one scroll — WHICH stocks are sitting in a swing zone today:

  • 30w        — defended a RISING 30-week MA (Weinstein Stage-2 keystone)
  • sma200     — held / reclaimed the 200 SMA (institutional line)
  • rsi30      — RSI reclaimed the 30-35 oversold zone (washout turning up)
  • ema_cross  — 8/21 EMA momentum flip (price above the 50)
  • opened_above — today's OPEN cleared a prior-WEEK / prior-MONTH high and is holding
                   (the premarket-reclaim of a level that had capped price)

`opened_above` is computed HERE (not in swing_quality) because it needs real calendar
week/month boundaries — the dateless normalized frame swing_quality works on can't
resample. Everything else is the exact live alert book, so the finder and the alerts
agree on what a swing is.

Pure over daily OHLC + a DB read for the universe — runs LOCALLY (yfinance works
off-cloud) and publishes to `market_reports` (kind=`swing_setups`) like the other
report scripts (morning_leaders / trend_scan_report).

    DATABASE_URL=postgresql://... python3 analytics/swing_setups_report.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import Callable, Optional

import pandas as pd

from analytics.swing_quality import (
    REGIME_BOUNCE,
    SwingQualification,
    evaluate_swing_quality,
)

# rule (rules[0].rule) / entry_level → the bucket a qualification lands in. The finder
# groups by the trader's mental model, not the internal rule name.
_RULE_BUCKET = {
    "30w_bounce": "30w",
    "rsi_recovery": "rsi30",
    "ema_8_21_cross": "ema_cross",
}

BUCKET_ORDER = ["opened_above", "30w", "sma200", "ema_cross", "rsi30", "ma_hold"]

BUCKET_TITLE = {
    "opened_above": "Opened above a prior week/month high · reclaimed a capping level",
    "30w": "30-week MA bounce · defended a rising Stage-2 trend line",
    "sma200": "200 SMA hold · defended the institutional line",
    "ema_cross": "8/21 EMA momentum cross · flipped up above the 50",
    "rsi30": "RSI reclaimed the oversold zone · washout turning up",
    "ma_hold": "Key-MA hold · defended a rising moving average",
}


def _bucket_for(q: SwingQualification) -> str:
    """Which display bucket a qualification belongs to."""
    rule = q.rules[0].rule if q.rules else ""
    if rule in _RULE_BUCKET:
        return _RULE_BUCKET[rule]
    if "200" in q.entry_level:
        return "sma200"
    return "ma_hold"


def _row(q: SwingQualification) -> dict:
    why = q.rules[0].detail if q.rules else q.summary
    return {
        "symbol": q.symbol,
        "entry": q.entry,
        "stop": q.stop,
        "target": q.target_1,
        "close": q.close,
        "level": q.entry_level,
        "why": why,
    }


def _opened_above(symbol: str, df: pd.DataFrame) -> Optional[dict]:
    """Today's OPEN cleared the prior calendar WEEK's high (PWH) or prior MONTH's high
    (PMH) and the bar is HOLDING above it (close still above the level). A reclaim of a
    level that had been capping price — the premarket-gap-and-hold the user wants surfaced.

    Needs the dated index (resample), so it lives here, not in swing_quality. Prefers the
    tighter prior-week level; falls back to the prior-month high. None if neither cleared."""
    if df is None or len(df) < 30 or not isinstance(df.index, pd.DatetimeIndex):
        return None
    o = float(df["Open"].iloc[-1])
    c = float(df["Close"].iloc[-1])
    prev_c = float(df["Close"].iloc[-2])
    # prior COMPLETED week / month highs (exclude the in-progress current period)
    wk = df["High"].resample("W").max().dropna()
    mo = df["High"].resample("MS").max().dropna()
    pwh = float(wk.iloc[-2]) if len(wk) >= 2 else None
    pmh = float(mo.iloc[-2]) if len(mo) >= 2 else None
    for name, lvl in (("prior-week high", pwh), ("prior-month high", pmh)):
        if lvl is None or lvl <= 0:
            continue
        # opened ABOVE the level, still holding above it, and it was a capping level
        # yesterday (prev close at/under it) → a fresh reclaim, not already extended.
        if o > lvl and c > lvl and prev_c <= lvl * 1.001:
            return {
                "symbol": symbol,
                "entry": round(lvl, 2),           # the reclaimed level = the entry/retest
                "stop": round(float(df["Low"].iloc[-1]), 2),
                "target": round(lvl * 1.06, 2),
                "close": round(c, 2),
                "level": name.upper().replace("PRIOR-WEEK HIGH", "PWH").replace("PRIOR-MONTH HIGH", "PMH"),
                "why": f"opened at ${o:.2f}, above the {name} (${lvl:.2f}) that had capped it — "
                       f"holding the reclaim",
            }
    return None


def build_swing_report(
    symbols: list[str], fetch: Callable[[str], Optional[pd.DataFrame]], session_date: str = ""
) -> dict:
    """Run the finalized swing book across `symbols` and bucket every qualifier.

    `fetch(symbol)` returns a daily OHLC DataFrame (Open/High/Low/Close/Volume, dated
    index) or None. Returns a report dict ready to persist as JSON.
    """
    buckets: dict[str, list[dict]] = {b: [] for b in BUCKET_ORDER}
    scanned = 0
    for s in symbols:
        df = fetch(s)
        if df is None or df.empty:
            continue
        scanned += 1
        # opened-above-level is independent of the book (a stock can gap over PWH without
        # otherwise qualifying) — check it first so it always surfaces.
        oa = _opened_above(s, df)
        if oa is not None:
            buckets["opened_above"].append(oa)
        q = evaluate_swing_quality(s, df, REGIME_BOUNCE, session_date=session_date)
        if q is not None:
            buckets[_bucket_for(q)].append(_row(q))
    # strongest evidence first within a bucket = closest to its level (smallest risk)
    for b in buckets.values():
        b.sort(key=lambda r: abs(r["close"] - r["entry"]) / max(r["entry"], 1e-9))
    counts = {b: len(rows) for b, rows in buckets.items()}
    return {
        "kind": "swing_setups",
        "session_date": session_date,
        "universe": scanned,
        "bucket_order": BUCKET_ORDER,
        "bucket_title": BUCKET_TITLE,
        "buckets": buckets,
        "counts": counts,
        "total": sum(counts.values()),
    }


# ── universe + fetch + publish (mirror morning_leaders / trend_scan_report) ──────────


def _watchlist(dsn: str) -> list[str]:
    """The MASTER watchlist account = the curated platform universe; fall back to the
    union of every user's watchlist if the master account is absent."""
    import psycopg2
    conn = psycopg2.connect(dsn, connect_timeout=15)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE lower(email)=lower('master@busytradersdesk')")
    row = cur.fetchone()
    if row:
        cur.execute("SELECT DISTINCT UPPER(symbol) FROM watchlist "
                    "WHERE user_id=%s AND symbol IS NOT NULL AND symbol<>''", (row[0],))
    else:
        cur.execute("SELECT DISTINCT UPPER(symbol) FROM watchlist WHERE symbol IS NOT NULL AND symbol<>''")
    syms = sorted(r[0] for r in cur.fetchall())
    cur.close(); conn.close()
    return syms


def _yf_fetch(symbol: str):  # pragma: no cover - network
    import warnings

    import yfinance as yf
    warnings.filterwarnings("ignore")
    # 15mo ≈ 315 trading days — enough for the 30W MA (150-day SMA) + its 20-day slope.
    df = yf.download(symbol, period="15mo", interval="1d", progress=False, auto_adjust=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()


def publish(report: dict, session_date: str) -> None:  # pragma: no cover - DB
    import psycopg2
    dsn = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(dsn, connect_timeout=15)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO market_reports (kind, session_date, body, created_at) "
        "VALUES ('swing_setups', %s, %s, NOW())",
        (session_date, json.dumps(report)),
    )
    conn.commit()
    cur.close(); conn.close()


def main() -> None:  # pragma: no cover - manual/cron entrypoint
    import datetime as _dt
    dsn = os.getenv("DATABASE_URL")
    session_date = _dt.date.today().isoformat()
    if not dsn:
        # offline smoke: scan a few names, print the report, don't publish
        syms = sys.argv[1:] or ["AAPL", "MSFT", "NVDA", "MU", "PLTR"]
        rep = build_swing_report(syms, _yf_fetch, session_date)
        print(json.dumps(rep, indent=2))
        return
    syms = _watchlist(dsn)
    rep = build_swing_report(syms, _yf_fetch, session_date)
    publish(rep, session_date)
    print(json.dumps({"published": "swing_setups", "date": session_date,
                      "universe": rep["universe"], "counts": rep["counts"], "total": rep["total"]}))


if __name__ == "__main__":
    main()
