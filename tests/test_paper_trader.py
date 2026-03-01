"""Unit tests for paper trading integration."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

# Minimal signal stub matching AlertSignal interface
@dataclass
class _Signal:
    symbol: str = "AAPL"
    direction: str = "BUY"
    price: float = 100.0
    entry: float | None = 100.0
    stop: float | None = 99.0
    target_1: float | None = 101.0
    target_2: float | None = 102.0
    score: int = 80

    class _AlertType:
        def __init__(self, value: str):
            self.value = value

    alert_type: _AlertType = None

    def __post_init__(self):
        if self.alert_type is None:
            self.alert_type = self._AlertType("ma_bounce_20")


# ---------------------------------------------------------------------------
# _is_actionable_buy
# ---------------------------------------------------------------------------

class TestIsActionableBuy:
    def test_actionable_buy_with_entry_stop_target(self):
        from alerting.paper_trader import _is_actionable_buy

        sig = _Signal()
        assert _is_actionable_buy(sig) is True

    def test_gap_fill_not_actionable(self):
        from alerting.paper_trader import _is_actionable_buy

        sig = _Signal(alert_type=_Signal._AlertType("gap_fill"))
        assert _is_actionable_buy(sig) is False

    def test_sell_signal_not_actionable(self):
        from alerting.paper_trader import _is_actionable_buy

        sig = _Signal(direction="SELL")
        assert _is_actionable_buy(sig) is False

    def test_buy_without_entry_not_actionable(self):
        from alerting.paper_trader import _is_actionable_buy

        sig = _Signal(entry=None)
        assert _is_actionable_buy(sig) is False

    def test_low_score_not_actionable(self):
        from alerting.paper_trader import _is_actionable_buy

        sig = _Signal(score=60)
        assert _is_actionable_buy(sig) is False


# ---------------------------------------------------------------------------
# _calculate_shares
# ---------------------------------------------------------------------------

class TestCalculateShares:
    def test_calculate_shares_standard(self):
        from alerting.paper_trader import _calculate_shares

        # $10,000 / $100 = 100 shares
        assert _calculate_shares(100.0) == 100

    def test_calculate_shares_rounds_down(self):
        from alerting.paper_trader import _calculate_shares

        # $10,000 / $130 = 76.9... → 76
        assert _calculate_shares(130.0) == 76

    def test_calculate_shares_zero_price(self):
        from alerting.paper_trader import _calculate_shares

        assert _calculate_shares(0.0) == 0


# ---------------------------------------------------------------------------
# is_enabled
# ---------------------------------------------------------------------------

class TestIsEnabled:
    @patch("alerting.paper_trader.PAPER_TRADE_ENABLED", True)
    @patch("alerting.paper_trader.ALPACA_API_KEY", "key123")
    @patch("alerting.paper_trader.ALPACA_SECRET_KEY", "secret456")
    def test_is_enabled_true(self):
        from alerting.paper_trader import is_enabled

        assert is_enabled() is True

    @patch("alerting.paper_trader.PAPER_TRADE_ENABLED", False)
    @patch("alerting.paper_trader.ALPACA_API_KEY", "key123")
    @patch("alerting.paper_trader.ALPACA_SECRET_KEY", "secret456")
    def test_is_enabled_false_when_disabled(self):
        from alerting.paper_trader import is_enabled

        assert is_enabled() is False


# ---------------------------------------------------------------------------
# place_bracket_order — duplicate guard
# ---------------------------------------------------------------------------

class TestPlaceBracketOrder:
    @patch("alerting.paper_trader.is_enabled", return_value=True)
    @patch("alerting.paper_trader._has_open_position", return_value=True)
    def test_place_bracket_order_skips_duplicate(self, mock_pos, mock_enabled):
        from alerting.paper_trader import place_bracket_order

        sig = _Signal()
        result = place_bracket_order(sig, alert_id=1)
        assert result is False
