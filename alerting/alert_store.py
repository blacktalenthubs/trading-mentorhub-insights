"""Alert persistence — SQLite CRUD and deduplication."""

from __future__ import annotations

from datetime import date

from analytics.intraday_rules import AlertSignal, AlertType
from db import get_db


def today_session() -> str:
    """Return today's session date as ISO string."""
    return date.today().isoformat()


def get_session_dates(user_id: int | None = None) -> list[str]:
    """Return distinct session dates with alerts, newest first.

    If *user_id* is provided, returns dates where that user has alerts
    plus legacy alerts with NULL user_id (same scoping as get_alerts_today).
    """
    with get_db() as conn:
        if user_id is not None:
            rows = conn.execute(
                "SELECT DISTINCT session_date FROM alerts WHERE (user_id = ? OR user_id IS NULL) ORDER BY session_date DESC",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT session_date FROM alerts ORDER BY session_date DESC"
            ).fetchall()
        return [r["session_date"] for r in rows]


def was_alert_fired(
    symbol: str,
    alert_type: str,
    session_date: str | None = None,
    user_id: int | None = None,
) -> bool:
    """Check if an alert was already fired for this symbol+type today.

    If *user_id* is provided, the check is scoped to that user.
    """
    session = session_date or today_session()
    with get_db() as conn:
        if user_id is not None:
            row = conn.execute(
                "SELECT 1 FROM alerts WHERE symbol=? AND alert_type=? AND session_date=? AND (user_id=? OR user_id IS NULL)",
                (symbol, alert_type, session, user_id),
            ).fetchone()
        else:
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
    user_id: int | None = None,
) -> int | None:
    """Insert a fired alert into the alerts table.

    Returns the new row id, or None on failure.  Dedup is handled by the
    caller via was_alert_fired() before calling this function.
    """
    session = session_date or today_session()
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO alerts
               (symbol, alert_type, direction, price, entry, stop, target_1, target_2,
                confidence, message, narrative, score, score_v2, notified_email, notified_sms,
                session_date, user_id, ai_conviction, ai_reasoning)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                getattr(signal, "narrative", ""),
                signal.score,
                getattr(signal, "score_v2", 0),
                int(notified_email),
                int(notified_sms),
                session,
                user_id,
                getattr(signal, "ai_conviction", None),
                getattr(signal, "ai_reasoning", None),
            ),
        )
        return cur.lastrowid or None


def update_alert_notification(
    alert_id: int,
    notified_email: bool = False,
    notified_sms: bool = False,
) -> None:
    """Update the notification status of an alert after delivery."""
    with get_db() as conn:
        conn.execute(
            "UPDATE alerts SET notified_email = ?, notified_sms = ? WHERE id = ?",
            (int(notified_email), int(notified_sms), alert_id),
        )


def create_active_entry(
    signal: AlertSignal,
    session_date: str | None = None,
    user_id: int | None = None,
):
    """Create an active entry record for tracking targets/stops."""
    session = session_date or today_session()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO active_entries
               (symbol, entry_price, stop_price, target_1, target_2,
                alert_type, session_date, status, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
               ON CONFLICT(symbol, session_date, alert_type, user_id) DO NOTHING""",
            (
                signal.symbol,
                signal.entry,
                signal.stop,
                signal.target_1,
                signal.target_2,
                signal.alert_type.value,
                session,
                user_id,
            ),
        )


def get_active_entries(
    symbol: str,
    session_date: str | None = None,
    user_id: int | None = None,
) -> list[dict]:
    """Get active BUY entries for a symbol today (for target/stop tracking).

    If *user_id* is provided, returns entries for that user plus legacy
    entries with NULL user_id.
    """
    session = session_date or today_session()
    with get_db() as conn:
        if user_id is not None:
            rows = conn.execute(
                """SELECT entry_price, stop_price, target_1, target_2, alert_type
                   FROM active_entries
                   WHERE symbol=? AND session_date=? AND status='active'
                     AND (user_id=? OR user_id IS NULL)""",
                (symbol, session, user_id),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT entry_price, stop_price, target_1, target_2, alert_type
                   FROM active_entries
                   WHERE symbol=? AND session_date=? AND status='active'""",
                (symbol, session),
            ).fetchall()
        return [dict(r) for r in rows]


def close_active_entry(
    symbol: str,
    alert_type: str,
    session_date: str | None = None,
    user_id: int | None = None,
):
    """Mark an active entry as closed (stopped or target hit)."""
    session = session_date or today_session()
    with get_db() as conn:
        if user_id is not None:
            conn.execute(
                """UPDATE active_entries SET status='closed'
                   WHERE symbol=? AND alert_type=? AND session_date=?
                     AND (user_id=? OR user_id IS NULL)""",
                (symbol, alert_type, session, user_id),
            )
        else:
            conn.execute(
                """UPDATE active_entries SET status='closed'
                   WHERE symbol=? AND alert_type=? AND session_date=?""",
                (symbol, alert_type, session),
            )


def close_all_entries_for_symbol(
    symbol: str,
    session_date: str | None = None,
    user_id: int | None = None,
):
    """Close all active entries for a symbol (used on stop loss)."""
    session = session_date or today_session()
    with get_db() as conn:
        if user_id is not None:
            conn.execute(
                """UPDATE active_entries SET status='stopped'
                   WHERE symbol=? AND session_date=? AND status='active'
                     AND (user_id=? OR user_id IS NULL)""",
                (symbol, session, user_id),
            )
        else:
            conn.execute(
                """UPDATE active_entries SET status='stopped'
                   WHERE symbol=? AND session_date=? AND status='active'""",
                (symbol, session),
            )


def get_alert_id(
    symbol: str,
    alert_type: str,
    session_date: str | None = None,
    user_id: int | None = None,
) -> int | None:
    """Look up an existing alert_id for a symbol+type+session. Returns None if not found."""
    session = session_date or today_session()
    with get_db() as conn:
        if user_id is not None:
            row = conn.execute(
                "SELECT id FROM alerts WHERE symbol=? AND alert_type=? AND session_date=? AND (user_id=? OR user_id IS NULL) LIMIT 1",
                (symbol, alert_type, session, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM alerts WHERE symbol=? AND alert_type=? AND session_date=? LIMIT 1",
                (symbol, alert_type, session),
            ).fetchone()
        return row["id"] if row else None


def get_alerts_today(session_date: str | None = None, user_id: int | None = None):
    """Get all alerts fired today as a list of dicts.

    If *user_id* is provided, returns alerts for that user plus legacy
    alerts with NULL user_id.
    """
    session = session_date or today_session()
    with get_db() as conn:
        if user_id is not None:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE session_date=? AND (user_id=? OR user_id IS NULL) ORDER BY created_at DESC",
                (session, user_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE session_date=? ORDER BY created_at DESC",
                (session,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_alerts_history(limit: int = 100, user_id: int | None = None):
    """Get recent alert history across all sessions.

    If *user_id* is provided, returns alerts for that user plus legacy
    alerts with NULL user_id.
    """
    with get_db() as conn:
        if user_id is not None:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE (user_id=? OR user_id IS NULL) ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM alerts ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def ack_alert(alert_id: int, action: str) -> bool:
    """Mark an alert as 'took' or 'skipped'. Returns True on success."""
    if action not in ("took", "skipped"):
        return False
    with get_db() as conn:
        conn.execute(
            "UPDATE alerts SET user_action = ?, acked_at = CURRENT_TIMESTAMP WHERE id = ?",
            (action, alert_id),
        )
    return True


def get_alert_by_id(alert_id: int) -> dict | None:
    """Fetch a single alert by its id."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
        return dict(row) if row else None


def get_acked_trades(user_id: int, days: int = 90) -> list[dict]:
    """Return alerts where user_action='took' within the last N days."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM alerts
               WHERE user_id = ? AND user_action = 'took'
                 AND created_at >= datetime('now', ? || ' days')
               ORDER BY created_at DESC""",
            (user_id, f"-{days}"),
        ).fetchall()
        return [dict(r) for r in rows]


def get_user_id_by_chat_id(chat_id: str) -> int | None:
    """Look up a user_id by their Telegram chat_id."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT user_id FROM user_notification_prefs WHERE telegram_chat_id = ? LIMIT 1",
            (str(chat_id),),
        ).fetchone()
        return row["user_id"] if row else None


def has_acked_entry(symbol: str, user_id: int, session_date: str | None = None) -> bool:
    """Check if user has ACK'd (took) any BUY/SHORT alert for this symbol today.

    Returns False if the user_action column doesn't exist yet (pre-migration).
    """
    session = session_date or today_session()
    try:
        with get_db() as conn:
            row = conn.execute(
                """SELECT 1 FROM alerts
                   WHERE symbol=? AND user_id=? AND session_date=?
                     AND direction IN ('BUY','SHORT') AND user_action='took'
                   LIMIT 1""",
                (symbol, user_id, session),
            ).fetchone()
            return row is not None
    except Exception:
        return False


def has_open_acked_direction(symbol: str, direction: str, user_id: int, session_date: str | None = None) -> bool:
    """Check if user has an ACK'd alert in the same direction with an open trade.

    Returns True if: alert exists with user_action='took' for this symbol+direction today
    AND there's an open real_trade for this symbol.
    """
    session = session_date or today_session()
    try:
        with get_db() as conn:
            row = conn.execute(
                """SELECT 1 FROM alerts a
                   JOIN real_trades rt ON rt.symbol = a.symbol AND rt.status = 'open'
                   WHERE a.symbol=? AND a.direction=? AND a.user_id=?
                     AND a.session_date=? AND a.user_action='took'
                   LIMIT 1""",
                (symbol, direction, user_id, session),
            ).fetchone()
            return row is not None
    except Exception:
        return False


def user_has_used_ack(user_id: int) -> bool:
    """Check if user has ever ACK'd or skipped any alert (used the button system).

    Returns False if the user_action column doesn't exist yet (pre-migration).
    """
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT 1 FROM alerts WHERE user_id=? AND user_action IS NOT NULL LIMIT 1",
                (user_id,),
            ).fetchone()
            return row is not None
    except Exception:
        return False


def create_active_entry_from_alert(alert_id: int, user_id: int | None = None):
    """Create an active entry from an existing alert record (ACK callback)."""
    alert = get_alert_by_id(alert_id)
    if not alert:
        return
    signal = AlertSignal(
        symbol=alert["symbol"],
        alert_type=AlertType(alert["alert_type"]),
        direction=alert["direction"],
        price=alert["price"],
        entry=alert.get("entry"),
        stop=alert.get("stop"),
        target_1=alert.get("target_1"),
        target_2=alert.get("target_2"),
        confidence=alert.get("confidence", "medium"),
        message=alert.get("message", ""),
    )
    create_active_entry(
        signal,
        alert.get("session_date") or today_session(),
        user_id=user_id or alert.get("user_id"),
    )


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


def get_session_summary(session_date: str | None = None, user_id: int | None = None) -> dict:
    """Aggregate today's alerts into a session summary.

    Returns dict with total, buy_count, sell_count, short_count,
    t1_hits, stopped_out, signals_by_type, best_signal, worst_signal.
    """
    alerts = get_alerts_today(session_date, user_id=user_id)

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
    user_id: int | None = None,
):
    """Persist a cooldown for a symbol. Survives process restarts."""
    from datetime import datetime, timedelta

    session = session_date or today_session()
    until = (datetime.now() + timedelta(minutes=minutes)).isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO cooldowns (symbol, cooldown_until, reason, session_date, user_id)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(symbol, session_date, user_id) DO UPDATE SET
                   cooldown_until = excluded.cooldown_until,
                   reason = excluded.reason""",
            (symbol, until, reason, session, user_id),
        )


def get_active_cooldowns(
    session_date: str | None = None,
    user_id: int | None = None,
) -> set[str]:
    """Return set of symbols currently in cooldown.

    If *user_id* is provided, returns cooldowns for that user plus legacy
    cooldowns with NULL user_id.
    """
    from datetime import datetime

    session = session_date or today_session()
    now = datetime.now().isoformat()
    with get_db() as conn:
        if user_id is not None:
            rows = conn.execute(
                "SELECT symbol FROM cooldowns WHERE session_date = ? AND cooldown_until > ? AND (user_id = ? OR user_id IS NULL)",
                (session, now, user_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT symbol FROM cooldowns WHERE session_date = ? AND cooldown_until > ?",
                (session, now),
            ).fetchall()
        return {row["symbol"] for row in rows}


def is_symbol_cooled_down(
    symbol: str,
    session_date: str | None = None,
    user_id: int | None = None,
) -> bool:
    """Check if a specific symbol is in cooldown.

    If *user_id* is provided, checks cooldowns for that user plus legacy
    cooldowns with NULL user_id.
    """
    from datetime import datetime

    session = session_date or today_session()
    now = datetime.now().isoformat()
    with get_db() as conn:
        if user_id is not None:
            row = conn.execute(
                "SELECT 1 FROM cooldowns WHERE symbol = ? AND session_date = ? AND cooldown_until > ? AND (user_id = ? OR user_id IS NULL)",
                (symbol, session, now, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM cooldowns WHERE symbol = ? AND session_date = ? AND cooldown_until > ?",
                (symbol, session, now),
            ).fetchone()
        return row is not None
