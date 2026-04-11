"""Tests for AI CoPilot Education — pattern library, education prompt, parsing."""

import pytest


# ── Pattern Library Tests ───────────────────────────────────────────

class TestPatternLibrary:
    """Validate pattern library content and structure."""

    @pytest.fixture
    def library(self):
        from analytics.chart_analyzer import PATTERN_LIBRARY
        return PATTERN_LIBRARY

    def test_has_14_patterns(self, library):
        assert len(library) >= 14, f"Expected 14+ patterns, got {len(library)}"

    def test_every_pattern_has_name(self, library):
        for key, p in library.items():
            assert "name" in p and p["name"], f"{key} missing name"

    def test_every_pattern_has_category(self, library):
        valid_categories = {"Support", "Resistance", "Breakout", "Reversal", "Momentum"}
        for key, p in library.items():
            assert p.get("category") in valid_categories, f"{key} has invalid category: {p.get('category')}"

    def test_every_pattern_has_difficulty(self, library):
        valid_levels = {"Beginner", "Intermediate", "Advanced"}
        for key, p in library.items():
            assert p.get("difficulty") in valid_levels, f"{key} has invalid difficulty: {p.get('difficulty')}"

    def test_every_pattern_has_description(self, library):
        for key, p in library.items():
            assert "description" in p and len(p["description"]) > 10, f"{key} missing/short description"

    def test_has_support_patterns(self, library):
        support = [k for k, v in library.items() if v["category"] == "Support"]
        assert len(support) >= 4, f"Need 4+ support patterns, got {len(support)}"

    def test_has_resistance_patterns(self, library):
        resistance = [k for k, v in library.items() if v["category"] == "Resistance"]
        assert len(resistance) >= 2, f"Need 2+ resistance patterns, got {len(resistance)}"

    def test_has_beginner_patterns(self, library):
        beginner = [k for k, v in library.items() if v["difficulty"] == "Beginner"]
        assert len(beginner) >= 4, f"Need 4+ beginner patterns, got {len(beginner)}"

    def test_has_advanced_patterns(self, library):
        advanced = [k for k, v in library.items() if v["difficulty"] == "Advanced"]
        assert len(advanced) >= 2, f"Need 2+ advanced patterns, got {len(advanced)}"


# ── Education Prompt Tests ───────────────────────────────────────────

class TestEducationPrompt:
    """Validate education prompt generation."""

    def test_prompt_includes_setup_type(self):
        from analytics.chart_analyzer import build_education_prompt
        prompt = build_education_prompt("PDL Bounce", "ETH-USD", 2230.0, 2220.0, 2246.0)
        assert "PDL Bounce" in prompt
        assert "ETH-USD" in prompt

    def test_prompt_includes_prices(self):
        from analytics.chart_analyzer import build_education_prompt
        prompt = build_education_prompt("VWAP Hold", "SPY", 673.5, 671.8, 677.0)
        assert "673" in prompt  # entry
        assert "671" in prompt  # stop
        assert "677" in prompt  # target

    def test_prompt_includes_all_sections(self):
        from analytics.chart_analyzer import build_education_prompt
        prompt = build_education_prompt("MA Bounce", "AAPL", 260.0, 258.0, 265.0)
        assert "WHAT IS IT" in prompt
        assert "WHY IT WORKS" in prompt
        assert "HOW TO CONFIRM" in prompt
        assert "RISK MANAGEMENT" in prompt

    def test_prompt_handles_zero_prices(self):
        from analytics.chart_analyzer import build_education_prompt
        prompt = build_education_prompt("PDL Bounce", "ETH-USD", 0, 0, 0)
        assert isinstance(prompt, str)
        assert len(prompt) > 50

    def test_prompt_is_concise(self):
        from analytics.chart_analyzer import build_education_prompt
        prompt = build_education_prompt("VWAP Hold", "BTC-USD", 72000, 71500, 73000)
        assert "150 words" in prompt or "simple" in prompt.lower()


# ── Education Response Parsing Tests ─────────────────────────────────

class TestEducationParsing:
    """Validate parsing of AI education responses."""

    def test_parse_full_response(self):
        from analytics.chart_analyzer import parse_education_response
        text = """WHAT IS IT: Price tested yesterday's low at $2230 and held above it. Buyers defended this level.

WHY IT WORKS:
• Institutional traders place orders at PDL
• Algorithms buy at yesterday's low
• Stop losses cluster below PDL — when it holds, shorts cover

HOW TO CONFIRM:
✓ Volume increases at the level
✓ 2-3 bars close above PDL
✓ RSI turns up from oversold
✗ Price closes below PDL — setup failed

RISK MANAGEMENT:
Entry: $2230 (PDL level)
Stop: $2220 (below session low)
Target: $2246 (VWAP)
R:R: 1:1.6"""

        result = parse_education_response(text)
        assert result["what"] is not None
        assert "yesterday's low" in result["what"]
        assert result["why"] is not None
        assert len(result["confirm_items"]) >= 3
        assert result["invalidation"] is not None
        assert "below PDL" in result["invalidation"]
        assert result["risk"] is not None

    def test_parse_missing_section(self):
        from analytics.chart_analyzer import parse_education_response
        text = """WHAT IS IT: Some explanation.

HOW TO CONFIRM:
✓ Check volume
✗ If price breaks"""

        result = parse_education_response(text)
        assert result["what"] is not None
        assert result["why"] is None  # missing
        assert result["confirm_items"] is not None

    def test_parse_empty_string(self):
        from analytics.chart_analyzer import parse_education_response
        result = parse_education_response("")
        assert result["what"] is None
        assert result["why"] is None
