#!/usr/bin/env python3
"""Build the TradingView import file that makes the `all_sectors` watchlist MATCH the
platform — every tracked symbol, organized into ###sections by the platform's own
groups, plus the IBD discovery lists on top.

This is the source-of-truth generator for the tv-watchlist-sync skill. The skill runs
it, then reconciles TV (`watchlist_get`) against the `target` symbols it prints — either
guiding a one-click Import (sectioned) or `watchlist_add`-ing the missing names flat.

    DATABASE_URL=postgresql://... python3 analytics/tv_build_import.py \
        --out ~/Downloads/all_sectors_import.txt \
        --ibd50 ../ibd50.xls --leaders ../sectorleaders.xls

Data sources (all live):
  • symbols  = union of every user's watchlist  (SELECT DISTINCT symbol FROM watchlist)
  • sections = each symbol's most-common watchlist_group  (Chips/Memory/Cloud/…)
               — screener_universe.sector is EMPTY, do not use it.
  • IBD 50 / Sector Leaders = the optional .xls exports (binary OLE2 → needs xlrd),
               added as the TOP sections. Dedup priority: Leaders > IBD 50 > sector > Other.
  • crypto is de-dashed for TV (BTC-USD → BTCUSD).

Prints JSON: {"target": [...], "out": "<path>", "sections": [["name", n], ...], "new_from_ibd": [...]}.
A symbol on no group lands in "Other".
"""
from __future__ import annotations
import argparse, collections, json, os, sys

# Display order for the platform's sectors (anything else slots in after, "Other" last).
SECTOR_ORDER = ["Mega Tech", "Chips", "Memory", "networking", "Optics", "Cloud",
                "software", "Conviction", "Payment", "BTC", "Crypto", "Power", "Space",
                "Speculation", "robotics", "Quantom", "Macro"]


def _ibd_symbols(path: str) -> list[str]:
    """Tickers from an IBD/MarketSurge .xls export (Symbol column under a header row)."""
    import pandas as pd
    df = pd.read_excel(path, header=None)
    hdr = next(i for i in range(min(10, len(df)))
               if "Symbol" in [str(x).strip() for x in df.iloc[i].tolist()])
    col = [str(x).strip() for x in df.iloc[hdr].tolist()].index("Symbol")
    out = []
    for s in df.iloc[hdr + 1:, col].dropna().astype(str):
        s = s.strip().upper()
        if s and s.lower() != "nan":
            out.append(s)
    return out


def _platform(conn) -> tuple[list[str], dict[str, str]]:
    """(all distinct symbols, symbol → most-common group) from the live DB."""
    cur = conn.cursor()
    cur.execute("SELECT UPPER(w.symbol), g.name FROM watchlist w "
                "JOIN watchlist_group g ON w.group_id = g.id")
    votes: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for sym, grp in cur.fetchall():
        votes[sym][grp] += 1
    best = {s: c.most_common(1)[0][0] for s, c in votes.items()}
    cur.execute("SELECT DISTINCT UPPER(symbol) FROM watchlist "
                "WHERE symbol IS NOT NULL AND symbol <> ''")
    syms = sorted(r[0] for r in cur.fetchall())
    cur.close()
    return syms, best


def _tv(sym: str) -> str:
    return sym.replace("-", "")   # crypto: BTC-USD → BTCUSD


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the sectioned all_sectors import file.")
    # Output filename = the TV list name on import. Name it `all_sectors` so the imported
    # list matches the alert-bound master (avoids a stray `all_sectors_import` list).
    ap.add_argument("--out", default=os.path.expanduser("~/Downloads/all_sectors.txt"))
    ap.add_argument("--ibd50", default=None, help="path to ibd50.xls (optional)")
    ap.add_argument("--leaders", default=None, help="path to sectorleaders.xls (optional)")
    args = ap.parse_args()

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        sys.exit("Set DATABASE_URL (postgresql://user:pass@host:port/db).")
    import psycopg2
    conn = psycopg2.connect(dsn, connect_timeout=15)
    try:
        wl, best = _platform(conn)
    finally:
        conn.close()

    leaders = _ibd_symbols(args.leaders) if args.leaders and os.path.exists(args.leaders) else []
    ibd50 = _ibd_symbols(args.ibd50) if args.ibd50 and os.path.exists(args.ibd50) else []

    placed: set[str] = set()
    sections: list[tuple[str, list[str]]] = []

    def add(name: str, syms: list[str]) -> None:
        fresh = [s for s in syms if s not in placed]
        for s in fresh:
            placed.add(s)
        if fresh:
            sections.append((name, [_tv(s) for s in fresh]))

    add("Sector Leaders", leaders)
    add("IBD 50", ibd50)
    bysec: dict[str, list[str]] = collections.defaultdict(list)
    for s in wl:
        bysec[best.get(s, "Other")].append(s)
    for name in ([k for k in SECTOR_ORDER if k in bysec]
                 + [k for k in bysec if k not in SECTOR_ORDER and k != "Other"]):
        add(name, bysec[name])
    add("Other", bysec.get("Other", []))

    lines: list[str] = []
    for name, syms in sections:
        lines.append("###" + name)
        lines.extend(syms)
    out = os.path.expanduser(args.out)
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")

    new_from_ibd = sorted((set(leaders) | set(ibd50)) - set(wl))
    print(json.dumps({
        "target": sorted(_tv(s) for s in placed),   # TV format (de-dashed) for direct diff
        "out": out,
        "sections": [[n, len(s)] for n, s in sections],
        "new_from_ibd": new_from_ibd,
    }))


if __name__ == "__main__":
    main()
