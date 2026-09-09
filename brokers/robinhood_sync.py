"""Robinhood daily sync — fetch fills, store them, rebuild realized P&L.

Orchestration only. The Robinhood payload mapping lives in brokers.robinhood
(pure, tested against fixtures); the FIFO pairing lives in
analytics.trade_matcher (already used by the PDF statement import). This module
just sequences them and owns the DB writes.

Pipeline
--------
    login -> fetch orders -> normalize -> window to the target dates
          -> skip fills already stored (external_id) -> insert
          -> re-run FIFO over the account's full history -> rebuild matched_trades

Idempotent by construction: re-running for the same day inserts nothing new and
rebuilds the same matched rows, so a retry, a redeploy, or a manual backfill is
always safe.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from analytics.trade_matcher import match_trades_fifo
from brokers.daily_target_sync import sync_to_daily_target
from brokers.robinhood import (
    ROBINHOOD_ACCOUNT_LABEL,
    ROBINHOOD_IMPORT_ENABLED,
    ROBINHOOD_USER_ID,
    RobinhoodClient,
    RobinhoodError,
    normalize_orders,
)
from db import (
    create_import,
    get_trades_monthly,
    insert_broker_fills,
    replace_matched_trades_for_account,
    update_import_count,
)
from models import ImportRecord, TradeMonthly

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """What one sync run did — returned so the caller can report or alert."""

    session_date: date
    fills_seen: int = 0        # fills in the window, before dedup
    fills_imported: int = 0    # rows actually written this run
    matched_trades: int = 0    # realized round-trips for the account, after rebuild
    realized_pnl: float = 0.0  # realized P&L on session_date only
    daily_target_rows: int = 0  # rows written to the Daily Target log
    skipped: str = ""          # non-empty when the run was a deliberate no-op
    error: str = ""            # non-empty when the run failed


def _window_dates(session_date: date, lookback_days: int) -> set[date]:
    """Dates to accept fills for.

    A small lookback (not just today) catches a fill Robinhood stamped late and
    lets a missed run self-heal on the next day — the external_id dedup makes
    the overlap free.
    """
    return {session_date - timedelta(days=n) for n in range(lookback_days + 1)}


def _rows_for_account(user_id: int, account: str) -> list[TradeMonthly]:
    """Every stored fill for one account, as TradeMonthly, oldest first.

    Read back from the DB rather than reusing the just-normalized rows because
    FIFO needs the full history, not only today's slice.
    """
    df = get_trades_monthly(user_id, account=account)
    if df.empty:
        return []

    rows: list[TradeMonthly] = []
    for r in df.to_dict("records"):
        trade_date = r.get("trade_date")
        # get_trades_monthly returns trade_date as a pandas Timestamp.
        trade_date = trade_date.date() if hasattr(trade_date, "date") else trade_date
        if trade_date is None:
            continue
        rows.append(TradeMonthly(
            account=r.get("account") or account,
            description=r.get("description") or "",
            symbol=r.get("symbol") or "",
            cusip=r.get("cusip") or "",
            acct_type=r.get("acct_type") or "",
            transaction_type=r.get("transaction_type") or "",
            trade_date=trade_date,
            quantity=float(r.get("quantity") or 0),
            price=float(r.get("price") or 0),
            amount=float(r.get("amount") or 0),
            is_option=bool(r.get("is_option")),
            option_detail=r.get("option_detail") or "",
            is_recurring=bool(r.get("is_recurring")),
            asset_type=r.get("asset_type") or "",
            category=r.get("category") or "",
            underlying_symbol=r.get("underlying_symbol") or "",
        ))
    return rows


def sync_robinhood_fills(
    session_date: date | None = None,
    lookback_days: int = 3,
    user_id: int | None = None,
    client: RobinhoodClient | None = None,
    force: bool = False,
) -> SyncResult:
    """Import Robinhood fills for `session_date` and rebuild realized P&L.

    `client` is injectable so tests drive the whole pipeline with a fake and no
    network. Never raises: a broker outage must not take down the scheduler, so
    failures come back on SyncResult.error for the caller to report.
    """
    session_date = session_date or date.today()
    user_id = user_id if user_id is not None else ROBINHOOD_USER_ID
    result = SyncResult(session_date=session_date)

    if not ROBINHOOD_IMPORT_ENABLED and not force:
        # force=True lets an explicit manual/UI trigger run even when the
        # scheduled job is disabled; the scheduler always passes force=False.
        result.skipped = "ROBINHOOD_IMPORT_ENABLED is not true"
        return result
    if not user_id:
        result.skipped = "ROBINHOOD_USER_ID is not set"
        return result

    # Self-heal the schema. The external_id column + unique index are added by
    # db.py init_db(), which the FastAPI API service does NOT run (it uses the
    # SQLAlchemy layer). Without this, a UI-triggered import fails on the dedup
    # query ("column external_id does not exist") until the worker is restarted.
    # The migration is idempotent, so calling it here is a safe no-op once applied.
    try:
        from db import _migrate_trades_monthly_external_id
        _migrate_trades_monthly_external_id()
    except Exception:
        pass

    try:
        if client is None:
            client = RobinhoodClient()
            client.login()

        stock_orders, option_orders = client.fetch_orders()
        fills = normalize_orders(stock_orders, option_orders, client.symbol_for_instrument)

        window = _window_dates(session_date, lookback_days)
        windowed = [(ext, t) for ext, t in fills if t.trade_date in window]
        result.fills_seen = len(windowed)

        if windowed:
            import_rec = ImportRecord(
                filename=f"robinhood-{session_date.isoformat()}",
                file_type="robinhood_daily",
                period=session_date.isoformat(),
                records_imported=0,
            )
            # The imports table is UNIQUE(filename, file_type), so a same-day
            # re-run collides. That is the intended signal that today is already
            # recorded — reuse the fill-level dedup and skip the insert.
            try:
                import_id = create_import(import_rec, user_id)
            except Exception:
                logger.info("Robinhood: import record for %s already exists", session_date)
                import_id = 0

            result.fills_imported = insert_broker_fills(windowed, import_id, user_id)
            if import_id:
                update_import_count(import_id, result.fills_imported)

        # Rebuild FIFO over the account's full history — a sell today can pair
        # against a lot opened long before the import window.
        all_rows = _rows_for_account(user_id, ROBINHOOD_ACCOUNT_LABEL)
        matched = match_trades_fifo(all_rows)
        replace_matched_trades_for_account(matched, user_id, ROBINHOOD_ACCOUNT_LABEL)

        result.matched_trades = len(matched)
        result.realized_pnl = round(
            sum(m.realized_pnl for m in matched if m.sell_date == session_date), 2
        )

        # Populate the Daily Target discipline log from the same fills, so the
        # page the trader actually reviews is filled in rather than hand-typed.
        try:
            dt_result = sync_to_daily_target(all_rows, session_date, user_id)
            result.daily_target_rows = dt_result.inserted + dt_result.updated
        except Exception:
            # The import itself succeeded — a Daily Target write failure must not
            # discard it or block the evaluation.
            logger.exception("Robinhood sync: Daily Target bridge failed")
        logger.info(
            "Robinhood sync %s — %d fills in window, %d imported, %d matched, $%.2f realized",
            session_date, result.fills_seen, result.fills_imported,
            result.matched_trades, result.realized_pnl,
        )
    except RobinhoodError as exc:
        result.error = str(exc)
        logger.error("Robinhood sync failed for %s: %s", session_date, exc)
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        logger.exception("Robinhood sync failed for %s", session_date)

    return result
