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


def _get(api_base: str, path: str, token: str):
    req = urllib.request.Request(
        f"{api_base.rstrip('/')}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r) or {}


def fetch_conviction(api_base: str, token: str) -> list[dict]:
    return _get(api_base, "/api/v1/screener/conviction", token).get("entries", [])


def fetch_master(api_base: str, token: str) -> list[str]:
    """The union of every user's watchlist symbols (admin token required)."""
    return _get(api_base, "/api/v1/watchlist/master-symbols", token).get("symbols", [])


def main():
    ap = argparse.ArgumentParser(description="Write a TV-importable symbol list (conviction Strong-Buy, or the master watchlist union).")
    ap.add_argument("--master", action="store_true",
                    help="Pull the UNION of all users' watchlists (master list) instead of conviction Strong-Buy.")
    ap.add_argument("--out", default=None, help="Output file (defaults per mode).")
    ap.add_argument("--api-base", default=os.getenv("API_BASE", "https://www.busytradersdesk.com"))
    args = ap.parse_args()
    token = os.getenv("API_TOKEN")
    if not token:
        sys.exit("Set API_TOKEN (an ADMIN BusyTradersDesk session token). "
                 "Optionally API_BASE (default https://www.busytradersdesk.com).")

    if args.master:
        out = args.out or "master_watchlist.txt"
        try:
            syms = [s.upper() for s in fetch_master(args.api_base, token) if s]
        except Exception as e:
            sys.exit(f"Couldn't fetch the master watchlist from {args.api_base}: {str(e)[:120]} "
                     "(needs an ADMIN token).")
        if not syms:
            sys.exit("Master watchlist is empty (no users have added symbols yet).")
        with open(out, "w") as f:
            f.write("\n".join(syms) + "\n")
        print(f"{len(syms)} master watchlist symbols (union of all users): {','.join(syms[:30])}{'…' if len(syms) > 30 else ''}")
        print(f"Wrote → {out}.  Import in TradingView: Watchlist menu ▸ Import list.")
        print("If it exceeds your plan's per-alert symbol cap, split into 2+ watchlists/alerts — the backend doesn't care.")
        return

    out = args.out or "conviction_watchlist.txt"
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
    with open(out, "w") as f:
        f.write("\n".join(strong) + "\n")
    print(f"{len(strong)} Strong-Buy conviction names: {','.join(strong)}")
    print(f"Wrote → {out}.  Import in TradingView: Watchlist menu ▸ Import list.")


if __name__ == "__main__":
    main()
