"""Unit tests for EOD AI review — build_eod_review + send_eod_review."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


def _spy_ctx(trend="bullish", regime="TRENDING_UP", close=520.3, rsi=58.0):
    return {
        "trend": trend,
        "close": close,
        "regime": regime,
        "spy_rsi14": rsi,
        "ma20": 518.0,
        "ma50": 510.0,
        "ma5": 519.0,
    }


def _make_summary(total=5, buy=3, sell=1, t1=1, t2=0, stopped=1, alerts=None):
    """Build a mock session summary."""
    if alerts is None:
        alerts = [
            {
                "symbol": "NVDA", "alert_type": "ma_bounce_20",
                "direction": "BUY", "price": 144.0,
                "entry": 143.5, "stop": 142.0, "target_1": 146.0,
                "confidence": "high", "score": 75, "message": "Near 20MA bounce",
                "created_at": "2025-06-02 10:15:00",
            },
            {
                "symbol": "AAPL", "alert_type": "support_bounce",
                "direction": "BUY", "price": 188.0,
                "entry": 187.5, "stop": 186.0, "target_1": 190.0,
                "confidence": "medium", "score": 55, "message": "Support test",
                "created_at": "2025-06-02 11:00:00",
            },
            {
                "symbol": "NVDA", "alert_type": "target_1_hit",
                "direction": "SELL", "price": 146.0,
                "entry": None, "stop": None, "target_1": None,
                "confidence": None, "score": 0, "message": "T1 hit",
                "created_at": "2025-06-02 13:00:00",
            },
        ]
    return {
        "total": total,
        "buy_count": buy,
        "sell_count": sell,
        "short_count": 0,
        "t1_hits": t1,
        "t2_hits": t2,
        "stopped_out": stopped,
        "signals_by_type": {"ma_bounce_20": 1, "support_bounce": 1, "target_1_hit": 1},
        "symbols": ["NVDA", "AAPL"],
        "alerts": alerts,
    }


# ===== build_eod_review =====


class TestBuildEodReview:
    """Tests for build_eod_review()."""

    @patch("analytics.eod_review._resolve_api_key", return_value="")
    def test_returns_none_no_api_key(self, _mock):
        from analytics.eod_review import build_eod_review
        assert build_eod_review() is None

    @patch("analytics.eod_review.get_spy_context", return_value=_spy_ctx())
    @patch("analytics.eod_review.get_session_summary", return_value=_make_summary(total=0, alerts=[]))
    @patch("analytics.eod_review._resolve_api_key", return_value="sk-test")
    def test_returns_none_no_alerts(self, _key, _sum, _spy):
        from analytics.eod_review import build_eod_review
        assert build_eod_review() is None

    def test_returns_review_on_success(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Great day. NVDA T1 hit. Focus on MA bounces.")]

        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response

        with (
            patch("analytics.eod_review._resolve_api_key", return_value="sk-test"),
            patch("analytics.eod_review.get_session_summary", return_value=_make_summary()),
            patch("analytics.eod_review.get_spy_context", return_value=_spy_ctx()),
            patch.dict(sys.modules, {"anthropic": mock_anthropic}),
        ):
            from analytics.eod_review import build_eod_review
            result = build_eod_review()

        assert result is not None
        assert "EOD REVIEW" in result
        assert "NVDA T1 hit" in result

    def test_api_error_returns_none(self):
        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value.messages.create.side_effect = Exception("API error")

        with (
            patch("analytics.eod_review._resolve_api_key", return_value="sk-test"),
            patch("analytics.eod_review.get_session_summary", return_value=_make_summary()),
            patch("analytics.eod_review.get_spy_context", return_value=_spy_ctx()),
            patch.dict(sys.modules, {"anthropic": mock_anthropic}),
        ):
            from analytics.eod_review import build_eod_review
            result = build_eod_review()

        assert result is None

    def test_prompt_includes_scorecard(self):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Review text")]

        mock_anthropic = MagicMock()
        mock_client = mock_anthropic.Anthropic.return_value
        mock_client.messages.create.return_value = mock_response

        with (
            patch("analytics.eod_review._resolve_api_key", return_value="sk-test"),
            patch("analytics.eod_review.get_session_summary", return_value=_make_summary(total=5, buy=3, t1=1, stopped=1)),
            patch("analytics.eod_review.get_spy_context", return_value=_spy_ctx()),
            patch.dict(sys.modules, {"anthropic": mock_anthropic}),
        ):
            from analytics.eod_review import build_eod_review
            build_eod_review()

        call_args = mock_client.messages.create.call_args
        user_msg = call_args[1]["messages"][0]["content"]
        assert "Total alerts: 5" in user_msg
        assert "Buys: 3" in user_msg
        assert "T1 hits: 1" in user_msg
        assert "Stopped out: 1" in user_msg

    def test_caps_alerts_at_30(self):
        alerts = [
            {
                "symbol": f"SYM{i}", "alert_type": "ma_bounce_20",
                "direction": "BUY", "price": 100.0 + i,
                "entry": 100.0, "stop": 99.0, "target_1": 102.0,
                "confidence": "medium", "score": 50,
                "message": f"Alert {i}",
                "created_at": f"2025-06-02 10:{i:02d}:00",
            }
            for i in range(50)
        ]

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Review text")]

        mock_anthropic = MagicMock()
        mock_client = mock_anthropic.Anthropic.return_value
        mock_client.messages.create.return_value = mock_response

        with (
            patch("analytics.eod_review._resolve_api_key", return_value="sk-test"),
            patch("analytics.eod_review.get_session_summary", return_value=_make_summary(total=50, buy=50, alerts=alerts)),
            patch("analytics.eod_review.get_spy_context", return_value=_spy_ctx()),
            patch.dict(sys.modules, {"anthropic": mock_anthropic}),
        ):
            from analytics.eod_review import build_eod_review
            build_eod_review()

        call_args = mock_client.messages.create.call_args
        user_msg = call_args[1]["messages"][0]["content"]
        assert "Total alerts: 50" in user_msg
        alert_entries = user_msg.count("Symbol:")
        assert alert_entries <= 30


# ===== send_eod_review =====


class TestSendEodReview:
    """Tests for send_eod_review()."""

    def setup_method(self):
        """Reset module-level guard between tests."""
        import analytics.eod_review as mod
        mod._eod_review_sent_date = None

    @patch("analytics.eod_review.build_eod_review", return_value=None)
    def test_returns_false_when_no_review(self, _mock):
        from analytics.eod_review import send_eod_review
        assert send_eod_review() is False

    @patch("analytics.eod_review._send_telegram_to", return_value=True)
    @patch("analytics.eod_review.build_eod_review", return_value="Review text")
    @patch("analytics.eod_review.today_session", return_value="2025-06-02")
    @patch("db.get_pro_users_with_telegram", return_value=[{"telegram_chat_id": "123", "user_id": 1}])
    def test_sends_once_per_day(self, _users, _ts, _rev, _tg):
        from analytics.eod_review import send_eod_review
        assert send_eod_review() is True
        assert send_eod_review() is False

    @patch("analytics.eod_review._send_telegram_to", return_value=True)
    @patch("analytics.eod_review.build_eod_review", return_value="Review text")
    @patch("analytics.eod_review.today_session")
    @patch("db.get_pro_users_with_telegram", return_value=[{"telegram_chat_id": "123", "user_id": 1}])
    def test_sends_on_new_day(self, _users, mock_ts, _rev, _tg):
        from analytics.eod_review import send_eod_review
        mock_ts.return_value = "2025-06-02"
        assert send_eod_review() is True

        mock_ts.return_value = "2025-06-03"
        assert send_eod_review() is True
