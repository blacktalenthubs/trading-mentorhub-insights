"""SPY-trend long gate — pure predicate spy_trend_blocks_buy. Blocks equity BUY
alerts when SPY is below BOTH its 8 & 21 EMA, except exempt names. True ⇒ suppress."""

from api.app.routers.tv_webhook import (
    SPY_TREND_EXEMPT_DEFAULT,
    spy_trend_blocks_buy,
)


class TestSpyTrendBlocksBuy:
    def test_blocks_non_exempt_buy_when_below_both(self):
        assert spy_trend_blocks_buy(True, "BUY", "AAPL") is True
        assert spy_trend_blocks_buy(True, "BUY", "MRVL") is True

    def test_exempt_names_always_flow(self):
        for sym in ("SPY", "QQQ", "DRAM", "NVDA"):
            assert sym in SPY_TREND_EXEMPT_DEFAULT
            assert spy_trend_blocks_buy(True, "BUY", sym) is False

    def test_above_or_none_never_blocks(self):
        # Above the 21 (False) or data missing (None) ⇒ longs flow.
        assert spy_trend_blocks_buy(False, "BUY", "AAPL") is False
        assert spy_trend_blocks_buy(None, "BUY", "AAPL") is False

    def test_only_buys_blocked(self):
        assert spy_trend_blocks_buy(True, "SHORT", "AAPL") is False
        assert spy_trend_blocks_buy(True, "SELL", "AAPL") is False
        assert spy_trend_blocks_buy(True, "NOTICE", "AAPL") is False

    def test_gate_disabled_never_blocks(self):
        assert spy_trend_blocks_buy(True, "BUY", "AAPL", enabled=False) is False

    def test_custom_exempt_list(self):
        custom = frozenset({"SPY", "TSLA"})
        assert spy_trend_blocks_buy(True, "BUY", "TSLA", custom) is False
        assert spy_trend_blocks_buy(True, "BUY", "NVDA", custom) is True  # not in custom list

    def test_case_insensitive(self):
        assert spy_trend_blocks_buy(True, "buy", "aapl") is True
        assert spy_trend_blocks_buy(True, "buy", "spy") is False
