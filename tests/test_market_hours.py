"""Tests for market hours helpers — crypto 24h support."""

from unittest.mock import patch

from analytics.market_hours import (
    _get_crypto_session_phase,
    get_session_phase_for_symbol,
    is_market_hours_for_symbol,
)


class TestCryptoMarketHours:
    def test_is_market_hours_for_btc_always_true(self):
        """Crypto symbols always return True for market hours."""
        assert is_market_hours_for_symbol("BTC-USD") is True
        assert is_market_hours_for_symbol("ETH-USD") is True

    def test_is_market_hours_for_equity_delegates(self):
        """Equity symbols delegate to is_market_hours()."""
        with patch("analytics.market_hours.is_market_hours", return_value=False):
            assert is_market_hours_for_symbol("AAPL") is False
        with patch("analytics.market_hours.is_market_hours", return_value=True):
            assert is_market_hours_for_symbol("AAPL") is True

    def test_crypto_session_phase_never_closed(self):
        """get_session_phase_for_symbol('BTC-USD') never returns 'closed'."""
        phase = get_session_phase_for_symbol("BTC-USD")
        assert phase != "closed"
        assert phase in ("asia", "europe", "us", "overlap")

    def test_crypto_session_phase_returns_valid_phase(self):
        """_get_crypto_session_phase() returns one of the valid phase names."""
        phase = _get_crypto_session_phase()
        assert phase in ("asia", "europe", "us", "overlap")

    def test_equity_session_phase_delegates(self):
        """Equity symbols delegate to get_session_phase()."""
        with patch("analytics.market_hours.get_session_phase", return_value="prime_time"):
            assert get_session_phase_for_symbol("AAPL") == "prime_time"
        with patch("analytics.market_hours.get_session_phase", return_value="closed"):
            assert get_session_phase_for_symbol("SPY") == "closed"


class TestCryptoSessionPhaseMapping:
    """Test UTC hour → session phase mapping for crypto."""

    def _mock_utc_hour(self, hour):
        """Create a mock datetime with the given UTC hour."""
        from datetime import datetime
        import pytz
        return datetime(2026, 3, 6, hour, 30, 0, tzinfo=pytz.utc)

    def test_asia_session(self):
        with patch("analytics.market_hours.datetime") as mock_dt:
            mock_dt.now.return_value = self._mock_utc_hour(3)
            assert _get_crypto_session_phase() == "asia"

    def test_europe_session(self):
        with patch("analytics.market_hours.datetime") as mock_dt:
            mock_dt.now.return_value = self._mock_utc_hour(10)
            assert _get_crypto_session_phase() == "europe"

    def test_us_session(self):
        with patch("analytics.market_hours.datetime") as mock_dt:
            mock_dt.now.return_value = self._mock_utc_hour(16)
            assert _get_crypto_session_phase() == "us"

    def test_overlap_session(self):
        with patch("analytics.market_hours.datetime") as mock_dt:
            mock_dt.now.return_value = self._mock_utc_hour(22)
            assert _get_crypto_session_phase() == "overlap"
