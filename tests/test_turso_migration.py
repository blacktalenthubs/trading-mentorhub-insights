"""Tests for Turso embedded-replica migration.

All tests run against local SQLite (no Turso credentials needed).
Verifies dual-mode connection, init_db schema, CRUD operations, and
that auth.py uses the shared db.get_db() connection.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from unittest.mock import patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    """Patch DB_PATH so all code uses a fresh temp DB."""
    db_path = str(tmp_path / "test.db")

    with patch("config.DB_PATH", db_path), \
         patch("db.DB_PATH", db_path):
        # Init schema
        from db import init_db
        init_db()
        yield db_path


# ---------------------------------------------------------------------------
# Connection mode tests
# ---------------------------------------------------------------------------

class TestConnectionMode:
    def test_local_sqlite_fallback(self, tmp_db):
        """Falls back to sqlite3 when TURSO_DB_URL is empty."""
        from db import get_connection
        conn = get_connection()
        # Should be a plain sqlite3 connection
        assert hasattr(conn, "execute")
        assert conn.row_factory == sqlite3.Row
        conn.close()

    def test_get_db_commits_and_closes(self, tmp_db):
        """Context manager auto-commits on success."""
        from db import get_db
        with get_db() as conn:
            conn.execute(
                "INSERT INTO watchlist (user_id, symbol) VALUES (NULL, 'TEST')"
            )
        # Read back with a new connection
        with get_db() as conn:
            row = conn.execute(
                "SELECT symbol FROM watchlist WHERE symbol = 'TEST'"
            ).fetchone()
            assert row is not None
            assert row["symbol"] == "TEST"


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestInitDb:
    EXPECTED_TABLES = [
        "users", "imports", "trades_1099", "trades_monthly",
        "matched_trades", "account_summaries", "trade_annotations",
        "session_tokens", "alerts", "active_entries", "cooldowns",
        "monitor_status", "paper_trades", "real_trades",
        "real_options_trades", "daily_plans", "chart_levels",
        "watchlist", "user_notification_prefs",
        "swing_trades", "swing_categories",
    ]

    def test_init_db_creates_all_tables(self, tmp_db):
        """init_db should create 20+ tables."""
        from db import get_db
        with get_db() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            tables = {r["name"] for r in rows}

        for table in self.EXPECTED_TABLES:
            assert table in tables, f"Missing table: {table}"


# ---------------------------------------------------------------------------
# Real trade CRUD
# ---------------------------------------------------------------------------

class TestRealTradeCrud:
    def test_open_and_close_trade(self, tmp_db):
        """Open a real_trade, close it, verify P&L."""
        from db import get_db
        with get_db() as conn:
            conn.execute(
                "INSERT INTO real_trades "
                "(symbol, direction, shares, entry_price, stop_price, "
                " target_price, status, session_date) "
                "VALUES (?, ?, ?, ?, ?, ?, 'open', ?)",
                ("AAPL", "BUY", 100, 150.0, 148.0, 155.0, "2026-03-04"),
            )

        with get_db() as conn:
            conn.execute(
                "UPDATE real_trades SET exit_price=?, pnl=?, status='closed', "
                "closed_at=CURRENT_TIMESTAMP WHERE symbol='AAPL' AND status='open'",
                (155.0, 500.0),
            )

        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM real_trades WHERE symbol='AAPL'"
            ).fetchone()
            assert row["status"] == "closed"
            assert row["pnl"] == 500.0
            assert row["exit_price"] == 155.0


# ---------------------------------------------------------------------------
# Options trade CRUD
# ---------------------------------------------------------------------------

class TestOptionsTradeCrud:
    def test_open_close_expire(self, tmp_db):
        """Open an options trade, close it, then test expiry status."""
        from db import get_db
        # Open
        with get_db() as conn:
            conn.execute(
                "INSERT INTO real_options_trades "
                "(symbol, option_type, strike, expiration, contracts, "
                " premium_per_contract, entry_cost, status, session_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)",
                ("SPY", "CALL", 500.0, "2026-04-17", 2, 3.50, 700.0, "2026-03-04"),
            )

        # Close
        with get_db() as conn:
            conn.execute(
                "UPDATE real_options_trades SET exit_premium=?, exit_proceeds=?, "
                "pnl=?, status='closed', closed_at=CURRENT_TIMESTAMP "
                "WHERE symbol='SPY' AND status='open'",
                (5.0, 1000.0, 300.0),
            )

        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM real_options_trades WHERE symbol='SPY'"
            ).fetchone()
            assert row["status"] == "closed"
            assert row["pnl"] == 300.0

    def test_expired_option(self, tmp_db):
        """Insert an expired option trade."""
        from db import get_db
        with get_db() as conn:
            conn.execute(
                "INSERT INTO real_options_trades "
                "(symbol, option_type, strike, expiration, contracts, "
                " premium_per_contract, entry_cost, pnl, status, session_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'expired', ?)",
                ("QQQ", "PUT", 400.0, "2026-03-01", 1, 2.0, 200.0, -200.0, "2026-03-01"),
            )

        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM real_options_trades WHERE symbol='QQQ'"
            ).fetchone()
            assert row["status"] == "expired"
            assert row["pnl"] == -200.0


# ---------------------------------------------------------------------------
# Auth uses shared connection
# ---------------------------------------------------------------------------

class TestAuthSharedConnection:
    def test_create_and_authenticate_user(self, tmp_db):
        """auth.create_user + authenticate_user work via db.get_db()."""
        with patch("auth.get_db") as mock_get_db:
            # Wire auth.get_db to the real (patched) get_db
            from db import get_db
            mock_get_db.side_effect = get_db

            from auth import authenticate_user, create_user
            uid = create_user("test@example.com", "password123", "Tester")
            assert uid is not None and uid > 0

            user = authenticate_user("test@example.com", "password123")
            assert user is not None
            assert user["email"] == "test@example.com"

            # Wrong password
            assert authenticate_user("test@example.com", "wrong") is None


# ---------------------------------------------------------------------------
# Alerts and watchlist CRUD
# ---------------------------------------------------------------------------

class TestAlertsAndWatchlist:
    def test_alert_recording(self, tmp_db):
        """Insert and retrieve an alert."""
        from db import get_db
        with get_db() as conn:
            conn.execute(
                "INSERT INTO alerts "
                "(symbol, alert_type, direction, price, confidence, "
                " message, session_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("NVDA", "ma_bounce_20", "BUY", 800.0, "high",
                 "Test alert", "2026-03-04"),
            )

        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM alerts WHERE symbol='NVDA'"
            ).fetchone()
            assert row["alert_type"] == "ma_bounce_20"
            assert row["confidence"] == "high"

    def test_watchlist_crud(self, tmp_db):
        """Add and remove watchlist symbols."""
        from db import get_db
        # Create a user first
        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (email, password_hash, display_name) "
                "VALUES ('u@test.com', 'hash', 'User')"
            )
            uid = conn.execute("SELECT id FROM users WHERE email='u@test.com'").fetchone()["id"]

        # Add symbols
        with get_db() as conn:
            conn.execute(
                "INSERT INTO watchlist (user_id, symbol) VALUES (?, ?)",
                (uid, "AAPL"),
            )
            conn.execute(
                "INSERT INTO watchlist (user_id, symbol) VALUES (?, ?)",
                (uid, "TSLA"),
            )

        with get_db() as conn:
            rows = conn.execute(
                "SELECT symbol FROM watchlist WHERE user_id=? ORDER BY symbol",
                (uid,),
            ).fetchall()
            symbols = [r["symbol"] for r in rows]
            assert symbols == ["AAPL", "TSLA"]

        # Remove one
        with get_db() as conn:
            conn.execute(
                "DELETE FROM watchlist WHERE user_id=? AND symbol=?",
                (uid, "TSLA"),
            )

        with get_db() as conn:
            rows = conn.execute(
                "SELECT symbol FROM watchlist WHERE user_id=?", (uid,),
            ).fetchall()
            assert len(rows) == 1
            assert rows[0]["symbol"] == "AAPL"


# ---------------------------------------------------------------------------
# Pandas compatibility
# ---------------------------------------------------------------------------

class TestPandasCompat:
    def test_pandas_read_sql_compat(self, tmp_db):
        """pd.read_sql_query works with our connection."""
        from db import get_connection
        conn = get_connection()
        try:
            # Insert test data
            conn.execute(
                "INSERT INTO real_trades "
                "(symbol, direction, shares, entry_price, status, session_date) "
                "VALUES ('SPY', 'BUY', 50, 500.0, 'open', '2026-03-04')"
            )
            conn.commit()

            df = pd.read_sql_query("SELECT * FROM real_trades", conn)
            assert len(df) == 1
            assert df.iloc[0]["symbol"] == "SPY"
            assert df.iloc[0]["entry_price"] == 500.0
        finally:
            conn.close()
