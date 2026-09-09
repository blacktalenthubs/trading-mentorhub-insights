"""Read-only Robinhood options chain + greeks. NO orders are ever placed.

Pure analysis — pulls the chain for a symbol/expiration with delta/theta/gamma/
vega/IV and the quote. Rides the stored session pickle (same login as the
import), so no MFA prompt once you've logged in via test_robinhood_login.py.

Usage:
    export ROBINHOOD_USERNAME="you@example.com"
    export ROBINHOOD_PASSWORD="..."
    python3 scripts/robinhood_options.py SPY --exp 2026-01-16 --type call
    python3 scripts/robinhood_options.py AAPL --exp 2026-01-16          # both sides
"""
from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only Robinhood options chain + greeks.")
    ap.add_argument("symbol", help="underlying ticker, e.g. SPY")
    ap.add_argument("--exp", required=True, help="expiration date YYYY-MM-DD")
    ap.add_argument("--type", default="both", choices=["call", "put", "both"])
    args = ap.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from brokers.robinhood_options import fetch_option_greeks
    from brokers.robinhood import RobinhoodError

    try:
        rows = fetch_option_greeks(args.symbol.upper(), args.exp, args.type)
    except RobinhoodError as exc:
        print(f"FAIL: {exc}")
        return 1

    if not rows:
        print("(no contracts returned — check the symbol/expiration)")
        return 0

    print(f"{args.symbol.upper()} {args.exp}  ({len(rows)} contracts)\n")
    hdr = (f"{'type':4} {'strike':>9} {'mark':>8} {'delta':>7} {'theta':>7} "
           f"{'gamma':>7} {'vega':>7} {'IV':>7} {'vol':>8} {'OI':>8}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['type']:4} {r['strike']:>9.2f} {r['mark']:>8.2f} "
              f"{r['delta']:>7.3f} {r['theta']:>7.3f} {r['gamma']:>7.4f} "
              f"{r['vega']:>7.3f} {r['iv']:>7.3f} {r['volume']:>8.0f} {r['open_interest']:>8.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
