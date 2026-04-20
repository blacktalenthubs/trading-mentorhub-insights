"""Smoke tests for analytics/ai_best_setups.py."""

from __future__ import annotations

import json

import pytest

from analytics.ai_best_setups import (
    MAX_PROXIMITY_PCT,
    _enrich_picks,
    _parse_ai_response,
    _validate_pick,
)


class TestValidatePick:
    def test_long_within_proximity_passes(self):
        pick = {"direction": "LONG", "entry": 100.0}
        ok, reason = _validate_pick(pick, current_price=101.0, symbol="AAPL", timeframe="day")
        assert ok
        assert reason is None

    def test_entry_outside_proximity_rejected(self):
        pick = {"direction": "LONG", "entry": 100.0}
        ok, reason = _validate_pick(pick, current_price=105.0, symbol="AAPL", timeframe="day")
        assert not ok
        assert "from price" in reason

    def test_short_on_non_spy_rejected(self):
        pick = {"direction": "SHORT", "entry": 100.0}
        ok, reason = _validate_pick(pick, current_price=101.0, symbol="AAPL", timeframe="day")
        assert not ok
        assert "SPY" in reason

    def test_short_on_spy_passes(self):
        pick = {"direction": "SHORT", "entry": 500.0}
        ok, reason = _validate_pick(pick, current_price=501.0, symbol="SPY", timeframe="swing")
        assert ok

    def test_unknown_direction_rejected(self):
        pick = {"direction": "HOLD", "entry": 100.0}
        ok, reason = _validate_pick(pick, current_price=100.0, symbol="AAPL", timeframe="day")
        assert not ok
        assert "direction" in reason

    def test_bad_timeframe_rejected(self):
        pick = {"direction": "LONG", "entry": 100.0}
        ok, reason = _validate_pick(pick, current_price=100.0, symbol="AAPL", timeframe="monthly")
        assert not ok
        assert "timeframe" in reason

    def test_missing_entry_rejected(self):
        pick = {"direction": "LONG"}
        ok, reason = _validate_pick(pick, current_price=100.0, symbol="AAPL", timeframe="day")
        assert not ok

    def test_proximity_constant_is_2pct(self):
        assert MAX_PROXIMITY_PCT == 2.0


class TestParseAiResponse:
    def test_parses_two_arrays(self):
        text = json.dumps({
            "day_trade_picks": [{"symbol": "AAPL", "direction": "LONG", "entry": 180}],
            "swing_trade_picks": [{"symbol": "NVDA", "direction": "LONG", "entry": 900}],
        })
        day, swing = _parse_ai_response(text)
        assert len(day) == 1 and day[0]["symbol"] == "AAPL"
        assert len(swing) == 1 and swing[0]["symbol"] == "NVDA"

    def test_empty_arrays_default(self):
        day, swing = _parse_ai_response("{}")
        assert day == [] and swing == []

    def test_strips_code_fences(self):
        text = '```json\n{"day_trade_picks": [], "swing_trade_picks": []}\n```'
        day, swing = _parse_ai_response(text)
        assert day == [] and swing == []

    def test_malformed_returns_empty(self):
        day, swing = _parse_ai_response("not json at all")
        assert day == [] and swing == []


class TestEnrichPicks:
    def test_validates_and_sorts_by_conviction_then_distance(self):
        raw = [
            {"symbol": "AAPL", "direction": "LONG", "entry": 100.0, "conviction": "LOW"},
            {"symbol": "NVDA", "direction": "LONG", "entry": 200.0, "conviction": "HIGH"},
            {"symbol": "TSLA", "direction": "LONG", "entry": 300.0, "conviction": "HIGH"},
        ]
        prices = {"AAPL": 100.5, "NVDA": 202.0, "TSLA": 300.5}
        failed: list = []
        out = _enrich_picks(raw, "day", prices, failed)
        assert [p["symbol"] for p in out] == ["TSLA", "NVDA", "AAPL"]
        assert failed == []

    def test_rejects_far_entry(self):
        raw = [
            {"symbol": "AAPL", "direction": "LONG", "entry": 100.0, "conviction": "HIGH"},
        ]
        prices = {"AAPL": 110.0}
        failed: list = []
        out = _enrich_picks(raw, "swing", prices, failed)
        assert out == []
        assert len(failed) == 1
        assert "swing" in failed[0]["reason"]

    def test_rejects_short_on_non_spy(self):
        raw = [{"symbol": "AAPL", "direction": "SHORT", "entry": 100.0}]
        prices = {"AAPL": 100.0}
        failed: list = []
        out = _enrich_picks(raw, "day", prices, failed)
        assert out == []
        assert "SPY" in failed[0]["reason"]

    def test_enriches_with_distance_pct(self):
        raw = [{"symbol": "AAPL", "direction": "LONG", "entry": 100.0, "conviction": "HIGH"}]
        prices = {"AAPL": 101.0}
        failed: list = []
        out = _enrich_picks(raw, "day", prices, failed)
        assert out[0]["distance_to_entry_pct"] == pytest.approx(0.99, abs=0.01)
        assert out[0]["timeframe"] == "day"
