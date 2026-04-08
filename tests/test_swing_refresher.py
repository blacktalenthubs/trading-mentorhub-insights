"""Tests for alerting.swing_refresher -- premarket swing alert refresh."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """Create a temp SQLite DB with alerts table (including refresh columns)."""
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
            user_id INTEGER,
            setup_level REAL,
            setup_condition TEXT,
            refreshed_entry REAL,
            refreshed_stop REAL,
            refreshed_at TIMESTAMP,
            gap_invalidated INTEGER DEFAULT 0,
            gap_pct REAL
        );
    """)
    conn.close()

    monkeypatch.setattr("db.get_db", _get_db)
    return _get_db


def _insert_swing_alert(get_db_fn, symbol, entry, stop=None, setup_level=None, setup_condition=None):
    """Insert a swing alert for today and return its id."""
    session = date.today().isoformat()
    with get_db_fn() as conn:
        cur = conn.execute(
            """INSERT INTO alerts
               (symbol, alert_type, direction, price, entry, stop,
                session_date, setup_level, setup_condition, gap_invalidated)
               VALUES (?, 'swing_pullback_20ema', 'BUY', ?, ?, ?, ?, ?, ?, 0)""",
            (symbol, entry, entry, stop, session, setup_level, setup_condition),
        )
        return cur.lastrowid


# ---------------------------------------------------------------------------
# Tests: fetch_premarket_price
# ---------------------------------------------------------------------------

class TestFetchPremarketPrice:
    @patch("config.is_crypto_alert_symbol", return_value=False)
    def test_returns_float_on_success(self, _mock_crypto):
        """fetch_premarket_price returns a float when yfinance succeeds."""
        mock_info = MagicMock()
        mock_info.last_price = 155.25
        mock_ticker = MagicMock()
        mock_ticker.fast_info = mock_info

        with patch("yfinance.Ticker", return_value=mock_ticker):
            from alerting.swing_refresher import fetch_premarket_price
            result = fetch_premarket_price("AAPL")

        assert result == 155.25
        assert isinstance(result, float)

    @patch("config.is_crypto_alert_symbol", return_value=False)
    def test_returns_none_on_failure(self, _mock_crypto):
        """fetch_premarket_price returns None when yfinance raises."""
        with patch("yfinance.Ticker", side_effect=Exception("network error")):
            from alerting.swing_refresher import fetch_premarket_price
            result = fetch_premarket_price("AAPL")

        assert result is None


# ---------------------------------------------------------------------------
# Tests: refresh_pending_swing_alerts
# ---------------------------------------------------------------------------

class TestRefreshPendingSwingAlerts:
    def test_gap_over_5pct_invalidates(self, tmp_db):
        """Gap >5% from setup_level should invalidate the alert."""
        alert_id = _insert_swing_alert(
            tmp_db, "AAPL", entry=100.0, stop=97.0,
            setup_level=100.0, setup_condition="Pullback to rising 20 EMA",
        )

        # Current price = 106 => gap = +6% => invalidated
        with patch("alerting.swing_refresher.fetch_premarket_price", return_value=106.0):
            from alerting.swing_refresher import refresh_pending_swing_alerts
            summary = refresh_pending_swing_alerts(None)

        assert summary["invalidated"] == 1
        assert summary["refreshed"] == 0

        # Verify DB
        with tmp_db() as conn:
            row = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
            assert row["gap_invalidated"] == 1
            assert row["gap_pct"] == 6.0

    def test_gap_under_5pct_refreshes(self, tmp_db):
        """Gap <5% should refresh entry and stop."""
        alert_id = _insert_swing_alert(
            tmp_db, "MSFT", entry=400.0, stop=394.0,
            setup_level=400.0, setup_condition="EMA5/20 bullish crossover",
        )

        # Current price = 402 => gap = +0.5%
        with patch("alerting.swing_refresher.fetch_premarket_price", return_value=402.0):
            from alerting.swing_refresher import refresh_pending_swing_alerts
            summary = refresh_pending_swing_alerts(None)

        assert summary["refreshed"] == 1
        assert summary["invalidated"] == 0

        # Verify refreshed entry/stop
        with tmp_db() as conn:
            row = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
            assert row["refreshed_entry"] == 402.0
            # Original stop distance: (400-394)/400 = 1.5%
            # Refreshed stop: 402 * (1 - 0.015) = 395.97
            assert row["refreshed_stop"] == 395.97
            assert row["gap_invalidated"] == 0

    def test_none_premarket_skipped(self, tmp_db):
        """If premarket price is None, alert is skipped (not refreshed or invalidated)."""
        _insert_swing_alert(
            tmp_db, "TSLA", entry=200.0, stop=195.0,
            setup_level=200.0,
        )

        with patch("alerting.swing_refresher.fetch_premarket_price", return_value=None):
            from alerting.swing_refresher import refresh_pending_swing_alerts
            summary = refresh_pending_swing_alerts(None)

        assert summary["refreshed"] == 0
        assert summary["invalidated"] == 0

    def test_no_pending_alerts(self, tmp_db):
        """Returns zeros when no swing alerts exist for today."""
        from alerting.swing_refresher import refresh_pending_swing_alerts

        summary = refresh_pending_swing_alerts(None)
        assert summary["refreshed"] == 0
        assert summary["invalidated"] == 0


# ---------------------------------------------------------------------------
# Tests: format_refresh_summary
# ---------------------------------------------------------------------------

class TestFormatRefreshSummary:
    def test_empty_summary_returns_empty_string(self):
        from alerting.swing_refresher import format_refresh_summary

        result = format_refresh_summary({"refreshed": 0, "invalidated": 0, "details": []})
        assert result == ""

    def test_summary_contains_counts_and_symbols(self):
        from alerting.swing_refresher import format_refresh_summary

        summary = {
            "refreshed": 1,
            "invalidated": 1,
            "details": [
                {"symbol": "AAPL", "action": "refreshed", "original": 150.0, "refreshed": 152.0, "gap_pct": 1.3},
                {"symbol": "TSLA", "action": "invalidated", "gap_pct": -6.5, "setup": "200MA hold"},
            ],
        }
        result = format_refresh_summary(summary)

        assert "SWING PREMARKET UPDATE" in result
        assert "1 refreshed, 1 invalidated" in result
        assert "AAPL" in result
        assert "TSLA" in result
        assert "INVALIDATED" in result
