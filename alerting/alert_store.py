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
