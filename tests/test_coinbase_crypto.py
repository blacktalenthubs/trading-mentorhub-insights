"""Tests for Coinbase crypto data fetching."""

import os
import sys
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

import pandas as pd
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _mock_coinbase_response(n=20, base_price=2200.0):
    """Create a mock Coinbase API response (list of lists).

    Coinbase format: [[timestamp, low, high, open, close, volume], ...]
    In reverse chronological order.
    """
    now = int(datetime.now(timezone.utc).timestamp())
    data = []
    for i in range(n):
        ts = now - (n - i) * 300  # 5-min candles
        o = base_price + np.random.randn() * 5
        h = o + abs(np.random.randn()) * 3
        l = o - abs(np.random.randn()) * 3
        c = o + np.random.randn() * 2
        v = float(np.random.randint(100, 5000))
        data.append([ts, l, h, o, c, v])
    # Coinbase returns reverse chronological
    return list(reversed(data))


class TestFetchCoinbaseCandles:
    """Test _fetch_coinbase_candles from intraday_data.py."""

    @patch("requests.get")
    def test_returns_dataframe_with_correct_columns(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _mock_coinbase_response()
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        from analytics.intraday_data import _fetch_coinbase_candles
        df = _fetch_coinbase_candles("ETH-USD", 300, 20)

        assert not df.empty
        assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
        assert df.index.tz is None  # naive ET

    @patch("requests.get")
    def test_sorted_chronologically(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = _mock_coinbase_response(10)
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        from analytics.intraday_data import _fetch_coinbase_candles
        df = _fetch_coinbase_candles("BTC-USD", 300, 10)

        # Index should be ascending
        assert (df.index == df.index.sort_values()).all()

    @patch("requests.get")
    def test_returns_empty_on_api_error(self, mock_get):
        mock_get.side_effect = Exception("Network error")

        from analytics.intraday_data import _fetch_coinbase_candles
        df = _fetch_coinbase_candles("ETH-USD", 300)

        assert df.empty

    @patch("requests.get")
    def test_returns_empty_on_empty_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        from analytics.intraday_data import _fetch_coinbase_candles
        df = _fetch_coinbase_candles("ETH-USD", 300)

        assert df.empty


class TestFetchIntradayCryptoFallback:
    """Test that fetch_intraday_crypto falls back to yfinance."""

    @patch("analytics.intraday_data._fetch_coinbase_candles")
    @patch("analytics.intraday_data.fetch_intraday")
    def test_uses_coinbase_when_available(self, mock_yf, mock_cb):
        # Coinbase returns data
        dates = pd.date_range(pd.Timestamp.now().normalize(), periods=20, freq="5min")
        mock_cb.return_value = pd.DataFrame({
            "Open": np.random.rand(20) * 100 + 2200,
            "High": np.random.rand(20) * 100 + 2210,
            "Low": np.random.rand(20) * 100 + 2190,
            "Close": np.random.rand(20) * 100 + 2200,
            "Volume": np.random.randint(100, 5000, 20),
        }, index=dates)

        from analytics.intraday_data import fetch_intraday_crypto
        df = fetch_intraday_crypto("ETH-USD", "5m")

        assert not df.empty
        mock_cb.assert_called_once()
        mock_yf.assert_not_called()  # yfinance not called

    @patch("analytics.intraday_data._fetch_coinbase_candles")
    @patch("analytics.intraday_data.fetch_intraday")
    def test_falls_back_to_yfinance(self, mock_yf, mock_cb):
        # Coinbase fails
        mock_cb.return_value = pd.DataFrame()
        # yfinance has data
        dates = pd.date_range(pd.Timestamp.now().normalize(), periods=20, freq="5min")
        mock_yf.return_value = pd.DataFrame({
            "Open": np.random.rand(20) * 100 + 2200,
            "High": np.random.rand(20) * 100 + 2210,
            "Low": np.random.rand(20) * 100 + 2190,
            "Close": np.random.rand(20) * 100 + 2200,
            "Volume": np.random.randint(100, 5000, 20),
        }, index=dates)

        from analytics.intraday_data import fetch_intraday_crypto
        df = fetch_intraday_crypto("ETH-USD", "5m")

        assert not df.empty
        mock_yf.assert_called_once()  # yfinance was used as fallback


class TestFetchOhlcCoinbase:
    """Test fetch_ohlc routes crypto through Coinbase."""

    @patch("analytics.market_data._fetch_ohlc_coinbase")
    def test_crypto_routes_through_coinbase(self, mock_cb):
        dates = pd.date_range("2026-01-01", periods=30, freq="D")
        mock_cb.return_value = pd.DataFrame({
            "Open": np.random.rand(30) * 100 + 2200,
            "High": np.random.rand(30) * 100 + 2210,
            "Low": np.random.rand(30) * 100 + 2190,
            "Close": np.random.rand(30) * 100 + 2200,
            "Volume": np.random.randint(100, 5000, 30),
        }, index=dates)

        from analytics.market_data import fetch_ohlc
        df = fetch_ohlc("ETH-USD", period="3mo", interval="1d")

        assert not df.empty
        mock_cb.assert_called_once()

    @patch("analytics.market_data._fetch_ohlc_coinbase")
    def test_equities_skip_coinbase(self, mock_cb):
        """SPY should NOT go through Coinbase."""
        from analytics.market_data import fetch_ohlc
        # This will call yfinance (may fail without network, that's OK)
        try:
            fetch_ohlc("SPY", period="5d", interval="1d")
        except Exception:
            pass
        mock_cb.assert_not_called()


class TestGranularityMapping:
    """Test interval → granularity mapping."""

    def test_5m_maps_to_300(self):
        from analytics.intraday_data import _COINBASE_GRANULARITY
        assert _COINBASE_GRANULARITY["5m"] == 300

    def test_1h_maps_to_3600(self):
        from analytics.intraday_data import _COINBASE_GRANULARITY
        assert _COINBASE_GRANULARITY["1h"] == 3600
        assert _COINBASE_GRANULARITY["60m"] == 3600

    def test_1d_maps_to_86400(self):
        from analytics.intraday_data import _COINBASE_GRANULARITY
        assert _COINBASE_GRANULARITY["1d"] == 86400
