#!/usr/bin/env python3
"""Conviction → TradingView watchlist — the LOCAL half of the sync.

The cloud backend can't write to your desktop TradingView (it only lives on your
Mac, reachable via CDP on localhost). This script runs locally: it pulls the
latest conviction scan's STRONG-BUY names from your platform API and writes a
TradingView-importable .txt — so the loop is:

    Run scan  →  "Sync Strong-Buy → watchlist" button (platform watchlist)
              →  python3 analytics/tv_sync.py        (this — writes the TV list)
              →  TradingView: Watchlist ▸ Import list (one click)
              →  Pine fires setups on them

    API_BASE=https://your-host  API_TOKEN=... python3 analytics/tv_sync.py
    python3 analytics/tv_sync.py --out conviction_watchlist.txt

For a fully hands-off version, the agent can instead push these to TV via the
TradingView MCP (watchlist_add) right after each scan — no import step. A local
always-on CDP daemon is also possible but fragile (depends on TV's internal API
+ the desktop staying open with CDP); the import-file flow above is the robust one.
"""
from __future__ import annotations
import argparse, json, os, sys, urllib.request


def fetch_conviction(api_base: str, token: str) -> list[dict]:
    req = urllib.request.Request(
        f"{api_base.rstrip('/')}/api/v1/screener/conviction",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return (json.load(r) or {}).get("entries", [])


def main():
    ap = argparse.ArgumentParser(description="Write a TV-importable list of Strong-Buy conviction names.")
    ap.add_argument("--out", default="conviction_watchlist.txt")
    ap.add_argument("--api-base", default=os.getenv("API_BASE", "https://tradesignalwithai.com"))
    args = ap.parse_args()
    token = os.getenv("API_TOKEN")
    if not token:
        sys.exit("Set API_TOKEN (your BusyTradersDesk session token). "
                 "Optionally API_BASE (default https://tradesignalwithai.com).")

    try:
        entries = fetch_conviction(args.api_base, token)
    except Exception as e:
        sys.exit(f"Couldn't fetch conviction from {args.api_base}: {str(e)[:120]}")

    strong = [
        (e.get("symbol") or "").upper()
        for e in entries
        if str(e.get("rec_key", "")).lower() == "strong_buy" and e.get("symbol")
    ]
    if not strong:
        sys.exit("No Strong-Buy names in the latest conviction scan (run a scan first).")

    # TradingView import accepts one symbol per line (bare tickers resolve).
    with open(args.out, "w") as f:
        f.write("\n".join(strong) + "\n")
    print(f"{len(strong)} Strong-Buy conviction names: {','.join(strong)}")
    print(f"Wrote → {args.out}.  Import in TradingView: Watchlist menu ▸ Import list.")


if __name__ == "__main__":
    main()
