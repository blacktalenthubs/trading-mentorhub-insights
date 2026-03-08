"""Tests for forgot password / reset password / change password flows."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    """Create a temp SQLite DB with users + password_reset_tokens tables."""
    db_path = str(tmp_path / "test.db")

    def _get_connection():
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
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
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0
        );
    """)
    conn.close()

    with patch("auth.get_db", _get_db), patch("db.get_db", _get_db):
        yield _get_db


@pytest.fixture()
def test_user(tmp_db):
    """Create a test user and return (user_id, email, password)."""
    from auth import hash_password

    email = "test@example.com"
    password = "secret123"
    pw_hash = hash_password(password)

    with tmp_db() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)",
            (email, pw_hash, "Test User"),
        )
        user_id = cur.lastrowid

    return user_id, email, password


# ---------------------------------------------------------------------------
# request_password_reset
# ---------------------------------------------------------------------------

class TestRequestPasswordReset:
    def test_creates_token(self, tmp_db, test_user):
        """Token is stored in DB with correct expiry."""
        from auth import request_password_reset

        user_id, email, _ = test_user
        with patch("alerting.notifier.send_plain_email", return_value=True) as mock_email:
            result = request_password_reset(email)

        assert result is True
        with tmp_db() as conn:
            row = conn.execute(
                "SELECT * FROM password_reset_tokens WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        assert row is not None
        assert row["used"] == 0
        # Verify expiry is ~1 hour from now
        expires = datetime.fromisoformat(row["expires_at"])
        assert expires > datetime.utcnow()
        assert expires < datetime.utcnow() + timedelta(hours=2)
        # Verify email was sent
        mock_email.assert_called_once()

    def test_unknown_email_returns_true(self, tmp_db):
        """No enumeration — returns True even for unknown email."""
        from auth import request_password_reset

        with patch("alerting.notifier.send_plain_email", return_value=True):
            result = request_password_reset("nobody@example.com")

        assert result is True
        # No token should be created
        with tmp_db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) as cnt FROM password_reset_tokens"
            ).fetchone()["cnt"]
        assert count == 0


# ---------------------------------------------------------------------------
# validate_reset_token
# ---------------------------------------------------------------------------

class TestValidateResetToken:
    def test_valid_token(self, tmp_db, test_user):
        """Valid, unexpired, unused token returns user dict."""
        from auth import validate_reset_token

        user_id, email, _ = test_user
        token = "valid-token-123"
        expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()

        with tmp_db() as conn:
            conn.execute(
                "INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user_id, expires),
            )

        result = validate_reset_token(token)
        assert result is not None
        assert result["id"] == user_id
        assert result["email"] == email

    def test_expired_token(self, tmp_db, test_user):
        """Expired token returns None."""
        from auth import validate_reset_token

        user_id, _, _ = test_user
        token = "expired-token-456"
        expires = (datetime.utcnow() - timedelta(hours=1)).isoformat()

        with tmp_db() as conn:
            conn.execute(
                "INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user_id, expires),
            )

        assert validate_reset_token(token) is None

    def test_used_token(self, tmp_db, test_user):
        """Already-used token returns None."""
        from auth import validate_reset_token

        user_id, _, _ = test_user
        token = "used-token-789"
        expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()

        with tmp_db() as conn:
            conn.execute(
                "INSERT INTO password_reset_tokens (token, user_id, expires_at, used) VALUES (?, ?, ?, 1)",
                (token, user_id, expires),
            )

        assert validate_reset_token(token) is None


# ---------------------------------------------------------------------------
# reset_password
# ---------------------------------------------------------------------------

class TestResetPassword:
    def test_updates_hash(self, tmp_db, test_user):
        """New password hash is verifiable with bcrypt."""
        from auth import reset_password, verify_password

        user_id, _, _ = test_user
        token = "reset-token-abc"
        expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()

        with tmp_db() as conn:
            conn.execute(
                "INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user_id, expires),
            )

        new_pw = "newpassword456"
        assert reset_password(token, new_pw) is True

        # Verify new password works
        with tmp_db() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        assert verify_password(new_pw, row["password_hash"])

    def test_marks_token_used(self, tmp_db, test_user):
        """Token is marked used=1 after successful reset."""
        from auth import reset_password

        user_id, _, _ = test_user
        token = "reset-token-def"
        expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()

        with tmp_db() as conn:
            conn.execute(
                "INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user_id, expires),
            )

        reset_password(token, "newpass789")

        with tmp_db() as conn:
            row = conn.execute(
                "SELECT used FROM password_reset_tokens WHERE token = ?",
                (token,),
            ).fetchone()
        assert row["used"] == 1

    def test_invalid_token(self, tmp_db):
        """Nonexistent token returns False."""
        from auth import reset_password

        assert reset_password("nonexistent-token", "password123") is False

    def test_short_password_rejected(self, tmp_db, test_user):
        """Password shorter than 6 chars is rejected."""
        from auth import reset_password

        user_id, _, _ = test_user
        token = "reset-token-short"
        expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()

        with tmp_db() as conn:
            conn.execute(
                "INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user_id, expires),
            )

        assert reset_password(token, "abc") is False


# ---------------------------------------------------------------------------
# change_password
# ---------------------------------------------------------------------------

class TestChangePassword:
    def test_wrong_current_password(self, tmp_db, test_user):
        """Rejects incorrect current password."""
        from auth import change_password

        user_id, _, _ = test_user
        ok, msg = change_password(user_id, "wrongpassword", "newpass123")
        assert ok is False
        assert "incorrect" in msg.lower()

    def test_success(self, tmp_db, test_user):
        """Updates hash, old password no longer works."""
        from auth import change_password, verify_password

        user_id, _, old_password = test_user
        new_password = "brandnew456"

        ok, msg = change_password(user_id, old_password, new_password)
        assert ok is True

        # Verify new password works, old doesn't
        with tmp_db() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        assert verify_password(new_password, row["password_hash"])
        assert not verify_password(old_password, row["password_hash"])

    def test_short_new_password(self, tmp_db, test_user):
        """Rejects new password shorter than 6 chars."""
        from auth import change_password

        user_id, _, old_password = test_user
        ok, msg = change_password(user_id, old_password, "abc")
        assert ok is False
        assert "6 characters" in msg
