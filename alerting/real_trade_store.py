"""Real trade tracking — CRUD for manually-confirmed trades."""

from __future__ import annotations

import math
from datetime import datetime

from alert_config import REAL_TRADE_POSITION_SIZE, REAL_TRADE_SPY_POSITION_SIZE
from db import get_db


def calculate_shares(symbol: str, entry_price: float) -> int:
    """Calculate position size: floor(cap / entry). 100k cap for SPY, 50k otherwise."""
    cap = REAL_TRADE_SPY_POSITION_SIZE if symbol.upper() == "SPY" else REAL_TRADE_POSITION_SIZE
    if entry_price <= 0:
        return 0
    return math.floor(cap / entry_price)


def open_real_trade(
    symbol: str,
    direction: str,
    entry_price: float,
    stop_price: float | None,
    target_price: float | None,
    target_2_price: float | None,
    alert_type: str | None,
    alert_id: int | None,
    session_date: str,
) -> int:
    """Insert a new real trade with auto-calculated shares. Returns the trade id."""
    shares = calculate_shares(symbol, entry_price)
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO real_trades
               (symbol, direction, shares, entry_price, stop_price,
                target_price, target_2_price, alert_type, alert_id,
                session_date, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')""",
            (
                symbol, direction, shares, entry_price, stop_price,
                target_price, target_2_price, alert_type, alert_id,
                session_date,
            ),
        )
        return cur.lastrowid


def _compute_pnl(direction: str, entry: float, exit_price: float, shares: int) -> float:
    """BUY -> (exit - entry) * shares, SHORT -> (entry - exit) * shares."""
    if direction == "SHORT":
        return (entry - exit_price) * shares
    return (exit_price - entry) * shares


def close_real_trade(trade_id: int, exit_price: float, notes: str = "") -> float:
    """Close a trade at exit_price. Returns computed P&L."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT direction, entry_price, shares FROM real_trades WHERE id=?",
            (trade_id,),
        ).fetchone()
        if not row:
            return 0.0
        pnl = _compute_pnl(row["direction"], row["entry_price"], exit_price, row["shares"])
        conn.execute(
            """UPDATE real_trades
               SET exit_price=?, pnl=?, status='closed', notes=?, closed_at=?
               WHERE id=?""",
            (exit_price, round(pnl, 2), notes, datetime.now().isoformat(), trade_id),
        )
        return pnl


def stop_real_trade(trade_id: int, exit_price: float, notes: str = "") -> float:
    """Mark a trade as stopped out. Returns computed P&L."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT direction, entry_price, shares FROM real_trades WHERE id=?",
            (trade_id,),
        ).fetchone()
        if not row:
            return 0.0
        pnl = _compute_pnl(row["direction"], row["entry_price"], exit_price, row["shares"])
        conn.execute(
            """UPDATE real_trades
               SET exit_price=?, pnl=?, status='stopped', notes=?, closed_at=?
               WHERE id=?""",
            (exit_price, round(pnl, 2), notes, datetime.now().isoformat(), trade_id),
        )
        return pnl


def update_trade_notes(trade_id: int, notes: str):
    """Update the journal notes for a trade."""
    with get_db() as conn:
        conn.execute("UPDATE real_trades SET notes=? WHERE id=?", (notes, trade_id))


def has_open_trade(symbol: str) -> bool:
    """Check if there's already an open real trade on this symbol."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM real_trades WHERE symbol=? AND status='open' LIMIT 1",
            (symbol,),
        ).fetchone()
        return row is not None


def get_open_trades() -> list[dict]:
    """Return all open real trades."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM real_trades WHERE status='open' ORDER BY opened_at DESC",
        ).fetchall()
        return [dict(r) for r in rows]


def get_closed_trades(limit: int = 200) -> list[dict]:
    """Return closed/stopped trades ordered by most recent."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM real_trades
               WHERE status IN ('closed', 'stopped')
               ORDER BY closed_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_real_trade_stats() -> dict:
    """Aggregate stats for all closed real trades."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT pnl FROM real_trades WHERE status IN ('closed', 'stopped') AND pnl IS NOT NULL",
        ).fetchall()

    if not rows:
        return {
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "expectancy": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
        }

    pnls = [r["pnl"] for r in rows]
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p <= 0]
    total = len(pnls)

    total_pnl = sum(pnls)
    win_rate = (len(winners) / total * 100) if total else 0.0
    avg_win = (sum(winners) / len(winners)) if winners else 0.0
    avg_loss = (sum(losers) / len(losers)) if losers else 0.0
    expectancy = total_pnl / total if total else 0.0

    return {
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 1),
        "total_trades": total,
        "expectancy": round(expectancy, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
    }
