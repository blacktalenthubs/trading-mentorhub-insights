"""Unit tests for analytics/trade_coach.py — AI Trade Coach."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# TestAssembleContext
# ---------------------------------------------------------------------------

_PATCH_TARGETS = [
    "alerting.real_trade_store.get_open_trades",
    "alerting.real_trade_store.get_closed_trades",
    "alerting.real_trade_store.get_real_trade_stats",
    "alerting.options_trade_store.get_options_trade_stats",
    "alerting.alert_store.get_session_summary",
    "analytics.intraday_data.get_spy_context",
    "db.get_all_daily_plans",
]


class TestAssembleContext:
    """Test context assembly from DB functions."""

    def setup_method(self):
        """Clear context cache between tests."""
        from analytics.trade_coach import _context_cache
        _context_cache.clear()

    @patch("db.get_all_daily_plans")
    @patch("analytics.intraday_data.get_spy_context")
    @patch("alerting.alert_store.get_session_summary")
    @patch("alerting.options_trade_store.get_options_trade_stats")
    @patch("alerting.real_trade_store.get_real_trade_stats")
    @patch("alerting.real_trade_store.get_closed_trades")
    @patch("alerting.real_trade_store.get_open_trades")
    def test_all_sections_present(
        self, mock_open, mock_closed, mock_stats, mock_opts,
        mock_summary, mock_spy, mock_plans,
    ):
        mock_open.return_value = [{"symbol": "AAPL", "direction": "BUY"}]
        mock_closed.return_value = [{"symbol": "MSFT", "pnl": 100}]
        mock_stats.return_value = {"total_pnl": 500.0, "win_rate": 60.0}
        mock_opts.return_value = {"total_pnl": 200.0}
        mock_summary.return_value = {"total": 5, "buy_count": 3}
        mock_spy.return_value = {"trend": "bullish", "regime": "TRENDING UP"}
        mock_plans.return_value = [{"symbol": "NVDA", "score": 80}]

        from analytics.trade_coach import assemble_context
        ctx = assemble_context()

        assert ctx["open_trades"] == [{"symbol": "AAPL", "direction": "BUY"}]
        assert ctx["recent_closed"] == [{"symbol": "MSFT", "pnl": 100}]
        assert ctx["trade_stats"]["total_pnl"] == 500.0
        assert ctx["options_stats"]["total_pnl"] == 200.0
        assert ctx["session_summary"]["total"] == 5
        assert ctx["spy_context"]["regime"] == "TRENDING UP"
        assert ctx["daily_plans"] == [{"symbol": "NVDA", "score": 80}]

    @patch("db.get_all_daily_plans")
    @patch("analytics.intraday_data.get_spy_context")
    @patch("alerting.alert_store.get_session_summary")
    @patch("alerting.options_trade_store.get_options_trade_stats")
    @patch("alerting.real_trade_store.get_real_trade_stats")
    @patch("alerting.real_trade_store.get_closed_trades")
    @patch("alerting.real_trade_store.get_open_trades")
    def test_handles_empty_data(
        self, mock_open, mock_closed, mock_stats, mock_opts,
        mock_summary, mock_spy, mock_plans,
    ):
        mock_open.return_value = []
        mock_closed.return_value = []
        mock_stats.return_value = {"total_pnl": 0.0, "win_rate": 0.0, "total_trades": 0}
        mock_opts.return_value = {"total_pnl": 0.0}
        mock_summary.return_value = {"total": 0}
        mock_spy.return_value = {"trend": "neutral", "regime": "CHOPPY"}
        mock_plans.return_value = []

        from analytics.trade_coach import assemble_context
        ctx = assemble_context()

        assert ctx["open_trades"] == []
        assert ctx["daily_plans"] == []

    @patch("db.get_all_daily_plans")
    @patch("analytics.intraday_data.get_spy_context")
    @patch("alerting.alert_store.get_session_summary")
    @patch("alerting.options_trade_store.get_options_trade_stats")
    @patch("alerting.real_trade_store.get_real_trade_stats")
    @patch("alerting.real_trade_store.get_closed_trades")
    @patch("alerting.real_trade_store.get_open_trades")
    def test_db_exception_fallback(
        self, mock_open, mock_closed, mock_stats, mock_opts,
        mock_summary, mock_spy, mock_plans,
    ):
        """If a DB call throws, the section should be None (not crash)."""
        mock_open.side_effect = Exception("DB down")
        mock_closed.side_effect = Exception("DB down")
        mock_stats.side_effect = Exception("DB down")
        mock_opts.side_effect = Exception("DB down")
        mock_summary.side_effect = Exception("DB down")
        mock_spy.side_effect = Exception("yfinance timeout")
        mock_plans.side_effect = Exception("DB down")

        from analytics.trade_coach import assemble_context
        ctx = assemble_context()

        assert ctx["open_trades"] is None
        assert ctx["trade_stats"] is None
        assert ctx["spy_context"] is None


# ---------------------------------------------------------------------------
# TestFormatSystemPrompt
# ---------------------------------------------------------------------------

class TestFormatSystemPrompt:
    """Test system prompt formatting from context dict."""

    def _make_context(self, **overrides):
        base = {
            "open_trades": None,
            "recent_closed": None,
            "trade_stats": None,
            "options_stats": None,
            "session_summary": None,
            "spy_context": None,
            "daily_plans": None,
        }
        base.update(overrides)
        return base

    def test_persona_always_present(self):
        from analytics.trade_coach import format_system_prompt
        prompt = format_system_prompt(self._make_context())
        assert "trading analyst" in prompt.lower()

    def test_open_positions_section(self):
        from analytics.trade_coach import format_system_prompt
        trades = [
            {"symbol": "AAPL", "direction": "BUY", "shares": 100,
             "entry_price": 180.0, "stop_price": 178.0, "target_price": 185.0},
        ]
        prompt = format_system_prompt(self._make_context(open_trades=trades))
        assert "[OPEN POSITIONS]" in prompt
        assert "AAPL" in prompt

    def test_no_positions_section_when_empty(self):
        from analytics.trade_coach import format_system_prompt
        prompt = format_system_prompt(self._make_context(open_trades=[]))
        assert "[OPEN POSITIONS]" not in prompt

    def test_spy_regime_section(self):
        from analytics.trade_coach import format_system_prompt
        spy = {"trend": "bullish", "close": 590.0, "regime": "TRENDING UP"}
        prompt = format_system_prompt(self._make_context(spy_context=spy))
        assert "[MARKET REGIME]" in prompt
        assert "TRENDING UP" in prompt

    def test_stats_section(self):
        from analytics.trade_coach import format_system_prompt
        stats = {
            "total_pnl": 1250.50, "win_rate": 62.5, "total_trades": 20,
            "expectancy": 62.53, "avg_win": 150.0, "avg_loss": -80.0,
        }
        prompt = format_system_prompt(self._make_context(trade_stats=stats))
        assert "[PERFORMANCE]" in prompt
        assert "1250.50" in prompt or "1,250.50" in prompt

    def test_no_stats_section_when_none(self):
        from analytics.trade_coach import format_system_prompt
        prompt = format_system_prompt(self._make_context(trade_stats=None))
        assert "[PERFORMANCE]" not in prompt

    def test_daily_plans_section(self):
        from analytics.trade_coach import format_system_prompt
        plans = [{"symbol": "NVDA", "support": 850.0, "entry": 855.0,
                  "stop": 845.0, "target_1": 870.0, "score": 82,
                  "score_label": "A", "pattern": "ma_bounce_20"}]
        prompt = format_system_prompt(self._make_context(daily_plans=plans))
        assert "[TODAY'S WATCHLIST PLANS]" in prompt
        assert "NVDA" in prompt

    def test_plans_capped_at_15(self):
        from analytics.trade_coach import format_system_prompt
        plans = [
            {"symbol": f"SYM{i}", "support": 100.0, "entry": 101.0,
             "stop": 99.0, "target_1": 105.0, "score": 50 + i,
             "score_label": "B", "pattern": "test"}
            for i in range(20)
        ]
        prompt = format_system_prompt(self._make_context(daily_plans=plans))
        # Should contain 15 symbols max (sorted by score desc, so SYM19 first)
        assert "SYM19" in prompt
        # SYM0 through SYM4 should NOT be present (lowest scores)
        assert "SYM0 " not in prompt  # trailing space to avoid matching SYM0 inside SYM0x

    def test_rules_always_present(self):
        from analytics.trade_coach import format_system_prompt
        prompt = format_system_prompt(self._make_context())
        assert "[RULES]" in prompt
        assert "probability" in prompt.lower() or "guarantee" in prompt.lower()


# ---------------------------------------------------------------------------
# TestAskCoach
# ---------------------------------------------------------------------------

class TestAskCoach:
    """Test Claude API streaming call."""

    def test_no_api_key_raises(self):
        from analytics.trade_coach import ask_coach
        with patch("analytics.trade_coach._resolve_api_key", return_value=""):
            with pytest.raises(ValueError, match="API key"):
                list(ask_coach("system", [{"role": "user", "content": "hi"}]))

    @patch("analytics.trade_coach._resolve_api_key", return_value="sk-test-key")
    @patch("analytics.trade_coach.CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    def test_streams_response(self, mock_key):
        from analytics.trade_coach import ask_coach

        # Mock the anthropic client and streaming
        mock_stream_ctx = MagicMock()
        mock_stream = MagicMock()
        mock_stream.text_stream = iter(["Hello", " trader", "!"])
        mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)

        with patch("anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.stream.return_value = mock_stream_ctx
            chunks = list(ask_coach("system prompt", [{"role": "user", "content": "test"}]))

        assert chunks == ["Hello", " trader", "!"]

    @patch("analytics.trade_coach._resolve_api_key", return_value="sk-test-key")
    @patch("analytics.trade_coach.CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    def test_passes_full_conversation(self, mock_key):
        from analytics.trade_coach import ask_coach

        mock_stream_ctx = MagicMock()
        mock_stream = MagicMock()
        mock_stream.text_stream = iter(["ok"])
        mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)

        messages = [
            {"role": "user", "content": "What's my P&L?"},
            {"role": "assistant", "content": "Your P&L is $500."},
            {"role": "user", "content": "What about win rate?"},
        ]

        with patch("anthropic.Anthropic") as MockClient:
            mock_client = MockClient.return_value
            mock_client.messages.stream.return_value = mock_stream_ctx
            list(ask_coach("system", messages))

        # Verify all messages were passed
        call_kwargs = mock_client.messages.stream.call_args[1]
        assert len(call_kwargs["messages"]) == 3
        # System prompt is now a list with cache_control for prompt caching
        assert isinstance(call_kwargs["system"], list)
        assert call_kwargs["system"][0]["text"] == "system"
        assert call_kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
