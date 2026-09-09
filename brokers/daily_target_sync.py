"""Bridge imported broker fills into the Daily Target page.

The Daily Target page is the "make my number, then stop" discipline log: one
DailyTrade row per trade, hand-typed today. Everything it asks for is already in
the imported fills, so this fills the rows in and leaves the human to add only
what a broker cannot know — the note and the exit reason.

Auto-filled from the fill itself: symbol, instrument, entry/exit, quantity,
position size, realized P&L, and day-vs-swing.
Auto-filled from the alert that fired for that symbol that session: `setup` (the
entry mechanism), plus the planned `target` and `stop`. A fill with no alert
behind it is left with setup NULL — that blank IS the signal that the entry was
off-plan.

Idempotent: rows are keyed by the broker's order id (external_id), so re-running
updates in place rather than duplicating. Hand-logged rows (external_id NULL)
are never touched.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from analytics.trade_matcher import match_trades_fifo
from db import get_db
from models import MatchedTrade, TradeMonthly

logger = logging.getLogger(__name__)

# An option contract controls 100 shares. The FIFO matcher works in per-unit
# prices, so its realized_pnl for an option is per-share and must be scaled to
# dollars here — this is the number the Daily Target page measures the day by.
OPTION_MULTIPLIER = 100.0


@dataclass
class DailyTargetSyncResult:
    inserted: int = 0
    updated: int = 0
    skipped_manual: int = 0


def _multiplier(asset_type: str) -> float:
    return OPTION_MULTIPLIER if (asset_type or "").lower() == "option" else 1.0


def _alert_for(symbol: str, session_date: date) -> dict | None:
    """The best alert that fired for this symbol on this session, if any.

    Highest score wins, so a symbol that triggered several rules is attributed
    to its strongest signal rather than whichever fired first.
    """
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT alert_type, entry, stop, target_1, score FROM alerts "
                "WHERE session_date=? AND UPPER(symbol)=? "
                "ORDER BY score DESC LIMIT 1",
                (session_date.isoformat(), (symbol or "").upper()),
            ).fetchone()
        return dict(row) if row else None
    except Exception:
        logger.exception("daily target sync: alert lookup failed for %s", symbol)
        return None


def build_daily_trade_rows(
    matched: list[MatchedTrade],
    fills: list[TradeMonthly],
    session_date: date,
) -> list[dict]:
    """Map one session's round-trips and still-open entries to DailyTrade fields.

    Pure: takes already-loaded data and returns plain dicts, so the mapping is
    testable without a database.
    """
    rows: list[dict] = []

    # Closed round-trips — realized, and they carry the P&L that counts.
    for m in matched:
        if m.sell_date != session_date:
            continue
        mult = _multiplier(m.asset_type)
        underlying = (m.underlying_symbol or m.symbol or "").upper()
        alert = _alert_for(underlying, m.buy_date)
        rows.append({
            "external_id": f"rt:{m.symbol}:{m.buy_date.isoformat()}:{m.sell_date.isoformat()}"
                           f":{m.quantity:g}:{m.buy_price:g}",
            "session_date": session_date.isoformat(),
            "symbol": underlying,
            "instrument": "option" if mult > 1 else "stock",
            "trade_type": "day" if m.holding_days == 0 else "swing",
            "direction": "long",  # the FIFO matcher pairs buy->sell only
            "entry_price": round(m.buy_price, 4),
            "exit_price": round(m.sell_price, 4),
            "quantity": m.quantity,
            "position_size": round(m.buy_amount * mult, 2),
            "pnl": round(m.realized_pnl * mult, 2),
            "is_open": False,
            "setup": (alert or {}).get("alert_type"),
            "target": _level_label(alert, "target_1"),
            "stop": _level_label(alert, "stop"),
            "source": "robinhood",
        })

    # Entries opened today and still held — shown as open so they do NOT count
    # toward the day's realized number (the summary endpoint excludes is_open).
    closed_keys = {(m.symbol, m.buy_date) for m in matched}
    for f in fills:
        if f.trade_date != session_date or f.transaction_type not in ("Buy", "BTO"):
            continue
        if (f.symbol, f.trade_date) in closed_keys:
            continue  # already represented by a round-trip above
        mult = _multiplier(f.asset_type)
        underlying = (f.underlying_symbol or f.symbol or "").upper()
        alert = _alert_for(underlying, session_date)
        rows.append({
            "external_id": f"open:{f.symbol}:{f.trade_date.isoformat()}:{f.quantity:g}:{f.price:g}",
            "session_date": session_date.isoformat(),
            "symbol": underlying,
            "instrument": "option" if f.is_option else "stock",
            "trade_type": "day",
            "direction": "long",
            "entry_price": round(f.price, 4),
            "exit_price": None,
            "quantity": f.quantity,
            "position_size": round(abs(f.amount), 2),
            "pnl": 0.0,  # unrealized — not the day's number
            "is_open": True,
            "setup": (alert or {}).get("alert_type"),
            "target": _level_label(alert, "target_1"),
            "stop": _level_label(alert, "stop"),
            "source": "robinhood",
        })

    return rows


def _level_label(alert: dict | None, key: str) -> str | None:
    """Render an alert price level as the short text the page's field expects."""
    if not alert:
        return None
    value = alert.get(key)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return f"${value:.2f}" if value > 0 else None


def upsert_daily_trades(rows: list[dict], user_id: int) -> DailyTargetSyncResult:
    """Write the mapped rows, updating in place on a re-run.

    Only ever touches rows this importer owns: the UPDATE is keyed on
    external_id, so a hand-logged trade (external_id NULL) can never be
    overwritten, and any note or exit_reason the trader added to an imported row
    is preserved because those columns are not in the update list.
    """
    result = DailyTargetSyncResult()
    if not rows:
        return result

    with get_db() as conn:
        for row in rows:
            existing = conn.execute(
                "SELECT id FROM daily_trades WHERE user_id=? AND external_id=?",
                (user_id, row["external_id"]),
            ).fetchone()

            if existing:
                conn.execute(
                    """UPDATE daily_trades
                       SET exit_price=?, pnl=?, is_open=?, quantity=?, position_size=?
                       WHERE id=?""",
                    (row["exit_price"], row["pnl"], bool(row["is_open"]),
                     row["quantity"], row["position_size"], existing["id"]),
                )
                result.updated += 1
                continue

            conn.execute(
                """INSERT INTO daily_trades
                   (user_id, session_date, symbol, instrument, trade_type, setup,
                    direction, entry_price, exit_price, quantity, position_size,
                    pnl, is_open, target, stop, external_id, source)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (user_id, row["session_date"], row["symbol"], row["instrument"],
                 row["trade_type"], row["setup"], row["direction"],
                 row["entry_price"], row["exit_price"], row["quantity"],
                 row["position_size"], row["pnl"], bool(row["is_open"]),
                 row["target"], row["stop"], row["external_id"], row["source"]),
            )
            result.inserted += 1

    logger.info(
        "Daily Target sync: %d inserted, %d updated", result.inserted, result.updated
    )
    return result


def sync_to_daily_target(
    fills: list[TradeMonthly],
    session_date: date,
    user_id: int,
) -> DailyTargetSyncResult:
    """Full bridge: FIFO-pair the account history, then upsert the session's rows."""
    matched = match_trades_fifo(fills)
    rows = build_daily_trade_rows(matched, fills, session_date)
    return upsert_daily_trades(rows, user_id)
