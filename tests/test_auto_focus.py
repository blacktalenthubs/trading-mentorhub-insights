"""Tests for the daily auto-focus agent (analytics/auto_focus.py).

Covers:
- Pure ranking: top-N by score, min_score floor, deterministic tie-break
- DB apply: sets auto focus on picks, preserves manual stars
- clear_auto_focus only clears 'auto' rows (manual untouched)
- Idempotent re-run replaces prior auto picks
- run() across multiple users
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from analytics.auto_focus import apply_for_user, run, select_top_setups


# ---------------------------------------------------------------------------
# Pure ranking — no DB
# ---------------------------------------------------------------------------

def test_select_top_setups_orders_by_score_desc():
    scores = {"AAA": 90, "BBB": 70, "CCC": 85, "DDD": 60}
    assert select_top_setups(["AAA", "BBB", "CCC", "DDD"], scores, top_n=2) == ["AAA", "CCC"]


def test_select_top_setups_respects_min_score():
    scores = {"AAA": 55, "BBB": 80, "CCC": 40}
    # Only BBB clears the default floor of 60.
    assert select_top_setups(["AAA", "BBB", "CCC"], scores, min_score=60) == ["BBB"]


def test_select_top_setups_tie_break_is_alphabetical():
    scores = {"ZZZ": 80, "AAA": 80, "MMM": 80}
    assert select_top_setups(["ZZZ", "AAA", "MMM"], scores, top_n=3) == ["AAA", "MMM", "ZZZ"]


def test_select_top_setups_missing_scores_default_zero():
    scores = {"AAA": 75}
    assert select_top_setups(["AAA", "BBB"], scores, min_score=60) == ["AAA"]


def test_select_top_setups_can_return_fewer_than_n():
    scores = {"AAA": 65, "BBB": 30}
    assert select_top_setups(["AAA", "BBB"], scores, top_n=5, min_score=60) == ["AAA"]


# ---------------------------------------------------------------------------
# DB-backed apply — temp SQLite
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    """Temp SQLite with watchlist + daily_plans; patches db.get_db to use it."""
    db_path = str(tmp_path / "test.db")

    def _connect():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _get_db():
        conn = _connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    conn = _connect()
    conn.executescript(
        """
        CREATE TABLE watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT NOT NULL,
            focus INTEGER DEFAULT 0,
            focus_source TEXT DEFAULT 'manual',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, symbol)
        );
        CREATE TABLE daily_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            session_date TEXT NOT NULL,
            support REAL,
            support_label TEXT,
            support_status TEXT,
            entry REAL,
            stop REAL,
            target_1 REAL,
            target_2 REAL,
            score INTEGER DEFAULT 0,
            score_label TEXT DEFAULT '',
            pattern TEXT DEFAULT 'normal',
            UNIQUE(symbol, session_date)
        );
        """
    )
    conn.commit()
    conn.close()

    with patch("db.get_db", _get_db):
        yield _get_db


def _add_symbol(get_db, user_id, symbol, focus=0, source="manual"):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO watchlist (user_id, symbol, focus, focus_source) VALUES (?, ?, ?, ?)",
            (user_id, symbol, focus, source),
        )


def _add_plan(get_db, symbol, score, session_date="2026-06-26"):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO daily_plans (symbol, session_date, score) VALUES (?, ?, ?)",
            (symbol, session_date, score),
        )


def _focus_state(get_db, user_id):
    """Return {symbol: (focus_int, source)} for assertions."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT symbol, focus, focus_source FROM watchlist WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return {r["symbol"]: (r["focus"], r["focus_source"]) for r in rows}


def test_apply_for_user_sets_auto_focus_on_top_picks(tmp_db):
    for sym, score in [("AAA", 90), ("BBB", 80), ("CCC", 30)]:
        _add_symbol(tmp_db, 1, sym)
    scores = {"AAA": 90, "BBB": 80, "CCC": 30}

    summary = apply_for_user(1, scores, top_n=2, min_score=60)

    assert summary["picks"] == ["AAA", "BBB"]
    assert set(summary["auto_set"]) == {"AAA", "BBB"}
    state = _focus_state(tmp_db, 1)
    assert state["AAA"] == (1, "auto")
    assert state["BBB"] == (1, "auto")
    assert state["CCC"] == (0, "manual")  # below floor, untouched


def test_manual_focus_is_never_overwritten(tmp_db):
    # User hand-starred CCC even though it scores low.
    _add_symbol(tmp_db, 1, "AAA", focus=0, source="manual")
    _add_symbol(tmp_db, 1, "CCC", focus=1, source="manual")
    scores = {"AAA": 90, "CCC": 95}

    summary = apply_for_user(1, scores, top_n=2, min_score=60)

    state = _focus_state(tmp_db, 1)
    # CCC stays a manual star (not downgraded to auto), AAA becomes auto.
    assert state["CCC"] == (1, "manual")
    assert state["AAA"] == (1, "auto")
    # CCC was a top pick but already manual, so not in the newly auto-set list.
    assert "CCC" in summary["picks"]
    assert "CCC" not in summary["auto_set"]


def test_rerun_replaces_stale_auto_picks(tmp_db):
    for sym in ["AAA", "BBB", "CCC"]:
        _add_symbol(tmp_db, 1, sym)

    # Day 1: AAA + BBB are best.
    apply_for_user(1, {"AAA": 90, "BBB": 80, "CCC": 10}, top_n=2, min_score=60)
    assert _focus_state(tmp_db, 1)["AAA"] == (1, "auto")

    # Day 2: CCC surges, AAA fades — auto picks should rotate.
    apply_for_user(1, {"AAA": 10, "BBB": 80, "CCC": 95}, top_n=2, min_score=60)
    state = _focus_state(tmp_db, 1)
    assert state["CCC"] == (1, "auto")
    assert state["BBB"] == (1, "auto")
    assert state["AAA"] == (0, "manual")  # cleared (auto picks reset to default)


def test_dry_run_changes_nothing(tmp_db):
    _add_symbol(tmp_db, 1, "AAA")
    summary = apply_for_user(1, {"AAA": 90}, top_n=2, min_score=60, dry_run=True)
    assert summary["picks"] == ["AAA"]
    assert summary["applied"] is False
    assert _focus_state(tmp_db, 1)["AAA"] == (0, "manual")


def test_run_across_multiple_users(tmp_db):
    _add_symbol(tmp_db, 1, "AAA")
    _add_symbol(tmp_db, 1, "BBB")
    _add_symbol(tmp_db, 2, "AAA")  # user 2 doesn't watch BBB
    _add_plan(tmp_db, "AAA", 90)
    _add_plan(tmp_db, "BBB", 80)

    summary = run(session_date="2026-06-26", top_n=5, min_score=60)

    assert summary["users"] == 2
    assert summary["total_auto"] == 3  # user1: AAA+BBB, user2: AAA
    assert _focus_state(tmp_db, 1)["AAA"] == (1, "auto")
    assert _focus_state(tmp_db, 2)["AAA"] == (1, "auto")


def test_run_no_plans_is_noop(tmp_db):
    _add_symbol(tmp_db, 1, "AAA")
    summary = run(top_n=5, min_score=60)  # no daily_plans rows at all
    assert summary["users"] == 0
    assert summary["total_auto"] == 0
