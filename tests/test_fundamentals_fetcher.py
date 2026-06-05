"""Tests for analytics/fundamentals_fetcher — Finnhub + yfinance parsing.

All network calls are mocked: the Finnhub `_get` helper (shared with the
earnings fetcher) and `yfinance.Ticker`. Asserts the parse/merge logic and
graceful degradation when a source returns nothing.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from analytics.fundamentals_fetcher import (
    _derive_consensus,
    fetch_fundamentals,
)


_PROFILE = {"name": "Nvidia Corp", "finnhubIndustry": "Semiconductors", "marketCapitalization": 3_000_000}
_METRIC = {"metric": {"epsTTM": 2.0, "epsForward": 3.0, "peTTM": 45.0}}
_RECS = [
    {"strongBuy": 30, "buy": 10, "hold": 5, "sell": 1, "strongSell": 0, "period": "2026-05-01"},
    {"strongBuy": 20, "buy": 8, "hold": 6, "sell": 2, "strongSell": 1, "period": "2026-04-01"},
]


def _fake_get(endpoint, params):
    if endpoint == "/stock/profile2":
        return _PROFILE
    if endpoint == "/stock/metric":
        return _METRIC
    if endpoint == "/stock/recommendation":
        return _RECS
    return None


def _fake_yf_info(summary="Nvidia designs GPUs.", sector="Technology", industry="Semiconductors"):
    ticker = MagicMock()
    ticker.info = {"longBusinessSummary": summary, "sector": sector, "industry": industry}
    return ticker


class TestConsensus:
    def test_strong_buy_is_buy(self):
        assert _derive_consensus(30, 10, 5, 1, 0) == "Buy"

    def test_balanced_is_hold(self):
        assert _derive_consensus(2, 3, 10, 3, 2) == "Hold"

    def test_negative_is_sell(self):
        assert _derive_consensus(0, 1, 2, 8, 10) == "Sell"

    def test_no_coverage_is_none(self):
        assert _derive_consensus(0, 0, 0, 0, 0) is None


class TestFetchFundamentals:
    def test_merges_all_sources(self):
        fake_yf = MagicMock()
        fake_yf.Ticker.return_value = _fake_yf_info()
        with (
            patch("analytics.fundamentals_fetcher._get", _fake_get),
            patch.dict("sys.modules", {"yfinance": fake_yf}),
        ):
            data = fetch_fundamentals("NVDA")

        assert data is not None
        assert data.company_name == "Nvidia Corp"
        assert data.trailing_eps == 2.0
        assert data.forward_eps == 3.0
        # (3 - 2) / 2 * 100 = 50.0
        assert data.eps_growth_pct == 50.0
        assert data.pe_ratio == 45.0
        # Market cap in millions → absolute USD.
        assert data.market_cap == 3_000_000 * 1e6
        assert data.consensus == "Buy"
        assert data.rec_strong_buy == 30
        assert data.rec_period == "2026-05-01"
        # yfinance fields win.
        assert data.description == "Nvidia designs GPUs."
        assert data.sector == "Technology"

    def test_skip_description_skips_yfinance(self):
        fake_yf = MagicMock()
        with (
            patch("analytics.fundamentals_fetcher._get", _fake_get),
            patch("analytics.fundamentals_fetcher._fetch_description") as mock_desc,
            patch.dict("sys.modules", {"yfinance": fake_yf}),
        ):
            data = fetch_fundamentals("NVDA", include_description=False)

        assert data is not None
        assert data.description is None
        # The rate-limited .info description fetch is skipped (price trend via
        # fast_info still runs — it's cheap and needs to be fresh).
        mock_desc.assert_not_called()
        # Finnhub industry survives when the description fetch is skipped.
        assert data.industry == "Semiconductors"

    def test_yfinance_failure_is_graceful(self):
        fake_yf = MagicMock()
        fake_yf.Ticker.side_effect = Exception("Yahoo rate limited")
        with (
            patch("analytics.fundamentals_fetcher._get", _fake_get),
            patch.dict("sys.modules", {"yfinance": fake_yf}),
        ):
            data = fetch_fundamentals("NVDA")

        assert data is not None
        assert data.description is None
        # Finnhub data still present.
        assert data.company_name == "Nvidia Corp"

    def test_all_sources_empty_returns_none(self):
        # Finnhub returns nothing AND yfinance yields no description / no price.
        empty_ticker = MagicMock(
            info={},
            fast_info=MagicMock(last_price=None, fifty_day_average=None, two_hundred_day_average=None),
        )
        with (
            patch("analytics.fundamentals_fetcher._get", lambda e, p: None),
            patch.dict("sys.modules", {"yfinance": MagicMock(Ticker=MagicMock(return_value=empty_ticker))}),
        ):
            data = fetch_fundamentals("ZZZZ")
        assert data is None

    def test_eps_growth_none_when_trailing_zero(self):
        metric = {"metric": {"epsTTM": 0, "epsForward": 3.0, "peTTM": 10.0}}

        def _get(endpoint, params):
            return metric if endpoint == "/stock/metric" else None

        with (
            patch("analytics.fundamentals_fetcher._get", _get),
        ):
            data = fetch_fundamentals("XYZ", include_description=False)
        assert data is not None
        assert data.eps_growth_pct is None
