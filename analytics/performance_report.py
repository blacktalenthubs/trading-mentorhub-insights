#!/usr/bin/env python3
"""
Performance scorer + report.

Reads DELIVERED alerts from the DB, replays each against price at EOD, and scores a
BINARY outcome on the stop-is-judge rule:
    LOSS  = the stop was hit (before target)      — the trade failed, you're out
    WIN   = target hit before stop, OR neither hit and it closed >= entry
Also captures MFE / MAE / MaxDD / drawdown-past-stop + the lenient "above entry" flag.

Day styles   -> window = alert time .. 16:00 ET same session (5m bars).
Swing/Long   -> window = session .. +10 trading days (daily bars); 'open' if not elapsed.

Runs locally or on the triage worker (yfinance works there). Emits JSON + an HTML report
grouped the way the Performance page reads it: pattern leaderboard + per-date groups.

    python3 analytics/performance_report.py --start 2026-06-27 --end 2026-07-03
"""
import argparse, json, os, pickle, re, sys, warnings
from collections import defaultdict
from datetime import datetime, timedelta, date

warnings.filterwarnings("ignore")
CACHE = os.environ.get("PERF_CACHE", "/private/tmp/claude-501/-Users-mentorhub-Documents-master-domain-hub/46bb711a-7edb-4257-971e-b7f8964ba375/scratchpad/eval_cache")
os.makedirs(CACHE, exist_ok=True)

SWING_WINDOW_DAYS = 10

# ---- alert_type -> (pattern label, style) ---------------------------------------
def classify(alert_type: str):
    a = (alert_type or "").replace("tv_", "")
    T = [
        ("rc_4h",           "4h reclaim",            "Day"),
        ("rc_daily",        "Daily reclaim",         "Day"),
        ("weekly_rc",       "Weekly reclaim",        "Swing"),
        ("monthly_rc",      "Monthly reclaim",       "Long"),
        ("cml",             "Current-month low",     "Day"),
        ("ma_bounce",       "MA bounce",             "Day"),
        ("staged_pdl",      "PDL held",              "Day"),
        ("staged_pdh",      "PDH break",             "Day"),
        ("staged_pwl",      "PWL held",              "Swing"),
        ("staged_pwh",      "PWH break",             "Swing"),
        ("open_reclaim",    "Open reclaim",          "Day"),
        ("open_lost",       "Open lost",             "Day"),
        ("orb",             "ORB break",             "Day"),
        ("gap",             "Gap-and-go",            "Day"),
        ("weekly_10w",      "10w held",              "Long"),
        ("weekly_30w",      "30w held",              "Long"),
        ("pml_held",        "PML held",              "Long"),
        ("rsi_oversold",    "RSI oversold",          "Day"),
        ("ema_trend",       "EMA trend",             "Swing"),
        ("ema_pullback",    "EMA trend",             "Swing"),
    ]
    for key, label, style in T:
        if a.startswith(key):
            return label, style
    return a or "other", "Day"


# ---- price fetch (yfinance; Alpaca-first can be swapped in on triage) ------------
def _yf():
    import yfinance as yf
    return yf

def fetch_intraday(symbol, day):
    """5m bars for one session_date (ET)."""
    fp = f"{CACHE}/{symbol}_{day}_5m.pkl"
    if os.path.exists(fp):
        return pickle.load(open(fp, "rb"))
    import pandas as pd
    nxt = (datetime.strptime(day, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    df = _yf().download(symbol, start=day, end=nxt, interval="5m", progress=False, auto_adjust=False)
    if df is not None and len(df):
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.tz_convert("America/New_York")
    pickle.dump(df, open(fp, "wb"))
    return df

def fetch_daily(symbol, start, end):
    fp = f"{CACHE}/{symbol}_{start}_{end}_1d.pkl"
    if os.path.exists(fp):
        return pickle.load(open(fp, "rb"))
    import pandas as pd
    df = _yf().download(symbol, start=start, end=end, interval="1d", progress=False, auto_adjust=False)
    if df is not None and len(df) and isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    pickle.dump(df, open(fp, "wb"))
    return df


# ---- the core scoring rule ------------------------------------------------------
def score(entry, stop, target, direction, bars):
    """bars: iterable of (high, low, close) in time order. Returns outcome dict."""
    bars = [(float(h), float(l), float(c)) for h, l, c in bars]
    if not bars or entry is None or entry <= 0:
        return None
    long = (direction or "").upper() in ("BUY", "LONG")
    first_hit = "neither"
    lo_after_stop = None
    stopped_at_idx = None
    for i, (h, l, c) in enumerate(bars):
        hit_stop = (l <= stop) if long else (h >= stop)
        hit_tgt = (h >= target) if (long and target) else ((l <= target) if target else False)
        if hit_stop and hit_tgt:                      # same bar -> assume stop first (conservative)
            first_hit = "stop"; stopped_at_idx = i; break
        if hit_stop:
            first_hit = "stop"; stopped_at_idx = i; break
        if hit_tgt:
            first_hit = "target"; break
    highs = [b[0] for b in bars]; lows = [b[1] for b in bars]
    intraday_high, intraday_low = max(highs), min(lows)
    eod_close = bars[-1][2]
    if stopped_at_idx is not None:
        tail = lows[stopped_at_idx:]
        lo_after_stop = min(tail) if tail else stop

    def pct(a, b):
        return (a - b) / b * 100.0

    if long:
        mfe = pct(intraday_high, entry); mae = pct(entry, intraday_low)  # mae positive = adverse
        dd_past_stop = pct(stop, lo_after_stop) if lo_after_stop is not None else 0.0
        above_entry = intraday_high > entry
        realized_stop = pct(stop, entry) if first_hit == "stop" else None
    else:
        mfe = pct(entry, intraday_low); mae = pct(intraday_high, entry)
        dd_past_stop = pct(lo_after_stop, stop) if lo_after_stop is not None else 0.0
        above_entry = intraday_low < entry
        realized_stop = pct(entry, stop) if first_hit == "stop" else None

    if first_hit == "stop":
        result = "LOSS"
    elif first_hit == "target":
        result = "WIN"
    else:
        result = "WIN" if ((eod_close >= entry) if long else (eod_close <= entry)) else "LOSS"

    return dict(result=result, first_hit=first_hit, above_entry=above_entry,
                intraday_high=round(intraday_high, 2), intraday_low=round(intraday_low, 2),
                eod_close=round(eod_close, 2), mfe_pct=round(mfe, 2), mae_pct=round(-mae, 2),
                max_dd_pct=round(-mae, 2), dd_past_stop_pct=round(dd_past_stop, 2),
                realized_stop_pct=round(realized_stop, 2) if realized_stop is not None else None)


def score_day(alert):
    df = fetch_intraday(alert["symbol"], alert["session_date"])
    if df is None or not len(df):
        return None
    d = df[df.index.strftime("%Y-%m-%d") == alert["session_date"]].between_time("09:30", "15:59")
    if not len(d):
        return None
    at = alert.get("alert_et")
    win = d.between_time(at, "15:59") if at else d
    if not len(win):
        win = d
    return score(alert["entry"], alert["stop"], alert["target"], alert["direction"],
                 zip(win["High"], win["Low"], win["Close"]))


def score_swing(alert):
    start = alert["session_date"]
    # Day 1 = POST-ALERT intraday only (the full daily bar's low leaks pre-alert price
    # and false-triggers the stop). Days 2..N = daily bars strictly after the alert day.
    bars = []
    intr = fetch_intraday(alert["symbol"], start)
    if intr is not None and len(intr):
        d1 = intr[intr.index.strftime("%Y-%m-%d") == start].between_time("09:30", "15:59")
        at = alert.get("alert_et")
        w = d1.between_time(at, "15:59") if at else d1
        if len(w):
            bars.append((float(w["High"].max()), float(w["Low"].min()), float(w["Close"].iloc[-1])))
    end = (datetime.strptime(start, "%Y-%m-%d") + timedelta(days=SWING_WINDOW_DAYS + 6)).strftime("%Y-%m-%d")
    dd = fetch_daily(alert["symbol"], start, end)
    if dd is not None and len(dd):
        later = dd[dd.index.strftime("%Y-%m-%d") > start].head(SWING_WINDOW_DAYS - 1)
        bars += [(float(h), float(l), float(c)) for h, l, c in zip(later["High"], later["Low"], later["Close"])]
    if not bars:
        return None
    out = score(alert["entry"], alert["stop"], alert["target"], alert["direction"], bars)
    if out:
        out["open"] = len(bars) < SWING_WINDOW_DAYS and out["first_hit"] == "neither"
        out["sessions_elapsed"] = len(bars)
    return out


def load_alerts(start, end):
    import psycopg2
    dsn = re.search(r'^DATABASE_URL=(.+)$', open(".env").read(), re.M).group(1).strip()
    conn = psycopg2.connect(dsn); conn.set_session(readonly=True); cur = conn.cursor()
    cur.execute("""
        SELECT symbol, direction, alert_type, entry, stop, target_1, session_date,
               to_char(min(created_at) - interval '4 hours', 'HH24:MI') et
        FROM alerts
        WHERE suppressed_reason IS NULL AND session_date BETWEEN %s AND %s
          AND entry IS NOT NULL AND entry > 0 AND direction IN ('BUY','LONG')
        GROUP BY symbol, direction, alert_type, entry, stop, target_1, session_date
        ORDER BY session_date, et
    """, (start, end))
    rows = cur.fetchall(); conn.close()
    out = []
    for sym, dirn, atype, entry, stop, tgt, sd, et in rows:
        label, style = classify(atype)
        out.append(dict(symbol=sym, direction=dirn, alert_type=atype, pattern=label, style=style,
                        entry=float(entry), stop=float(stop) if stop else None,
                        target=float(tgt) if tgt else None,
                        session_date=str(sd), alert_et=et))
    return out


def prefetch_intraday(alerts):
    """Batch-download 5m per day (chunks of 30) into the per-symbol-day cache — far fewer
    yfinance calls than one-at-a-time, and caches misses so we don't retry them."""
    import pandas as pd
    byday = defaultdict(set)
    for a in alerts:
        byday[a["session_date"]].add(a["symbol"])
    for day in sorted(byday):
        need = [s for s in byday[day] if not os.path.exists(f"{CACHE}/{s}_{day}_5m.pkl")]
        nxt = (datetime.strptime(day, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        for i in range(0, len(need), 30):
            chunk = need[i:i+30]
            try:
                df = _yf().download(" ".join(chunk), start=day, end=nxt, interval="5m",
                                    group_by="ticker", progress=False, auto_adjust=False, threads=True)
            except Exception:
                df = None
            for s in chunk:
                sub = None
                try:
                    if df is not None and len(df):
                        if len(chunk) == 1:
                            sub = df
                        elif s in df.columns.get_level_values(0):
                            sub = df[s].dropna()
                    if sub is not None and len(sub):
                        if isinstance(sub.columns, pd.MultiIndex):
                            sub.columns = sub.columns.get_level_values(0)
                        sub = sub.tz_convert("America/New_York")
                except Exception:
                    sub = None
                pickle.dump(sub, open(f"{CACHE}/{s}_{day}_5m.pkl", "wb"))
        print(f"  prefetched {day}: {len(need)} symbols")

def run(start, end):
    alerts = load_alerts(start, end)
    print(f"loaded {len(alerts)} delivered long alerts {start}..{end}")
    print("prefetching intraday (batched)...")
    prefetch_intraday(alerts)
    scored = []
    for a in alerts:
        if a["stop"] is None:
            continue
        try:
            o = score_swing(a) if a["style"] in ("Swing", "Long") else score_day(a)
        except Exception as e:
            o = None
        if o:
            scored.append({**a, **o})
    print(f"scored {len(scored)}")
    return scored


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--out", default="performance_report.json")
    args = ap.parse_args()
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (for .env)
    scored = run(args.start, args.end)
    json.dump(scored, open(args.out, "w"), indent=2, default=str)
    # quick console summary
    byp = defaultdict(list)
    for s in scored:
        byp[s["pattern"]].append(s)
    print("\n=== pattern leaderboard (win = stop-is-judge) ===")
    lb = []
    for pat, items in byp.items():
        closed = [i for i in items if not i.get("open")]
        if not closed:
            continue
        wins = sum(1 for i in closed if i["result"] == "WIN")
        wr = wins * 100 // len(closed)
        mfe = sorted(i["mfe_pct"] for i in closed)[len(closed)//2]
        lb.append((wr, pat, len(closed), mfe))
    for wr, pat, n, mfe in sorted(lb, reverse=True):
        print(f"  {wr:>3}%  {pat:22} n={n:<4} medMFE {mfe:+.1f}%")
    print(f"\nwrote {args.out}")
