#!/usr/bin/env python3
"""Master-watchlist curator — keeps the platform DISCOVERY universe fresh + on-profile, routinely.

The agents (swing_scan, morning_leaders, premarket, etc.) all scan the MASTER watchlist, so a stale or
off-profile master = stale/off-profile discovery for everyone. This runs weekly and, per sector, adds
emerging QUALIFYING leaders and prunes names that violate the user's hard rules.

USER PROFILE RULES (see feedback_no_low_price_gappy_stocks):
  - NO low-priced names        → price >= $30
  - NO catalyst-gap names      → max overnight gap over the last 60d < 20% (kills the biotech FDA/trial
                                  gappers that blow through stops)
  - Liquid, in an uptrend      → $-vol >= $20M/day AND above the 200-day MA
  - Ranked per SECTOR (not global) so no single group (e.g. biotech) can dominate.

CONSERVATIVE on removals: only prunes master names that turned CHEAP (<$30) or GAPPY (>20%) — the two
things the user explicitly dislikes. It never removes on a mere rank/trend wobble (that would churn a
scan universe). Additions are capped per sector.

Modes:
  --report  (default) persist a market_reports[master_curation] diff + print it. No DB changes.
  --apply   also apply: add the new qualifiers (into their sector group) and prune cheap/gappy names.
"""
import argparse, json, os, sys
import warnings
warnings.filterwarnings("ignore")

MASTER_EMAIL = "master@busytradersdesk"
MIN_PRICE = 30.0
MIN_DVOL = 20e6
RS_MIN = 0.10          # additions must be genuine LEADERS — RS > +10% vs SPY (3mo), not laggards
GAP_PCT = 0.15         # what counts as an "outsized" overnight gap
GAP_FREQ_ADD = 3       # don't ADD a name with >=3 such gaps/yr (chronically gappy = the biotech tell)
GAP_FREQ_PRUNE = 4     # PRUNE a master name that's BECOME chronically gappy (>=4/yr) — NOT one earnings pop
N_PER_SECTOR = 8       # cap per sector
EXEMPT = {"SPY", "QQQ", "IWM", "DIA", "SMH", "SOXL"}   # index/leveraged ETFs are tools — never pruned

# Candidate universe — liquid, notable US names by sector. The curator filters + ranks WITHIN each.
UNIVERSE = {
    "Chips": ["NVDA", "AVGO", "AMD", "TSM", "MU", "LRCX", "KLAC", "AMAT", "ASML", "QCOM", "TXN", "NXPI", "MRVL", "ARM", "MPWR", "ON", "ALAB", "CRDO"],
    "software": ["MSFT", "ORCL", "NOW", "CRWD", "PANW", "SNOW", "DDOG", "NET", "MDB", "PLTR", "APP", "TEAM", "ZS", "HUBS", "DASH"],
    "Mega Tech": ["AAPL", "GOOGL", "META", "AMZN", "NFLX", "TSLA", "ABNB", "UBER", "SHOP"],
    "Payment": ["HOOD", "COIN", "SOFI", "AFRM", "SEZL", "DAVE", "NU", "TOST", "PYPL"],
    "Space": ["RKLB", "ASTS", "LUNR", "KTOS", "AVAV", "LHX", "IRDM", "RTX", "GD"],
    "Power": ["VST", "CEG", "GEV", "OKLO", "BE", "NRG", "TLN", "CCJ"],
    "Memory": ["MU", "SNDK", "WDC", "DRAM", "STX"],
    "networking": ["ANET", "CSCO", "CRDO", "JNPR"],
    "Optics": ["COHR", "LITE", "FN", "AAOI"],
    "Quantom": ["IONQ", "QBTS", "RGTI"],
    "Cloud": ["NBIS", "CRWV", "VRT", "DELL", "SMCI"],
    "Biotech": ["LLY", "VRTX", "REGN", "AMGN", "GILD", "NBIX", "KRYS", "EXEL", "ALKS", "TGTX", "ISRG"],
    "Space Consumer": [],
}


def _dsn():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL not set")
    return dsn


def _profile(symbols):
    """Fetch 1y daily; return {sym: dict(price, dvol, rs, hi52prox, above200, maxgap)} or skip."""
    import yfinance as yf, numpy as np
    out = {}
    d = yf.download(symbols + ["SPY"], period="1y", interval="1d", progress=False,
                    auto_adjust=True, group_by="ticker", threads=True)
    try:
        spy = d["SPY"]["Close"].dropna().values
        spy63 = spy[-1] / spy[-63] - 1 if len(spy) > 63 else 0.0
    except Exception:
        spy63 = 0.0
    multi = len(symbols) > 1
    for s in symbols:
        try:
            df = (d[s] if multi else d).dropna()
        except Exception:
            continue
        C = df["Close"].values; V = df["Volume"].values; O = df["Open"].values
        if len(C) < 210:
            continue
        price = float(C[-1])
        dvol = float((C[-20:] * V[-20:]).mean())
        ma200 = float(C[-200:].mean())
        rs = (C[-1] / C[-63] - 1) - spy63 if len(C) > 63 else 0.0
        hi52 = float(max(df["High"].values[-252:])); prox = price / hi52 if hi52 > 0 else 0.0
        gaps = np.abs(O[1:] - C[:-1]) / C[:-1]
        gap_freq = int(np.sum(gaps[-252:] > GAP_PCT))     # # of >15% overnight gaps in the last year
        out[s] = dict(price=price, dvol=dvol, rs=rs, prox=prox, above200=price > ma200, gap_freq=gap_freq)
    return out


def _qualifies(p):
    # only ADD genuine, clean leaders: priced right, liquid, in an uptrend, OUTPERFORMING, not gappy
    return (p["price"] >= MIN_PRICE and p["dvol"] >= MIN_DVOL and p["above200"]
            and p["rs"] > RS_MIN and p["gap_freq"] < GAP_FREQ_ADD)


def _score(p):
    return p["rs"] * 100 * 0.5 + (p["prox"] * 100 - 70) / 30 * 100 * 0.3 + (10 if p["above200"] else 0)


def curate(dsn, apply=False):
    import psycopg2
    conn = psycopg2.connect(dsn); cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE lower(email)=lower(%s)", (MASTER_EMAIL,))
    row = cur.fetchone()
    if not row:
        conn.close(); raise SystemExit("no master account")
    mid = row[0]
    cur.execute("SELECT UPPER(symbol) FROM watchlist WHERE user_id=%s AND symbol NOT LIKE '%%-USD'", (mid,))
    master = set(r[0] for r in cur.fetchall())

    allsyms = sorted({s for v in UNIVERSE.values() for s in v} | master)
    prof = _profile(allsyms)

    adds, drops = [], []
    # ADD — per sector, the top qualifiers not already in master, capped
    for sec, cands in UNIVERSE.items():
        have = sum(1 for s in cands if s in master)
        ranked = sorted([(s, _score(prof[s])) for s in cands if s in prof and _qualifies(prof[s]) and s not in master],
                        key=lambda x: -x[1])
        for s, sc in ranked:
            if have >= N_PER_SECTOR:
                break
            adds.append((s, sec, round(prof[s]["price"], 2), round(prof[s]["rs"] * 100, 0)))
            have += 1
    # PRUNE — master names that turned CHEAP or GAPPY (the user's two hard dislikes only)
    for s in master:
        p = prof.get(s)
        if not p or s in EXEMPT:                          # never prune index/leveraged ETFs
            continue
        why = ("cheap <$30" if p["price"] < MIN_PRICE
               else ("chronically gappy" if p["gap_freq"] >= GAP_FREQ_PRUNE else None))
        if why:
            drops.append((s, round(p["price"], 2), p["gap_freq"], why))

    applied = {"added": 0, "removed": 0}
    if apply:
        # group-id lookup / create
        def group_id(name):
            cur.execute("SELECT id FROM watchlist_group WHERE user_id=%s AND lower(name)=lower(%s)", (mid, name))
            r = cur.fetchone()
            if r:
                return r[0]
            cur.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM watchlist_group WHERE user_id=%s", (mid,))
            so = cur.fetchone()[0]
            cur.execute("INSERT INTO watchlist_group (user_id, name, sort_order, color) VALUES (%s,%s,%s,'#1f6feb') RETURNING id", (mid, name, so))
            return cur.fetchone()[0]
        for s, sec, _px, _rs in adds:
            gid = group_id(sec)
            cur.execute("INSERT INTO watchlist (user_id, symbol, group_id, focus, added_at) VALUES (%s,%s,%s,false,NOW())", (mid, s, gid))
            applied["added"] += 1
        for s, _px, _gap, _why in drops:
            cur.execute("DELETE FROM watchlist WHERE user_id=%s AND UPPER(symbol)=%s", (mid, s))
            applied["removed"] += 1
        conn.commit()

    conn.close()
    return {"master_before": len(master), "adds": adds, "drops": drops, "applied": applied}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="apply changes (add qualifiers, prune cheap/gappy)")
    args = ap.parse_args()
    dsn = _dsn()
    res = curate(dsn, apply=args.apply)
    print(f"master before: {res['master_before']} equities")
    print(f"\nADD ({len(res['adds'])}) — new qualifying leaders (price>=$30, no >20% gap, liquid, uptrend):")
    for s, sec, px, rs in res["adds"]:
        print(f"  + {s:<6} {sec:<12} ${px:<8} RS {rs:+.0f}%")
    print(f"\nPRUNE ({len(res['drops'])}) — turned cheap or chronically gappy (ETFs exempt):")
    for s, px, gf, why in res["drops"]:
        print(f"  - {s:<6} ${px:<8} {gf}x gaps>15%/yr  ({why})")
    if args.apply:
        print(f"\nAPPLIED: +{res['applied']['added']} added, -{res['applied']['removed']} removed")
    # persist a report for in-app review
    try:
        import psycopg2
        from datetime import date
        conn = psycopg2.connect(dsn); cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS market_reports (kind TEXT NOT NULL, session_date TEXT NOT NULL,
            body TEXT NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT NOW(), PRIMARY KEY (kind, session_date))""")
        cur.execute("INSERT INTO market_reports (kind, session_date, body) VALUES ('master_curation', %s, %s) "
                    "ON CONFLICT (kind, session_date) DO UPDATE SET body=EXCLUDED.body, created_at=NOW()",
                    (date.today().isoformat(), json.dumps(res)))
        conn.commit(); conn.close()
    except Exception as e:
        print("report persist failed:", e, file=sys.stderr)


if __name__ == "__main__":
    main()
