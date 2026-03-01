"""Alert persistence — SQLite CRUD and deduplication."""

from __future__ import annotations

from datetime import date

from analytics.intraday_rules import AlertSignal, AlertType
from db import get_db


def today_session() -> str:
    """Return today's session date as ISO string."""
    return date.today().isoformat()


def was_alert_fired(symbol: str, alert_type: str, session_date: str | None = None) -> bool:
    """Check if an alert was already fired for this symbol+type today."""
    session = session_date or today_session()
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM alerts WHERE symbol=? AND alert_type=? AND session_date=?",
            (symbol, alert_type, session),
        ).fetchone()
        return row is not None


def record_alert(
    signal: AlertSignal,
    session_date: str | None = None,
    notified_email: bool = False,
    notified_sms: bool = False,
) -> int:
    """Insert a fired alert into the alerts table. Returns the new row id."""
    session = session_date or today_session()
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO alerts
               (symbol, alert_type, direction, price, entry, stop, target_1, target_2,
                confidence, message, notified_email, notified_sms, session_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal.symbol,
                signal.alert_type.value,
                signal.direction,
                signal.price,
                signal.entry,
                signal.stop,
                signal.target_1,
                signal.target_2,
                signal.confidence,
                signal.message,
                int(notified_email),
                int(notified_sms),
                session,
            ),
        )
        return cur.lastrowid


def create_active_entry(signal: AlertSignal, session_date: str | None = None):
    """Create an active entry record for tracking targets/stops."""
    session = session_date or today_session()
    with get_db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO active_entries
               (symbol, entry_price, stop_price, target_1, target_2,
                alert_type, session_date, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'active')""",
            (
                signal.symbol,
                signal.entry,
                signal.stop,
                signal.target_1,
                signal.target_2,
                signal.alert_type.value,
                session,
            ),
        )


def get_active_entries(symbol: str, session_date: str | None = None) -> list[dict]:
    """Get active BUY entries for a symbol today (for target/stop tracking)."""
    session = session_date or today_session()
    with get_db() as conn:
        rows = conn.execute(
            """SELECT entry_price, stop_price, target_1, target_2, alert_type
               FROM active_entries
               WHERE symbol=? AND session_date=? AND status='active'""",
            (symbol, session),
        ).fetchall()
        return [dict(r) for r in rows]


def close_active_entry(symbol: str, alert_type: str, session_date: str | None = None):
    """Mark an active entry as closed (stopped or target hit)."""
    session = session_date or today_session()
    with get_db() as conn:
        conn.execute(
            """UPDATE active_entries SET status='closed'
               WHERE symbol=? AND alert_type=? AND session_date=?""",
            (symbol, alert_type, session),
        )


def close_all_entries_for_symbol(symbol: str, session_date: str | None = None):
    """Close all active entries for a symbol (used on stop loss)."""
    session = session_date or today_session()
    with get_db() as conn:
        conn.execute(
            """UPDATE active_entries SET status='stopped'
               WHERE symbol=? AND session_date=? AND status='active'""",
            (symbol, session),
        )


def get_alert_id(symbol: str, alert_type: str, session_date: str | None = None) -> int | None:
    """Look up an existing alert_id for a symbol+type+session. Returns None if not found."""
    session = session_date or today_session()
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM alerts WHERE symbol=? AND alert_type=? AND session_date=? LIMIT 1",
            (symbol, alert_type, session),
        ).fetchone()
        return row["id"] if row else None


def get_alerts_today(session_date: str | None = None):
    """Get all alerts fired today as a list of dicts."""
    session = session_date or today_session()
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM alerts WHERE session_date=? ORDER BY created_at DESC""",
            (session,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_alerts_history(limit: int = 100):
    """Get recent alert history across all sessions."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM alerts ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_monitor_status(symbols_checked: int, alerts_fired: int, status: str = "running"):
    """Update the single-row monitor heartbeat."""
    with get_db() as conn:
        conn.execute(
            """INSERT INTO monitor_status (id, last_poll_at, symbols_checked, alerts_fired, status)
               VALUES (1, CURRENT_TIMESTAMP, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   last_poll_at=CURRENT_TIMESTAMP,
                   symbols_checked=excluded.symbols_checked,
                   alerts_fired=excluded.alerts_fired,
                   status=excluded.status""",
            (symbols_checked, alerts_fired, status),
        )


def get_monitor_status() -> dict | None:
    """Get the monitor's last heartbeat."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM monitor_status WHERE id=1").fetchone()
        return dict(row) if row else None


def get_session_summary(session_date: str | None = None) -> dict:
    """Aggregate today's alerts into a session summary.

    Returns dict with total, buy_count, sell_count, short_count,
    t1_hits, stopped_out, signals_by_type, best_signal, worst_signal.
    """
    alerts = get_alerts_today(session_date)

    summary = {
        "total": len(alerts),
        "buy_count": 0,
        "sell_count": 0,
        "short_count": 0,
        "t1_hits": 0,
        "t2_hits": 0,
        "stopped_out": 0,
        "signals_by_type": {},
        "symbols": set(),
        "alerts": alerts,
    }

    for a in alerts:
        direction = a.get("direction", "")
        alert_type = a.get("alert_type", "")
        symbol = a.get("symbol", "")

        if direction == "BUY":
            summary["buy_count"] += 1
        elif direction == "SELL":
            summary["sell_count"] += 1
        elif direction == "SHORT":
            summary["short_count"] += 1

        if alert_type == "target_1_hit":
            summary["t1_hits"] += 1
        elif alert_type == "target_2_hit":
            summary["t2_hits"] += 1
        elif alert_type in ("stop_loss_hit", "auto_stop_out"):
            summary["stopped_out"] += 1

        summary["signals_by_type"][alert_type] = summary["signals_by_type"].get(alert_type, 0) + 1
        summary["symbols"].add(symbol)

    summary["symbols"] = list(summary["symbols"])
    return summary


# ---------------------------------------------------------------------------
# Cooldown persistence
# ---------------------------------------------------------------------------


def save_cooldown(
    symbol: str,
    minutes: int,
    reason: str = "",
    session_date: str | None = None,
):
    """Persist a cooldown for a symbol. Survives process restarts."""
    from datetime import datetime, timedelta

    session = session_date or today_session()
    until = (datetime.now() + timedelta(minutes=minutes)).isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO cooldowns (symbol, cooldown_until, reason, session_date)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(symbol, session_date) DO UPDATE SET
                   cooldown_until = excluded.cooldown_until,
                   reason = excluded.reason""",
            (symbol, until, reason, session),
        )


def get_active_cooldowns(session_date: str | None = None) -> set[str]:
    """Return set of symbols currently in cooldown."""
    from datetime import datetime

    session = session_date or today_session()
    now = datetime.now().isoformat()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT symbol FROM cooldowns WHERE session_date = ? AND cooldown_until > ?",
            (session, now),
        ).fetchall()
        return {row["symbol"] for row in rows}


def is_symbol_cooled_down(symbol: str, session_date: str | None = None) -> bool:
    """Check if a specific symbol is in cooldown."""
    from datetime import datetime

    session = session_date or today_session()
    now = datetime.now().isoformat()
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM cooldowns WHERE symbol = ? AND session_date = ? AND cooldown_until > ?",
            (symbol, session, now),
        ).fetchone()
        return row is not None
