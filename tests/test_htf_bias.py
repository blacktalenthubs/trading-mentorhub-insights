"""Phase 2 (2026-04-23) — higher-timeframe bias computation + gating helpers.

The module lives at analytics/htf_bias.py and is a pure-Python port of
`analytics.ai_day_scanner._compute_htf_bias`. monitor.py calls these after
evaluate_rules() to (a) drop counter-trend LONG/SHORT entries and (b) stamp
`_confluence_score` on each surviving signal so the Telegram 🟢/🟡 emoji
lights up.
"""
from __future__ import annotations

import pandas as pd

from analytics.htf_bias import (
    BEAR,
    BULL,
    NEUTRAL,
    HTFBias,
    _compute_bias_from_bars,
    compute_htf_bias,
    confluence_score,
    should_gate_long,
    should_gate_short,
)


def _bars_bullish():
    # 5+ bars, rising highs + higher lows + close above EMA-20.
    return pd.DataFrame([
        {"Open": 100, "High": 101, "Low": 99.5, "Close": 100.5, "Volume": 1000},
        {"Open": 100.5, "High": 102, "Low": 100.0, "Close": 101.8, "Volume": 1100},
        {"Open": 101.8, "High": 103, "Low": 101.2, "Close": 102.8, "Volume": 1200},
        {"Open": 102.8, "High": 104, "Low": 102.3, "Close": 103.5, "Volume": 1300},
        {"Open": 103.5, "High": 105, "Low": 103.0, "Close": 104.5, "Volume": 1400},
        {"Open": 104.5, "High": 106, "Low": 104.0, "Close": 105.5, "Volume": 1500},
    ])


def _bars_bearish():
    return pd.DataFrame([
        {"Open": 100, "High": 100.5, "Low": 99, "Close": 99.5, "Volume": 1000},
        {"Open": 99.5, "High": 100, "Low": 98.5, "Close": 98.8, "Volume": 1100},
        {"Open": 98.8, "High": 99.2, "Low": 97.8, "Close": 98.0, "Volume": 1200},
        {"Open": 98.0, "High": 98.5, "Low": 97.0, "Close": 97.2, "Volume": 1300},
        {"Open": 97.2, "High": 97.5, "Low": 96.5, "Close": 96.8, "Volume": 1400},
        {"Open": 96.8, "High": 97.0, "Low": 96.0, "Close": 96.3, "Volume": 1500},
    ])


def _bars_flat():
    return pd.DataFrame([
        {"Open": 100, "High": 100.5, "Low": 99.5, "Close": 100.0, "Volume": 1000},
        {"Open": 100, "High": 100.4, "Low": 99.6, "Close": 100.1, "Volume": 1000},
        {"Open": 100.1, "High": 100.5, "Low": 99.7, "Close": 100.0, "Volume": 1000},
        {"Open": 100, "High": 100.3, "Low": 99.7, "Close": 99.9, "Volume": 1000},
        {"Open": 99.9, "High": 100.2, "Low": 99.6, "Close": 100.0, "Volume": 1000},
        {"Open": 100, "High": 100.3, "Low": 99.7, "Close": 100.0, "Volume": 1000},
    ])


class TestComputeBiasFromBars:
    def test_bullish_bars_return_bull(self):
        assert _compute_bias_from_bars(_bars_bullish()) == BULL

    def test_bearish_bars_return_bear(self):
        assert _compute_bias_from_bars(_bars_bearish()) == BEAR

    def test_flat_bars_return_neutral(self):
        assert _compute_bias_from_bars(_bars_flat()) == NEUTRAL

    def test_fewer_than_five_bars_return_neutral(self):
        """Fail-open: too little history shouldn't gate trades."""
        bars = _bars_bullish().head(4)
        assert _compute_bias_from_bars(bars) == NEUTRAL

    def test_empty_bars_return_neutral(self):
        assert _compute_bias_from_bars(pd.DataFrame()) == NEUTRAL

    def test_none_bars_return_neutral(self):
        assert _compute_bias_from_bars(None) == NEUTRAL


class TestComputeHTFBias:
    def test_both_timeframes_bull(self):
        bias = compute_htf_bias(_bars_bullish(), _bars_bullish())
        assert bias.htf_1h == BULL
        assert bias.htf_4h == BULL
        assert bias.aligned_bull is True
        assert bias.aligned_bear is False

    def test_both_timeframes_bear(self):
        bias = compute_htf_bias(_bars_bearish(), _bars_bearish())
        assert bias.aligned_bear is True

    def test_mixed_timeframes(self):
        bias = compute_htf_bias(_bars_bullish(), _bars_bearish())
        assert bias.htf_1h == BULL
        assert bias.htf_4h == BEAR
        assert bias.aligned_bull is False
        assert bias.aligned_bear is False

    def test_missing_bars_default_neutral(self):
        bias = compute_htf_bias(None, None)
        assert bias.htf_1h == NEUTRAL
        assert bias.htf_4h == NEUTRAL


class TestShouldGateLong:
    def test_blocks_long_in_4h_bear_with_neutral_1h(self):
        bias = HTFBias(htf_1h=NEUTRAL, htf_4h=BEAR)
        assert should_gate_long(bias) is True

    def test_blocks_long_in_4h_bear_with_bear_1h(self):
        bias = HTFBias(htf_1h=BEAR, htf_4h=BEAR)
        assert should_gate_long(bias) is True

    def test_allows_long_when_4h_bear_but_1h_bull(self):
        """Tactical bottom inside a larger downtrend — allow."""
        bias = HTFBias(htf_1h=BULL, htf_4h=BEAR)
        assert should_gate_long(bias) is False

    def test_allows_long_in_aligned_bull(self):
        bias = HTFBias(htf_1h=BULL, htf_4h=BULL)
        assert should_gate_long(bias) is False

    def test_allows_long_in_neutral(self):
        bias = HTFBias(htf_1h=NEUTRAL, htf_4h=NEUTRAL)
        assert should_gate_long(bias) is False


class TestShouldGateShort:
    def test_blocks_short_in_4h_bull_with_neutral_1h(self):
        bias = HTFBias(htf_1h=NEUTRAL, htf_4h=BULL)
        assert should_gate_short(bias) is True

    def test_allows_short_when_4h_bull_but_1h_bear(self):
        bias = HTFBias(htf_1h=BEAR, htf_4h=BULL)
        assert should_gate_short(bias) is False

    def test_allows_short_in_aligned_bear(self):
        bias = HTFBias(htf_1h=BEAR, htf_4h=BEAR)
        assert should_gate_short(bias) is False


class TestConfluenceScore:
    def test_long_aligned_bull_scores_three(self):
        bias = HTFBias(htf_1h=BULL, htf_4h=BULL)
        assert confluence_score("BUY", bias) == 3

    def test_long_only_1h_agrees_scores_two(self):
        bias = HTFBias(htf_1h=BULL, htf_4h=NEUTRAL)
        assert confluence_score("BUY", bias) == 2

    def test_long_no_htf_agreement_scores_one(self):
        bias = HTFBias(htf_1h=NEUTRAL, htf_4h=NEUTRAL)
        assert confluence_score("BUY", bias) == 1

    def test_long_bear_htf_scores_one_baseline(self):
        """Even if HTF is bearish, the rule still fired → base 1 pt."""
        bias = HTFBias(htf_1h=BEAR, htf_4h=BEAR)
        assert confluence_score("BUY", bias) == 1

    def test_short_aligned_bear_scores_three(self):
        bias = HTFBias(htf_1h=BEAR, htf_4h=BEAR)
        assert confluence_score("SHORT", bias) == 3

    def test_resistance_gets_base_one(self):
        """RESISTANCE/NOTICE don't map to directional agreement."""
        bias = HTFBias(htf_1h=BULL, htf_4h=BULL)
        assert confluence_score("RESISTANCE", bias) == 1

    def test_direction_case_insensitive(self):
        bias = HTFBias(htf_1h=BULL, htf_4h=BULL)
        assert confluence_score("buy", bias) == 3
        assert confluence_score("long", bias) == 3
