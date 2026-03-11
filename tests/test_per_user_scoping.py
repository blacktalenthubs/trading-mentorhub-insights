"""Tests for per-user scoping of active entries, cooldowns, and alert flow.

Covers:
- Cooldown isolation: each user has independent cooldowns
- Active entry isolation: each user has independent entries
- Backward compat: NULL user_id entries/cooldowns visible to all
- Integration: full alert flow per-user
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest

from analytics.intraday_rules import AlertSignal, AlertType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    """Create a temporary SQLite DB with the full schema (including user_id
    on active_entries and cooldowns) and patch get_db to use it."""
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
            ai_conviction INTEGER,
            ai_reasoning TEXT,
            notified_email INTEGER DEFAULT 0,
            notified_sms INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            session_date TEXT NOT NULL,
            user_id INTEGER
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_dedup ON alerts(symbol, alert_type, session_date, user_id);

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

        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, symbol)
        );

        CREATE TABLE IF NOT EXISTS user_notification_prefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            telegram_chat_id TEXT DEFAULT '',
            notification_email TEXT DEFAULT '',
            telegram_enabled INTEGER DEFAULT 1,
            email_enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
# Cooldown isolation tests
# ---------------------------------------------------------------------------

class TestCooldownIsolation:
    def test_save_cooldown_scoped_to_user(self, tmp_db):
        """User 1 cooldown does not affect User 2."""
        from alerting.alert_store import is_symbol_cooled_down, save_cooldown

        session = date.today().isoformat()
        save_cooldown("AAPL", 30, reason="stop_loss_hit", session_date=session, user_id=1)

        assert is_symbol_cooled_down("AAPL", session_date=session, user_id=1) is True
        assert is_symbol_cooled_down("AAPL", session_date=session, user_id=2) is False

    def test_get_active_cooldowns_per_user(self, tmp_db):
        """Each user sees only their own cooldowns."""
        from alerting.alert_store import get_active_cooldowns, save_cooldown

        session = date.today().isoformat()
        save_cooldown("AAPL", 30, reason="stop", session_date=session, user_id=1)
        save_cooldown("TSLA", 30, reason="stop", session_date=session, user_id=2)

        assert get_active_cooldowns(session_date=session, user_id=1) == {"AAPL"}
        assert get_active_cooldowns(session_date=session, user_id=2) == {"TSLA"}

    def test_is_cooled_down_per_user(self, tmp_db):
        """User 1 cooled on AAPL, User 2 is not."""
        from alerting.alert_store import is_symbol_cooled_down, save_cooldown

        session = date.today().isoformat()
        save_cooldown("AAPL", 30, reason="stop", session_date=session, user_id=1)

        assert is_symbol_cooled_down("AAPL", session_date=session, user_id=1) is True
        assert is_symbol_cooled_down("AAPL", session_date=session, user_id=2) is False

    def test_cooldown_upsert_per_user(self, tmp_db):
        """Same symbol, different cooldowns per user (upsert works per-user)."""
        from alerting.alert_store import is_symbol_cooled_down, save_cooldown

        session = date.today().isoformat()

        # User 1: expired cooldown
        save_cooldown("AAPL", 0, reason="first", session_date=session, user_id=1)
        # User 2: active cooldown
        save_cooldown("AAPL", 30, reason="stop", session_date=session, user_id=2)

        assert is_symbol_cooled_down("AAPL", session_date=session, user_id=1) is False
        assert is_symbol_cooled_down("AAPL", session_date=session, user_id=2) is True

        # User 1 upserts to active
        save_cooldown("AAPL", 30, reason="second", session_date=session, user_id=1)
        assert is_symbol_cooled_down("AAPL", session_date=session, user_id=1) is True


# ---------------------------------------------------------------------------
# Active entry isolation tests
# ---------------------------------------------------------------------------

class TestActiveEntryIsolation:
    def test_create_entry_per_user(self, tmp_db):
        """Two users can track the same symbol independently."""
        from alerting.alert_store import create_active_entry, get_active_entries

        session = date.today().isoformat()
        signal = _make_signal("AAPL")

        create_active_entry(signal, session, user_id=1)
        create_active_entry(signal, session, user_id=2)

        entries_u1 = get_active_entries("AAPL", session, user_id=1)
        entries_u2 = get_active_entries("AAPL", session, user_id=2)

        assert len(entries_u1) == 1
        assert len(entries_u2) == 1

    def test_get_entries_scoped_to_user(self, tmp_db):
        """Each user sees only their own entries."""
        from alerting.alert_store import create_active_entry, get_active_entries

        session = date.today().isoformat()

        create_active_entry(_make_signal("AAPL"), session, user_id=1)
        create_active_entry(_make_signal("TSLA"), session, user_id=2)

        assert len(get_active_entries("AAPL", session, user_id=1)) == 1
        assert len(get_active_entries("AAPL", session, user_id=2)) == 0
        assert len(get_active_entries("TSLA", session, user_id=2)) == 1
        assert len(get_active_entries("TSLA", session, user_id=1)) == 0

    def test_close_entry_per_user(self, tmp_db):
        """Closing User 1's entry doesn't affect User 2."""
        from alerting.alert_store import (
            close_active_entry, create_active_entry, get_active_entries,
        )

        session = date.today().isoformat()
        signal = _make_signal("AAPL")

        create_active_entry(signal, session, user_id=1)
        create_active_entry(signal, session, user_id=2)

        close_active_entry("AAPL", "ma_bounce_20", session, user_id=1)

        assert len(get_active_entries("AAPL", session, user_id=1)) == 0
        assert len(get_active_entries("AAPL", session, user_id=2)) == 1

    def test_close_all_entries_per_user(self, tmp_db):
        """Stop-out closes only that user's entries."""
        from alerting.alert_store import (
            close_all_entries_for_symbol, create_active_entry, get_active_entries,
        )

        session = date.today().isoformat()

        create_active_entry(_make_signal("AAPL"), session, user_id=1)
        create_active_entry(
            _make_signal("AAPL", alert_type=AlertType.INTRADAY_SUPPORT_BOUNCE),
            session, user_id=1,
        )
        create_active_entry(_make_signal("AAPL"), session, user_id=2)

        close_all_entries_for_symbol("AAPL", session, user_id=1)

        assert len(get_active_entries("AAPL", session, user_id=1)) == 0
        assert len(get_active_entries("AAPL", session, user_id=2)) == 1


# ---------------------------------------------------------------------------
# Backward compatibility tests
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_null_user_id_cooldowns_visible(self, tmp_db):
        """Legacy cooldowns (NULL user_id) are visible to all users."""
        from alerting.alert_store import get_active_cooldowns

        session = date.today().isoformat()
        until = (datetime.now() + timedelta(minutes=30)).isoformat()

        # Insert legacy cooldown with NULL user_id
        with tmp_db() as conn:
            conn.execute(
                "INSERT INTO cooldowns (symbol, cooldown_until, reason, session_date, user_id) VALUES (?, ?, ?, ?, NULL)",
                ("AAPL", until, "legacy", session),
            )

        assert "AAPL" in get_active_cooldowns(session_date=session, user_id=1)
        assert "AAPL" in get_active_cooldowns(session_date=session, user_id=2)

    def test_null_user_id_entries_visible(self, tmp_db):
        """Legacy entries (NULL user_id) are visible to all users."""
        from alerting.alert_store import get_active_entries

        session = date.today().isoformat()

        # Insert legacy entry with NULL user_id
        with tmp_db() as conn:
            conn.execute(
                """INSERT INTO active_entries
                   (symbol, entry_price, stop_price, target_1, target_2,
                    alert_type, session_date, status, user_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'active', NULL)""",
                ("AAPL", 150.0, 149.0, 151.0, 152.0, "ma_bounce_20", session),
            )

        assert len(get_active_entries("AAPL", session, user_id=1)) == 1
        assert len(get_active_entries("AAPL", session, user_id=2)) == 1


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_alert_flow_per_user(self, tmp_db):
        """Signal → record + entry + cooldown all scoped to user."""
        from alerting.alert_store import (
            create_active_entry,
            get_active_cooldowns,
            get_active_entries,
            record_alert,
            save_cooldown,
            was_alert_fired,
        )

        session = date.today().isoformat()
        signal = _make_signal("AAPL")

        # Record alert for user 1
        record_alert(signal, session, user_id=1)
        create_active_entry(signal, session, user_id=1)

        # Stop out → cooldown for user 1
        save_cooldown("AAPL", 30, reason="stop_loss_hit", session_date=session, user_id=1)

        # User 1: alert fired, entry exists, cooled
        assert was_alert_fired("AAPL", "ma_bounce_20", session, user_id=1) is True
        assert len(get_active_entries("AAPL", session, user_id=1)) == 1
        assert "AAPL" in get_active_cooldowns(session_date=session, user_id=1)

        # User 2: nothing
        assert was_alert_fired("AAPL", "ma_bounce_20", session, user_id=2) is False
        assert len(get_active_entries("AAPL", session, user_id=2)) == 0
        assert "AAPL" not in get_active_cooldowns(session_date=session, user_id=2)

    def test_two_users_same_symbol_independent(self, tmp_db):
        """Full isolation end-to-end: two users, same symbol, different states."""
        from alerting.alert_store import (
            close_all_entries_for_symbol,
            create_active_entry,
            get_active_cooldowns,
            get_active_entries,
            record_alert,
            save_cooldown,
        )

        session = date.today().isoformat()
        signal = _make_signal("AAPL")

        # Both users get the signal
        record_alert(signal, session, user_id=1)
        record_alert(signal, session, user_id=2)
        create_active_entry(signal, session, user_id=1)
        create_active_entry(signal, session, user_id=2)

        # User 1 gets stopped out
        close_all_entries_for_symbol("AAPL", session, user_id=1)
        save_cooldown("AAPL", 30, reason="stop_loss_hit", session_date=session, user_id=1)

        # User 1: no active entries, cooled
        assert len(get_active_entries("AAPL", session, user_id=1)) == 0
        assert "AAPL" in get_active_cooldowns(session_date=session, user_id=1)

        # User 2: still has entry, not cooled
        assert len(get_active_entries("AAPL", session, user_id=2)) == 1
        assert "AAPL" not in get_active_cooldowns(session_date=session, user_id=2)
