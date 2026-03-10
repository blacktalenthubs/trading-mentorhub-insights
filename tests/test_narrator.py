"""Tests for AI Trade Narrator — narrative generation, caching, and integration."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from analytics.intraday_rules import AlertSignal, AlertType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_signal(
    symbol="AAPL",
    alert_type=AlertType.MA_BOUNCE_20,
    direction="BUY",
    price=150.0,
    **kwargs,
) -> AlertSignal:
    defaults = dict(
        symbol=symbol,
        alert_type=alert_type,
        direction=direction,
        price=price,
        entry=price,
        stop=price - 1.0,
        target_1=price + 2.0,
        target_2=price + 4.0,
        confidence="high",
        message="MA bounce off 20MA",
        score=72,
        score_label="A",
        volume_label="high volume",
        vwap_position="above VWAP",
        spy_trend="bullish",
    )
    defaults.update(kwargs)
    return AlertSignal(**defaults)


@pytest.fixture()
def tmp_db(tmp_path):
    """Temporary SQLite DB with alerts table for integration tests."""
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
    """)
    conn.commit()
    conn.close()

    with (
        patch("db.get_db", _get_db),
        patch("db.get_connection", _get_connection),
        patch("alerting.alert_store.get_db", _get_db),
    ):
        yield _get_db


# ---------------------------------------------------------------------------
# Narrator unit tests
# ---------------------------------------------------------------------------

class TestGenerateNarrativeGuards:
    def test_disabled_returns_empty(self):
        """Returns '' when CLAUDE_NARRATIVE_ENABLED is false."""
        signal = _make_signal()
        with patch("alerting.narrator.CLAUDE_NARRATIVE_ENABLED", False):
            from alerting.narrator import generate_narrative
            assert generate_narrative(signal) == ""

    def test_no_api_key_returns_empty(self):
        """Returns '' when ANTHROPIC_API_KEY is empty."""
        signal = _make_signal()
        with patch("alerting.narrator.ANTHROPIC_API_KEY", ""):
            from alerting.narrator import generate_narrative
            assert generate_narrative(signal) == ""

    def test_skip_target_1_hit(self):
        """Returns '' for TARGET_1_HIT (exit signal)."""
        signal = _make_signal(alert_type=AlertType.TARGET_1_HIT, direction="SELL")
        with (
            patch("alerting.narrator.CLAUDE_NARRATIVE_ENABLED", True),
            patch("alerting.narrator.ANTHROPIC_API_KEY", "test-key"),
        ):
            from alerting.narrator import generate_narrative
            assert generate_narrative(signal) == ""

    def test_skip_stop_loss_hit(self):
        """Returns '' for STOP_LOSS_HIT (exit signal)."""
        signal = _make_signal(alert_type=AlertType.STOP_LOSS_HIT, direction="SELL")
        with (
            patch("alerting.narrator.CLAUDE_NARRATIVE_ENABLED", True),
            patch("alerting.narrator.ANTHROPIC_API_KEY", "test-key"),
        ):
            from alerting.narrator import generate_narrative
            assert generate_narrative(signal) == ""


class TestGenerateNarrativeAPI:
    def test_success(self):
        """Mocked API call returns narrative string."""
        signal = _make_signal()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="AAPL is bouncing off 20MA at $150 with high volume above VWAP. R:R of 2:1 in a bullish SPY regime makes this an A-grade setup.")]

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response

        import sys
        with (
            patch("alerting.narrator.CLAUDE_NARRATIVE_ENABLED", True),
            patch("alerting.narrator.ANTHROPIC_API_KEY", "test-key"),
            patch("alerting.narrator._narrative_cache", {}),
            patch.dict(sys.modules, {"anthropic": mock_anthropic}),
        ):
            from alerting.narrator import generate_narrative
            result = generate_narrative(signal)
            assert "AAPL" in result
            assert "20MA" in result
            mock_anthropic.Anthropic.return_value.messages.create.assert_called_once()

    def test_api_error_returns_empty(self):
        """API exception returns '' (graceful fallback)."""
        signal = _make_signal()

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value.messages.create.side_effect = Exception("API timeout")

        import sys
        with (
            patch("alerting.narrator.CLAUDE_NARRATIVE_ENABLED", True),
            patch("alerting.narrator.ANTHROPIC_API_KEY", "test-key"),
            patch("alerting.narrator._narrative_cache", {}),
            patch.dict(sys.modules, {"anthropic": mock_anthropic}),
        ):
            from alerting.narrator import generate_narrative
            result = generate_narrative(signal)
            assert result == ""

    def test_caching_skips_second_api_call(self):
        """Second call for same (symbol, type, session) uses cache."""
        signal = _make_signal()
        cached_text = "Cached narrative for AAPL MA bounce."
        session = date.today().isoformat()
        cache_key = (signal.symbol, signal.alert_type.value, session)

        with (
            patch("alerting.narrator.CLAUDE_NARRATIVE_ENABLED", True),
            patch("alerting.narrator.ANTHROPIC_API_KEY", "test-key"),
            patch("alerting.narrator._narrative_cache", {cache_key: cached_text}),
            patch("alerting.narrator._cache_session", session),
        ):
            from alerting.narrator import generate_narrative
            result = generate_narrative(signal)
            assert result == cached_text


# ---------------------------------------------------------------------------
# Notification integration tests
# ---------------------------------------------------------------------------

class TestNarrativeInNotifications:
    def test_narrative_in_email_body(self):
        """Narrative appears in formatted email body."""
        from alerting.notifier import _format_email_body

        signal = _make_signal()
        signal.narrative = "Strong 20MA bounce with institutional support."
        body = _format_email_body(signal)
        assert "THESIS:" in body
        assert "Strong 20MA bounce" in body

    def test_narrative_in_sms_body(self):
        """First sentence of narrative appears in Telegram message."""
        from alerting.notifier import _format_sms_body

        signal = _make_signal()
        signal.narrative = "Strong 20MA bounce with institutional support. R:R is favorable at 2:1."
        body = _format_sms_body(signal)
        assert "Strong 20MA bounce with institutional support." in body


# ---------------------------------------------------------------------------
# DB integration test
# ---------------------------------------------------------------------------

class TestNarrativeInDB:
    def test_record_alert_with_narrative(self, tmp_db):
        """Narrative is persisted to the alerts table."""
        from alerting.alert_store import record_alert

        signal = _make_signal()
        signal.narrative = "Test narrative for DB persistence."
        session = date.today().isoformat()
        alert_id = record_alert(signal, session_date=session)

        with tmp_db() as conn:
            row = conn.execute(
                "SELECT narrative FROM alerts WHERE id = ?", (alert_id,)
            ).fetchone()
            assert row["narrative"] == "Test narrative for DB persistence."
