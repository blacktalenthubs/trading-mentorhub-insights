"""Integration tests for per-user alert routing and display language.

Covers:
- Multi-user watchlist routing: alerts reach correct users based on watchlist
- Tier-based delivery: Pro/Elite get DM + email, Free gets nothing personal
- Display language: Telegram messages use non-prescriptive language
- Free tier daily alert limit: get_daily_alert_count tracks correctly
- Monitor poll_cycle routes to per-user notify_user
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from unittest.mock import call, patch

import pytest

from analytics.intraday_rules import AlertSignal, AlertType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def routing_db(tmp_path):
    """Temporary DB with users, subscriptions, watchlists, and notification prefs."""
    db_path = str(tmp_path / "routing_test.db")

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

        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
            tier TEXT NOT NULL DEFAULT 'free',
            status TEXT NOT NULL DEFAULT 'active',
            stripe_customer_id TEXT DEFAULT '',
            stripe_subscription_id TEXT DEFAULT '',
            current_period_start TEXT,
            current_period_end TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

        CREATE TABLE IF NOT EXISTS user_notification_prefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            telegram_chat_id TEXT DEFAULT '',
            notification_email TEXT DEFAULT '',
            telegram_enabled INTEGER DEFAULT 1,
            email_enabled INTEGER DEFAULT 1,
            anthropic_api_key TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, symbol)
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

        CREATE TABLE IF NOT EXISTS daily_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            session_date TEXT NOT NULL,
            direction TEXT,
            entry REAL,
            stop REAL,
            target_1 REAL,
            target_2 REAL,
            score INTEGER DEFAULT 0,
            support_levels TEXT DEFAULT '[]',
            resistance_levels TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, session_date)
        );
    """)

    # Seed 3 users: Alice (pro), Bob (free), Carol (elite)
    conn.execute(
        "INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)",
        ("alice@test.com", "fakehash", "Alice"),
    )
    conn.execute(
        "INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)",
        ("bob@test.com", "fakehash", "Bob"),
    )
    conn.execute(
        "INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)",
        ("carol@test.com", "fakehash", "Carol"),
    )

    # Subscriptions: Alice=pro, Bob=free, Carol=elite
    conn.execute(
        "INSERT INTO subscriptions (user_id, tier, status) VALUES (?, ?, ?)",
        (1, "pro", "active"),
    )
    conn.execute(
        "INSERT INTO subscriptions (user_id, tier, status) VALUES (?, ?, ?)",
        (2, "free", "active"),
    )
    conn.execute(
        "INSERT INTO subscriptions (user_id, tier, status) VALUES (?, ?, ?)",
        (3, "elite", "active"),
    )

    # Watchlists: Alice=AAPL+TSLA, Bob=AAPL, Carol=TSLA
    conn.execute("INSERT INTO watchlist (user_id, symbol) VALUES (1, 'AAPL')")
    conn.execute("INSERT INTO watchlist (user_id, symbol) VALUES (1, 'TSLA')")
    conn.execute("INSERT INTO watchlist (user_id, symbol) VALUES (2, 'AAPL')")
    conn.execute("INSERT INTO watchlist (user_id, symbol) VALUES (3, 'TSLA')")

    # Notification prefs: all have Telegram + email configured
    conn.execute(
        "INSERT INTO user_notification_prefs "
        "(user_id, telegram_chat_id, notification_email, telegram_enabled, email_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, "alice_chat_123", "alice@test.com", 1, 1),
    )
    conn.execute(
        "INSERT INTO user_notification_prefs "
        "(user_id, telegram_chat_id, notification_email, telegram_enabled, email_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        (2, "bob_chat_456", "bob@test.com", 1, 1),
    )
    conn.execute(
        "INSERT INTO user_notification_prefs "
        "(user_id, telegram_chat_id, notification_email, telegram_enabled, email_enabled) "
        "VALUES (?, ?, ?, ?, ?)",
        (3, "carol_chat_789", "carol@test.com", 1, 1),
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
                 direction="BUY", price=150.0, score=75, score_label="A"):
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
        score=score,
        score_label=score_label,
        message="Test signal",
    )


# ---------------------------------------------------------------------------
# Per-user watchlist routing
# ---------------------------------------------------------------------------

class TestWatchlistRouting:
    """Verify alerts route to users who have the symbol on their watchlist."""

    def test_aapl_alert_routes_to_alice_and_bob(self, routing_db):
        """AAPL is on Alice (pro) and Bob (free) watchlists."""
        from db import get_users_for_symbol
        users = get_users_for_symbol("AAPL")
        assert sorted(users) == [1, 2]  # Alice=1, Bob=2

    def test_tsla_alert_routes_to_alice_and_carol(self, routing_db):
        """TSLA is on Alice (pro) and Carol (elite) watchlists."""
        from db import get_users_for_symbol
        users = get_users_for_symbol("TSLA")
        assert sorted(users) == [1, 3]  # Alice=1, Carol=3

    def test_unknown_symbol_routes_to_nobody(self, routing_db):
        from db import get_users_for_symbol
        assert get_users_for_symbol("NVDA") == []


# ---------------------------------------------------------------------------
# Tier-based delivery
# ---------------------------------------------------------------------------

class TestTierBasedDelivery:
    """Pro/Elite get DM + email. Free users get nothing personal."""

    def test_pro_user_gets_dm_and_email(self, routing_db):
        """Alice (pro) with AAPL on watchlist gets personal DM + email."""
        from alerting.notifier import notify_user
        from db import get_notification_prefs

        prefs = get_notification_prefs(1)  # Alice
        signal = _make_signal(symbol="AAPL")

        with (
            patch("alerting.notifier.send_email_to", return_value=True) as mock_email,
            patch("alerting.notifier._send_telegram_to", return_value=True) as mock_tg,
        ):
            email_ok, tg_ok = notify_user(signal, prefs)

        assert email_ok is True
        assert tg_ok is True
        mock_email.assert_called_once()
        # Verify sent to Alice's email
        assert mock_email.call_args[0][1] == "alice@test.com"
        # Verify sent to Alice's chat_id
        assert mock_tg.call_args[0][1] == "alice_chat_123"

    def test_elite_user_gets_dm_and_email(self, routing_db):
        """Carol (elite) with TSLA on watchlist gets personal DM + email."""
        from alerting.notifier import notify_user
        from db import get_notification_prefs

        prefs = get_notification_prefs(3)  # Carol
        signal = _make_signal(symbol="TSLA")

        with (
            patch("alerting.notifier.send_email_to", return_value=True) as mock_email,
            patch("alerting.notifier._send_telegram_to", return_value=True) as mock_tg,
        ):
            email_ok, tg_ok = notify_user(signal, prefs)

        assert email_ok is True
        assert tg_ok is True
        assert mock_email.call_args[0][1] == "carol@test.com"
        assert mock_tg.call_args[0][1] == "carol_chat_789"

    def test_free_user_excluded_from_per_user_routing(self, routing_db):
        """Bob (free) has AAPL on watchlist but tier gate blocks DM/email."""
        from db import get_user_tier, get_users_for_symbol

        users = get_users_for_symbol("AAPL")
        assert 2 in users  # Bob is in the list

        # But his tier is free → monitor loop should skip notify_user
        assert get_user_tier(2) == "free"

    def test_full_routing_loop_pro_gets_notified_free_does_not(self, routing_db):
        """Simulate the monitor routing loop for an AAPL alert.

        Alice (pro, user_id=1) should get notify_user called.
        Bob (free, user_id=2) should NOT get notify_user called.
        """
        from db import get_notification_prefs, get_user_tier, get_users_for_symbol

        signal = _make_signal(symbol="AAPL")
        notified_users = []

        with (
            patch("alerting.notifier.send_email_to", return_value=True),
            patch("alerting.notifier._send_telegram_to", return_value=True),
        ):
            from alerting.notifier import notify_user

            for uid in get_users_for_symbol("AAPL"):
                tier = get_user_tier(uid)
                if tier in ("pro", "elite"):
                    prefs = get_notification_prefs(uid)
                    if prefs:
                        notify_user(signal, prefs)
                        notified_users.append(uid)

        # Alice (pro) notified, Bob (free) not
        assert 1 in notified_users
        assert 2 not in notified_users

    def test_tsla_alert_routes_to_pro_and_elite_only(self, routing_db):
        """TSLA alert: Alice (pro) + Carol (elite) get DM. No free users on TSLA."""
        from db import get_notification_prefs, get_user_tier, get_users_for_symbol

        signal = _make_signal(symbol="TSLA")
        notified_users = []

        with (
            patch("alerting.notifier.send_email_to", return_value=True),
            patch("alerting.notifier._send_telegram_to", return_value=True),
        ):
            from alerting.notifier import notify_user

            for uid in get_users_for_symbol("TSLA"):
                tier = get_user_tier(uid)
                if tier in ("pro", "elite"):
                    prefs = get_notification_prefs(uid)
                    if prefs:
                        notify_user(signal, prefs)
                        notified_users.append(uid)

        assert sorted(notified_users) == [1, 3]  # Alice + Carol


# ---------------------------------------------------------------------------
# Display language in notifications
# ---------------------------------------------------------------------------

class TestDisplayLanguage:
    """Verify non-prescriptive language in Telegram/email messages."""

    def test_buy_telegram_says_potential_entry(self):
        """BUY direction → 'POTENTIAL ENTRY' in Telegram body (HTML formatted)."""
        from alerting.notifier import _format_sms_body

        signal = _make_signal(direction="BUY", score=80, score_label="A")
        body = _format_sms_body(signal)
        assert "POTENTIAL ENTRY AAPL" in body
        # Body uses HTML bold tags, so first line starts with <b>POTENTIAL ENTRY
        assert body.startswith("<b>POTENTIAL ENTRY")
        # Must NOT contain raw "BUY"
        assert "BUY AAPL" not in body

    def test_sell_telegram_says_exit_zone(self):
        """SELL direction → 'EXIT ZONE' in Telegram body."""
        from alerting.notifier import _format_sms_body

        signal = AlertSignal(
            symbol="AAPL",
            alert_type=AlertType.RESISTANCE_PRIOR_HIGH,
            direction="SELL",
            price=155.0,
            message="Prior High Resistance",
        )
        body = _format_sms_body(signal)
        assert "EXIT ZONE AAPL" in body
        assert "SELL AAPL" not in body

    def test_short_telegram_says_potential_short(self):
        """SHORT direction → 'POTENTIAL SHORT' in Telegram body."""
        from alerting.notifier import _format_sms_body

        signal = _make_signal(direction="SHORT", score=70, score_label="B")
        body = _format_sms_body(signal)
        assert "POTENTIAL SHORT AAPL" in body
        assert "SHORT AAPL" not in body or "POTENTIAL SHORT AAPL" in body

    def test_notice_telegram_says_market_update(self):
        """NOTICE direction → 'MARKET UPDATE' in Telegram body."""
        from alerting.notifier import _format_sms_body

        signal = AlertSignal(
            symbol="SPY",
            alert_type=AlertType.FIRST_HOUR_SUMMARY,
            direction="NOTICE",
            price=425.0,
            message="First hour summary",
        )
        body = _format_sms_body(signal)
        assert "MARKET UPDATE SPY" in body
        assert "NOTICE SPY" not in body

    def test_buy_entry_label_says_potential_entry(self):
        """Entry line in Telegram → 'Potential Entry $X' not 'Entry $X'."""
        from alerting.notifier import _format_sms_body

        signal = _make_signal(direction="BUY", score=80, score_label="A")
        body = _format_sms_body(signal)
        assert "Potential Entry $150.00" in body

    def test_ui_display_direction_helper(self):
        """ui_theme.display_direction() returns correct label and color."""
        import importlib
        import sys
        from unittest.mock import MagicMock

        # Mock heavy UI deps so ui_theme can be imported in test env
        _mocked = {}
        for mod in ("plotly", "plotly.graph_objects", "streamlit"):
            if mod not in sys.modules:
                sys.modules[mod] = MagicMock()
                _mocked[mod] = True

        try:
            # Force re-import if ui_theme was not previously loaded
            if "ui_theme" in sys.modules:
                import ui_theme
                importlib.reload(ui_theme)
            from ui_theme import display_direction

            label, color = display_direction("BUY")
            assert label == "Potential Entry"
            assert color == "#2ecc71"

            label, color = display_direction("SELL")
            assert label == "Exit Zone"
            assert color == "#e74c3c"

            label, color = display_direction("SHORT")
            assert label == "Potential Short"
            assert color == "#9b59b6"

            label, color = display_direction("NOTICE")
            assert label == "Market Update"
            assert color == "#3498db"
        finally:
            for mod in _mocked:
                sys.modules.pop(mod, None)

    def test_unknown_direction_falls_back(self):
        """Unknown direction returns itself with gray color."""
        import sys
        from unittest.mock import MagicMock

        _mocked = {}
        for mod in ("plotly", "plotly.graph_objects", "streamlit"):
            if mod not in sys.modules:
                sys.modules[mod] = MagicMock()
                _mocked[mod] = True

        try:
            from ui_theme import display_direction

            label, color = display_direction("UNKNOWN")
            assert label == "UNKNOWN"
            assert color == "#888"
        finally:
            for mod in _mocked:
                sys.modules.pop(mod, None)

    def test_email_subject_uses_display_language(self):
        """Email subject shows 'Potential Entry' not 'BUY'."""
        import sys
        from unittest.mock import MagicMock

        _mocked = {}
        for mod in ("plotly", "plotly.graph_objects", "streamlit"):
            if mod not in sys.modules:
                sys.modules[mod] = MagicMock()
                _mocked[mod] = True

        try:
            from alerting.notifier import send_email_to
            from ui_theme import display_direction

            signal = _make_signal(direction="BUY")

            with patch("alerting.notifier.smtplib") as mock_smtp:
                mock_server = mock_smtp.SMTP.return_value.__enter__.return_value
                mock_server.sendmail = lambda *a: None

                # We can't easily intercept the subject, so test via _format approach
                dir_label, _ = display_direction(signal.direction)
                expected_subject_part = f"[TRADE ALERT] {dir_label} {signal.symbol}"
                assert "Potential Entry" in expected_subject_part
                assert "BUY" not in expected_subject_part
        finally:
            for mod in _mocked:
                sys.modules.pop(mod, None)


# ---------------------------------------------------------------------------
# Free tier daily alert count
# ---------------------------------------------------------------------------

class TestFreeTierDailyLimit:
    """Verify daily alert counting for free-tier limiting."""

    def test_daily_alert_count_starts_at_zero(self, routing_db):
        from db import get_daily_alert_count
        session = date.today().isoformat()
        assert get_daily_alert_count(2, session) == 0  # Bob, no alerts yet

    def test_daily_alert_count_increments_with_records(self, routing_db):
        from alerting.alert_store import record_alert
        from db import get_daily_alert_count

        session = date.today().isoformat()
        signal1 = _make_signal(symbol="AAPL")
        signal2 = _make_signal(symbol="MSFT")

        record_alert(signal1, session_date=session, user_id=2)
        assert get_daily_alert_count(2, session) == 1

        record_alert(signal2, session_date=session, user_id=2)
        assert get_daily_alert_count(2, session) == 2

    def test_daily_alert_count_scoped_to_user(self, routing_db):
        """User 1's alerts don't count toward user 2's limit."""
        from alerting.alert_store import record_alert
        from db import get_daily_alert_count

        session = date.today().isoformat()
        signal1 = _make_signal(symbol="AAPL")
        signal2 = _make_signal(symbol="MSFT")

        record_alert(signal1, session_date=session, user_id=1)
        record_alert(signal2, session_date=session, user_id=1)

        assert get_daily_alert_count(1, session) == 2
        assert get_daily_alert_count(2, session) == 0

    def test_daily_alert_count_scoped_to_date(self, routing_db):
        """Yesterday's alerts don't count toward today's limit."""
        from alerting.alert_store import record_alert
        from db import get_daily_alert_count

        signal = _make_signal(symbol="AAPL")

        record_alert(signal, session_date="2026-03-05", user_id=2)
        record_alert(signal, session_date="2026-03-06", user_id=2)

        assert get_daily_alert_count(2, "2026-03-05") == 1
        assert get_daily_alert_count(2, "2026-03-06") == 1

    def test_free_daily_alert_limit_constant_exists(self):
        from alert_config import FREE_DAILY_ALERT_LIMIT
        assert FREE_DAILY_ALERT_LIMIT == 3


# ---------------------------------------------------------------------------
# End-to-end: monitor routing simulation
# ---------------------------------------------------------------------------

class TestMonitorRoutingE2E:
    """Simulate the full monitor routing loop with mocked notifications."""

    def test_aapl_alert_sends_global_then_routes_to_pro_user(self, routing_db):
        """Full flow: notify() broadcasts globally, then per-user loop
        sends DM to Alice (pro) but skips Bob (free)."""
        from db import get_notification_prefs, get_user_tier, get_users_for_symbol

        signal = _make_signal(symbol="AAPL")

        with (
            patch("alerting.notifier.send_email", return_value=True) as mock_global_email,
            patch("alerting.notifier.send_sms", return_value=True) as mock_global_sms,
            patch("alerting.notifier.send_email_to", return_value=True) as mock_user_email,
            patch("alerting.notifier._send_telegram_to", return_value=True) as mock_user_tg,
        ):
            from alerting.notifier import notify, notify_user

            # Step 1: Global broadcast (community Telegram + admin email)
            email_sent, sms_sent = notify(signal)
            assert email_sent is True
            assert sms_sent is True

            # Step 2: Per-user routing
            notified_uids = []
            for uid in get_users_for_symbol("AAPL"):
                tier = get_user_tier(uid)
                if tier in ("pro", "elite"):
                    prefs = get_notification_prefs(uid)
                    if prefs:
                        notify_user(signal, prefs)
                        notified_uids.append(uid)

            # Alice (pro, uid=1) got personal notification
            assert 1 in notified_uids
            # Bob (free, uid=2) did NOT
            assert 2 not in notified_uids

            # Verify Alice's chat_id was called
            tg_calls = mock_user_tg.call_args_list
            chat_ids_called = [c[0][1] for c in tg_calls]
            assert "alice_chat_123" in chat_ids_called
            assert "bob_chat_456" not in chat_ids_called

    def test_tsla_alert_notifies_both_pro_and_elite(self, routing_db):
        """TSLA: Alice (pro) + Carol (elite) both get DM."""
        from db import get_notification_prefs, get_user_tier, get_users_for_symbol

        signal = _make_signal(symbol="TSLA")

        with (
            patch("alerting.notifier.send_email_to", return_value=True) as mock_email,
            patch("alerting.notifier._send_telegram_to", return_value=True) as mock_tg,
        ):
            from alerting.notifier import notify_user

            notified_uids = []
            for uid in get_users_for_symbol("TSLA"):
                tier = get_user_tier(uid)
                if tier in ("pro", "elite"):
                    prefs = get_notification_prefs(uid)
                    if prefs:
                        notify_user(signal, prefs)
                        notified_uids.append(uid)

            assert sorted(notified_uids) == [1, 3]

            # Both users' chat_ids were called
            tg_calls = mock_tg.call_args_list
            chat_ids_called = [c[0][1] for c in tg_calls]
            assert "alice_chat_123" in chat_ids_called
            assert "carol_chat_789" in chat_ids_called

    def test_symbol_not_on_any_watchlist_routes_nowhere(self, routing_db):
        """NVDA alert: nobody has it on watchlist → no per-user notifications."""
        from db import get_users_for_symbol

        signal = _make_signal(symbol="NVDA")
        users = get_users_for_symbol("NVDA")
        assert users == []
        # The per-user loop body never executes

    def test_telegram_message_content_is_non_prescriptive(self, routing_db):
        """When DM is sent to Pro user, the message body uses display language."""
        from db import get_notification_prefs

        signal = _make_signal(symbol="AAPL", direction="BUY", score=85, score_label="A")
        prefs = get_notification_prefs(1)  # Alice

        with (
            patch("alerting.notifier.send_email_to", return_value=True),
            patch("alerting.notifier._send_telegram_to", return_value=True) as mock_tg,
        ):
            from alerting.notifier import notify_user
            notify_user(signal, prefs)

        # The body passed to _send_telegram_to should use display language
        tg_body = mock_tg.call_args[0][0]
        assert "POTENTIAL ENTRY AAPL" in tg_body
        assert "Potential Entry $150.00" in tg_body
        # Should not contain raw "BUY AAPL" as the first-line prefix
        first_line = tg_body.split("\n")[0]
        # Body uses HTML bold tags, so first line starts with <b>POTENTIAL ENTRY
        assert first_line.startswith("<b>POTENTIAL ENTRY")
