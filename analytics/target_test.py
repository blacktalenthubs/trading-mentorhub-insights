#!/usr/bin/env python3
"""
Target-scheme A/B test — does an ATR-based target beat the current "next resistance level"?

Current system (analytics/target_picker.py + exit_plan.py): a DAY trade's target is the
nearest resistance LEVEL above entry. Problem (proven by the Performance page): that level is
often 10%+ away (10-40 R:R), so it's rarely reached intraday and the trade rides back to the
stop = LOSS.

This replays every real DELIVERED DAY-trade alert against its actual 5-min intraday path and,
for each of several target schemes, simulates taking profit at the target (limit) or the stop,
sequence-aware. It reports, per scheme: how often the target was hit, and the AVG REALIZED %
per trade (the expectancy) — assuming a disciplined exit at target-or-stop.

    python3 analytics/target_test.py

Reads the perf backfill JSON (entry/stop/target/symbol/date already there) + the warm 5-min
cache the scorer built; fetches daily bars once per symbol for ATR(14).
"""
import json, os, pickle, warnings
from collections import defaultdict
warnings.filterwarnings("ignore")

CACHE = os.environ.get("PERF_CACHE", "/tmp/perf_cache")
BACKFILL = os.environ.get("PERF_JSON",
    "/private/tmp/claude-501/-Users-mentorhub-Documents-master-domain-hub/46bb711a-7edb-4257-971e-b7f8964ba375/scratchpad/perf_backfill.json")

def _yf():
    import yfinance as yf
    return yf

def daily_atr(symbol, first_date, period=14):
    """ATR(14) series (dict date->atr) from daily bars; as-of, no lookahead."""
    import pandas as pd
    from datetime import datetime, timedelta
    fp = f"{CACHE}/{symbol}_atr.pkl"
    if os.path.exists(fp):
        return pickle.load(open(fp, "rb"))
    start = (datetime.strptime(first_date, "%Y-%m-%d") - timedelta(days=60)).strftime("%Y-%m-%d")
    df = _yf().download(symbol, start=start, interval="1d", progress=False, auto_adjust=False)
    out = {}
    if df is not None and len(df):
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        pc = df["Close"].shift(1)
        tr = pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        for ix, v in atr.items():
            if v == v:  # not NaN
                out[ix.strftime("%Y-%m-%d")] = float(v)
    pickle.dump(out, open(fp, "wb"))
    return out

def atr_asof(atr_map, day):
    """ATR as of the last trading day <= the alert day (no lookahead)."""
    keys = sorted(k for k in atr_map if k <= day)
    return atr_map[keys[-1]] if keys else None

def intraday(symbol, day):
    fp = f"{CACHE}/{symbol}_{day}_5m.pkl"
    return pickle.load(open(fp, "rb")) if os.path.exists(fp) else None

def simulate(entry, stop, tgt, alert_et, bars):
    """Walk 5m bars from the alert; return realized % taking profit at tgt (limit) or stop."""
    d = bars.between_time(alert_et or "09:30", "15:59") if alert_et else bars
    if not len(d):
        return None
    for _, b in d.iterrows():
        if float(b["Low"]) <= stop:   return (stop - entry) / entry * 100.0   # stopped first
        if float(b["High"]) >= tgt:   return (tgt - entry) / entry * 100.0    # target first
    return (float(d["Close"].iloc[-1]) - entry) / entry * 100.0               # neither -> EOD

def main():
    S = json.load(open(BACKFILL))
    day = [x for x in S if x["style"] == "Day" and x.get("stop") and x.get("target")
           and x["stop"] < x["entry"] < x["target"]]   # valid long day trades with a real stop+target
    print(f"{len(day)} day-trade alerts with a valid stop+target")

    # ATR per symbol
    atr_maps = {}
    for sym in sorted({x["symbol"] for x in day}):
        atr_maps[sym] = daily_atr(sym, min(x["session_date"] for x in day if x["symbol"] == sym))

    SCHEMES = ["current", "atr0.75", "atr1.0", "atr1.5", "atr_cap1.0"]
    agg = {s: {"n": 0, "hit": 0, "realized": [], "wins": 0} for s in SCHEMES}
    bypat = defaultdict(lambda: {s: [] for s in SCHEMES})

    for x in day:
        bars = intraday(x["symbol"], x["session_date"])
        if bars is None or not len(bars):
            continue
        d = bars[bars.index.strftime("%Y-%m-%d") == x["session_date"]].between_time("09:30", "15:59")
        if not len(d):
            continue
        e, stp = x["entry"], x["stop"]
        atr = atr_asof(atr_maps.get(x["symbol"], {}), x["session_date"])
        if not atr:
            continue
        targets = {
            "current": x["target"],
            "atr0.75": e + 0.75 * atr,
            "atr1.0": e + 1.0 * atr,
            "atr1.5": e + 1.5 * atr,
            "atr_cap1.0": min(e + 1.0 * atr, x["target"]),   # ATR distance, but never past the level
        }
        for s, tg in targets.items():
            r = simulate(e, stp, tg, x.get("alert_et"), d)
            if r is None:
                continue
            a = agg[s]; a["n"] += 1; a["realized"].append(r)
            if abs(r - (tg - e) / e * 100.0) < 1e-6: a["hit"] += 1
            if r > 0: a["wins"] += 1
            bypat[x["pattern"]][s].append(r)

    import statistics as st
    print(f"\n{'scheme':<12} {'n':>4} {'tgt-hit':>8} {'win%':>6} {'avg R%':>8} {'median':>8}  (realized % per trade, exit at tgt-or-stop)")
    for s in SCHEMES:
        a = agg[s]
        if not a["n"]:
            continue
        avg = st.mean(a["realized"]); med = st.median(a["realized"])
        print(f"{s:<12} {a['n']:>4} {a['hit']*100//a['n']:>7}% {a['wins']*100//a['n']:>5}% {avg:>+7.2f}% {med:>+7.2f}%")

    print(f"\n=== avg realized % by pattern (current vs atr1.0 vs atr_cap1.0) ===")
    print(f"{'pattern':<20} {'n':>4} {'current':>9} {'atr1.0':>9} {'cap1.0':>9}")
    for p, sch in sorted(bypat.items(), key=lambda kv: -len(kv[1]['current'])):
        n = len(sch["current"])
        if n < 8:
            continue
        c = st.mean(sch["current"]); a1 = st.mean(sch["atr1.0"]); ac = st.mean(sch["atr_cap1.0"])
        print(f"{p:<20} {n:>4} {c:>+8.2f}% {a1:>+8.2f}% {ac:>+8.2f}%")

if __name__ == "__main__":
    main()
