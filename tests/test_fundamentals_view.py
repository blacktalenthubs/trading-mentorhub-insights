"""Tests for analytics/fundamentals_view — AI short/long-term view generation.

Mocks the Anthropic client + the key resolver. Verifies marker parsing, the
disabled/no-key short-circuit, and graceful empty return on API failure.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import json

from analytics.fundamentals_fetcher import SymbolFundamentalsData
from analytics.fundamentals_view import _parse_views, generate_views, generate_brief


def _fund():
    return SymbolFundamentalsData(
        symbol="NVDA",
        company_name="Nvidia Corp",
        description="Designs GPUs.",
        sector="Technology",
        industry="Semiconductors",
        trailing_eps=2.0,
        forward_eps=3.0,
        eps_growth_pct=50.0,
        pe_ratio=45.0,
        rec_strong_buy=30,
        rec_buy=10,
        rec_hold=5,
        rec_sell=1,
        rec_strong_sell=0,
        consensus="Buy",
    )


class TestParseViews:
    def test_splits_markers(self):
        text = (
            "SHORT_TERM: Momentum is strong with bullish analyst tilt.\n"
            "LONG_TERM: Durable AI demand supports multi-quarter growth."
        )
        short, long = _parse_views(text)
        assert short.startswith("Momentum is strong")
        assert long.startswith("Durable AI demand")

    def test_multiline_body(self):
        text = "SHORT_TERM: Line one.\nLine two.\nLONG_TERM: Long view."
        short, long = _parse_views(text)
        assert "Line one." in short and "Line two." in short
        assert long == "Long view."


class TestGenerateViews:
    def test_no_key_returns_empty(self):
        with patch("analytics.fundamentals_view._resolve_api_key", return_value=""):
            assert generate_views(_fund()) == ("", "")

    def test_success(self):
        resp = MagicMock()
        resp.content = [MagicMock(text="SHORT_TERM: Bullish near term.\nLONG_TERM: Strong franchise.")]
        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value.messages.create.return_value = resp

        with (
            patch("analytics.fundamentals_view._resolve_api_key", return_value="k"),
            patch.dict(sys.modules, {"anthropic": mock_anthropic}),
        ):
            short, long = generate_views(_fund(), score=70)
        assert short == "Bullish near term."
        assert long == "Strong franchise."
        mock_anthropic.Anthropic.return_value.messages.create.assert_called_once()

    def test_api_error_returns_empty(self):
        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value.messages.create.side_effect = Exception("timeout")
        with (
            patch("analytics.fundamentals_view._resolve_api_key", return_value="k"),
            patch.dict(sys.modules, {"anthropic": mock_anthropic}),
        ):
            assert generate_views(_fund()) == ("", "")


def _brief_resp(text: str) -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    m = MagicMock()
    m.Anthropic.return_value.messages.create.return_value = resp
    return m


class TestGenerateBrief:
    _BRIEF = {
        "summary": "Strong AI compute play.",
        "business": "Designs GPUs for AI.",
        "growth": "EPS +50%.",
        "valuation": "P/E 45 vs high growth.",
        "analyst": "Buy consensus.",
        "bull_case": "AI demand.",
        "risks": "Competition.",
        "short_term": "Momentum strong.",
        "long_term": "Durable franchise.",
    }

    def test_no_key_returns_none(self):
        with patch("analytics.fundamentals_view._resolve_api_key", return_value=""):
            assert generate_brief(_fund()) is None

    def test_parses_json_object(self):
        mock_anthropic = _brief_resp(json.dumps(self._BRIEF))
        with (
            patch("analytics.fundamentals_view._resolve_api_key", return_value="k"),
            patch.dict(sys.modules, {"anthropic": mock_anthropic}),
        ):
            brief = generate_brief(_fund())
        assert brief is not None
        assert brief["summary"] == "Strong AI compute play."
        assert brief["short_term"] == "Momentum strong."
        assert brief["model"]  # model tag attached

    def test_strips_code_fence(self):
        fenced = "```json\n" + json.dumps(self._BRIEF) + "\n```"
        mock_anthropic = _brief_resp(fenced)
        with (
            patch("analytics.fundamentals_view._resolve_api_key", return_value="k"),
            patch.dict(sys.modules, {"anthropic": mock_anthropic}),
        ):
            brief = generate_brief(_fund())
        assert brief is not None and brief["business"] == "Designs GPUs for AI."

    def test_bad_json_returns_none(self):
        mock_anthropic = _brief_resp("not json at all")
        with (
            patch("analytics.fundamentals_view._resolve_api_key", return_value="k"),
            patch.dict(sys.modules, {"anthropic": mock_anthropic}),
        ):
            assert generate_brief(_fund()) is None

    def test_api_error_returns_none(self):
        mock_anthropic = MagicMock()
        mock_anthropic.Anthropic.return_value.messages.create.side_effect = Exception("timeout")
        with (
            patch("analytics.fundamentals_view._resolve_api_key", return_value="k"),
            patch.dict(sys.modules, {"anthropic": mock_anthropic}),
        ):
            assert generate_brief(_fund()) is None
