"""Options trade tracking — CRUD for manually-confirmed options plays."""

from __future__ import annotations

from datetime import datetime

from db import get_db


def open_options_trade(
    symbol: str,
    option_type: str,
    strike: float,
    expiration: str,
    contracts: int,
    premium_per_contract: float,
    alert_type: str | None,
    alert_id: int | None,
    session_date: str,
) -> int:
    """Insert a new options trade. Returns the trade id."""
    entry_cost = contracts * premium_per_contract * 100
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO real_options_trades
               (symbol, option_type, strike, expiration, contracts,
                premium_per_contract, entry_cost, alert_type, alert_id,
                session_date, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')""",
            (
                symbol, option_type, strike, expiration, contracts,
                premium_per_contract, entry_cost, alert_type, alert_id,
                session_date,
            ),
        )
        return cur.lastrowid


def close_options_trade(trade_id: int, exit_premium: float, notes: str = "") -> float:
    """Close an options trade at exit_premium. Returns computed P&L."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT premium_per_contract, contracts FROM real_options_trades WHERE id=?",
            (trade_id,),
        ).fetchone()
        if not row:
            return 0.0
        contracts = row["contracts"]
        exit_proceeds = contracts * exit_premium * 100
        entry_cost = contracts * row["premium_per_contract"] * 100
        pnl = exit_proceeds - entry_cost
        conn.execute(
            """UPDATE real_options_trades
               SET exit_premium=?, exit_proceeds=?, pnl=?, status='closed',
                   notes=?, closed_at=?
               WHERE id=?""",
            (
                exit_premium, round(exit_proceeds, 2), round(pnl, 2),
                notes, datetime.now().isoformat(), trade_id,
            ),
        )
        return pnl


def expire_options_trade(trade_id: int, notes: str = "") -> float:
    """Mark an options trade as expired worthless. Returns P&L (negative)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT entry_cost FROM real_options_trades WHERE id=?",
            (trade_id,),
        ).fetchone()
        if not row:
            return 0.0
        pnl = -row["entry_cost"]
        conn.execute(
            """UPDATE real_options_trades
               SET exit_premium=0, exit_proceeds=0, pnl=?, status='expired',
                   notes=?, closed_at=?
               WHERE id=?""",
            (round(pnl, 2), notes, datetime.now().isoformat(), trade_id),
        )
        return pnl


def has_open_options_trade(symbol: str) -> bool:
    """Check if there's already an open options trade on this symbol."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM real_options_trades WHERE symbol=? AND status='open' LIMIT 1",
            (symbol,),
        ).fetchone()
        return row is not None


def get_open_options_trades() -> list[dict]:
    """Return all open options trades."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM real_options_trades WHERE status='open' ORDER BY opened_at DESC",
        ).fetchall()
        return [dict(r) for r in rows]


def get_closed_options_trades(limit: int = 200) -> list[dict]:
    """Return closed/expired options trades ordered by most recent."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM real_options_trades
               WHERE status IN ('closed', 'expired')
               ORDER BY closed_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_options_trade_stats() -> dict:
    """Aggregate stats for closed options trades."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT pnl FROM real_options_trades WHERE status IN ('closed', 'expired') AND pnl IS NOT NULL",
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


def update_options_trade_notes(trade_id: int, notes: str):
    """Update the journal notes for an options trade."""
    with get_db() as conn:
        conn.execute(
            "UPDATE real_options_trades SET notes=? WHERE id=?", (notes, trade_id),
        )
