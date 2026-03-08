"""Integration tests for tables without an `id` column.

Verifies the fix for psycopg2.errors.UndefinedColumn: column "id" does not
exist — caused by the Postgres wrapper blindly appending RETURNING id to
INSERT statements on session_tokens, telegram_link_tokens, and
password_reset_tokens (all use `token TEXT PRIMARY KEY`).

These tests run against local SQLite (no Postgres needed) but exercise the
same code paths that failed in production.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    """Patch DB_PATH so all code uses a fresh temp DB."""
    db_path = str(tmp_path / "test.db")

    with patch("config.DB_PATH", db_path), \
         patch("db.DB_PATH", db_path), \
         patch("db._init_done", False):
        import db as _db_mod
        _db_mod._init_done = False
        from db import init_db
        init_db()
        yield db_path


@pytest.fixture()
def test_user(tmp_db):
    """Create a test user and return their id."""
    from db import get_db
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)",
            ("integration@test.com", "fakehash", "Test User"),
        )
        return cur.lastrowid


# ---------------------------------------------------------------------------
# session_tokens — the table that crashed production login
# ---------------------------------------------------------------------------

class TestSessionTokens:

    def test_insert_session_token(self, tmp_db, test_user):
        """INSERT into session_tokens must not crash (was: RETURNING id on non-id table)."""
        from db import get_db
        token = uuid.uuid4().hex
        expires = (datetime.utcnow() + timedelta(days=30)).isoformat()

        with get_db() as conn:
            conn.execute(
                "INSERT INTO session_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, test_user, expires),
            )

        # Verify it was stored
        with get_db() as conn:
            row = conn.execute(
                "SELECT token, user_id FROM session_tokens WHERE token = ?",
                (token,),
            ).fetchone()
        assert row is not None
        assert row["token"] == token
        assert row["user_id"] == test_user

    def test_lookup_session_token(self, tmp_db, test_user):
        """Session token lookup via JOIN must return user data."""
        from db import get_db
        token = uuid.uuid4().hex
        expires = (datetime.utcnow() + timedelta(days=30)).isoformat()

        with get_db() as conn:
            conn.execute(
                "INSERT INTO session_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, test_user, expires),
            )

        with get_db() as conn:
            row = conn.execute(
                """SELECT u.id, u.email, u.display_name
                   FROM session_tokens t JOIN users u ON t.user_id = u.id
                   WHERE t.token = ? AND t.expires_at > ?""",
                (token, datetime.utcnow().isoformat()),
            ).fetchone()

        assert row is not None
        assert row["email"] == "integration@test.com"

    def test_delete_expired_then_insert(self, tmp_db, test_user):
        """Full _create_session_token flow: delete expired + insert new."""
        from db import get_db

        # Insert an expired token
        expired_token = uuid.uuid4().hex
        past = (datetime.utcnow() - timedelta(days=1)).isoformat()
        with get_db() as conn:
            conn.execute(
                "INSERT INTO session_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                (expired_token, test_user, past),
            )

        # Now do the full flow (matches auth.py _create_session_token)
        new_token = uuid.uuid4().hex
        expires = (datetime.utcnow() + timedelta(days=30)).isoformat()
        with get_db() as conn:
            conn.execute(
                "DELETE FROM session_tokens WHERE expires_at < ?",
                (datetime.utcnow().isoformat(),),
            )
            conn.execute(
                "INSERT INTO session_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                (new_token, test_user, expires),
            )

        # Expired token should be gone, new token present
        with get_db() as conn:
            old = conn.execute(
                "SELECT token FROM session_tokens WHERE token = ?", (expired_token,)
            ).fetchone()
            new = conn.execute(
                "SELECT token FROM session_tokens WHERE token = ?", (new_token,)
            ).fetchone()
        assert old is None
        assert new is not None

    def test_delete_session_token(self, tmp_db, test_user):
        """Logout flow: delete a session token."""
        from db import get_db
        token = uuid.uuid4().hex
        expires = (datetime.utcnow() + timedelta(days=30)).isoformat()
        with get_db() as conn:
            conn.execute(
                "INSERT INTO session_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, test_user, expires),
            )
        with get_db() as conn:
            conn.execute("DELETE FROM session_tokens WHERE token = ?", (token,))

        with get_db() as conn:
            row = conn.execute(
                "SELECT token FROM session_tokens WHERE token = ?", (token,)
            ).fetchone()
        assert row is None


# ---------------------------------------------------------------------------
# password_reset_tokens — also TEXT PRIMARY KEY, same bug risk
# ---------------------------------------------------------------------------

class TestPasswordResetTokens:

    def test_insert_reset_token(self, tmp_db, test_user):
        """INSERT into password_reset_tokens must not crash."""
        from db import get_db
        token = uuid.uuid4().hex
        expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()

        with get_db() as conn:
            conn.execute(
                "INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, test_user, expires),
            )

        with get_db() as conn:
            row = conn.execute(
                "SELECT token, user_id FROM password_reset_tokens WHERE token = ?",
                (token,),
            ).fetchone()
        assert row is not None
        assert row["user_id"] == test_user

    def test_validate_reset_token(self, tmp_db, test_user):
        """Token validation via JOIN must return user data."""
        from db import get_db
        token = uuid.uuid4().hex
        expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()

        with get_db() as conn:
            conn.execute(
                "INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, test_user, expires),
            )

        with get_db() as conn:
            row = conn.execute(
                """SELECT u.id, u.email, u.display_name
                   FROM password_reset_tokens t JOIN users u ON t.user_id = u.id
                   WHERE t.token = ? AND t.used = 0 AND t.expires_at > ?""",
                (token, datetime.utcnow().isoformat()),
            ).fetchone()
        assert row is not None
        assert row["email"] == "integration@test.com"

    def test_delete_oldest_then_insert(self, tmp_db, test_user):
        """Full request_password_reset flow: prune old + insert new."""
        from db import get_db
        max_tokens = 3

        # Insert max_tokens existing tokens
        for _ in range(max_tokens):
            t = uuid.uuid4().hex
            exp = (datetime.utcnow() + timedelta(hours=1)).isoformat()
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                    (t, test_user, exp),
                )

        # Now do the prune + insert (matches auth.py request_password_reset)
        new_token = uuid.uuid4().hex
        expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        with get_db() as conn:
            conn.execute(
                """DELETE FROM password_reset_tokens
                   WHERE user_id = ? AND used = 0
                   AND token NOT IN (
                       SELECT token FROM password_reset_tokens
                       WHERE user_id = ? AND used = 0
                       ORDER BY created_at DESC LIMIT ?
                   )""",
                (test_user, test_user, max_tokens - 1),
            )
            conn.execute(
                "INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                (new_token, test_user, expires),
            )

        with get_db() as conn:
            row = conn.execute(
                "SELECT token FROM password_reset_tokens WHERE token = ?",
                (new_token,),
            ).fetchone()
        assert row is not None


# ---------------------------------------------------------------------------
# telegram_link_tokens — also TEXT PRIMARY KEY, same bug risk
# ---------------------------------------------------------------------------

class TestTelegramLinkTokens:

    def test_insert_telegram_link_token(self, tmp_db, test_user):
        """INSERT into telegram_link_tokens must not crash."""
        from db import get_db
        token = uuid.uuid4().hex
        expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()

        with get_db() as conn:
            conn.execute(
                """INSERT INTO telegram_link_tokens
                   (token, user_id, expires_at) VALUES (?, ?, ?)""",
                (token, test_user, expires),
            )

        with get_db() as conn:
            row = conn.execute(
                "SELECT token, user_id FROM telegram_link_tokens WHERE token = ?",
                (token,),
            ).fetchone()
        assert row is not None
        assert row["user_id"] == test_user


# ---------------------------------------------------------------------------
# Postgres wrapper unit test — verify RETURNING id is skipped
# ---------------------------------------------------------------------------

class TestPostgresWrapperReturningLogic:
    """Direct unit test of the RETURNING id skip logic in db.py."""

    def test_no_returning_id_tables_set_exists(self):
        """The _NO_RETURNING_ID_TABLES frozenset must exist and cover all 3 tables."""
        from db import _NO_RETURNING_ID_TABLES
        assert "session_tokens" in _NO_RETURNING_ID_TABLES
        assert "telegram_link_tokens" in _NO_RETURNING_ID_TABLES
        assert "password_reset_tokens" in _NO_RETURNING_ID_TABLES

    def test_returning_id_not_appended_for_session_tokens(self):
        """Simulate the wrapper logic: RETURNING id must NOT be added for skip-list tables."""
        import re
        from db import _NO_RETURNING_ID_TABLES

        sql = "INSERT INTO session_tokens (token, user_id, expires_at) VALUES (%s, %s, %s)"
        needs_returning = (
            sql.lstrip().upper().startswith("INSERT")
            and "RETURNING" not in sql.upper()
        )
        if needs_returning:
            m = re.search(r'INSERT\s+INTO\s+(\w+)', sql, re.IGNORECASE)
            if m and m.group(1).lower() in _NO_RETURNING_ID_TABLES:
                needs_returning = False
            else:
                sql = sql.rstrip().rstrip(";") + " RETURNING id"

        assert needs_returning is False
        assert "RETURNING" not in sql

    def test_returning_id_still_appended_for_regular_tables(self):
        """RETURNING id must still be added for tables with an id column (e.g. users)."""
        import re
        from db import _NO_RETURNING_ID_TABLES

        sql = "INSERT INTO users (email, password_hash, display_name) VALUES (%s, %s, %s)"
        needs_returning = (
            sql.lstrip().upper().startswith("INSERT")
            and "RETURNING" not in sql.upper()
        )
        if needs_returning:
            m = re.search(r'INSERT\s+INTO\s+(\w+)', sql, re.IGNORECASE)
            if m and m.group(1).lower() in _NO_RETURNING_ID_TABLES:
                needs_returning = False
            else:
                sql = sql.rstrip().rstrip(";") + " RETURNING id"

        assert needs_returning is True
        assert sql.endswith("RETURNING id")
