"""Tests for get_mtf_analysis() wrapper in intel_hub.py."""

import os
import sys
from unittest.mock import patch, MagicMock

import pandas as pd
import numpy as np
import pytest

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_daily_df(n=60, base_price=180.0):
    """Create a fake daily DataFrame with OHLCV."""
    dates = pd.date_range("2026-01-01", periods=n, freq="B")
    close = base_price + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame({
        "Open": close - np.random.rand(n),
        "High": close + np.random.rand(n) * 2,
        "Low": close - np.random.rand(n) * 2,
        "Close": close,
        "Volume": np.random.randint(1_000_000, 10_000_000, n),
    }, index=dates)
    return df


def _make_weekly_df(n=20, base_price=180.0):
    """Create a fake weekly DataFrame."""
    dates = pd.date_range("2025-07-01", periods=n, freq="W-FRI")
    close = base_price + np.cumsum(np.random.randn(n) * 1.0)
    df = pd.DataFrame({
        "Open": close - np.random.rand(n) * 2,
        "High": close + np.random.rand(n) * 4,
        "Low": close - np.random.rand(n) * 4,
        "Close": close,
        "Volume": np.random.randint(5_000_000, 50_000_000, n),
    }, index=dates)
    return df


def _make_mas(close_val):
    return {
        "sma20": close_val * 0.99,
        "sma50": close_val * 0.97,
        "sma100": close_val * 0.95,
        "sma200": close_val * 0.93,
        "ema20": close_val * 0.99,
        "ema50": close_val * 0.97,
    }


def _make_wmas(close_val):
    return {
        "wma10": close_val * 0.98,
        "wma20": close_val * 0.96,
        "wma50": close_val * 0.92,
    }


class TestGetMtfAnalysis:
    """Test the get_mtf_analysis() high-level wrapper."""

    @patch("analytics.intel_hub.get_weekly_bars")
    @patch("analytics.intel_hub.get_daily_bars")
    def test_returns_dict_with_required_keys(self, mock_daily, mock_weekly):
        """get_mtf_analysis returns dict with daily, weekly, alignment, confluence_score."""
        daily_df = _make_daily_df()
        weekly_df = _make_weekly_df()
        mock_daily.return_value = (daily_df, _make_mas(180.0))
        mock_weekly.return_value = (weekly_df, _make_wmas(180.0))

        from analytics.intel_hub import get_mtf_analysis
        result = get_mtf_analysis("SPY")

        assert "daily" in result
        assert "weekly" in result
        assert "alignment" in result
        assert "confluence_score" in result
        assert "mtf_text" in result

    @patch("analytics.intel_hub.get_weekly_bars")
    @patch("analytics.intel_hub.get_daily_bars")
    def test_daily_has_setup_fields(self, mock_daily, mock_weekly):
        """Daily dict should contain setup_type, score, edge, etc."""
        daily_df = _make_daily_df()
        weekly_df = _make_weekly_df()
        mock_daily.return_value = (daily_df, _make_mas(180.0))
        mock_weekly.return_value = (weekly_df, _make_wmas(180.0))

        from analytics.intel_hub import get_mtf_analysis
        result = get_mtf_analysis("AAPL")

        daily = result["daily"]
        assert "setup_type" in daily
        assert "score" in daily
        assert "edge" in daily

    @patch("analytics.intel_hub.get_weekly_bars")
    @patch("analytics.intel_hub.get_daily_bars")
    def test_handles_empty_daily(self, mock_daily, mock_weekly):
        """Should not crash when daily data is empty."""
        mock_daily.return_value = (pd.DataFrame(), {})
        mock_weekly.return_value = (_make_weekly_df(), _make_wmas(180.0))

        from analytics.intel_hub import get_mtf_analysis
        result = get_mtf_analysis("BAD")

        assert result["daily"]["setup_type"] == "NO_SETUP"
        assert result["confluence_score"] >= 0

    @patch("analytics.intel_hub.get_weekly_bars")
    @patch("analytics.intel_hub.get_daily_bars")
    def test_handles_empty_weekly(self, mock_daily, mock_weekly):
        """Should not crash when weekly data is empty."""
        mock_daily.return_value = (_make_daily_df(), _make_mas(180.0))
        mock_weekly.return_value = (pd.DataFrame(), {})

        from analytics.intel_hub import get_mtf_analysis
        result = get_mtf_analysis("BAD")

        assert result["weekly"]["setup_type"] == "NO_SETUP"
        assert result["confluence_score"] >= 0

    @patch("analytics.intel_hub.get_weekly_bars")
    @patch("analytics.intel_hub.get_daily_bars")
    def test_alignment_values(self, mock_daily, mock_weekly):
        """Alignment should be one of: bullish, bearish, conflict, mixed."""
        daily_df = _make_daily_df()
        weekly_df = _make_weekly_df()
        mock_daily.return_value = (daily_df, _make_mas(180.0))
        mock_weekly.return_value = (weekly_df, _make_wmas(180.0))

        from analytics.intel_hub import get_mtf_analysis
        result = get_mtf_analysis("SPY")

        assert result["alignment"] in ("bullish", "bearish", "conflict", "mixed")

    @patch("analytics.intel_hub.get_weekly_bars")
    @patch("analytics.intel_hub.get_daily_bars")
    def test_confluence_score_range(self, mock_daily, mock_weekly):
        """Confluence score should be between 0 and 10."""
        daily_df = _make_daily_df()
        weekly_df = _make_weekly_df()
        mock_daily.return_value = (daily_df, _make_mas(180.0))
        mock_weekly.return_value = (weekly_df, _make_wmas(180.0))

        from analytics.intel_hub import get_mtf_analysis
        result = get_mtf_analysis("SPY")

        assert 0 <= result["confluence_score"] <= 10

    @patch("analytics.intel_hub.get_weekly_bars")
    @patch("analytics.intel_hub.get_daily_bars")
    def test_mtf_text_is_string(self, mock_daily, mock_weekly):
        """mtf_text should be a non-empty string for AI prompt injection."""
        daily_df = _make_daily_df()
        weekly_df = _make_weekly_df()
        mock_daily.return_value = (daily_df, _make_mas(180.0))
        mock_weekly.return_value = (weekly_df, _make_wmas(180.0))

        from analytics.intel_hub import get_mtf_analysis
        result = get_mtf_analysis("SPY")

        assert isinstance(result["mtf_text"], str)
        assert len(result["mtf_text"]) > 50
