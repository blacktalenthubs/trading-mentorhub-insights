"""On-demand Robinhood import — run any time, for any date.

Unlike the 16:45 ET scheduled job, this lets you pull fills whenever you want
and target a specific session date (e.g. yesterday). The sync fetches your full
order history and windows it to [--date minus --lookback, --date]; FIFO P&L is
rebuilt over the whole account each run.

WRITES to the database (test_robinhood_login.py is read-only; this is not).
Fills are deduped by external id, so re-running the same date is safe.

Env (same as the deployed job):
    DATABASE_URL              prod Postgres, or unset for local sqlite
    ROBINHOOD_IMPORT_ENABLED  must be "true"
    ROBINHOOD_USERNAME / ROBINHOOD_PASSWORD
    ROBINHOOD_SESSION_B64     optional — restores a session on a fresh host
    ROBINHOOD_USER_ID         platform user id to attribute trades to (e.g. 185)

Usage:
    python3 scripts/robinhood_import.py                     # today, last 3 days
    python3 scripts/robinhood_import.py --date 2026-09-08   # that day (+lookback)
    python3 scripts/robinhood_import.py --date 2026-09-08 --lookback 1   # just that day
    python3 scripts/robinhood_import.py --lookback 7        # today back 7 days
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime


def main() -> int:
    ap = argparse.ArgumentParser(description="On-demand Robinhood fill import.")
    ap.add_argument("--date", help="session date YYYY-MM-DD (default: today)")
    ap.add_argument("--lookback", type=int, default=3,
                    help="days before --date to also include (default: 3)")
    args = ap.parse_args()

    try:
        session_date = (
            datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
        )
    except ValueError:
        print(f"Bad --date {args.date!r}; expected YYYY-MM-DD")
        return 2

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from brokers.robinhood_sync import sync_robinhood_fills

    print(f"Importing Robinhood fills for {session_date} "
          f"(window: last {args.lookback} day(s)) ...")
    r = sync_robinhood_fills(session_date=session_date, lookback_days=args.lookback)

    if r.skipped:
        print(f"SKIPPED: {r.skipped}")
        return 1
    if r.error:
        print(f"ERROR: {r.error}")
        return 1

    print(f"  fills seen in window : {r.fills_seen}")
    print(f"  fills imported (new) : {r.fills_imported}")
    print(f"  matched round-trips  : {r.matched_trades}")
    print(f"  Daily Target rows    : {r.daily_target_rows}")
    print(f"  realized P&L on {session_date}: ${r.realized_pnl:.2f}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
