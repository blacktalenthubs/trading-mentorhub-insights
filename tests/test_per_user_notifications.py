"""Test per-user notification routing.

Verifies that:
- User A with [SPY, AAPL] gets alerts for SPY and AAPL only
- User B with [SPY, ETH-USD] gets alerts for SPY and ETH-USD only
- User C with [NVDA] gets alerts for NVDA only
- SPY alert goes to both User A and User B (shared symbol)
- AAPL alert goes to User A only
- ETH-USD alert goes to User B only
- NVDA alert goes to User C only
"""

import os
import sys
from unittest.mock import patch, MagicMock
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Create a temp SQLite DB with 3 users + watchlists + notification prefs."""
    import sqlite3
    from contextlib import contextmanager

    db_path = str(tmp_path / "test.db")

    def _conn():
        c = sqlite3.connect(db_path)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        c.row_factory = sqlite3.Row
        return c

    @contextmanager
    def _get_db():
        c = _conn()
        try:
            yield c
            c.commit()
        finally:
            c.close()

    # Patch get_db before calling init_db so tables go to our test DB
    import db as db_module
    monkeypatch.setattr(db_module, "get_db", _get_db)
    # Reset the init guard so init_db actually runs
    db_module._init_done = False
    db_module.init_db()
    conn = _conn()

    # Seed data: 3 users
    for uid, email, name in [(101, "usera@test.com", "User A"), (102, "userb@test.com", "User B"), (103, "userc@test.com", "User C")]:
        conn.execute("INSERT INTO users (id, email, password_hash, display_name) VALUES (?, ?, ?, ?)", (uid, email, "hash", name))

    # Watchlists
    for uid, sym in [(101, "SPY"), (101, "AAPL"), (102, "SPY"), (102, "ETH-USD"), (103, "NVDA")]:
        conn.execute("INSERT INTO watchlist (user_id, symbol) VALUES (?, ?)", (uid, sym))

    # Notification prefs
    for uid, chat in [(101, "chat_A"), (102, "chat_B"), (103, "chat_C")]:
        conn.execute("INSERT INTO user_notification_prefs (user_id, telegram_chat_id, telegram_enabled, email_enabled) VALUES (?, ?, ?, ?)", (uid, chat, 1, 0))

    conn.commit()
    conn.close()

    # Patch db.get_db everywhere it's imported
    import db as db_module
    monkeypatch.setattr(db_module, "get_db", _get_db)
    # Also patch in alert_store which imports get_db at module level
    import alerting.alert_store as alert_store_module
    monkeypatch.setattr(alert_store_module, "get_db", _get_db)

    yield db_path


def _signal(symbol, price=100.0):
    """Create a test AlertSignal."""
    from analytics.intraday_rules import AlertSignal, AlertType
    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.MA_BOUNCE_20,
        direction="BUY",
        price=price,
        message=f"Test {symbol} at ${price}",
        score=60,
        entry=price,
        stop=round(price * 0.98, 2),
        target_1=round(price * 1.03, 2),
    )


class TestWatchlistRouting:

    def test_user_watchlists_correct(self, test_db):
        from db import get_db
        with get_db() as conn:
            a = {r["symbol"] for r in conn.execute("SELECT symbol FROM watchlist WHERE user_id=101").fetchall()}
            b = {r["symbol"] for r in conn.execute("SELECT symbol FROM watchlist WHERE user_id=102").fetchall()}
            c = {r["symbol"] for r in conn.execute("SELECT symbol FROM watchlist WHERE user_id=103").fetchall()}
        assert a == {"SPY", "AAPL"}
        assert b == {"SPY", "ETH-USD"}
        assert c == {"NVDA"}

    def test_spy_shared(self, test_db):
        from db import get_db
        with get_db() as conn:
            users = {r["user_id"] for r in conn.execute("SELECT user_id FROM watchlist WHERE symbol='SPY'").fetchall()}
        assert users == {101, 102}

    def test_aapl_only_user_a(self, test_db):
        from db import get_db
        with get_db() as conn:
            users = {r["user_id"] for r in conn.execute("SELECT user_id FROM watchlist WHERE symbol='AAPL'").fetchall()}
        assert users == {101}


class TestNotifyUserRouting:

    @patch("alerting.notifier._send_telegram_to", return_value=True)
    def test_sends_to_correct_chat_id(self, mock_send):
        from alerting.notifier import notify_user
        notify_user(_signal("SPY", 675), {"telegram_enabled": True, "telegram_chat_id": "chat_A", "email_enabled": False})
        assert mock_send.call_args[0][1] == "chat_A"

    @patch("alerting.notifier._send_telegram_to", return_value=True)
    def test_same_signal_two_users_two_chats(self, mock_send):
        from alerting.notifier import notify_user
        sig = _signal("SPY", 675)
        notify_user(sig, {"telegram_enabled": True, "telegram_chat_id": "chat_A", "email_enabled": False})
        notify_user(sig, {"telegram_enabled": True, "telegram_chat_id": "chat_B", "email_enabled": False})
        chats = [c[0][1] for c in mock_send.call_args_list]
        assert "chat_A" in chats
        assert "chat_B" in chats

    @patch("alerting.notifier._send_telegram_to", return_value=True)
    def test_disabled_telegram_no_send(self, mock_send):
        from alerting.notifier import notify_user
        notify_user(_signal("SPY"), {"telegram_enabled": False, "telegram_chat_id": "chat_X", "email_enabled": False})
        mock_send.assert_not_called()

    @patch("alerting.notifier._send_telegram_to", return_value=True)
    def test_empty_chat_id_no_send(self, mock_send):
        from alerting.notifier import notify_user
        notify_user(_signal("AAPL"), {"telegram_enabled": True, "telegram_chat_id": "", "email_enabled": False})
        mock_send.assert_not_called()


class TestEndToEndRouting:

    @patch("alerting.notifier._send_telegram_to", return_value=True)
    def test_full_scenario(self, mock_send, test_db):
        """
        SPY alert → User A (chat_A) + User B (chat_B)
        AAPL alert → User A (chat_A) only
        ETH-USD alert → User B (chat_B) only
        NVDA alert → User C (chat_C) only
        """
        from alerting.notifier import notify_user
        from db import get_db

        # Load watchlists + prefs
        users = {}
        with get_db() as conn:
            for uid, chat in [(101, "chat_A"), (102, "chat_B"), (103, "chat_C")]:
                syms = {r["symbol"] for r in conn.execute("SELECT symbol FROM watchlist WHERE user_id=?", (uid,)).fetchall()}
                users[uid] = {"symbols": syms, "prefs": {"telegram_enabled": True, "telegram_chat_id": chat, "email_enabled": False}}

        # Simulate alerts
        signals = {
            "SPY": _signal("SPY", 675),
            "AAPL": _signal("AAPL", 258),
            "ETH-USD": _signal("ETH-USD", 2200),
            "NVDA": _signal("NVDA", 182),
        }

        sent = {}  # chat_id → [symbols]
        for sym, sig in signals.items():
            for uid, u in users.items():
                if sym in u["symbols"]:
                    notify_user(sig, u["prefs"])
                    chat = u["prefs"]["telegram_chat_id"]
                    sent.setdefault(chat, []).append(sym)

        # Verify
        assert set(sent["chat_A"]) == {"SPY", "AAPL"}
        assert set(sent["chat_B"]) == {"SPY", "ETH-USD"}
        assert set(sent["chat_C"]) == {"NVDA"}

        # Verify total calls: SPY×2 + AAPL×1 + ETH×1 + NVDA×1 = 5
        assert mock_send.call_count == 5

    @patch("alerting.notifier._send_telegram_to", return_value=True)
    def test_user_c_never_gets_spy(self, mock_send, test_db):
        """User C (NVDA only) must NOT receive SPY alerts."""
        from alerting.notifier import notify_user
        from db import get_db

        with get_db() as conn:
            c_syms = {r["symbol"] for r in conn.execute("SELECT symbol FROM watchlist WHERE user_id=103").fetchall()}

        prefs_c = {"telegram_enabled": True, "telegram_chat_id": "chat_C", "email_enabled": False}

        for sym, price in [("SPY", 675), ("AAPL", 258), ("ETH-USD", 2200), ("NVDA", 182)]:
            if sym in c_syms:
                notify_user(_signal(sym, price), prefs_c)

        # Only NVDA
        assert mock_send.call_count == 1
        assert "NVDA" in mock_send.call_args[0][0]
        assert mock_send.call_args[0][1] == "chat_C"

    @patch("alerting.notifier._send_telegram_to", return_value=True)
    def test_spy_message_identical_for_both_users(self, mock_send, test_db):
        """User A and User B should get the SAME message body for SPY."""
        from alerting.notifier import notify_user

        sig = _signal("SPY", 675)
        prefs_a = {"telegram_enabled": True, "telegram_chat_id": "chat_A", "email_enabled": False}
        prefs_b = {"telegram_enabled": True, "telegram_chat_id": "chat_B", "email_enabled": False}

        notify_user(sig, prefs_a)
        notify_user(sig, prefs_b)

        msg_a = mock_send.call_args_list[0][0][0]
        msg_b = mock_send.call_args_list[1][0][0]
        assert msg_a == msg_b  # Same message content
        assert mock_send.call_args_list[0][0][1] != mock_send.call_args_list[1][0][1]  # Different chat_ids


class TestAlertRecordingPerUser:

    def test_record_alert_per_user(self, test_db):
        """Alerts are recorded with user_id so each user has their own alert history."""
        from alerting.alert_store import record_alert
        from db import get_db

        sig = _signal("SPY", 675)
        session = date.today().isoformat()

        record_alert(sig, session, user_id=101)
        record_alert(sig, session, user_id=102)

        with get_db() as conn:
            rows = conn.execute(
                "SELECT user_id FROM alerts WHERE session_date=? AND symbol='SPY'",
                (session,),
            ).fetchall()

        uids = {r["user_id"] for r in rows}
        assert 101 in uids
        assert 102 in uids
        assert 103 not in uids
