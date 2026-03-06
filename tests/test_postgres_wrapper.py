"""Tests for Postgres wrapper — runs against a local Postgres via Docker.

Skip automatically if Docker/Postgres is not available.
Run with: pytest tests/test_postgres_wrapper.py -v
"""

from __future__ import annotations

import os
import subprocess
import time

import pytest

CONTAINER_NAME = "test_trade_analytics_pg"
PG_PORT = 15432
DATABASE_URL = f"postgresql://postgres:testpass@localhost:{PG_PORT}/testdb"


def _docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, check=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _start_postgres():
    """Start a throwaway Postgres container. Returns True if successful."""
    # Remove stale container if exists
    subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        capture_output=True,
    )
    result = subprocess.run(
        [
            "docker", "run", "-d",
            "--name", CONTAINER_NAME,
            "-e", "POSTGRES_PASSWORD=testpass",
            "-e", "POSTGRES_DB=testdb",
            "-p", f"{PG_PORT}:5432",
            "postgres:16-alpine",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False

    # Wait for Postgres to be ready (max 15s)
    for _ in range(30):
        check = subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "pg_isready", "-U", "postgres"],
            capture_output=True,
        )
        if check.returncode == 0:
            return True
        time.sleep(0.5)
    return False


def _stop_postgres():
    subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True)


@pytest.fixture(scope="module")
def pg_env():
    """Start Postgres, set DATABASE_URL, yield, then tear down."""
    if not _docker_available():
        pytest.skip("Docker not available")

    if not _start_postgres():
        pytest.skip("Could not start Postgres container")

    # Set env before importing db module
    os.environ["DATABASE_URL"] = DATABASE_URL
    yield DATABASE_URL

    # Cleanup
    os.environ.pop("DATABASE_URL", None)
    _stop_postgres()


@pytest.fixture(autouse=True)
def _fresh_db_module(pg_env):
    """Re-import db module with DATABASE_URL set so _USE_POSTGRES is True."""
    import importlib
    import db as db_mod

    # Force re-evaluation of _USE_POSTGRES
    db_mod._USE_POSTGRES = True
    import psycopg2
    import psycopg2.extras
    import psycopg2.errors
    db_mod.psycopg2 = psycopg2
    db_mod._DB_OPERATIONAL_ERRORS = (
        __import__("sqlite3").OperationalError,
        psycopg2.errors.DuplicateColumn,
        psycopg2.errors.DuplicateTable,
    )
    db_mod._DB_INTEGRITY_ERRORS = (
        __import__("sqlite3").IntegrityError,
        psycopg2.IntegrityError,
    )
    db_mod.IntegrityError = db_mod._DB_INTEGRITY_ERRORS

    # Drop all tables before each test for a clean slate
    import psycopg2 as pg2
    conn = pg2.connect(pg_env)
    cur = conn.cursor()
    cur.execute("""
        DO $$ DECLARE r RECORD;
        BEGIN
            FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
            END LOOP;
        END $$;
    """)
    conn.commit()
    conn.close()

    yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPostgresInit:
    def test_init_db_creates_tables(self, pg_env):
        """init_db() should create all 20+ tables in Postgres."""
        from db import get_db, init_db

        init_db()

        import psycopg2 as pg2
        conn = pg2.connect(pg_env)
        cur = conn.cursor()
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        tables = {row[0] for row in cur.fetchall()}
        conn.close()

        expected = [
            "users", "imports", "trades_1099", "trades_monthly",
            "matched_trades", "account_summaries", "trade_annotations",
            "session_tokens", "alerts", "active_entries", "cooldowns",
            "monitor_status", "paper_trades", "real_trades",
            "real_options_trades", "daily_plans", "chart_levels",
            "watchlist", "user_notification_prefs",
            "swing_trades", "swing_categories",
        ]
        for table in expected:
            assert table in tables, f"Missing table: {table}"


class TestPostgresCrud:
    def test_insert_and_select(self, pg_env):
        """Basic INSERT/SELECT through the wrapper."""
        from db import get_db, init_db

        init_db()

        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, display_name) "
                "VALUES (?, ?, ?)",
                ("test@pg.com", "hash123", "PGUser"),
            )
            assert cur.lastrowid is not None
            uid = cur.lastrowid

        with get_db() as conn:
            row = conn.execute(
                "SELECT id, email, display_name FROM users WHERE id = ?",
                (uid,),
            ).fetchone()
            assert row["email"] == "test@pg.com"
            assert row["display_name"] == "PGUser"

    def test_executemany(self, pg_env):
        """executemany should insert multiple rows."""
        from db import get_db, init_db

        init_db()

        with get_db() as conn:
            # Create a user first
            conn.execute(
                "INSERT INTO users (email, password_hash, display_name) "
                "VALUES (?, ?, ?)",
                ("wl@test.com", "hash", "WLUser"),
            )
            row = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
            uid = row["id"]

            conn.executemany(
                "INSERT INTO watchlist (user_id, symbol) VALUES (?, ?) "
                "ON CONFLICT(user_id, symbol) DO NOTHING",
                [(uid, "AAPL"), (uid, "TSLA"), (uid, "NVDA")],
            )

        with get_db() as conn:
            rows = conn.execute(
                "SELECT symbol FROM watchlist ORDER BY symbol"
            ).fetchall()
            symbols = [r["symbol"] for r in rows]
            assert symbols == ["AAPL", "NVDA", "TSLA"]

    def test_on_conflict_do_nothing(self, pg_env):
        """ON CONFLICT DO NOTHING should not raise on duplicate."""
        from db import get_db, init_db

        init_db()

        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (email, password_hash, display_name) "
                "VALUES (?, ?, ?)",
                ("dup@test.com", "hash", "User"),
            )
            row = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
            uid = row["id"]

            conn.execute(
                "INSERT INTO watchlist (user_id, symbol) VALUES (?, ?) "
                "ON CONFLICT(user_id, symbol) DO NOTHING",
                (uid, "SPY"),
            )
            # Second insert — should not raise
            conn.execute(
                "INSERT INTO watchlist (user_id, symbol) VALUES (?, ?) "
                "ON CONFLICT(user_id, symbol) DO NOTHING",
                (uid, "SPY"),
            )

        with get_db() as conn:
            rows = conn.execute(
                "SELECT symbol FROM watchlist WHERE user_id = ?", (uid,)
            ).fetchall()
            assert len(rows) == 1


class TestPostgresPandas:
    def test_pd_read_sql(self, pg_env):
        """_pd_read_sql should return a DataFrame from Postgres."""
        from db import _pd_read_sql, get_db, init_db

        init_db()

        with get_db() as conn:
            conn.execute(
                "INSERT INTO real_trades "
                "(symbol, direction, shares, entry_price, status, session_date) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("SPY", "BUY", 50, 500.0, "open", "2026-03-04"),
            )

        with get_db() as conn:
            df = _pd_read_sql("SELECT * FROM real_trades", conn)
            assert len(df) == 1
            assert df.iloc[0]["symbol"] == "SPY"
            assert df.iloc[0]["entry_price"] == 500.0


class TestPostgresAlertStore:
    def test_record_alert_and_lastrowid(self, pg_env):
        """record_alert should return a valid row id via RETURNING."""
        from db import init_db

        init_db()

        from alerting.alert_store import record_alert, was_alert_fired
        from analytics.intraday_rules import AlertSignal, AlertType

        signal = AlertSignal(
            symbol="AAPL",
            alert_type=AlertType.MA_BOUNCE_20,
            direction="BUY",
            price=150.0,
            entry=150.0,
            stop=149.0,
            target_1=151.0,
            target_2=152.0,
            confidence="high",
            message="Test",
        )

        alert_id = record_alert(signal, session_date="2026-03-05")
        assert alert_id is not None and alert_id > 0
        assert was_alert_fired("AAPL", "ma_bounce_20", "2026-03-05") is True

    def test_create_active_entry_on_conflict(self, pg_env):
        """Duplicate active_entry insert should not raise."""
        from db import init_db

        init_db()

        from alerting.alert_store import create_active_entry
        from analytics.intraday_rules import AlertSignal, AlertType

        signal = AlertSignal(
            symbol="TSLA",
            alert_type=AlertType.MA_BOUNCE_20,
            direction="BUY",
            price=200.0,
            entry=200.0,
            stop=198.0,
            target_1=202.0,
            target_2=204.0,
            confidence="high",
            message="Test",
        )

        create_active_entry(signal, session_date="2026-03-05")
        # Second call should not raise (ON CONFLICT DO NOTHING)
        create_active_entry(signal, session_date="2026-03-05")
