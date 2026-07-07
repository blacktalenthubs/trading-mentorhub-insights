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
import tempfile
CACHE = os.environ.get("PERF_CACHE") or os.path.join(tempfile.gettempdir(), "perf_cache")
os.makedirs(CACHE, exist_ok=True)


def _dsn():
    """DATABASE_URL from the environment first (Railway / triage worker), then a local
    .env fallback (dev). Lets the same scorer run locally and on the triage cron."""
    v = os.environ.get("DATABASE_URL")
    if v:
        return v.strip()
    return re.search(r'^DATABASE_URL=(.+)$', open(".env").read(), re.M).group(1).strip()

SWING_WINDOW_DAYS = 10
CRYPTO_WINDOW_DAYS = int(os.environ.get("CRYPTO_WINDOW_DAYS", "5"))   # crypto = 24/7, judge N days from entry

# ---- alert_type -> (pattern label, style) ---------------------------------------
def classify(alert_type: str):
    a = (alert_type or "").replace("tv_", "")
    T = [
        ("rc_4h",           "4h reclaim",            "Day"),
        ("rc_daily",        "Daily reclaim",         "Day"),
        ("weekly_rc",       "Weekly reclaim",        "Day"),   # a reclaim is a day-trade tool, not a hold (2026-07-07)
        ("monthly_rc",      "Monthly reclaim",       "Day"),   # reclaim = day-trade tool
        ("cml",             "Current-month low",     "Day"),
        ("ma_bounce_long_v3_ema200", "200-EMA hold",     "Swing"),  # sustained trend support — a swing (user 2026-07-07)
        ("ma_bounce",       "MA bounce",             "Day"),
        ("staged_pdl",      "PDL held",              "Day"),
        ("staged_pdh",      "PDH break",             "Day"),
        ("staged_pwl",      "PWL held",              "Day"),   # level hold = day-trade tool
        ("staged_pwh",      "PWH break",             "Swing"),
        ("open_reclaim",    "Open reclaim",          "Day"),
        ("open_lost",       "Open lost",             "Day"),
        ("orb",             "ORB break",             "Day"),
        ("gap",             "Gap-and-go",            "Day"),
        ("weekly_10w",      "10w held",              "Long"),
        ("weekly_30w",      "30w held",              "Long"),
        ("pml_held",        "PML held",              "Long"),
        ("rsi_oversold",    "RSI 30 buy",            "Swing"),  # oversold reclaim — a multi-day bottom, not a day trade
        ("ema_5_20",         "5/20 EMA cross",        "Swing"),  # Steve Burns 5/20 — a sustained trend flip (swing)
        ("ema_trend",       "EMA trend",             "Swing"),
        ("ema_pullback",    "EMA trend",             "Swing"),
        ("character_change", "Character Change",      "Swing"),
        ("base_buy",        "Buying in Bases",       "Swing"),
    ]
    for key, label, style in T:
        if a.startswith(key):
            return label, style
    return a or "other", "Day"


def is_crypto(symbol):
    """Crypto trades 24/7 — no RTH session, no EOD close. yfinance stores it as '<X>-USD'."""
    return (symbol or "").upper().endswith("-USD")


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
def score(entry, stop, target, direction, bars, mode="day"):
    """bars: iterable of (high, low, close) in time order. Returns outcome dict.

    DAY trades are judged purely on INTRADAY MOVEMENT — the alert targets are unreliable for
    day trades (often 10-40 R:R), so we ignore them: a day trade is a WIN if the intraday high
    cleared entry (you take the intraday pop), LOSS if it never went green.

    SWING/LONG trades are judged at the LATEST price: WIN if the stop was never hit AND price
    is above entry; LOSS if the stop was hit; still-OPEN if the stop held but it's not yet
    above entry (exit zone is RSI ~50-70; the thing that kills it is the stop)."""
    bars = [(float(h), float(l), float(c)) for h, l, c in bars]
    if not bars or entry is None or entry <= 0:
        return None
    long = (direction or "").upper() in ("BUY", "LONG")
    # only honor a stop that sits on the risk side of entry (level alerts store the level in
    # entry AND stop → no real stop; don't let a phantom stop decide anything)
    valid_stop = stop is not None and stop > 0 and (stop < entry if long else stop > entry)
    intraday_high = max(b[0] for b in bars)
    intraday_low = min(b[1] for b in bars)
    eod_close = bars[-1][2]

    def pct(a, b):
        return (a - b) / b * 100.0

    lo_close = min(b[2] for b in bars); hi_close = max(b[2] for b in bars)
    if long:
        mfe = pct(intraday_high, entry); mae = pct(intraday_low, entry)   # mae <= 0
        above_entry = intraday_high > entry
        # SWING stops on a CLOSE below the level (that's how swings exit — not an intraday wick).
        stop_hit = valid_stop and (lo_close <= stop if mode != "day" else intraday_low <= stop)
        dd_past_stop = pct(intraday_low, stop) if stop_hit else 0.0
        realized_stop = pct(stop, entry) if stop_hit else None
        closed_green = eod_close > entry
    else:
        mfe = pct(entry, intraday_low); mae = pct(entry, intraday_high)   # mae <= 0
        above_entry = intraday_low < entry
        stop_hit = valid_stop and (hi_close >= stop if mode != "day" else intraday_high >= stop)
        dd_past_stop = pct(stop, intraday_high) if stop_hit else 0.0
        realized_stop = pct(entry, stop) if stop_hit else None
        closed_green = eod_close < entry

    is_open = False
    if mode == "day":
        # TRUE state — don't assume the user sold the high. A day trade with a stop is a WIN
        # only if it reached a REALISTIC profit (+1R off the stop) BEFORE the stop was hit;
        # if the stop came first, they were stopped out = LOSS. Sequence-aware (walk the bars).
        # Alert targets are ignored (unreliable, 10-40 R:R). No real stop -> judged by close.
        if valid_stop:
            r1 = 2 * entry - stop                          # entry + risk (1:1) = a realistic day target
            first = "neither"
            for h, l, c in bars:
                if (l <= stop) if long else (h >= stop):
                    first = "stop"; break
                if (h >= r1) if long else (l <= r1):
                    first = "target"; break
            result = "WIN" if first == "target" else ("LOSS" if first == "stop" else ("WIN" if closed_green else "LOSS"))
        else:
            result = "WIN" if above_entry else "LOSS"
    elif stop_hit:
        result = "LOSS"
    elif closed_green:
        result = "WIN"                                     # swing: stop intact + above entry = win
    else:
        result = "LOSS"; is_open = True                    # swing: stop held, not yet green -> pending

    return dict(result=result, above_entry=above_entry, open=is_open, stop_hit=bool(stop_hit),
                intraday_high=round(intraday_high, 2), intraday_low=round(intraday_low, 2),
                eod_close=round(eod_close, 2), mfe_pct=round(mfe, 2), mae_pct=round(mae, 2),
                max_dd_pct=round(mae, 2), dd_past_stop_pct=round(dd_past_stop, 2),
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
        # late/after-hours alert (fired after 15:59) — DROP it rather than fall back to the
        # whole session, which would score it against pre-entry price (lookahead). Nothing
        # that couldn't be filled after the alert should ever count.
        return None
    out = score(alert["entry"], alert["stop"], alert["target"], alert["direction"],
                zip(win["High"], win["Low"], win["Close"]))
    if out and at:
        # Timestamp the intraday PATH (entry / high / low / close) so the UI can PROVE the
        # favorable move came AFTER the alert fired — a high before entry never counts.
        try:
            out["entry_et"] = at
            out["hi_et"] = win["High"].idxmax().strftime("%H:%M")
            out["lo_et"] = win["Low"].idxmin().strftime("%H:%M")
            out["eod_et"] = win.index[-1].strftime("%H:%M")
        except Exception:
            pass
    return out


def score_swing(alert, crypto=False):
    start = alert["session_date"]
    # Day 1 = POST-ALERT price only (the full daily bar's low leaks pre-alert price and
    # false-triggers the stop). Days 2..N = daily bars after the alert day. CRYPTO = 24/7, so
    # no RTH slice — use the whole day from the alert time (crypto daily bars are 24h too).
    bars = []
    intr = fetch_intraday(alert["symbol"], start)
    if intr is not None and len(intr):
        day = intr[intr.index.strftime("%Y-%m-%d") == start]
        d1 = day if crypto else day.between_time("09:30", "15:59")
        at = alert.get("alert_et")
        w = d1.between_time(at, "23:59" if crypto else "15:59") if at else d1
        if len(w):
            bars.append((float(w["High"].max()), float(w["Low"].min()), float(w["Close"].iloc[-1])))
    # days 2..TODAY — a swing is judged at the LATEST price, not a fixed 10-day window
    end = (date.today() + timedelta(days=2)).isoformat()
    dd = fetch_daily(alert["symbol"], start, end)
    if dd is not None and len(dd):
        later = dd[dd.index.strftime("%Y-%m-%d") > start]
        if crypto:
            later = later.head(CRYPTO_WINDOW_DAYS - 1)   # crypto swing = a few days from entry, not weeks
        bars += [(float(h), float(l), float(c)) for h, l, c in zip(later["High"], later["Low"], later["Close"])]
    if not bars:
        return None
    out = score(alert["entry"], alert["stop"], alert["target"], alert["direction"], bars, mode="swing")
    if out:
        out["sessions_elapsed"] = len(bars)
    return out


def load_alerts(start, end):
    import psycopg2
    dsn = _dsn()
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
        if is_crypto(sym):
            style = "Swing"      # 24/7 → no session/EOD, judge over days from entry
        out.append(dict(symbol=sym, direction=dirn, alert_type=atype, pattern=label, style=style,
                        crypto=is_crypto(sym),
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
            if a.get("crypto"):
                o = score_swing(a, crypto=True)      # 24/7 — days-from-entry, no RTH/EOD
            elif a["style"] in ("Swing", "Long"):
                o = score_swing(a)
            else:
                o = score_day(a)
        except Exception:
            o = None
        if o:
            scored.append({**a, **o})
    print(f"scored {len(scored)}")
    return scored


def publish(scored, start, end):
    """Upsert the scored-alert blob into market_reports[kind=performance] — the /performance
    API reads the latest of these. No price fetching ever happens in the cloud API this way."""
    import psycopg2
    dsn = _dsn()
    body = json.dumps({"start": start, "end": end, "alerts": scored}, default=str)
    conn = psycopg2.connect(dsn); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS market_reports (
        kind TEXT NOT NULL, session_date TEXT NOT NULL, body TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(), PRIMARY KEY (kind, session_date))""")
    cur.execute("""INSERT INTO market_reports (kind, session_date, body) VALUES ('performance', %s, %s)
        ON CONFLICT (kind, session_date) DO UPDATE SET body = EXCLUDED.body, created_at = NOW()""",
                (end, body))
    conn.commit(); conn.close()
    print(f"published -> market_reports[performance] session_date={end}, {len(scored)} alerts")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--days", type=int, help="score the last N calendar days ending today (for the cron)")
    ap.add_argument("--out", default="performance_report.json")
    ap.add_argument("--publish", action="store_true", help="upsert into market_reports for the API")
    args = ap.parse_args()
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (for .env fallback)
    if args.days:
        end = date.today().isoformat()
        start = (date.today() - timedelta(days=args.days)).isoformat()
    elif args.start and args.end:
        start, end = args.start, args.end
    else:
        ap.error("need --days OR both --start and --end")
    scored = run(start, end)
    json.dump(scored, open(args.out, "w"), indent=2, default=str)
    if args.publish:
        publish(scored, start, end)
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
