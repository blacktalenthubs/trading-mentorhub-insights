"""Tests for per-user notification preferences and alert scoping.

Covers:
- Notification prefs CRUD (get/upsert)
- Per-user dedup (was_alert_fired with user_id)
- Per-user alert recording and retrieval
- notify_user routing (email/telegram enabled/disabled)
- get_users_for_symbol mapping
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from unittest.mock import patch

import pytest

from analytics.intraday_rules import AlertSignal, AlertType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    """Create a temporary SQLite DB with the full schema and patch get_db."""
    db_path = str(tmp_path / "test.db")

    def _get_connection():
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _get_db():
        conn = _get_connection()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    conn = _get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            direction TEXT NOT NULL,
            price REAL NOT NULL,
            entry REAL,
            stop REAL,
            target_1 REAL,
            target_2 REAL,
            confidence TEXT,
            message TEXT,
            narrative TEXT DEFAULT '',
            score INTEGER DEFAULT 0,
            score_v2 INTEGER DEFAULT 0,
            notified_email INTEGER DEFAULT 0,
            notified_sms INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            session_date TEXT NOT NULL,
            user_id INTEGER
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_dedup ON alerts(symbol, alert_type, session_date, user_id);

        CREATE TABLE IF NOT EXISTS user_notification_prefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            telegram_chat_id TEXT DEFAULT '',
            notification_email TEXT DEFAULT '',
            telegram_enabled INTEGER DEFAULT 1,
            email_enabled INTEGER DEFAULT 1,
            anthropic_api_key TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, symbol)
        );

        CREATE TABLE IF NOT EXISTS active_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            entry_price REAL,
            stop_price REAL,
            target_1 REAL,
            target_2 REAL,
            alert_type TEXT,
            session_date TEXT,
            status TEXT DEFAULT 'active',
            user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, session_date, alert_type, user_id)
        );

        CREATE TABLE IF NOT EXISTS cooldowns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            cooldown_until TEXT NOT NULL,
            reason TEXT,
            session_date TEXT NOT NULL,
            user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, session_date, user_id)
        );

        CREATE TABLE IF NOT EXISTS monitor_status (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_poll_at TIMESTAMP,
            symbols_checked INTEGER DEFAULT 0,
            alerts_fired INTEGER DEFAULT 0,
            status TEXT DEFAULT 'idle'
        );
    """)
    # Seed two test users
    conn.execute(
        "INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)",
        ("alice@test.com", "fakehash", "Alice"),
    )
    conn.execute(
        "INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)",
        ("bob@test.com", "fakehash", "Bob"),
    )
    conn.commit()
    conn.close()

    with (
        patch("db.get_db", _get_db),
        patch("db.get_connection", _get_connection),
        patch("alerting.alert_store.get_db", _get_db),
    ):
        yield _get_db


def _make_signal(symbol="AAPL", alert_type=AlertType.MA_BOUNCE_20,
                 direction="BUY", price=150.0):
    return AlertSignal(
        symbol=symbol,
        alert_type=alert_type,
        direction=direction,
        price=price,
        entry=price,
        stop=price - 1.0,
        target_1=price + 1.0,
        target_2=price + 2.0,
        confidence="high",
        message="Test signal",
    )


# ---------------------------------------------------------------------------
# Notification Prefs CRUD
# ---------------------------------------------------------------------------

class TestNotificationPrefs:
    def test_get_prefs_returns_none_when_empty(self, tmp_db):
        from db import get_notification_prefs
        assert get_notification_prefs(1) is None

    def test_upsert_and_get_prefs(self, tmp_db):
        from db import get_notification_prefs, upsert_notification_prefs

        upsert_notification_prefs(
            1,
            telegram_chat_id="12345",
            notification_email="alice@test.com",
            telegram_enabled=True,
            email_enabled=False,
        )
        prefs = get_notification_prefs(1)
        assert prefs is not None
        assert prefs["telegram_chat_id"] == "12345"
        assert prefs["notification_email"] == "alice@test.com"
        assert prefs["telegram_enabled"] == 1
        assert prefs["email_enabled"] == 0

    def test_upsert_updates_existing(self, tmp_db):
        from db import get_notification_prefs, upsert_notification_prefs

        upsert_notification_prefs(1, telegram_chat_id="old_id")
        upsert_notification_prefs(1, telegram_chat_id="new_id")

        prefs = get_notification_prefs(1)
        assert prefs["telegram_chat_id"] == "new_id"

    def test_different_users_have_separate_prefs(self, tmp_db):
        from db import get_notification_prefs, upsert_notification_prefs

        upsert_notification_prefs(1, telegram_chat_id="alice_chat")
        upsert_notification_prefs(2, telegram_chat_id="bob_chat")

        assert get_notification_prefs(1)["telegram_chat_id"] == "alice_chat"
        assert get_notification_prefs(2)["telegram_chat_id"] == "bob_chat"


# ---------------------------------------------------------------------------
# Per-user dedup
# ---------------------------------------------------------------------------

class TestPerUserDedup:
    def test_was_alert_fired_scoped_to_user(self, tmp_db):
        from alerting.alert_store import record_alert, was_alert_fired

        session = date.today().isoformat()
        signal = _make_signal()

        # Record for user 1
        record_alert(signal, session_date=session, user_id=1)

        # User 1 should see it as fired
        assert was_alert_fired("AAPL", "ma_bounce_20", session, user_id=1) is True
        # User 2 should NOT see it as fired
        assert was_alert_fired("AAPL", "ma_bounce_20", session, user_id=2) is False

    def test_get_alerts_today_scoped_to_user(self, tmp_db):
        from alerting.alert_store import get_alerts_today, record_alert

        session = date.today().isoformat()
        signal = _make_signal()

        record_alert(signal, session_date=session, user_id=1)
        record_alert(signal, session_date=session, user_id=2)

        # Each user sees only their alert
        assert len(get_alerts_today(session, user_id=1)) == 1
        assert len(get_alerts_today(session, user_id=2)) == 1
        # Global view sees both
        assert len(get_alerts_today(session)) == 2

    def test_get_alerts_history_scoped_to_user(self, tmp_db):
        from alerting.alert_store import get_alerts_history, record_alert

        session = date.today().isoformat()
        record_alert(_make_signal(), session_date=session, user_id=1)
        record_alert(_make_signal("TSLA"), session_date=session, user_id=2)

        assert len(get_alerts_history(user_id=1)) == 1
        assert len(get_alerts_history(user_id=2)) == 1
        assert len(get_alerts_history()) == 2

    def test_get_session_summary_scoped_to_user(self, tmp_db):
        from alerting.alert_store import get_session_summary, record_alert

        session = date.today().isoformat()
        record_alert(_make_signal(), session_date=session, user_id=1)
        record_alert(_make_signal("TSLA"), session_date=session, user_id=2)

        assert get_session_summary(session, user_id=1)["total"] == 1
        assert get_session_summary(session, user_id=2)["total"] == 1
        assert get_session_summary(session)["total"] == 2


# ---------------------------------------------------------------------------
# get_users_for_symbol
# ---------------------------------------------------------------------------

class TestGetUsersForSymbol:
    def test_returns_users_for_symbol(self, tmp_db):
        from db import get_users_for_symbol

        # Add watchlist entries
        with tmp_db() as conn:
            conn.execute("INSERT INTO watchlist (user_id, symbol) VALUES (1, 'AAPL')")
            conn.execute("INSERT INTO watchlist (user_id, symbol) VALUES (2, 'AAPL')")
            conn.execute("INSERT INTO watchlist (user_id, symbol) VALUES (1, 'TSLA')")

        users = get_users_for_symbol("AAPL")
        assert sorted(users) == [1, 2]

    def test_returns_empty_for_unknown_symbol(self, tmp_db):
        from db import get_users_for_symbol
        assert get_users_for_symbol("UNKNOWN") == []

    def test_returns_single_user_for_unique_symbol(self, tmp_db):
        from db import get_users_for_symbol

        with tmp_db() as conn:
            conn.execute("INSERT INTO watchlist (user_id, symbol) VALUES (2, 'META')")

        assert get_users_for_symbol("META") == [2]


# ---------------------------------------------------------------------------
# notify_user routing
# ---------------------------------------------------------------------------

class TestNotifyUser:
    def test_email_and_telegram_both_enabled(self, tmp_db):
        from alerting.notifier import notify_user

        signal = _make_signal()
        prefs = {
            "email_enabled": 1,
            "notification_email": "alice@test.com",
            "telegram_enabled": 1,
            "telegram_chat_id": "12345",
        }

        with (
            patch("alerting.notifier.send_email_to", return_value=True) as mock_email,
            patch("alerting.notifier._send_telegram_to", return_value=True) as mock_tg,
        ):
            email_ok, tg_ok = notify_user(signal, prefs)

        assert email_ok is True
        assert tg_ok is True
        mock_email.assert_called_once()
        mock_tg.assert_called_once()

    def test_email_disabled_telegram_enabled(self, tmp_db):
        from alerting.notifier import notify_user

        signal = _make_signal()
        prefs = {
            "email_enabled": 0,
            "notification_email": "alice@test.com",
            "telegram_enabled": 1,
            "telegram_chat_id": "12345",
        }

        with (
            patch("alerting.notifier.send_email_to") as mock_email,
            patch("alerting.notifier._send_telegram_to", return_value=True) as mock_tg,
        ):
            email_ok, tg_ok = notify_user(signal, prefs)

        assert email_ok is False
        assert tg_ok is True
        mock_email.assert_not_called()

    def test_empty_chat_id_skips_telegram(self, tmp_db):
        from alerting.notifier import notify_user

        signal = _make_signal()
        prefs = {
            "email_enabled": 0,
            "telegram_enabled": 1,
            "telegram_chat_id": "",
        }

        with patch("alerting.notifier._send_telegram_to") as mock_tg:
            email_ok, tg_ok = notify_user(signal, prefs)

        assert tg_ok is False
        mock_tg.assert_not_called()

    def test_both_disabled_sends_nothing(self, tmp_db):
        from alerting.notifier import notify_user

        signal = _make_signal()
        prefs = {
            "email_enabled": 0,
            "notification_email": "alice@test.com",
            "telegram_enabled": 0,
            "telegram_chat_id": "12345",
        }

        with (
            patch("alerting.notifier.send_email_to") as mock_email,
            patch("alerting.notifier._send_telegram_to") as mock_tg,
        ):
            email_ok, tg_ok = notify_user(signal, prefs)

        assert email_ok is False
        assert tg_ok is False
        mock_email.assert_not_called()
        mock_tg.assert_not_called()
