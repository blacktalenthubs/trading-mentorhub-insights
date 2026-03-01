"""Unit tests for pre-market brief — is_premarket, fetch_premarket_bars, compute_premarket_brief."""

from datetime import datetime
from unittest.mock import patch, MagicMock

import pandas as pd
import pytz
import pytest

from analytics.intraday_data import compute_premarket_brief, fetch_premarket_bars
from analytics.market_hours import is_premarket

ET = pytz.timezone("US/Eastern")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_pm_bars(rows: list[dict], date: str = "2025-06-02") -> pd.DataFrame:
    """Create synthetic pre-market bars with proper datetime index."""
    records = []
    for r in rows:
        ts = pd.Timestamp(f"{date} {r['time']}")
        records.append({
            "Open": r.get("open", 100),
            "High": r.get("high", 101),
            "Low": r.get("low", 99),
            "Close": r.get("close", 100.5),
        })
    df = pd.DataFrame(records, index=pd.DatetimeIndex([
        pd.Timestamp(f"{date} {r['time']}") for r in rows
    ]))
    return df


def _make_prior_day(
    close=100.0, high=102.0, low=98.0, open_=99.5,
    ma20=100.0, ma50=97.0, parent_range=4.0,
) -> dict:
    """Create a synthetic prior_day dict matching fetch_prior_day output."""
    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1_000_000,
        "ma20": ma20,
        "ma50": ma50,
        "pattern": "inside",
        "direction": "bullish",
        "is_inside": False,
        "parent_high": high + 1,
        "parent_low": low - 1,
        "parent_range": parent_range,
        "prior_week_high": high + 2,
        "prior_week_low": low - 2,
    }


# ===== is_premarket =====


class TestIsPremarket:
    @patch("analytics.market_hours.datetime")
    def test_true_at_7am_weekday(self, mock_dt):
        mock_dt.now.return_value = datetime(2025, 6, 2, 7, 0, tzinfo=ET)  # Monday 7:00 AM
        assert is_premarket() is True

    @patch("analytics.market_hours.datetime")
    def test_true_at_4am_weekday(self, mock_dt):
        mock_dt.now.return_value = datetime(2025, 6, 2, 4, 0, tzinfo=ET)  # Monday 4:00 AM
        assert is_premarket() is True

    @patch("analytics.market_hours.datetime")
    def test_false_at_930am(self, mock_dt):
        mock_dt.now.return_value = datetime(2025, 6, 2, 9, 30, tzinfo=ET)  # Monday 9:30 AM
        assert is_premarket() is False

    @patch("analytics.market_hours.datetime")
    def test_false_at_3am(self, mock_dt):
        mock_dt.now.return_value = datetime(2025, 6, 2, 3, 59, tzinfo=ET)  # Monday 3:59 AM
        assert is_premarket() is False

    @patch("analytics.market_hours.datetime")
    def test_false_on_saturday(self, mock_dt):
        mock_dt.now.return_value = datetime(2025, 6, 7, 7, 0, tzinfo=ET)  # Saturday
        assert is_premarket() is False


# ===== compute_premarket_brief — gap scenarios =====


class TestComputePremarketBriefGapUp:
    def test_gap_up(self):
        pm_bars = _make_pm_bars([
            {"time": "04:00", "open": 101.5, "high": 102.0, "low": 101.0, "close": 101.8},
            {"time": "04:05", "open": 101.8, "high": 102.5, "low": 101.5, "close": 102.2},
        ])
        prior = _make_prior_day(close=100.0, high=102.0, low=98.0)
        result = compute_premarket_brief("AAPL", pm_bars, prior)

        assert result is not None
        assert result["gap_type"] == "gap_up"
        assert result["gap_pct"] == 1.5  # (101.5 - 100) / 100
        assert "GAP UP +1.5%" in result["flags"]
        assert result["priority_score"] >= 30  # gap > 1%


class TestComputePremarketBriefGapDown:
    def test_gap_down(self):
        pm_bars = _make_pm_bars([
            {"time": "04:00", "open": 98.0, "high": 98.5, "low": 97.5, "close": 97.8},
            {"time": "04:05", "open": 97.8, "high": 98.2, "low": 97.0, "close": 97.2},
        ])
        prior = _make_prior_day(close=100.0, high=102.0, low=98.0)
        result = compute_premarket_brief("AAPL", pm_bars, prior)

        assert result is not None
        assert result["gap_type"] == "gap_down"
        assert result["gap_pct"] == -2.0
        assert "GAP DOWN -2.0%" in result["flags"]
        assert result["below_prior_low"] is True
        assert "TESTING PRIOR LOW" in result["flags"]


class TestComputePremarketBriefFlat:
    def test_flat(self):
        pm_bars = _make_pm_bars([
            {"time": "04:00", "open": 100.1, "high": 100.3, "low": 100.0, "close": 100.2},
            {"time": "04:05", "open": 100.2, "high": 100.3, "low": 100.0, "close": 100.1},
        ])
        prior = _make_prior_day(close=100.0, high=102.0, low=98.0, ma20=95.0, ma50=90.0)
        result = compute_premarket_brief("AAPL", pm_bars, prior)

        assert result is not None
        assert result["gap_type"] == "flat"
        assert result["above_prior_high"] is False
        assert result["below_prior_low"] is False
        assert result["near_ma20"] is False
        assert result["priority_label"] == "LOW"


# ===== Priority scoring =====


class TestPriorityScoreHigh:
    def test_large_gap_plus_level_test_equals_high(self):
        # Gap > 1% (+30) + testing prior high (+20) + non-flat gap (+5) = 55 => HIGH
        pm_bars = _make_pm_bars([
            {"time": "04:00", "open": 101.5, "high": 103.0, "low": 101.0, "close": 102.5},
        ])
        prior = _make_prior_day(close=100.0, high=102.0, low=98.0)
        result = compute_premarket_brief("AAPL", pm_bars, prior)

        assert result is not None
        assert result["priority_score"] >= 50
        assert result["priority_label"] == "HIGH"


class TestPriorityScoreLow:
    def test_flat_open_no_proximity(self):
        pm_bars = _make_pm_bars([
            {"time": "04:00", "open": 100.1, "high": 100.2, "low": 100.0, "close": 100.1},
        ])
        prior = _make_prior_day(close=100.0, high=105.0, low=95.0, ma20=110.0, ma50=90.0)
        result = compute_premarket_brief("AAPL", pm_bars, prior)

        assert result is not None
        assert result["priority_score"] < 25
        assert result["priority_label"] == "LOW"


# ===== Flag tests =====


class TestNearMA20Flag:
    def test_pm_last_within_half_pct_of_ma20(self):
        # MA20 = 100.0, PM last = 100.4 → 0.4% away, within 0.5%
        pm_bars = _make_pm_bars([
            {"time": "04:00", "open": 100.5, "high": 101.0, "low": 100.0, "close": 100.4},
        ])
        prior = _make_prior_day(close=100.0, high=105.0, low=95.0, ma20=100.0)
        result = compute_premarket_brief("AAPL", pm_bars, prior)

        assert result is not None
        assert result["near_ma20"] is True
        assert "NEAR 20MA" in result["flags"]


class TestAbovePriorHighFlag:
    def test_pm_high_exceeds_prior_high(self):
        pm_bars = _make_pm_bars([
            {"time": "04:00", "open": 101.5, "high": 103.0, "low": 101.0, "close": 102.5},
        ])
        prior = _make_prior_day(close=100.0, high=102.0, low=98.0)
        result = compute_premarket_brief("AAPL", pm_bars, prior)

        assert result is not None
        assert result["above_prior_high"] is True
        assert "TESTING PRIOR HIGH" in result["flags"]


# ===== fetch_premarket_bars =====


class TestFetchPremarketBarsFiltersHours:
    @patch("analytics.intraday_data.yf.Ticker")
    def test_filters_to_premarket_hours_only(self, mock_ticker_cls):
        """Mock yfinance and verify only 4:00-9:29 bars are returned."""
        today_et = pd.Timestamp.now(tz=ET).normalize()

        # Create bars spanning pre-market AND market hours
        index = pd.DatetimeIndex([
            today_et + pd.Timedelta(hours=3, minutes=55),   # 3:55 — excluded
            today_et + pd.Timedelta(hours=4, minutes=0),     # 4:00 — included
            today_et + pd.Timedelta(hours=7, minutes=30),    # 7:30 — included
            today_et + pd.Timedelta(hours=9, minutes=25),    # 9:25 — included
            today_et + pd.Timedelta(hours=9, minutes=30),    # 9:30 — excluded
            today_et + pd.Timedelta(hours=10, minutes=0),    # 10:00 — excluded
        ], tz=ET)

        data = {
            "Open": [100, 101, 102, 103, 104, 105],
            "High": [101, 102, 103, 104, 105, 106],
            "Low": [99, 100, 101, 102, 103, 104],
            "Close": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5],
            "Volume": [0, 0, 0, 0, 1000, 2000],
        }
        hist = pd.DataFrame(data, index=index)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = hist
        mock_ticker_cls.return_value = mock_ticker

        result = fetch_premarket_bars("AAPL")

        assert len(result) == 3  # 4:00, 7:30, 9:25
        assert "Volume" not in result.columns


# ===== Edge cases =====


class TestComputePremarketBriefEdgeCases:
    def test_returns_none_for_empty_bars(self):
        result = compute_premarket_brief("AAPL", pd.DataFrame(), _make_prior_day())
        assert result is None

    def test_returns_none_for_none_prior_day(self):
        pm_bars = _make_pm_bars([
            {"time": "04:00", "open": 100, "high": 101, "low": 99, "close": 100},
        ])
        result = compute_premarket_brief("AAPL", pm_bars, None)
        assert result is None

    def test_near_ma50_flag(self):
        # MA50 = 100.0, PM last = 99.6 → 0.4% away, within 0.5%
        pm_bars = _make_pm_bars([
            {"time": "04:00", "open": 99.5, "high": 100.0, "low": 99.0, "close": 99.6},
        ])
        prior = _make_prior_day(close=100.0, high=105.0, low=95.0, ma20=110.0, ma50=100.0)
        result = compute_premarket_brief("AAPL", pm_bars, prior)

        assert result is not None
        assert result["near_ma50"] is True
        assert "NEAR 50MA" in result["flags"]

    def test_wide_range_flag(self):
        # PM range > 1%: high=102, low=100 → 2%
        pm_bars = _make_pm_bars([
            {"time": "04:00", "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5},
        ])
        prior = _make_prior_day(close=100.0, high=105.0, low=95.0, ma20=110.0, ma50=90.0)
        result = compute_premarket_brief("AAPL", pm_bars, prior)

        assert result is not None
        assert result["pm_range_pct"] == 2.0
        assert "WIDE RANGE 2.0%" in result["flags"]

    def test_score_capped_at_100(self):
        # All factors: gap>1%(+30) + prior high(+20) + near MA20(+15) + wide range(+10) + non-flat(+5) = 80
        pm_bars = _make_pm_bars([
            {"time": "04:00", "open": 103.0, "high": 106.0, "low": 102.0, "close": 105.5},
        ])
        prior = _make_prior_day(close=100.0, high=105.0, low=95.0, ma20=105.5, ma50=90.0)
        result = compute_premarket_brief("AAPL", pm_bars, prior)

        assert result is not None
        assert result["priority_score"] <= 100
