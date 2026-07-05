#!/usr/bin/env python3
"""
Long Term Finders — the "ETF technique".

Pull the TOP-10 holdings (by weight) of a curated set of ETFs, then surface the names that
show up across MULTIPLE ETFs (overlap = conviction) — the way you'd find RKLB/AST before they
go mainstream: a name that's a top holding in a broad ETF AND its sector/thematic ETF is
doubly-confirmed. Tags each as "core" (a mega-cap in the broad-market ETFs) or "emerging"
(only in the sector/thematic ETFs — the actual finders).

Publishes a JSON blob to market_reports[kind=long_term_finders]; the Trade Ideas page reads it.
Runs offline (yfinance funds_data is blocked on the main API) — local or the triage worker.

    python3 analytics/etf_finders.py --publish
"""
import argparse, json, os, re, warnings
warnings.filterwarnings("ignore")

# Broad + sector + thematic + small-cap. Broad ones flag "core" vs "emerging".
ETF_LIST = os.environ.get("ETF_FINDER_LIST", "SPY,QQQ,XLK,SMH,SOXX,ARKX,UFO,XBI,ARKK,IWM").split(",")
BROAD = {"SPY", "QQQ", "IWM"}   # a top holding here = an already-mainstream "core" name
ETF_DESC = {
    "SPY": "S&P 500", "QQQ": "Nasdaq 100", "XLK": "Technology", "SMH": "Semiconductors",
    "SOXX": "Semiconductors", "ARKX": "Space & Exploration", "UFO": "Space", "XBI": "Biotech",
    "ARKK": "Innovation", "IWM": "Russell 2000",
}


def _dsn():
    v = os.environ.get("DATABASE_URL")
    if v:
        return v.strip()
    return re.search(r'^DATABASE_URL=(.+)$', open(".env").read(), re.M).group(1).strip()


def pull_holdings(etf):
    """[(symbol, name, weight_pct), ...] top holdings of one ETF, or [] on failure."""
    import yfinance as yf
    try:
        th = yf.Ticker(etf).funds_data.top_holdings
        if th is None or not len(th):
            return []
        out = []
        for sym in th.index:
            name = str(th.loc[sym, "Name"]) if "Name" in th.columns else sym
            w = float(th.loc[sym, "Holding Percent"]) * 100.0
            out.append((str(sym).upper(), name, round(w, 2)))
        return out
    except Exception:
        return []


def build(etfs=ETF_LIST):
    per_etf = []
    by_sym = {}
    for etf in etfs:
        hold = pull_holdings(etf)
        if not hold:
            print(f"  {etf}: no holdings (skipped)")
            continue
        per_etf.append({"etf": etf, "desc": ETF_DESC.get(etf, ""),
                        "top": [{"symbol": s, "name": n, "weight": w} for s, n, w in hold]})
        for s, n, w in hold:
            rec = by_sym.setdefault(s, {"symbol": s, "name": n, "etfs": [], "weights": {}})
            rec["etfs"].append(etf)
            rec["weights"][etf] = w
        print(f"  {etf}: {len(hold)} holdings")
    finders = []
    for s, rec in by_sym.items():
        etfs_in = rec["etfs"]
        in_broad = any(e in BROAD for e in etfs_in)
        finders.append({
            "symbol": s, "name": rec["name"],
            "etfs": etfs_in, "overlap": len(etfs_in),
            "max_weight": max(rec["weights"].values()),
            "weights": rec["weights"],
            "tier": "core" if in_broad else "emerging",
        })
    # rank: most overlap first, then heaviest weight
    finders.sort(key=lambda f: (-f["overlap"], -f["max_weight"]))
    return {"etfs": per_etf, "finders": finders}


def publish(payload, session_date):
    import psycopg2
    body = json.dumps(payload, default=str)
    conn = psycopg2.connect(_dsn()); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS market_reports (
        kind TEXT NOT NULL, session_date TEXT NOT NULL, body TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(), PRIMARY KEY (kind, session_date))""")
    cur.execute("""INSERT INTO market_reports (kind, session_date, body) VALUES ('long_term_finders', %s, %s)
        ON CONFLICT (kind, session_date) DO UPDATE SET body = EXCLUDED.body, created_at = NOW()""",
                (session_date, body))
    conn.commit(); conn.close()
    print(f"published -> market_reports[long_term_finders] {session_date}, {len(payload['finders'])} names")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--out", default="long_term_finders.json")
    args = ap.parse_args()
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (.env fallback)
    from datetime import date
    payload = build()
    json.dump(payload, open(args.out, "w"), indent=2, default=str)
    print(f"\n=== Long Term Finders (overlap-ranked) ===")
    for f in payload["finders"][:18]:
        tag = "★" if f["tier"] == "emerging" else " "
        print(f"  {tag} {f['symbol']:6} {f['overlap']}x  {f['max_weight']:>5.1f}%  {'+'.join(f['etfs'])}")
    if args.publish:
        publish(payload, date.today().isoformat())
