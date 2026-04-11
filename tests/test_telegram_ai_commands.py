"""Tests for Telegram AI commands — /spy, /eth, /btc, /levels."""

from scripts.telegram_bot import _resolve_symbol, _SYMBOL_MAP


class TestResolveSymbol:
    def test_spy(self):
        assert _resolve_symbol("/spy") == "SPY"

    def test_eth_maps_to_eth_usd(self):
        assert _resolve_symbol("/eth") == "ETH-USD"

    def test_btc_maps_to_btc_usd(self):
        assert _resolve_symbol("/btc") == "BTC-USD"

    def test_aapl_uppercase(self):
        assert _resolve_symbol("/aapl") == "AAPL"

    def test_tsla_uppercase(self):
        assert _resolve_symbol("/TSLA") == "TSLA"

    def test_empty_returns_none(self):
        assert _resolve_symbol("/") is None
        assert _resolve_symbol("") is None

    def test_with_space_after(self):
        assert _resolve_symbol("/spy ") == "SPY"

    def test_numeric_returns_none(self):
        assert _resolve_symbol("/123") is None

    def test_sol_maps_to_sol_usd(self):
        assert _resolve_symbol("/sol") == "SOL-USD"


class TestSymbolMap:
    def test_crypto_shortcuts_exist(self):
        assert "eth" in _SYMBOL_MAP
        assert "btc" in _SYMBOL_MAP

    def test_crypto_shortcuts_have_usd_suffix(self):
        for key, val in _SYMBOL_MAP.items():
            assert val.endswith("-USD"), f"{key} → {val} should end with -USD"
