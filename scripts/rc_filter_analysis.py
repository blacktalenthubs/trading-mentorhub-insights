#!/usr/bin/env python3
"""Offline RC filter analysis — DATA FIRST, no filtering applied.

Goal (per founder): before adding any quality filter to the 4h RC (and weekly
RC) alerts, measure what actually works. We pull every RC fire we've logged,
reconstruct the OUTCOME and candidate FEATURES from market data, and report
which features separate winners from losers — so a filter is chosen on
evidence, and we can see the real lift without losing genuine signals.

Outcome convention mirrors analytics/alert_outcomes.py exactly:
    R   = (price - E) / (E - S)          # long
    MFE = max R reached, MAE = min R reached
    worked  = MFE hits +1R before MAE hits -1R
    failed  = MAE hits -1R first
    inconclusive = neither within the forward window
    same-bar tie -> failed (conservative)

Candidate features (computed at fire time, never used to filter here):
    undercut_pct   how far the RC candle's low dug below the prior candle's low
    risk_pct       (entry-stop)/entry*100  — the R size as a % (tight vs wide)
    vol_ratio      RC candle volume / trailing average (real stop-run?)
    rsi_14         daily RSI at fire (oversold reclaim vs mid-range)
    hour_et        time of day
    spy_day_chg    SPY % change that session (tape regime)

Usage:
    DBURL='postgresql://...'  python3 scripts/rc_filter_analysis.py
    (reads DBURL or DATABASE_URL from the env — no secret in this file)

Optional args:
    --rule rc_4h|weekly_stage|both   (default both)
    --days N                          lookback window (default 14)
    --fwd-bars N                      forward 15m bars to score outcome (default 52 ~ 2 sessions)
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import psycopg2
import yfinance as yf

ET = "America/New_York"


# ---------------------------------------------------------------- data pull
def fetch_rc_fires(dburl: str, rules: list[str], days: int) -> pd.DataFrame:
    """Distinct RC fires (collapse the per-user fan-out)."""
    con = psycopg2.connect(dburl)
    con.set_session(readonly=True)
    q = """
        SELECT DISTINCT ON (alert_type, symbol, price, created_at)
               alert_type, symbol, direction, price, entry, stop,
               created_at, session_date
        FROM alerts
        WHERE alert_type = ANY(%s)
          AND created_at > NOW() - (INTERVAL '1 day' * %s)
        ORDER BY alert_type, symbol, price, created_at
    """
    tv_rules = [f"tv_{r}" for r in rules]
    df = pd.read_sql_query(q, con, params=(tv_rules, days))
    con.close()
    return df


# ---------------------------------------------------------------- market data
_BAR_CACHE: dict = {}


def bars(symbol: str, interval: str, period: str) -> pd.DataFrame | None:
    key = (symbol, interval, period)
    if key in _BAR_CACHE:
        return _BAR_CACHE[key]
    try:
        df = yf.Ticker(symbol).history(period=period, interval=interval)
        if df.empty:
            df = None
        else:
            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    except Exception:
        df = None
    _BAR_CACHE[key] = df
    return df


def to_et_naive(ts) -> pd.Timestamp:
    """DB created_at is UTC; convert to naive ET to compare with yfinance bars."""
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return t.tz_convert(ET).tz_localize(None)


# ---------------------------------------------------------------- outcome
def classify_long(fwd: pd.DataFrame, entry: float, stop: float) -> dict:
    risk = entry - stop
    if risk <= 0 or fwd is None or len(fwd) == 0:
        return {"outcome": None, "mfe_r": None, "mae_r": None}
    mfe = mae = 0.0
    outcome = None
    for _, r in fwd.iterrows():
        hi = (r["High"] - entry) / risk
        lo = (r["Low"] - entry) / risk
        mfe = max(mfe, hi)
        mae = min(mae, lo)
        if lo <= -1.0:
            outcome = "failed"
            break
        if hi >= 1.0:
            outcome = "worked"
            break
    return {"outcome": outcome or "inconclusive", "mfe_r": round(mfe, 3), "mae_r": round(mae, 3)}


def rsi(closes: pd.Series, n: int = 14) -> float | None:
    if len(closes) < n + 1:
        return None
    d = closes.diff().dropna()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    val = 100 - 100 / (1 + rs.iloc[-1])
    return None if pd.isna(val) else round(float(val), 1)


# ---------------------------------------------------------------- per-fire enrichment
def enrich(row, fwd_bars: int, spy_daily: pd.DataFrame) -> dict | None:
    sym = row["symbol"]
    entry, stop = row["entry"], row["stop"]
    if entry is None or stop is None or entry <= stop:
        return None
    fire_et = to_et_naive(row["created_at"])

    # forward outcome from 15m bars
    intr = bars(sym, "15m", "30d")
    out = {"outcome": None, "mfe_r": None, "mae_r": None}
    if intr is not None:
        idx = intr.index.tz_localize(None) if intr.index.tz is not None else intr.index
        intr = intr.copy()
        intr.index = idx
        fwd = intr[intr.index > fire_et].head(fwd_bars)
        out = classify_long(fwd, entry, stop)

    # features from 4h bars
    undercut = vol_ratio = None
    h4 = bars(sym, "4h", "30d")
    if h4 is not None:
        i4 = h4.index.tz_localize(None) if h4.index.tz is not None else h4.index
        h4 = h4.copy()
        h4.index = i4
        # RC candle = the 4h bar whose low is closest to the stamped stop, near fire
        near = h4[(h4.index <= fire_et + pd.Timedelta(hours=5))].tail(8)
        if len(near) >= 2:
            cand = (near["Low"] - stop).abs().idxmin()
            pos = near.index.get_loc(cand)
            if pos >= 1:
                prior_low = near["Low"].iloc[pos - 1]
                if prior_low > 0:
                    undercut = round((prior_low - near["Low"].iloc[pos]) / prior_low * 100, 3)
            vavg = h4["Volume"].rolling(20).mean()
            v_at = h4["Volume"].get(cand)
            v_av = vavg.get(cand)
            if v_at and v_av and v_av > 0:
                vol_ratio = round(float(v_at / v_av), 2)

    # daily RSI up to fire date
    dy = bars(sym, "1d", "3mo")
    rsi14 = None
    if dy is not None:
        di = dy.index.tz_localize(None) if dy.index.tz is not None else dy.index
        dyc = dy.copy()
        dyc.index = di
        upto = dyc[dyc.index <= fire_et]["Close"]
        rsi14 = rsi(upto)

    # SPY tape regime that session
    spy_chg = None
    if spy_daily is not None:
        sd = pd.Timestamp(row["session_date"])
        match = spy_daily[spy_daily.index.normalize() == sd.normalize()]
        if len(match):
            o, c = match["Open"].iloc[0], match["Close"].iloc[0]
            if o:
                spy_chg = round((c - o) / o * 100, 2)

    return {
        "rule": row["alert_type"].replace("tv_", ""),
        "symbol": sym,
        "fire_et": fire_et.strftime("%m-%d %H:%M"),
        "entry": entry, "stop": stop,
        "risk_pct": round((entry - stop) / entry * 100, 2),
        "undercut_pct": undercut,
        "vol_ratio": vol_ratio,
        "rsi_14": rsi14,
        "hour_et": fire_et.hour,
        "spy_day_chg": spy_chg,
        **out,
    }


# ---------------------------------------------------------------- reporting
def winrate(rows: list[dict]) -> str:
    w = sum(1 for r in rows if r["outcome"] == "worked")
    f = sum(1 for r in rows if r["outcome"] == "failed")
    inc = sum(1 for r in rows if r["outcome"] == "inconclusive")
    dec = w + f
    wr = f"{100*w/dec:.0f}%" if dec else "n/a"
    mfe = np.mean([r["mfe_r"] for r in rows if r["mfe_r"] is not None]) if rows else 0
    mae = np.mean([r["mae_r"] for r in rows if r["mae_r"] is not None]) if rows else 0
    return f"n={len(rows):3} win={wr:>4} (W{w}/L{f}/inc{inc})  avgMFE={mfe:+.2f}R avgMAE={mae:+.2f}R"


def bucket_report(rows: list[dict], feat: str, edges: list[float], label: str) -> list[str]:
    out = [f"\n  by {label}:"]
    vals = [(r, r[feat]) for r in rows if r.get(feat) is not None]
    if not vals:
        return out + ["    (no data)"]
    buckets = defaultdict(list)
    for r, v in vals:
        placed = False
        for i in range(len(edges) - 1):
            if edges[i] <= v < edges[i + 1]:
                buckets[f"{edges[i]:g}..{edges[i+1]:g}"].append(r)
                placed = True
                break
        if not placed:
            buckets[f">={edges[-1]:g}"].append(r)
    for b in sorted(buckets):
        out.append(f"    {b:>12}: {winrate(buckets[b])}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rule", default="both", choices=["rc_4h", "weekly_stage", "both"])
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--fwd-bars", type=int, default=52)
    args = ap.parse_args()

    dburl = os.environ.get("DBURL") or os.environ.get("DATABASE_URL")
    if not dburl:
        sys.exit("ERROR: set DBURL (or DATABASE_URL) in the environment.")

    rules = ["rc_4h", "weekly_stage"] if args.rule == "both" else [args.rule]
    df = fetch_rc_fires(dburl, rules, args.days)
    if df.empty:
        sys.exit(f"No RC fires found for {rules} in the last {args.days} days.")
    print(f"Pulled {len(df)} distinct RC fires ({', '.join(rules)}, last {args.days}d). Scoring…", file=sys.stderr)

    spy_daily = bars("SPY", "1d", "3mo")
    rows = []
    for _, r in df.iterrows():
        e = enrich(r, args.fwd_bars, spy_daily)
        if e:
            rows.append(e)

    # ---- report ----
    lines = []
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"# RC filter analysis — {stamp}")
    lines.append(f"Scored {len(rows)} RC fires (last {args.days}d). Outcome = R-multiple, +1R before -1R.\n")

    for rule in rules:
        rr = [r for r in rows if r["rule"] == rule]
        if not rr:
            continue
        lines.append(f"\n## {rule}  —  {winrate(rr)}")
        lines += bucket_report(rr, "undercut_pct", [0, 0.25, 0.5, 1.0, 2.0], "undercut depth %")
        lines += bucket_report(rr, "risk_pct", [0, 0.5, 1.0, 2.0, 4.0], "risk (stop) %")
        lines += bucket_report(rr, "vol_ratio", [0, 0.8, 1.0, 1.5, 2.5], "4h volume ratio")
        lines += bucket_report(rr, "rsi_14", [0, 30, 45, 55, 70], "daily RSI")
        lines += bucket_report(rr, "hour_et", [7, 10, 12, 14, 16], "hour ET")
        lines += bucket_report(rr, "spy_day_chg", [-5, -1, 0, 1, 5], "SPY day %")

    # per-fire table
    lines.append("\n## raw fires (audit)")
    lines.append(f"  {'rule':12} {'sym':6} {'fired':11} {'entry':>8} {'risk%':>5} {'under%':>6} {'vol':>4} {'rsi':>4} {'out':>6} {'mfe':>5} {'mae':>6}")
    for r in sorted(rows, key=lambda x: (x["rule"], x["fire_et"])):
        lines.append(f"  {r['rule']:12} {r['symbol']:6} {r['fire_et']:11} {r['entry']:8} "
                     f"{r['risk_pct']:5} {str(r['undercut_pct']):>6} {str(r['vol_ratio']):>4} "
                     f"{str(r['rsi_14']):>4} {str(r['outcome'])[:6]:>6} {str(r['mfe_r']):>5} {str(r['mae_r']):>6}")

    report = "\n".join(lines)
    print(report)
    outdir = os.path.join(os.path.dirname(__file__), "..", "reports")
    os.makedirs(outdir, exist_ok=True)
    fn = os.path.join(outdir, f"rc_filter_analysis_{datetime.now(timezone.utc):%Y-%m-%d}.md")
    with open(fn, "w") as f:
        f.write(report + "\n")
    print(f"\n[saved] {os.path.abspath(fn)}", file=sys.stderr)


if __name__ == "__main__":
    main()
