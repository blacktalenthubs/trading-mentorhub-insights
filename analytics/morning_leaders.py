#!/usr/bin/env python3
"""Morning "Leaders Near a Buy Point" — the IBD-modeled top-3 focus picks.

NOT premarket gappers. The bar (IBD Leaderboard): a market LEADER (high RS / leading
group), sitting AT or just below a defined BUY POINT (the pivot = the high of its base),
INSIDE the buy zone (pivot → +5%, not extended), on a VOLUME surge, in a HEALTHY market.
"Near the 20 EMA" is not a reason — the buy point is.

Runs locally (yfinance works off-cloud). Prints a markdown report + JSON the morning
agent pushes to all users (market_reports kind=morning_focus).

    DATABASE_URL=postgresql://... python3 analytics/morning_leaders.py \
        --ibd50 ../ibd50.xls --leaders ../sectorleaders.xls --top 3

Scoring (gate = ALL must hold): leader (IBD RS ≥ rs_min OR sector-leader), Stage-2
(above the 200-DMA), price IN the buy zone (within ±zone% of its base pivot), and the
market OK (SPY above its 8 & 21 EMA). Ranked by RS + volume + proximity to the pivot.
"""
from __future__ import annotations
import argparse, collections, json, os, sys
from datetime import datetime


def _ibd(path):
    """symbol -> {rank, comp, eps, rs, group} from an IBD/MarketSurge .xls export."""
    import pandas as pd
    out = {}
    if not path or not os.path.exists(path):
        return out
    df = pd.read_excel(path, header=None)
    hdr = next(i for i in range(min(10, len(df)))
               if "Symbol" in [str(x).strip() for x in df.iloc[i].tolist()])
    cols = [str(x).strip() for x in df.iloc[hdr].tolist()]
    ix = {c: cols.index(c) for c in cols if c}
    def g(row, name):
        return str(row[ix[name]]).strip() if name in ix and ix[name] < len(row) else ""
    for _, row in df.iloc[hdr + 1:].iterrows():
        r = row.tolist()
        sym = g(r, "Symbol").upper()
        if not sym or sym.lower() == "nan":
            continue
        def num(name):
            v = g(r, name)
            try:
                return float(v)
            except Exception:
                return None
        out[sym] = {
            "rank": num("Rank"), "comp": num("SmartSelect Comp Rating"),
            "eps": num("EPS Rating"), "rs": num("RS Rating"),
            "group": g(r, "Industry Group RS"),
        }
    return out


def _watchlist(dsn):
    import psycopg2
    conn = psycopg2.connect(dsn, connect_timeout=15)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT UPPER(symbol) FROM watchlist WHERE symbol IS NOT NULL AND symbol<>''")
    syms = sorted(r[0] for r in cur.fetchall())
    cur.close(); conn.close()
    return syms


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ibd50", default=None)
    ap.add_argument("--leaders", default=None)
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--rs-min", type=float, default=90.0)
    ap.add_argument("--zone", type=float, default=5.0, help="buy-zone half-width % around the pivot")
    ap.add_argument("--pivot-lookback", type=int, default=50, help="trading days for the base-high pivot")
    ap.add_argument("--persist", action="store_true", help="write the report straight to market_reports (DB, offline)")
    ap.add_argument("--publish", action="store_true", help="POST to the API → persist + PUSH to all users (uses API_BASE/API_TOKEN)")
    args = ap.parse_args()

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        sys.exit("Set DATABASE_URL.")
    import yfinance as yf
    import pandas as pd

    ibd = _ibd(args.ibd50)
    leaders = _ibd(args.leaders)          # sector leaders (membership = a credential)
    wl = set(_watchlist(dsn))
    # Universe = the LEADERS (IBD 50 + sector leaders) — that IS IBD's pool; we don't
    # gate it on the platform watchlist (the IBD names may only be in the TV import yet).
    # A name already on the watchlist gets a small "tracked" nudge in scoring.
    cands = sorted(set(ibd) | set(leaders))
    if not cands:
        print(json.dumps({"market": "unknown", "picks": [], "detail": "no candidates"}))
        return

    # Market gate — SPY above its daily 8 AND 21 EMA = healthy.
    spy = yf.download("SPY", period="3mo", interval="1d", progress=False, auto_adjust=False)
    spy_close = spy["Close"].dropna()
    spy_close = spy_close.iloc[:, 0] if hasattr(spy_close, "columns") else spy_close
    market_ok = bool(spy_close.iloc[-1] > spy_close.ewm(span=8).mean().iloc[-1]
                     and spy_close.iloc[-1] > spy_close.ewm(span=21).mean().iloc[-1])

    # 15mo so the 200-day SMA (Stage-2 check) actually has 200 bars (9mo only gives ~187).
    data = yf.download(cands, period="15mo", interval="1d", progress=False,
                       auto_adjust=False, group_by="ticker", threads=True)

    picks = []
    for sym in cands:
        try:
            df = data[sym] if len(cands) > 1 else data
            c = df["Close"].dropna(); h = df["High"].dropna()
            v = df["Volume"].dropna(); lo = df["Low"].dropna()
            if len(c) < 200:
                continue
            price = float(c.iloc[-1])
            pivot = float(h.iloc[-(args.pivot_lookback + 1):-1].max())   # base high (excl. today)
            sma200 = float(c.rolling(200).mean().iloc[-1])
            sma50 = float(c.rolling(50).mean().iloc[-1])
            vol_avg = float(v.rolling(50).mean().iloc[-1])
            vol_now = float(v.iloc[-1])
            swing_low = float(lo.iloc[-10:].min())
            chg = (price / float(c.iloc[-2]) - 1.0) * 100.0

            rs = (ibd.get(sym) or leaders.get(sym) or {}).get("rs")
            is_leader = (rs is not None and rs >= args.rs_min) or sym in leaders
            stage2 = price > sma200
            # buy zone = within ±zone% of the pivot (approaching, or just-cleared, not extended)
            dist_pct = (price - pivot) / pivot * 100.0
            in_zone = -args.zone <= dist_pct <= args.zone
            vol_surge = vol_avg > 0 and vol_now > vol_avg * 1.3

            # Hard gate = leader + Stage-2 + in the buy zone. Market health modulates
            # POSITION SIZE + the report flag (IBD stays 60-80% invested, not all-or-none).
            if not (is_leader and stage2 and in_zone):
                continue

            score = (rs or 80) + (15 if vol_surge else 0) + max(0, 8 - abs(dist_pct)) + (3 if sym in wl else 0)
            stop = max(swing_low, min(sma50, pivot * 0.93))
            r_mult = (price - stop)
            reasons = []
            meta = ibd.get(sym) or leaders.get(sym) or {}
            if meta.get("rank"):
                reasons.append(f"IBD #{int(meta['rank'])}, RS {int(rs)} , {meta.get('group','')} group".replace(" ,", ","))
            elif rs:
                reasons.append(f"RS {int(rs)} leader")
            if sym in leaders:
                reasons.append("sector leader")
            reasons.append(f"in the buy zone — buy point ${pivot:.2f} (range ${pivot:.2f}–${pivot*(1+args.zone/100):.2f})"
                           + (", just cleared it" if dist_pct > 0 else f", {abs(dist_pct):.1f}% below"))
            if vol_surge:
                reasons.append(f"volume {vol_now/vol_avg:.1f}× avg")
            reasons.append("Stage 2 (above the 200-day)")
            picks.append({
                "symbol": sym, "score": round(score, 1), "type": "SWING",
                "price": round(price, 2), "buy_point": round(pivot, 2),
                "buy_range": [round(pivot, 2), round(pivot * (1 + args.zone / 100), 2)],
                "position": "Full" if (market_ok and rs and rs >= 95 and vol_surge) else "Half",
                "stop": round(stop, 2), "rs": int(rs) if rs else None,
                "chg_pct": round(chg, 2), "reasons": reasons,
            })
        except Exception:
            continue

    picks.sort(key=lambda p: -p["score"])
    picks = picks[:args.top]

    # markdown report
    date = datetime.utcnow().strftime("%Y-%m-%d")
    L = [f"# Today's Leaders Near a Buy Point — {date}", ""]
    L.append(f"Market: {'🟢 healthy (SPY above 8 & 21 EMA)' if market_ok else '🔴 weak — be selective'}")
    L.append("")
    if not picks:
        L.append("_No leader is in a clean buy zone today — nothing to chase. Patience._")
    for p in picks:
        L.append(f"### {p['symbol']} — {p['type']} · buy ${p['buy_point']} (range ${p['buy_range'][0]}–${p['buy_range'][1]}) · {p['position']} size")
        for r in p["reasons"]:
            L.append(f"- {r}")
        L.append(f"- stop ${p['stop']} · entry near ${p['price']}")
        L.append("")
    report = "\n".join(L)
    print(report)
    print("\n---JSON---")
    print(json.dumps({"market_ok": market_ok, "candidates": len(cands), "picks": picks}))

    if args.publish:
        # POST to the API → persists to market_reports (kind=morning_focus) AND pushes an
        # APNs blast to all users. Server-side keeps APNs creds where they belong.
        import urllib.request
        base = os.getenv("API_BASE", "https://tradesignalwithai.com").rstrip("/")
        tok = os.getenv("API_TOKEN")
        if not tok:
            sys.exit("--publish needs API_TOKEN (and optional API_BASE).")
        syms = ", ".join(p["symbol"] for p in picks)
        push_title = ("📋 Today's focus: " + syms) if picks else "📋 No leaders in a buy zone today"
        push_body = "Leaders near a buy point — tap for the plan." if picks else "Nothing to chase. Patience."
        data = json.dumps({"kind": "morning_focus", "body": report, "session_date": date,
                           "push_title": push_title, "push_body": push_body}).encode()
        req = urllib.request.Request(base + "/api/v1/intel/reports/publish", data=data,
                                     headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                print("[published]", json.load(r))
        except Exception as e:
            sys.exit(f"publish failed: {str(e)[:160]}")
    elif args.persist:
        import psycopg2
        conn = psycopg2.connect(dsn, connect_timeout=15)
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO market_reports (kind, session_date, body, created_at) "
                        "VALUES ('morning_focus', %s, %s, NOW())", (date, report))
            conn.commit(); cur.close()
            print(f"[persisted to market_reports kind=morning_focus session_date={date}]")
        finally:
            conn.close()


if __name__ == "__main__":
    main()
