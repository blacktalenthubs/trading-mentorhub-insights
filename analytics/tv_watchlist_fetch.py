#!/usr/bin/env python3
"""Fetch the MASTER watchlist symbols (union of every user's watchlist) for the
TV-watchlist-sync skill. Prints JSON {"count": N, "symbols": [...]} to stdout so
the agent driving the TradingView MCP can reconcile the TV watchlist against it.

The cloud backend can't write to your desktop TradingView (CDP is localhost-only),
so this is the LOCAL half: pull the authoritative symbol set from the API, then the
agent adds the missing ones to TV via the MCP (watchlist_add). See the skill
.claude/skills/tv-watchlist-sync/SKILL.md.

    API_BASE=https://tradesignalwithai.com API_TOKEN=... python3 analytics/tv_watchlist_fetch.py

Endpoint: GET /api/v1/watchlist/master-symbols (auth required) — the union built
for exactly this sync (#248). Also folds in Strong-Buy conviction names so the
hottest discovery picks get scanned too.
"""
from __future__ import annotations
import json, os, sys, urllib.request


def _get(api_base: str, path: str, token: str):
    req = urllib.request.Request(
        f"{api_base.rstrip('/')}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main() -> None:
    api_base = os.getenv("API_BASE", "https://tradesignalwithai.com")
    token = os.getenv("API_TOKEN")
    if not token:
        sys.exit("Set API_TOKEN (your BusyTradersDesk session token). Optionally API_BASE.")

    symbols: set[str] = set()
    try:
        master = _get(api_base, "/api/v1/watchlist/master-symbols", token)
        symbols.update((s or "").strip().upper() for s in (master.get("symbols") or []))
    except Exception as e:
        sys.exit(f"Couldn't fetch master-symbols from {api_base}: {str(e)[:140]}")

    # Fold in Strong-Buy conviction names (best-effort — discovery picks should be
    # scanned too). A failure here is non-fatal; the master list is the floor.
    try:
        conv = _get(api_base, "/api/v1/screener/conviction", token)
        for e in (conv.get("entries") or []):
            if str(e.get("rec_key", "")).lower() == "strong_buy" and e.get("symbol"):
                symbols.add(str(e["symbol"]).strip().upper())
    except Exception:
        pass

    out = sorted(s for s in symbols if s)
    print(json.dumps({"count": len(out), "symbols": out}))


if __name__ == "__main__":
    main()
