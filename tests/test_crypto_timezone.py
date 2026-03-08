"""Tests for crypto timezone normalization in intraday_data.py.

Verifies that yfinance UTC timestamps for crypto are correctly converted
to ET before stripping timezone, so date comparisons in fetch_prior_day()
and fetch_intraday() work correctly around UTC midnight (7-8 PM ET).
"""

import pandas as pd
import pytz
import pytest

from analytics.intraday_data import _normalize_index_to_et

ET = pytz.timezone("US/Eastern")
UTC = pytz.UTC


class TestNormalizeIndexToET:
    """Tests for the _normalize_index_to_et() helper."""

    def test_utc_aware_timestamps_converted_to_et(self):
        """UTC midnight bar should become 7 or 8 PM ET previous day."""
        # Simulate BTC-USD daily bar at UTC midnight (March 8, 00:00 UTC)
        idx = pd.DatetimeIndex(
            [pd.Timestamp("2026-03-08 00:00:00", tz="UTC")],
        )
        df = pd.DataFrame({"Close": [67000.0]}, index=idx)

        result = _normalize_index_to_et(df)

        # UTC midnight = 7 PM ET (during EST, UTC-5) or 8 PM ET (during EDT, UTC-4)
        # March 8, 2026 is still EST (DST starts March 8 at 2 AM)
        # At 00:00 UTC on March 8 → March 7 at 19:00 EST
        assert result.index[0].date() == pd.Timestamp("2026-03-07").date()
        assert result.index.tz is None  # timezone stripped

    def test_utc_5min_bars_converted_to_et(self):
        """Crypto 5-min bars at UTC midnight should map to ET evening."""
        idx = pd.DatetimeIndex([
            pd.Timestamp("2026-03-08 00:00:00", tz="UTC"),
            pd.Timestamp("2026-03-08 00:05:00", tz="UTC"),
            pd.Timestamp("2026-03-08 00:10:00", tz="UTC"),
        ])
        df = pd.DataFrame({
            "Open": [67000, 67100, 67050],
            "High": [67200, 67200, 67150],
            "Low": [66900, 67000, 67000],
            "Close": [67100, 67050, 67100],
            "Volume": [100, 120, 110],
        }, index=idx)

        result = _normalize_index_to_et(df)

        # All bars should be on March 7 in ET
        for ts in result.index:
            assert ts.date() == pd.Timestamp("2026-03-07").date()
        assert result.index.tz is None

    def test_et_aware_timestamps_unchanged(self):
        """Equity timestamps already in ET should pass through correctly."""
        idx = pd.DatetimeIndex([
            pd.Timestamp("2026-03-06 09:30:00", tz="US/Eastern"),
            pd.Timestamp("2026-03-06 09:35:00", tz="US/Eastern"),
        ])
        df = pd.DataFrame({"Close": [150.0, 151.0]}, index=idx)

        result = _normalize_index_to_et(df)

        # Date should still be March 6
        assert result.index[0].date() == pd.Timestamp("2026-03-06").date()
        # Hour should still be 9:30
        assert result.index[0].hour == 9
        assert result.index[0].minute == 30
        assert result.index.tz is None

    def test_naive_timestamps_treated_as_utc(self):
        """Timezone-naive index (edge case) should be treated as UTC."""
        idx = pd.DatetimeIndex([
            pd.Timestamp("2026-03-08 00:00:00"),  # naive, no tz
        ])
        df = pd.DataFrame({"Close": [67000.0]}, index=idx)

        result = _normalize_index_to_et(df)

        # Treated as UTC → converted to ET → March 7 evening
        assert result.index[0].date() == pd.Timestamp("2026-03-07").date()
        assert result.index.tz is None

    def test_dataframe_data_preserved(self):
        """Column data should be unchanged after timezone normalization."""
        idx = pd.DatetimeIndex([
            pd.Timestamp("2026-03-08 00:00:00", tz="UTC"),
        ])
        df = pd.DataFrame({
            "Open": [67000.0], "High": [67500.0],
            "Low": [66800.0], "Close": [67200.0],
            "Volume": [1500],
        }, index=idx)

        result = _normalize_index_to_et(df)

        assert result["Open"].iloc[0] == 67000.0
        assert result["High"].iloc[0] == 67500.0
        assert result["Low"].iloc[0] == 66800.0
        assert result["Close"].iloc[0] == 67200.0
        assert result["Volume"].iloc[0] == 1500

    def test_empty_dataframe_handled(self):
        """Empty DataFrame should not raise."""
        df = pd.DataFrame()
        result = _normalize_index_to_et(df)
        assert result.empty
