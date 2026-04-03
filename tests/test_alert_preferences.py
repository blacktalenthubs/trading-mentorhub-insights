"""Tests for user alert category preferences.

Covers:
- Category mapping completeness (every enabled rule has a category)
- _should_notify filtering logic (category toggle, score filter, exit bypass)
- DB CRUD for category prefs and min_alert_score
"""

from __future__ import annotations

import sqlite3
import tempfile
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Category mapping tests
# ---------------------------------------------------------------------------


class TestCategoryMapping:
    """Verify ALERT_CATEGORIES covers all enabled alert types."""

    def test_all_enabled_rules_have_category(self):
        """Every alert type in ENABLED_RULES must map to exactly one category."""
        from alert_config import ALERT_CATEGORIES, ALERT_TYPE_TO_CATEGORY, ENABLED_RULES

        for rule in ENABLED_RULES:
            assert rule in ALERT_TYPE_TO_CATEGORY, (
                f"Alert type '{rule}' is in ENABLED_RULES but not mapped to any category"
            )

    def test_no_duplicate_alert_type_across_categories(self):
        """No alert type should appear in more than one category."""
        from alert_config import ALERT_CATEGORIES

        seen: dict[str, str] = {}
        for cat_id, cat in ALERT_CATEGORIES.items():
            for at in cat["alert_types"]:
                assert at not in seen, (
                    f"Alert type '{at}' is in both '{seen[at]}' and '{cat_id}'"
                )
                seen[at] = cat_id

    def test_exit_alert_types_defined(self):
        """EXIT_ALERT_TYPES must contain the key exit alerts."""
        from alert_config import EXIT_ALERT_TYPES

        expected = {"target_1_hit", "target_2_hit", "stop_loss_hit", "auto_stop_out"}
        for e in expected:
            assert e in EXIT_ALERT_TYPES, f"'{e}' missing from EXIT_ALERT_TYPES"

    def test_categories_have_required_fields(self):
        """Each category must have name, description, alert_types."""
        from alert_config import ALERT_CATEGORIES

        for cat_id, cat in ALERT_CATEGORIES.items():
            assert "name" in cat, f"Category '{cat_id}' missing 'name'"
            assert "description" in cat, f"Category '{cat_id}' missing 'description'"
            assert "alert_types" in cat, f"Category '{cat_id}' missing 'alert_types'"
            assert len(cat["alert_types"]) > 0, f"Category '{cat_id}' has no alert types"


# ---------------------------------------------------------------------------
# _should_notify logic tests
# ---------------------------------------------------------------------------


class TestShouldNotify:
    """Test the notification filtering logic."""

    def _make_signal(self, alert_type: str, score: int = 50, direction: str = "BUY"):
        """Create a minimal mock signal."""
        from analytics.intraday_rules import AlertSignal, AlertType
        return AlertSignal(
            symbol="TEST",
            alert_type=AlertType(alert_type),
            direction=direction,
            price=100.0,
            score=score,
            message="test",
        )

    def test_all_enabled_sends(self):
        """With all categories enabled and min_score=0, everything sends."""
        from alert_config import ALERT_CATEGORIES
        from monitor import _should_notify

        all_enabled = {cat_id: True for cat_id in ALERT_CATEGORIES}
        sig = self._make_signal("ma_bounce_20", score=30)
        assert _should_notify(sig, all_enabled, 0) is True

    def test_category_disabled_blocks(self):
        """Disabling a category blocks its alerts."""
        from alert_config import ALERT_CATEGORIES
        from monitor import _should_notify

        prefs = {cat_id: True for cat_id in ALERT_CATEGORIES}
        prefs["entry_signals"] = False  # disable entry signals
        sig = self._make_signal("ma_bounce_20", score=80)
        assert _should_notify(sig, prefs, 0) is False

    def test_category_enabled_sends(self):
        """Enabled category sends its alerts."""
        from alert_config import ALERT_CATEGORIES
        from monitor import _should_notify

        prefs = {cat_id: True for cat_id in ALERT_CATEGORIES}
        sig = self._make_signal("ma_bounce_20", score=80)
        assert _should_notify(sig, prefs, 0) is True

    def test_exit_bypasses_score_filter(self):
        """Exit alerts (T1/T2/Stop) always send regardless of score filter."""
        from alert_config import ALERT_CATEGORIES
        from monitor import _should_notify

        prefs = {cat_id: True for cat_id in ALERT_CATEGORIES}
        sig = self._make_signal("stop_loss_hit", score=10, direction="SELL")
        assert _should_notify(sig, prefs, min_score=90) is True

    def test_exit_bypasses_category_disabled(self):
        """Exit alerts send even if their category is disabled."""
        from alert_config import ALERT_CATEGORIES
        from monitor import _should_notify

        prefs = {cat_id: False for cat_id in ALERT_CATEGORIES}  # all disabled
        sig = self._make_signal("target_1_hit", score=10, direction="SELL")
        assert _should_notify(sig, prefs, min_score=0) is True

    def test_below_min_score_blocks(self):
        """Alert below min_score is blocked."""
        from alert_config import ALERT_CATEGORIES
        from monitor import _should_notify

        prefs = {cat_id: True for cat_id in ALERT_CATEGORIES}
        sig = self._make_signal("ma_bounce_20", score=40)
        assert _should_notify(sig, prefs, min_score=60) is False

    def test_at_min_score_sends(self):
        """Alert exactly at min_score sends."""
        from alert_config import ALERT_CATEGORIES
        from monitor import _should_notify

        prefs = {cat_id: True for cat_id in ALERT_CATEGORIES}
        sig = self._make_signal("ma_bounce_20", score=60)
        assert _should_notify(sig, prefs, min_score=60) is True

    def test_zero_min_score_sends_everything(self):
        """min_score=0 means no score filtering."""
        from alert_config import ALERT_CATEGORIES
        from monitor import _should_notify

        prefs = {cat_id: True for cat_id in ALERT_CATEGORIES}
        sig = self._make_signal("ma_bounce_20", score=1)
        assert _should_notify(sig, prefs, min_score=0) is True

    def test_unknown_alert_type_sends(self):
        """Alert type not in any category defaults to sending (fail-open)."""
        from monitor import _should_notify

        prefs = {}  # empty prefs
        sig = self._make_signal("ma_bounce_20", score=50)
        # Even with empty prefs, defaults to True (fail-open)
        assert _should_notify(sig, prefs, min_score=0) is True


# ---------------------------------------------------------------------------
# DB CRUD tests
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """Create a temporary SQLite DB and patch get_db to use it."""
    db_path = str(tmp_path / "test.db")

    from contextlib import contextmanager

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

    # Create minimal schema needed for preference tests
    conn = _get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS user_notification_prefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
            telegram_chat_id TEXT DEFAULT '',
            notification_email TEXT DEFAULT '',
            telegram_enabled INTEGER DEFAULT 1,
            email_enabled INTEGER DEFAULT 1,
            anthropic_api_key TEXT DEFAULT '',
            min_alert_score INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS user_alert_category_prefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category_id TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, category_id)
        );
        INSERT INTO users (email, password_hash) VALUES ('test@test.com', 'hash');
        INSERT INTO user_notification_prefs (user_id) VALUES (1);
    """)
    conn.commit()
    conn.close()

    import db as db_mod
    monkeypatch.setattr(db_mod, "get_db", _get_db)

    yield db_path


class TestCategoryPrefsCRUD:
    """Test DB operations for alert category preferences."""

    def test_get_empty_prefs_returns_empty(self, tmp_db):
        from db import get_alert_category_prefs
        prefs = get_alert_category_prefs(1)
        assert prefs == {}

    def test_upsert_and_get(self, tmp_db):
        from db import get_alert_category_prefs, upsert_alert_category_prefs
        upsert_alert_category_prefs(1, "entry_signals", False)
        upsert_alert_category_prefs(1, "breakout_signals", True)
        prefs = get_alert_category_prefs(1)
        assert prefs["entry_signals"] is False
        assert prefs["breakout_signals"] is True

    def test_upsert_updates_existing(self, tmp_db):
        from db import get_alert_category_prefs, upsert_alert_category_prefs
        upsert_alert_category_prefs(1, "entry_signals", True)
        upsert_alert_category_prefs(1, "entry_signals", False)
        prefs = get_alert_category_prefs(1)
        assert prefs["entry_signals"] is False

    def test_different_users_independent(self, tmp_db):
        from db import get_alert_category_prefs, upsert_alert_category_prefs, get_db
        # Create second user
        with get_db() as conn:
            conn.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", ("user2@test.com", "hash"))
        upsert_alert_category_prefs(1, "entry_signals", False)
        upsert_alert_category_prefs(2, "entry_signals", True)
        assert get_alert_category_prefs(1)["entry_signals"] is False
        assert get_alert_category_prefs(2)["entry_signals"] is True


class TestMinScoreCRUD:
    """Test DB operations for min_alert_score."""

    def test_default_score_is_zero(self, tmp_db):
        from db import get_min_alert_score
        assert get_min_alert_score(1) == 0

    def test_set_and_get(self, tmp_db):
        from db import get_min_alert_score, set_min_alert_score
        set_min_alert_score(1, 65)
        assert get_min_alert_score(1) == 65

    def test_update_score(self, tmp_db):
        from db import get_min_alert_score, set_min_alert_score
        set_min_alert_score(1, 50)
        set_min_alert_score(1, 80)
        assert get_min_alert_score(1) == 80
