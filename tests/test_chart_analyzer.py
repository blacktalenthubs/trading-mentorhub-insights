"""Tests for analytics/chart_analyzer.py."""

import os
import sys
from unittest.mock import patch, MagicMock

import pandas as pd
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics.chart_analyzer import (
    TF_HIERARCHY,
    TF_PARAMS,
    assemble_analysis_context,
    build_analysis_prompt,
    compute_confluence_score,
    parse_trade_plan,
    get_cached_analysis,
    set_cached_analysis,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_bars(n=60, base=180.0):
    dates = pd.date_range("2026-01-01", periods=n, freq="h")
    close = base + np.cumsum(np.random.randn(n) * 0.3)
    return pd.DataFrame({
        "Open": close - np.random.rand(n) * 0.5,
        "High": close + np.random.rand(n),
        "Low": close - np.random.rand(n),
        "Close": close,
        "Volume": np.random.randint(100_000, 5_000_000, n),
    }, index=dates)


# ---------------------------------------------------------------------------
# TF_HIERARCHY tests
# ---------------------------------------------------------------------------

class TestTimeframeHierarchy:
    def test_all_timeframes_have_hierarchy(self):
        for tf in ["1m", "5m", "15m", "30m", "1H", "4H", "D", "W"]:
            assert tf in TF_HIERARCHY, f"Missing hierarchy for {tf}"
            assert len(TF_HIERARCHY[tf]) == 2, f"{tf} should have 2 higher TFs"

    def test_5m_checks_1h_and_daily(self):
        assert TF_HIERARCHY["5m"] == ["1H", "D"]

    def test_1h_checks_daily_and_weekly(self):
        assert TF_HIERARCHY["1H"] == ["D", "W"]

    def test_daily_checks_weekly_and_monthly(self):
        assert TF_HIERARCHY["D"] == ["W", "M"]


# ---------------------------------------------------------------------------
# TF_PARAMS tests
# ---------------------------------------------------------------------------

class TestTimeframeParams:
    def test_scalp_has_tight_stops(self):
        assert "0.1" in TF_PARAMS["1m"]["stop_range"]
        assert "minutes" in TF_PARAMS["1m"]["hold"]

    def test_swing_has_wide_stops(self):
        assert "1-3%" in TF_PARAMS["D"]["stop_range"]
        assert "days" in TF_PARAMS["D"]["hold"]

    def test_all_params_have_required_keys(self):
        for tf, params in TF_PARAMS.items():
            assert "style" in params
            assert "stop_range" in params
            assert "hold" in params
            assert "focus" in params


# ---------------------------------------------------------------------------
# assemble_analysis_context tests
# ---------------------------------------------------------------------------

class TestAssembleContext:
    @patch("analytics.chart_analyzer._fetch_bars", return_value=_make_bars())
    def test_returns_required_keys(self, mock_fetch):
        ctx = assemble_analysis_context("SPY", "1H")

        assert "symbol" in ctx
        assert "timeframe" in ctx
        assert "bars_df" in ctx
        assert "indicators" in ctx
        assert "higher_tfs" in ctx
        assert "tf_params" in ctx

    @patch("analytics.chart_analyzer._fetch_bars", return_value=_make_bars())
    def test_fetches_higher_tfs(self, mock_fetch):
        ctx = assemble_analysis_context("SPY", "5m")
        # 5m should fetch 1H and D as higher TFs
        assert len(ctx["higher_tfs"]) == 2
        assert ctx["higher_tfs"][0]["timeframe"] == "1H"
        assert ctx["higher_tfs"][1]["timeframe"] == "D"

    def test_uses_provided_bars(self):
        bars = [
            {"timestamp": "2026-04-07T10:00:00", "Open": 520.0, "High": 521.0,
             "Low": 519.0, "Close": 520.5, "Volume": 1000000},
        ]
        with patch("analytics.chart_analyzer._fetch_bars", return_value=_make_bars()):
            ctx = assemble_analysis_context("SPY", "1H", bars=bars)
        assert not ctx["bars_df"].empty


# ---------------------------------------------------------------------------
# build_analysis_prompt tests
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def test_includes_symbol_and_timeframe(self):
        ctx = {
            "symbol": "AAPL", "timeframe": "D", "bars_df": _make_bars(20),
            "indicators": {"sma20": 180.0, "rsi14": 55.0, "last_close": 182.0, "bar_count": 20},
            "higher_tfs": [], "mtf_analysis": {}, "spy_context": {},
            "sr_levels": [], "win_rates": {},
            "tf_params": TF_PARAMS["D"],
        }
        prompt = build_analysis_prompt(ctx)
        assert "AAPL" in prompt
        assert "swing" in prompt.lower()

    def test_includes_output_format(self):
        ctx = {
            "symbol": "SPY", "timeframe": "1H", "bars_df": _make_bars(10),
            "indicators": {"last_close": 520.0, "bar_count": 10},
            "higher_tfs": [], "mtf_analysis": {}, "spy_context": {},
            "sr_levels": [], "win_rates": {},
            "tf_params": TF_PARAMS["1H"],
        }
        prompt = build_analysis_prompt(ctx)
        assert "DIRECTION:" in prompt
        assert "ENTRY:" in prompt
        assert "STOP:" in prompt
        assert "TARGET_1:" in prompt
        assert "CONFIDENCE:" in prompt
        assert "CONFLUENCE_SCORE:" in prompt

    def test_adapts_to_scalp_timeframe(self):
        ctx = {
            "symbol": "SPY", "timeframe": "1m", "bars_df": _make_bars(10),
            "indicators": {"last_close": 520.0, "bar_count": 10},
            "higher_tfs": [], "mtf_analysis": {}, "spy_context": {},
            "sr_levels": [], "win_rates": {},
            "tf_params": TF_PARAMS["1m"],
        }
        prompt = build_analysis_prompt(ctx)
        assert "scalp" in prompt.lower()
        assert "0.1-0.3%" in prompt

    def test_adapts_to_weekly_timeframe(self):
        ctx = {
            "symbol": "SPY", "timeframe": "W", "bars_df": _make_bars(10),
            "indicators": {"last_close": 520.0, "bar_count": 10},
            "higher_tfs": [], "mtf_analysis": {}, "spy_context": {},
            "sr_levels": [], "win_rates": {},
            "tf_params": TF_PARAMS["W"],
        }
        prompt = build_analysis_prompt(ctx)
        assert "position" in prompt.lower()
        assert "3-8%" in prompt

    def test_includes_win_rates_when_sufficient(self):
        ctx = {
            "symbol": "NVDA", "timeframe": "1H", "bars_df": _make_bars(10),
            "indicators": {"last_close": 140.0, "bar_count": 10},
            "higher_tfs": [], "mtf_analysis": {}, "spy_context": {},
            "sr_levels": [],
            "win_rates": {"win_rate": 73.0, "wins": 22, "losses": 8, "total": 30},
            "tf_params": TF_PARAMS["1H"],
        }
        prompt = build_analysis_prompt(ctx)
        assert "73" in prompt
        assert "22W" in prompt or "22" in prompt


# ---------------------------------------------------------------------------
# parse_trade_plan tests
# ---------------------------------------------------------------------------

class TestParseTradePlan:
    def test_parses_complete_response(self):
        ai_text = """DIRECTION: LONG
ENTRY: $521.50
STOP: $519.80
TARGET_1: $524.00
TARGET_2: $527.00
RR_RATIO: 1.47
CONFIDENCE: HIGH
CONFLUENCE_SCORE: 8
TIMEFRAME_FIT: 2-4 hours
KEY_LEVELS: $519.80 (50EMA support), $524.00 (prior day high), $527.00 (weekly resistance)

REASONING:
SPY hourly shows a clean pullback to the rising 50EMA at $519.80 with RSI at 45. Volume is picking up.

HIGHER_TF_SUMMARY:
Daily uptrend above all MAs, RSI 58. Weekly bullish, above 10/20 WMA."""

        plan = parse_trade_plan(ai_text)
        assert plan["direction"] == "LONG"
        assert plan["entry"] == 521.50
        assert plan["stop"] == 519.80
        assert plan["target_1"] == 524.00
        assert plan["target_2"] == 527.00
        assert plan["rr_ratio"] == 1.47
        assert plan["confidence"] == "HIGH"
        assert plan["confluence_score"] == 8
        assert "2-4 hours" in plan["timeframe_fit"]
        assert len(plan["key_levels"]) == 3
        assert "50EMA" in plan["reasoning"]
        assert "Weekly" in plan["higher_tf_summary"]

    def test_parses_no_trade(self):
        ai_text = """DIRECTION: NO_TRADE
ENTRY: N/A
STOP: N/A
TARGET_1: N/A
TARGET_2: N/A
RR_RATIO: 0
CONFIDENCE: LOW
CONFLUENCE_SCORE: 2
TIMEFRAME_FIT: N/A
KEY_LEVELS: $155.00 (range low), $162.00 (range high)

REASONING:
AMD is consolidating in a tight range. No clear edge. Wait for breakout above $162 or breakdown below $155.

HIGHER_TF_SUMMARY:
Daily mixed, weekly neutral. No clear direction on any timeframe."""

        plan = parse_trade_plan(ai_text)
        assert plan["direction"] == "NO_TRADE"
        assert plan["confidence"] == "LOW"
        assert plan["confluence_score"] == 2
        assert "consolidating" in plan["reasoning"]

    def test_handles_empty_text(self):
        plan = parse_trade_plan("")
        assert plan["direction"] is None
        assert plan["entry"] is None

    def test_handles_malformed_text(self):
        plan = parse_trade_plan("This is just random text with no structure")
        assert plan["direction"] is None


# ---------------------------------------------------------------------------
# compute_confluence_score tests
# ---------------------------------------------------------------------------

class TestConfluenceScore:
    def test_all_bullish_scores_high(self):
        score, explanation = compute_confluence_score(
            user_tf_indicators={"rsi14": 60},
            higher_tf_data=[
                {"indicators": {"rsi14": 65}},
                {"indicators": {"rsi14": 58}},
            ],
            mtf_analysis={"alignment": "bullish", "daily": {"setup_type": "TREND_CONTINUATION"}},
        )
        assert score >= 8

    def test_conflicting_scores_low(self):
        score, explanation = compute_confluence_score(
            user_tf_indicators={"rsi14": 60},
            higher_tf_data=[
                {"indicators": {"rsi14": 35}},
                {"indicators": {"rsi14": 40}},
            ],
            mtf_analysis={"alignment": "conflict", "daily": {"setup_type": "BREAKDOWN"}},
        )
        assert score <= 4

    def test_score_always_0_to_10(self):
        for alignment in ["bullish", "bearish", "conflict", "mixed"]:
            score, _ = compute_confluence_score(
                user_tf_indicators={},
                higher_tf_data=[],
                mtf_analysis={"alignment": alignment, "daily": {}},
            )
            assert 0 <= score <= 10


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------

class TestCache:
    def test_set_and_get(self):
        set_cached_analysis(1, "SPY", "1H", {"test": True})
        result = get_cached_analysis(1, "SPY", "1H")
        assert result == {"test": True}

    def test_miss_on_different_key(self):
        set_cached_analysis(1, "SPY", "1H", {"test": True})
        result = get_cached_analysis(1, "AAPL", "1H")
        assert result is None

    def test_case_insensitive_symbol(self):
        set_cached_analysis(1, "spy", "1H", {"test": True})
        result = get_cached_analysis(1, "SPY", "1H")
        assert result == {"test": True}
