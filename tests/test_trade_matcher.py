"""FIFO matcher — the money-critical bit is the option contract multiplier.

An option is quoted per share but controls 100 shares, so realized_pnl / buy_amount
/ sell_amount must come out in real dollars while buy_price / sell_price stay the
quoted per-share premium. A stock round-trip is never scaled.
"""

from datetime import date

import pytest

from analytics.trade_matcher import match_trades_fifo
from models import TradeMonthly

D1 = date(2026, 9, 9)
D2 = date(2026, 9, 10)


def _fill(**kw) -> TradeMonthly:
    row = dict(
        account="Robinhood", description="", symbol="AAPL", cusip="", acct_type="",
        transaction_type="Buy", trade_date=D1, quantity=10.0, price=100.0,
        amount=-1000.0, is_option=False, option_detail="", is_recurring=False,
        asset_type="stock", category="", underlying_symbol="AAPL",
    )
    row.update(kw)
    return TradeMonthly(**row)


def test_stock_round_trip_is_not_scaled():
    matched = match_trades_fifo([
        _fill(transaction_type="Buy", trade_date=D1, price=100.0),
        _fill(transaction_type="Sell", trade_date=D2, price=110.0),
    ])
    assert len(matched) == 1
    m = matched[0]
    assert m.buy_price == 100.0 and m.sell_price == 110.0
    assert m.buy_amount == pytest.approx(1000.0)
    assert m.sell_amount == pytest.approx(1100.0)
    assert m.realized_pnl == pytest.approx(100.0)   # (110-100) x 10, no x100


def test_option_round_trip_is_scaled_to_dollars():
    """2 contracts, +$1.00/share premium move → $200 realized (x100), prices stay per-share."""
    opt = dict(
        symbol="SPY 2026-09-19 C 696", asset_type="option", is_option=True,
        underlying_symbol="SPY", quantity=2.0,
    )
    matched = match_trades_fifo([
        _fill(transaction_type="BTO", trade_date=D1, price=3.25, amount=-650.0, **opt),
        _fill(transaction_type="STC", trade_date=D2, price=4.25, amount=850.0, **opt),
    ])
    assert len(matched) == 1
    m = matched[0]
    assert m.asset_type == "option"
    assert m.buy_price == 3.25 and m.sell_price == 4.25   # premium stays per-share
    assert m.buy_amount == pytest.approx(650.0)           # 3.25 x 2 x 100
    assert m.sell_amount == pytest.approx(850.0)          # 4.25 x 2 x 100
    assert m.realized_pnl == pytest.approx(200.0)         # (4.25-3.25) x 2 x 100


def test_partial_fill_scales_only_the_matched_quantity():
    """Buy 3 contracts, sell 1 — realized is scaled for the 1 matched contract only."""
    opt = dict(symbol="QQQ 2026-09-19 C 500", asset_type="option", is_option=True,
               underlying_symbol="QQQ")
    matched = match_trades_fifo([
        _fill(transaction_type="BTO", trade_date=D1, price=2.00, quantity=3.0, amount=-600.0, **opt),
        _fill(transaction_type="STC", trade_date=D2, price=2.50, quantity=1.0, amount=250.0, **opt),
    ])
    assert len(matched) == 1
    assert matched[0].quantity == 1.0
    assert matched[0].realized_pnl == pytest.approx(50.0)  # (2.50-2.00) x 1 x 100
