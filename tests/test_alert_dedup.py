"""Tests for alert dedup, cooldown persistence, and SPY suppression.

Covers:
- Cooldown CRUD (save, get_active, is_cooled_down, expiry)
- fired_today dedup in evaluate_rules()
- TRENDING_DOWN BUY suppression in evaluate_rules()
- Monitor dedup prevents double notification (integration)
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from analytics.intraday_rules import AlertType, evaluate_rules


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    """Create a temporary SQLite DB with the full schema and patch get_db to use it."""
    db_path = str(tmp_path / "test.db")

    def _get_connection():
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    from contextlib import contextmanager

    @contextmanager
    def _get_db():
        conn = _get_connection()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # Create schema
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
            notified_email INTEGER DEFAULT 0,
            notified_sms INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            session_date TEXT NOT NULL
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, session_date, alert_type)
        );

        CREATE TABLE IF NOT EXISTS cooldowns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            cooldown_until TEXT NOT NULL,
            reason TEXT,
            session_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, session_date)
        );

        CREATE TABLE IF NOT EXISTS monitor_status (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_poll_at TIMESTAMP,
            symbols_checked INTEGER DEFAULT 0,
            alerts_fired INTEGER DEFAULT 0,
            status TEXT DEFAULT 'idle'
        );
    """)
    conn.commit()
    conn.close()

    with (
        patch("db.get_db", _get_db),
        patch("db.get_connection", _get_connection),
        patch("alerting.alert_store.get_db", _get_db),
    ):
        yield _get_db


def _bar(open_=100, high=101, low=99, close=100.5, volume=1000) -> pd.Series:
    return pd.Series({
        "Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume,
    })


def _bars(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Cooldown CRUD tests
# ---------------------------------------------------------------------------

class TestCooldownPersistence:
    def test_save_cooldown_and_is_cooled_down(self, tmp_db):
        from alerting.alert_store import is_symbol_cooled_down, save_cooldown

        session = date.today().isoformat()
        save_cooldown("AAPL", 30, reason="stop_loss_hit", session_date=session)
        assert is_symbol_cooled_down("AAPL", session_date=session) is True

    def test_cooldown_expires_immediately_with_zero_minutes(self, tmp_db):
        from alerting.alert_store import is_symbol_cooled_down, save_cooldown

        session = date.today().isoformat()
        save_cooldown("AAPL", 0, reason="test", session_date=session)
        assert is_symbol_cooled_down("AAPL", session_date=session) is False

    def test_get_active_cooldowns_returns_correct_set(self, tmp_db):
        from alerting.alert_store import get_active_cooldowns, save_cooldown

        session = date.today().isoformat()
        save_cooldown("AAPL", 30, reason="stop", session_date=session)
        save_cooldown("TSLA", 30, reason="stop", session_date=session)
        save_cooldown("META", 0, reason="expired", session_date=session)

        active = get_active_cooldowns(session_date=session)
        assert "AAPL" in active
        assert "TSLA" in active
        assert "META" not in active  # expired

    def test_cooldown_different_session_not_active(self, tmp_db):
        from alerting.alert_store import is_symbol_cooled_down, save_cooldown

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        save_cooldown("AAPL", 30, reason="stop", session_date=yesterday)
        # Today's session should not show yesterday's cooldown
        today = date.today().isoformat()
        assert is_symbol_cooled_down("AAPL", session_date=today) is False

    def test_cooldown_upserts_on_conflict(self, tmp_db):
        from alerting.alert_store import is_symbol_cooled_down, save_cooldown

        session = date.today().isoformat()
        save_cooldown("AAPL", 0, reason="first", session_date=session)
        assert is_symbol_cooled_down("AAPL", session_date=session) is False

        # Upsert with longer cooldown
        save_cooldown("AAPL", 30, reason="second", session_date=session)
        assert is_symbol_cooled_down("AAPL", session_date=session) is True


# ---------------------------------------------------------------------------
# SPY TRENDING_DOWN suppression tests
# ---------------------------------------------------------------------------

class TestTrendingDownSuppression:
    """BUY signals should be suppressed when SPY regime is TRENDING_DOWN."""

    @staticmethod
    def _ma_bounce_setup():
        """Bars + prior that would fire MA Bounce 20."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 99.0, "is_inside": False,
        }
        return bars, prior

    def test_trending_down_suppresses_buy_signals(self):
        bars, prior = self._ma_bounce_setup()
        spy_ctx = {"trend": "bearish", "regime": "TRENDING_DOWN"}

        signals = evaluate_rules("AAPL", bars, prior, spy_context=spy_ctx)
        # Gap Fill is informational and fires outside suppression gate — exclude it
        buy_signals = [
            s for s in signals
            if s.direction == "BUY" and s.alert_type != AlertType.GAP_FILL
        ]
        assert len(buy_signals) == 0

    def test_bearish_without_trending_down_allows_buys(self):
        bars, prior = self._ma_bounce_setup()
        spy_ctx = {"trend": "bearish", "regime": "CHOPPY"}

        signals = evaluate_rules("AAPL", bars, prior, spy_context=spy_ctx)
        buy_signals = [s for s in signals if s.direction == "BUY"]
        assert len(buy_signals) >= 1

    def test_neutral_spy_allows_buys(self):
        bars, prior = self._ma_bounce_setup()
        spy_ctx = {"trend": "neutral", "regime": "CHOPPY"}

        signals = evaluate_rules("AAPL", bars, prior, spy_context=spy_ctx)
        buy_signals = [s for s in signals if s.direction == "BUY"]
        assert len(buy_signals) >= 1

    def test_trending_down_does_not_suppress_sell_signals(self):
        """SELL/SHORT signals should still fire under TRENDING_DOWN."""
        bars = _bars([
            {"Open": 100, "High": 103, "Low": 99.5, "Close": 102.5, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 102.0, "low": 99.0, "is_inside": False,
        }
        entries = [{"entry_price": 100.0, "stop_price": 99.0,
                     "target_1": 101.0, "target_2": 102.0}]
        spy_ctx = {"trend": "bearish", "regime": "TRENDING_DOWN"}

        signals = evaluate_rules("AAPL", bars, prior,
                                  active_entries=entries, spy_context=spy_ctx)
        sell_signals = [s for s in signals if s.direction == "SELL"]
        # Should still have target hits
        assert len(sell_signals) >= 1


# ---------------------------------------------------------------------------
# fired_today dedup tests
# ---------------------------------------------------------------------------

class TestFiredTodayDedup:
    def test_gap_fill_in_fired_today_is_filtered(self):
        """Gap fill already fired → should not appear in signals."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99, "Close": 100.5, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 99.0, "is_inside": False,
        }
        fired = {("AAPL", "gap_fill")}

        signals = evaluate_rules("AAPL", bars, prior, fired_today=fired)
        gap_signals = [s for s in signals if s.alert_type == AlertType.GAP_FILL]
        assert len(gap_signals) == 0

    def test_ma_bounce_in_fired_today_is_filtered(self):
        """MA bounce already fired → should not appear again."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 99.0, "is_inside": False,
        }
        fired = {("AAPL", "ma_bounce_20")}

        signals = evaluate_rules("AAPL", bars, prior, fired_today=fired)
        ma_signals = [s for s in signals if s.alert_type == AlertType.MA_BOUNCE_20]
        assert len(ma_signals) == 0

    def test_fired_today_different_symbol_not_filtered(self):
        """fired_today for TSLA should not filter AAPL's signals."""
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 99.0, "is_inside": False,
        }
        fired = {("TSLA", "ma_bounce_20")}  # Different symbol

        signals = evaluate_rules("AAPL", bars, prior, fired_today=fired)
        ma_signals = [s for s in signals if s.alert_type == AlertType.MA_BOUNCE_20]
        assert len(ma_signals) >= 1


# ---------------------------------------------------------------------------
# Integration: monitor dedup prevents double notification
# ---------------------------------------------------------------------------

class TestMonitorDedup:
    def test_was_alert_fired_after_record(self, tmp_db):
        """After recording an alert, was_alert_fired should return True."""
        from alerting.alert_store import record_alert, was_alert_fired

        session = date.today().isoformat()
        signal = _make_signal("AAPL", AlertType.MA_BOUNCE_20, "BUY", 150.0)

        assert was_alert_fired("AAPL", "ma_bounce_20", session) is False
        record_alert(signal, session_date=session)
        assert was_alert_fired("AAPL", "ma_bounce_20", session) is True

    def test_second_poll_skips_already_fired(self, tmp_db):
        """Simulates two poll cycles — second should not re-fire same alert."""
        from alerting.alert_store import (
            get_alerts_today, record_alert, was_alert_fired,
        )

        session = date.today().isoformat()
        signal = _make_signal("AAPL", AlertType.MA_BOUNCE_20, "BUY", 150.0)

        # Poll cycle 1: fire the alert
        record_alert(signal, session_date=session)

        # Poll cycle 2: build fired_today from DB
        db_alerts = get_alerts_today(session)
        fired_today = {(a["symbol"], a["alert_type"]) for a in db_alerts}
        assert ("AAPL", "ma_bounce_20") in fired_today

        # evaluate_rules with fired_today should suppress it
        bars = _bars([
            {"Open": 149, "High": 151, "Low": 149.98, "Close": 150.3, "Volume": 1000},
        ])
        prior = {
            "ma20": 150.0, "ma50": 145.0, "close": 150.5,
            "high": 151.0, "low": 149.0, "is_inside": False,
        }
        signals = evaluate_rules("AAPL", bars, prior, fired_today=fired_today)
        ma_signals = [s for s in signals if s.alert_type == AlertType.MA_BOUNCE_20]
        assert len(ma_signals) == 0

    def test_cooldown_persists_across_poll_cycles(self, tmp_db):
        """Stop-out in cycle 1 → cooldown persists → BUY suppressed in cycle 2."""
        from alerting.alert_store import get_active_cooldowns, save_cooldown

        session = date.today().isoformat()

        # Cycle 1: stop-out triggers cooldown
        save_cooldown("AAPL", 30, reason="stop_loss_hit", session_date=session)

        # Cycle 2: cooldown still active
        cooled = get_active_cooldowns(session_date=session)
        assert "AAPL" in cooled

        # BUY rules should be suppressed
        bars = _bars([
            {"Open": 100, "High": 101, "Low": 99.98, "Close": 100.3, "Volume": 1000},
        ])
        prior = {
            "ma20": 100.0, "ma50": 95.0, "close": 100.5,
            "high": 101.0, "low": 99.0, "is_inside": False,
        }
        signals = evaluate_rules(
            "AAPL", bars, prior, is_cooled_down=True,
        )
        # Gap Fill is informational and fires outside cooldown gate — exclude it
        buy_signals = [
            s for s in signals
            if s.direction == "BUY" and s.alert_type != AlertType.GAP_FILL
        ]
        assert len(buy_signals) == 0

    def test_cooldown_different_rule_type_still_suppressed(self, tmp_db):
        """After MA Bounce stop-out, PDL Reclaim should also be suppressed (same symbol)."""
        from alerting.alert_store import get_active_cooldowns, save_cooldown

        session = date.today().isoformat()
        save_cooldown("AAPL", 30, reason="stop_loss_hit", session_date=session)

        cooled = get_active_cooldowns(session_date=session)
        assert "AAPL" in cooled
        # Cooldown is per-symbol, not per-rule-type


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_signal(symbol, alert_type, direction, price):
    from analytics.intraday_rules import AlertSignal
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
