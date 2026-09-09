"""Daily Target bridge — mapping imported fills onto the discipline log.

The mapping is what the trader reads every evening, so the cases that matter are
the ones that would quietly report the wrong number: the option contract
multiplier, open positions leaking into realized P&L, and hand-logged rows being
clobbered by a re-run.
"""

from __future__ import annotations

from datetime import date

import pytest

from brokers import daily_target_sync as dts
from brokers.daily_target_sync import build_daily_trade_rows
from models import MatchedTrade, TradeMonthly

SESSION = date(2026, 9, 8)


@pytest.fixture(autouse=True)
def no_alert_lookup(monkeypatch):
    """Default to 'no alert fired'; individual tests opt in to one."""
    monkeypatch.setattr(dts, "_alert_for", lambda *_a, **_k: None)


def _matched(**kw) -> MatchedTrade:
    row = dict(
        account="Robinhood", symbol="AAPL", buy_date=SESSION, sell_date=SESSION,
        quantity=10.0, buy_price=100.0, sell_price=110.0, buy_amount=1000.0,
        sell_amount=1100.0, realized_pnl=100.0, holding_days=0,
        asset_type="stock", category="", holding_period_type="day_trade",
        underlying_symbol="AAPL",
    )
    row.update(kw)
    return MatchedTrade(**row)


def _fill(**kw) -> TradeMonthly:
    row = dict(
        account="Robinhood", description="", symbol="AAPL", cusip="", acct_type="",
        transaction_type="Buy", trade_date=SESSION, quantity=10.0, price=100.0,
        amount=-1000.0, is_option=False, option_detail="", is_recurring=False,
        asset_type="stock", category="", underlying_symbol="AAPL",
    )
    row.update(kw)
    return TradeMonthly(**row)


def test_closed_round_trip_maps_to_a_realized_row():
    rows = build_daily_trade_rows([_matched()], [], SESSION)
    assert len(rows) == 1
    r = rows[0]
    assert r["symbol"] == "AAPL"
    assert r["entry_price"] == 100.0
    assert r["exit_price"] == 110.0
    assert r["pnl"] == pytest.approx(100.0)
    assert r["is_open"] is False
    assert r["trade_type"] == "day"  # holding_days == 0


def test_multi_day_hold_is_labelled_swing():
    rows = build_daily_trade_rows(
        [_matched(buy_date=date(2026, 9, 2), holding_days=4)], [], SESSION)
    assert rows[0]["trade_type"] == "swing"


def test_option_pnl_is_scaled_by_the_contract_multiplier():
    """A contract controls 100 shares — without this the day's number is 100x low."""
    rows = build_daily_trade_rows([
        _matched(symbol="SPY 2026-09-19 C 696", asset_type="option",
                 underlying_symbol="SPY", quantity=2.0,
                 buy_price=3.25, sell_price=4.25, buy_amount=6.50,
                 realized_pnl=2.0)  # matcher works per-share: 2 x $1.00
    ], [], SESSION)
    r = rows[0]
    assert r["instrument"] == "option"
    assert r["symbol"] == "SPY"                      # underlying, not the contract key
    assert r["entry_price"] == 3.25                  # premium stays as quoted
    assert r["pnl"] == pytest.approx(200.0)          # 2 contracts x $1.00 x 100
    assert r["position_size"] == pytest.approx(650.0)


def test_stock_pnl_is_not_scaled():
    rows = build_daily_trade_rows([_matched()], [], SESSION)
    assert rows[0]["pnl"] == pytest.approx(100.0)


def test_open_entry_is_flagged_open_with_zero_pnl():
    """The summary endpoint excludes is_open rows — unrealized must not count."""
    rows = build_daily_trade_rows([], [_fill()], SESSION)
    assert len(rows) == 1
    assert rows[0]["is_open"] is True
    assert rows[0]["pnl"] == 0.0
    assert rows[0]["exit_price"] is None


def test_an_entry_already_closed_is_not_also_listed_as_open():
    """The same buy must not appear twice — once matched, once as a live position."""
    rows = build_daily_trade_rows([_matched()], [_fill()], SESSION)
    assert len(rows) == 1
    assert rows[0]["is_open"] is False


def test_sells_are_never_treated_as_open_entries():
    rows = build_daily_trade_rows([], [_fill(transaction_type="Sell")], SESSION)
    assert rows == []


def test_only_the_requested_session_is_mapped():
    rows = build_daily_trade_rows(
        [_matched(sell_date=date(2026, 9, 5))],
        [_fill(trade_date=date(2026, 9, 5))],
        SESSION,
    )
    assert rows == []


def test_alert_autofills_setup_target_and_stop(monkeypatch):
    """The entry mechanism the trader would otherwise type by hand."""
    monkeypatch.setattr(dts, "_alert_for", lambda *_a, **_k: {
        "alert_type": "ema_reclaim_21", "entry": 100.0, "stop": 98.5,
        "target_1": 104.0, "score": 78,
    })
    rows = build_daily_trade_rows([_matched()], [], SESSION)
    assert rows[0]["setup"] == "ema_reclaim_21"
    assert rows[0]["target"] == "$104.00"
    assert rows[0]["stop"] == "$98.50"


def test_no_alert_leaves_setup_blank_marking_the_entry_off_plan():
    """A blank setup is the off-plan signal — it must not be back-filled."""
    rows = build_daily_trade_rows([_matched()], [], SESSION)
    assert rows[0]["setup"] is None


def test_external_ids_are_deterministic_across_runs():
    """Re-running the import must update the same row, not add another."""
    first = build_daily_trade_rows([_matched()], [], SESSION)
    second = build_daily_trade_rows([_matched()], [], SESSION)
    assert first[0]["external_id"] == second[0]["external_id"]


def test_imported_rows_are_tagged_with_their_source():
    """The UI needs to tell auto-filled rows from hand-logged ones."""
    rows = build_daily_trade_rows([_matched()], [_fill(symbol="MSFT")], SESSION)
    assert {r["source"] for r in rows} == {"robinhood"}
