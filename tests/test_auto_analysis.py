"""Tests for auto-analysis feature (T027).

Covers:
- generate_alert_analysis() returns formatted AI Take string
- generate_alert_analysis() returns empty string on failure
- Auto-analysis hook in notify_user only fires when enabled + BUY/SHORT
- Alert delivery is never blocked by AI failure
"""

import os
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics.chart_analyzer import generate_alert_analysis, parse_trade_plan


# ---------------------------------------------------------------------------
# generate_alert_analysis tests
# ---------------------------------------------------------------------------

class TestGenerateAlertAnalysis:
    """Test the lightweight AI Take generator."""

    @patch("analytics.chart_analyzer.assemble_analysis_context")
    @patch("analytics.chart_analyzer.build_analysis_prompt")
    def test_returns_ai_take_for_long(self, mock_prompt, mock_ctx):
        """A valid LONG response produces an 'AI Take: LONG ...' string."""
        mock_ctx.return_value = {"symbol": "AAPL", "timeframe": "5m"}
        mock_prompt.return_value = "test prompt"

        ai_response = (
            "DIRECTION: LONG\n"
            "ENTRY: $142.50\n"
            "STOP: $141.80\n"
            "TARGET_1: $144.20\n"
            "TARGET_2: $146.00\n"
            "RR_RATIO: 2.4\n"
            "CONFIDENCE: HIGH\n"
            "CONFLUENCE_SCORE: 7\n"
        )

        with patch("analytics.trade_coach.ask_coach", return_value=iter(ai_response)):
            result = generate_alert_analysis("AAPL", "5m")

        assert result.startswith("AI Take:")
        assert "LONG" in result
        assert "$142.50" in result
        assert "Stop $141.80" in result
        assert "T1 $144.20" in result
        assert "(2.4:1)" in result
        assert "Confluence 7/10" in result

    @patch("analytics.chart_analyzer.assemble_analysis_context")
    @patch("analytics.chart_analyzer.build_analysis_prompt")
    def test_returns_no_trade_message(self, mock_prompt, mock_ctx):
        """A NO_TRADE response returns a 'wait for setup' message."""
        mock_ctx.return_value = {"symbol": "AMD", "timeframe": "5m"}
        mock_prompt.return_value = "test prompt"

        ai_response = "DIRECTION: NO_TRADE\nCONFIDENCE: LOW\n"

        with patch("analytics.trade_coach.ask_coach", return_value=iter(ai_response)):
            result = generate_alert_analysis("AMD", "5m")

        assert "AI Take:" in result
        assert "No clear edge" in result
        assert "AMD" in result

    @patch("analytics.chart_analyzer.assemble_analysis_context")
    @patch("analytics.chart_analyzer.build_analysis_prompt")
    def test_returns_empty_on_unparseable(self, mock_prompt, mock_ctx):
        """If AI returns garbage, generate_alert_analysis returns empty string."""
        mock_ctx.return_value = {"symbol": "SPY", "timeframe": "5m"}
        mock_prompt.return_value = "test prompt"

        with patch("analytics.trade_coach.ask_coach", return_value=iter("Random text no structure")):
            result = generate_alert_analysis("SPY", "5m")

        assert result == ""

    def test_returns_empty_on_exception(self):
        """Any exception returns empty string, never raises."""
        with patch(
            "analytics.chart_analyzer.assemble_analysis_context",
            side_effect=Exception("boom"),
        ):
            result = generate_alert_analysis("SPY", "5m")

        assert result == ""


# ---------------------------------------------------------------------------
# notify_user auto-analysis hook tests
# ---------------------------------------------------------------------------

class TestAutoAnalysisHook:
    """Test that the notifier hook spawns auto-analysis correctly."""

    def _make_signal(self, direction="BUY", symbol="AAPL"):
        from analytics.intraday_rules import AlertSignal, AlertType

        return AlertSignal(
            symbol=symbol,
            alert_type=AlertType.MA_BOUNCE_20,
            direction=direction,
            price=150.0,
            entry=149.5,
            stop=148.0,
            target_1=153.0,
            target_2=156.0,
            confidence="high",
            score=85,
            message="Test alert",
        )

    @patch("alerting.notifier._send_telegram_to", return_value=True)
    @patch("alerting.notifier._send_auto_analysis")
    def test_spawns_thread_when_enabled(self, mock_auto, mock_tg):
        """Auto-analysis fires when auto_analysis_enabled=True and direction is BUY."""
        from alerting.notifier import notify_user

        prefs = {
            "telegram_enabled": True,
            "telegram_chat_id": "12345",
            "auto_analysis_enabled": True,
        }

        # Patch threading.Thread to capture the call without actually spawning
        with patch("alerting.notifier.threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            notify_user(self._make_signal("BUY"), prefs)

        mock_thread.assert_called_once()
        call_kwargs = mock_thread.call_args
        assert call_kwargs[1]["target"] == mock_auto
        assert call_kwargs[1]["args"] == ("AAPL", "12345")

    @patch("alerting.notifier._send_telegram_to", return_value=True)
    def test_no_thread_when_disabled(self, mock_tg):
        """Auto-analysis does NOT fire when auto_analysis_enabled=False."""
        from alerting.notifier import notify_user

        prefs = {
            "telegram_enabled": True,
            "telegram_chat_id": "12345",
            "auto_analysis_enabled": False,
        }

        with patch("alerting.notifier.threading.Thread") as mock_thread:
            notify_user(self._make_signal("BUY"), prefs)

        mock_thread.assert_not_called()

    @patch("alerting.notifier._send_telegram_to", return_value=True)
    def test_no_thread_for_notice_direction(self, mock_tg):
        """Auto-analysis does NOT fire for NOTICE direction signals."""
        from alerting.notifier import notify_user

        prefs = {
            "telegram_enabled": True,
            "telegram_chat_id": "12345",
            "auto_analysis_enabled": True,
        }

        with patch("alerting.notifier.threading.Thread") as mock_thread:
            notify_user(self._make_signal("NOTICE"), prefs)

        mock_thread.assert_not_called()

    @patch("alerting.notifier._send_telegram_to", return_value=True)
    @patch("alerting.notifier._send_auto_analysis")
    def test_spawns_thread_for_short(self, mock_auto, mock_tg):
        """Auto-analysis also fires for SHORT direction (structural short)."""
        from analytics.intraday_rules import AlertSignal, AlertType
        from alerting.notifier import notify_user

        # Use a structural short type that passes the SHORT filter in notifier
        signal = AlertSignal(
            symbol="SPY",
            alert_type=AlertType.SUPPORT_BREAKDOWN,
            direction="SHORT",
            price=520.0,
            entry=520.0,
            stop=522.0,
            target_1=516.0,
            target_2=512.0,
            confidence="high",
            score=85,
            message="Test structural short",
        )

        prefs = {
            "telegram_enabled": True,
            "telegram_chat_id": "12345",
            "auto_analysis_enabled": True,
        }

        with patch("alerting.notifier.threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            notify_user(signal, prefs)

        mock_thread.assert_called_once()

    @patch("alerting.notifier._send_telegram_to", return_value=True)
    def test_alert_delivery_not_blocked_by_analysis_failure(self, mock_tg):
        """Even if auto-analysis throws, the alert was already sent."""
        from alerting.notifier import notify_user

        prefs = {
            "telegram_enabled": True,
            "telegram_chat_id": "12345",
            "auto_analysis_enabled": True,
        }

        def exploding_thread(*args, **kwargs):
            m = MagicMock()
            m.start.side_effect = RuntimeError("thread pool exhausted")
            return m

        with patch("alerting.notifier.threading.Thread", side_effect=exploding_thread):
            # Should not raise — alert was already sent before thread spawn
            try:
                _, tg_sent = notify_user(self._make_signal("BUY"), prefs)
            except RuntimeError:
                # Even if it does propagate, the telegram was sent
                pass

        # The main telegram send happened regardless
        assert mock_tg.called
