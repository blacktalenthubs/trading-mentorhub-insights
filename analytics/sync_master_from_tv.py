#!/usr/bin/env python3
"""Reconcile the desk MASTER watchlist (master@busytradersdesk) with TradingView's
master2 list — the list the trader actually edits (trader decision 2026-11-04:
"whatever we have in master should be used — we only keep updating master").

Why this exists: the two "masters" drifted. The desk Master was copied from the
trader's personal list in May 2026 and curated desk-side, while new names land on
the TradingView list (e.g. CAKE, added to TV master2 from the 2026-11-04 Zanger
Report, TBA 119). The Pine fires on TV master2, but the desk gates the trader's
alert copies and the scanner universe on desk-side lists — a name on TV master2
but missing from desk Master is exactly the ISRG/ZTS/CAKE miss class.

This script closes the gap one-way, TV → desk, INSERT-ONLY:
  * resolves the master account by email (never a hardcoded user id),
  * parses a TradingView watchlist export (or --symbols) into bare symbols,
  * inserts only the symbols desk Master is missing (group_id NULL — ungrouped,
    same as the 2026-10-11 Zanger load; scanners select by user_id only),
  * NEVER deletes or renames anything desk-side — removals stay manual, so the
    desk list can only grow toward master2, never shrink under the trader.

Dry-run by default; pass --apply to write. Requires DATABASE_URL.

    python3 analytics/sync_master_from_tv.py --file master2_export.txt          # dry-run diff
    python3 analytics/sync_master_from_tv.py --file master2_export.txt --apply  # insert missing
    python3 analytics/sync_master_from_tv.py --symbols CAKE --apply             # one-name reconcile

Ongoing sync path: after editing master2 in TradingView, export it (Watchlist
menu ▸ Export list), re-run with --apply; the run is idempotent and prints the
full diff (including desk-only names, which it leaves untouched). Symbols are
stored bare (NASDAQ:CAKE → CAKE). Crypto needs the desk's internal -USD form
(COINBASE:ETHUSD is ETH-USD desk-side) — the parser deliberately does not guess
that mapping; pass such names explicitly, e.g. --symbols ETH-USD.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

MASTER_EMAIL = "master@busytradersdesk"

_SYMBOL_OK = re.compile(r"^[A-Z][A-Z0-9.\-]{0,11}$")


def parse_tv_export(text: str) -> list[str]:
    """Parse a TradingView watchlist export into a sorted unique bare-symbol list.

    Handles TV's shapes: 'NASDAQ:CAKE' tokens, comma/newline separation, and
    '###Section Name' headers (dropped whole, up to the next comma/newline)."""
    text = re.sub(r"###[^,\n]*", " ", text or "")
    out: set[str] = set()
    for tok in re.split(r"[,\s]+", text):
        tok = tok.strip()
        if not tok:
            continue
        if ":" in tok:
            tok = tok.split(":", 1)[1]
        tok = tok.upper()
        if _SYMBOL_OK.match(tok):
            out.add(tok)
    return sorted(out)


def _dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL not set")
    return dsn


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Insert TV-master2 symbols missing from the desk MASTER watchlist (insert-only)."
    )
    ap.add_argument("--file", help="Path to a TradingView watchlist export .txt (master2).")
    ap.add_argument("--symbols", help="Comma-separated symbols, in addition to / instead of --file.")
    ap.add_argument("--apply", action="store_true", help="Write the inserts (default is dry-run).")
    args = ap.parse_args()

    tv_syms: set[str] = set()
    if args.file:
        with open(args.file) as f:
            tv_syms |= set(parse_tv_export(f.read()))
    if args.symbols:
        tv_syms |= set(parse_tv_export(args.symbols))
    if not tv_syms:
        raise SystemExit("No symbols parsed — pass --file and/or --symbols.")

    import psycopg2

    conn = psycopg2.connect(_dsn(), connect_timeout=15)
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE lower(email)=lower(%s)", (MASTER_EMAIL,))
        row = cur.fetchone()
        if not row:
            raise SystemExit(f"master account {MASTER_EMAIL} not found")
        master_id = row[0]

        cur.execute("SELECT DISTINCT UPPER(symbol) FROM watchlist WHERE user_id=%s", (master_id,))
        existing = {r[0] for r in cur.fetchall()}
        missing = sorted(tv_syms - existing)
        desk_only = sorted(existing - tv_syms)

        print(
            f"TV master2: {len(tv_syms)} symbols · desk Master: {len(existing)}"
            f" · missing desk-side: {len(missing)}"
        )
        if missing:
            print("Missing (to insert):", ", ".join(missing))
        if desk_only:
            print(
                f"Desk-only ({len(desk_only)}, left untouched — removals are manual):",
                ", ".join(desk_only),
            )
        if not missing:
            print("Already in sync — nothing to insert.")
            return
        if not args.apply:
            print("Dry-run only — re-run with --apply to insert.")
            return
        for sym in missing:
            cur.execute(
                "INSERT INTO watchlist (user_id, symbol) VALUES (%s, %s) "
                "ON CONFLICT (user_id, symbol) DO NOTHING",
                (master_id, sym),
            )
        conn.commit()
        print(f"Inserted {len(missing)} symbols into desk Master (user_id={master_id}).")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
