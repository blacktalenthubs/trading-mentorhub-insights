"""Rebuild matched_trades for every account after the option-×100 source fix.

The FIFO matcher now scales option contracts to dollars at the source
(analytics/trade_matcher.py). Existing matched_trades rows were written by the OLD
per-share matcher, so their option realized_pnl is ~100× too small. This re-runs
FIFO from the stored fills (trades_monthly) and replaces matched_trades for each
(user_id, account) — using the CURRENT code, so the rebuilt rows are in dollars.

daily_trades is NOT touched: its option pnl was already correct (daily_target_sync
used to apply the ×100), and it stays correct now that the matcher does.

Usage:
    # dry run — show what would change, write nothing:
    DATABASE_URL="postgresql://..." python3 scripts/rebuild_matched_trades.py --dry-run
    # apply:
    DATABASE_URL="postgresql://..." python3 scripts/rebuild_matched_trades.py
"""
from __future__ import annotations

import sys

from analytics.trade_matcher import match_trades_fifo
from brokers.robinhood_sync import _rows_for_account
from db import get_db, replace_matched_trades_for_account


def _accounts() -> list[tuple[int, str]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT user_id, account FROM trades_monthly "
            "WHERE account IS NOT NULL AND account <> '' ORDER BY user_id, account"
        ).fetchall()
    return [(r["user_id"], r["account"]) for r in rows]


def _option_realized(user_id: int, account: str) -> float:
    """Current stored sum of option realized_pnl (to show the before/after delta)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(realized_pnl),0) AS s FROM matched_trades "
            "WHERE user_id=? AND account=? AND LOWER(asset_type)='option'",
            (user_id, account),
        ).fetchone()
    return float(row["s"] or 0.0)


def main() -> int:
    dry = "--dry-run" in sys.argv
    accounts = _accounts()
    if not accounts:
        print("No accounts found in trades_monthly — nothing to rebuild.")
        return 0

    print(f"{'DRY RUN — ' if dry else ''}rebuilding matched_trades for {len(accounts)} account(s)\n")
    for user_id, account in accounts:
        rows = _rows_for_account(user_id, account)
        matched = match_trades_fifo(rows)
        opt_before = _option_realized(user_id, account)
        opt_after = sum(m.realized_pnl for m in matched if (m.asset_type or "").lower() == "option")
        stock_after = sum(m.realized_pnl for m in matched if (m.asset_type or "").lower() != "option")
        print(f"  user {user_id} / {account!r}: {len(rows)} fills -> {len(matched)} matched")
        print(f"      option realized:  before={opt_before:,.2f}  after={opt_after:,.2f}")
        print(f"      stock  realized:  after={stock_after:,.2f}  (unchanged by the fix)")
        if not dry:
            replace_matched_trades_for_account(matched, user_id, account)
            print("      -> replaced.")
    print("\nDone." if not dry else "\nDry run complete — no writes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
