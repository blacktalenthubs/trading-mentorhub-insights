"""Robinhood import — payload normalization + the full sync pipeline.

Every test runs against recorded-shape fixtures with no network. The Robinhood
payloads here mirror the real private-API shape: numbers as strings, an
instrument URL instead of a ticker, and options nested one level down in legs.
"""

from __future__ import annotations

from datetime import date

import pytest

from analytics.trade_matcher import match_trades_fifo
from brokers import robinhood as rh
from brokers.robinhood import (
    normalize_option_order,
    normalize_orders,
    normalize_stock_order,
    option_contract_symbol,
)

INSTRUMENT = "https://api.robinhood.com/instruments/abc-123/"


def _stock_order(side="buy", state="filled", qty="10.00000000", price="123.4500",
                 order_id="order-1", ts="2026-09-08T14:31:02.123456Z"):
    return {
        "id": order_id,
        "state": state,
        "side": side,
        "instrument": INSTRUMENT,
        "quantity": qty,
        "cumulative_quantity": qty,
        "average_price": price,
        "created_at": "2026-09-08T13:29:00.000000Z",
        "last_transaction_at": ts,
        "executions": [{"price": price, "quantity": qty, "timestamp": ts}],
    }


def _option_order(side="buy", effect="open", state="filled", order_id="opt-1",
                  price="3.2500", qty="2.00000", strike="696.0000"):
    return {
        "id": order_id,
        "state": state,
        "chain_symbol": "SPY",
        "created_at": "2026-09-08T14:00:00.000000Z",
        "legs": [{
            "side": side,
            "position_effect": effect,
            "option_type": "call",
            "strike_price": strike,
            "expiration_date": "2026-09-19",
            "executions": [{
                "price": price, "quantity": qty,
                "timestamp": "2026-09-08T14:05:11.000000Z",
            }],
        }],
    }


# ── Stock normalization ──────────────────────────────────────────────

def test_stock_buy_normalizes_to_a_debit():
    row = normalize_stock_order(_stock_order(), "AAPL")
    assert row is not None
    assert row.symbol == "AAPL"
    assert row.transaction_type == "Buy"
    assert row.quantity == 10.0
    assert row.price == pytest.approx(123.45)
    assert row.amount == pytest.approx(-1234.50)  # a buy is a debit
    assert row.trade_date == date(2026, 9, 8)
    assert row.is_option is False


def test_stock_sell_normalizes_to_a_credit():
    row = normalize_stock_order(_stock_order(side="sell"), "AAPL")
    assert row.transaction_type == "Sell"
    assert row.amount == pytest.approx(1234.50)


@pytest.mark.parametrize("state", ["queued", "cancelled", "rejected", "confirmed"])
def test_unfilled_orders_are_dropped(state):
    """Only filled orders are real fills — a queued order has no P&L."""
    assert normalize_stock_order(_stock_order(state=state), "AAPL") is None


def test_partial_fill_uses_cumulative_quantity_not_requested():
    """`quantity` is what was asked for; `cumulative_quantity` is what filled."""
    order = _stock_order(qty="10.00000000")
    order["cumulative_quantity"] = "4.00000000"
    order["executions"] = [{"price": "100.00", "quantity": "4.00000000",
                            "timestamp": "2026-09-08T14:31:02.123456Z"}]
    row = normalize_stock_order(order, "AAPL")
    assert row.quantity == 4.0
    assert row.amount == pytest.approx(-400.0)


def test_price_is_volume_weighted_across_executions():
    """A single order filling in two prints must average by size, not evenly."""
    order = _stock_order(qty="30.00000000")
    order["average_price"] = None  # force the executions path
    order["executions"] = [
        {"price": "100.00", "quantity": "10.00000000", "timestamp": "2026-09-08T14:31:00Z"},
        {"price": "110.00", "quantity": "20.00000000", "timestamp": "2026-09-08T14:32:00Z"},
    ]
    row = normalize_stock_order(order, "AAPL")
    # (10*100 + 20*110) / 30 — a plain mean would wrongly give 105.
    assert row.price == pytest.approx(106.6667, abs=1e-3)


def test_fill_date_comes_from_the_execution_not_the_placement():
    """An order placed pre-market and filled at the open belongs to the fill day."""
    order = _stock_order(ts="2026-09-09T13:30:05.000000Z")
    order["created_at"] = "2026-09-08T11:00:00.000000Z"
    row = normalize_stock_order(order, "AAPL")
    assert row.trade_date == date(2026, 9, 9)


def test_zero_price_order_is_dropped():
    """A filled row with no price would corrupt P&L — drop it instead."""
    order = _stock_order(price="0.0000")
    order["executions"] = []
    assert normalize_stock_order(order, "AAPL") is None


# ── Option normalization ─────────────────────────────────────────────

def test_option_open_is_bto_and_prices_per_contract():
    rows = normalize_option_order(_option_order())
    assert len(rows) == 1
    row = rows[0]
    assert row.transaction_type == "BTO"
    assert row.underlying_symbol == "SPY"
    assert row.is_option is True
    assert row.price == pytest.approx(3.25)          # per share
    assert row.amount == pytest.approx(-650.0)       # 2 x 3.25 x 100
    assert row.symbol == "SPY 2026-09-19 C 696"


def test_option_close_is_stc():
    rows = normalize_option_order(_option_order(side="sell", effect="close"))
    assert rows[0].transaction_type == "STC"
    assert rows[0].amount == pytest.approx(650.0)


def test_multi_leg_order_yields_one_row_per_leg():
    """A spread fills two contracts under one order id — each is its own position."""
    order = _option_order()
    order["legs"].append({
        "side": "sell", "position_effect": "open",
        "option_type": "call", "strike_price": "700.0000",
        "expiration_date": "2026-09-19",
        "executions": [{"price": "1.5000", "quantity": "2.00000",
                        "timestamp": "2026-09-08T14:05:11.000000Z"}],
    })
    rows = normalize_option_order(order)
    assert len(rows) == 2
    assert {r.symbol for r in rows} == {"SPY 2026-09-19 C 696", "SPY 2026-09-19 C 700"}


def test_different_strikes_get_different_fifo_keys():
    """The bug this guards: FIFO pairs on symbol, so contracts must not collide."""
    assert option_contract_symbol("SPY", "2026-09-19", "call", 696.0) != \
           option_contract_symbol("SPY", "2026-09-19", "call", 700.0)
    assert option_contract_symbol("SPY", "2026-09-19", "call", 696.0) != \
           option_contract_symbol("SPY", "2026-09-19", "put", 696.0)


def test_a_call_buy_does_not_fifo_match_a_put_sell():
    """End-to-end version of the same guard, through the real matcher."""
    call_buy = normalize_option_order(_option_order(order_id="a"))[0]
    put_order = _option_order(side="sell", effect="close", order_id="b")
    put_order["legs"][0]["option_type"] = "put"
    put_sell = normalize_option_order(put_order)[0]

    assert match_trades_fifo([call_buy, put_sell]) == []


# ── normalize_orders: symbol resolution + isolation ──────────────────

def test_orders_with_unresolvable_symbols_are_skipped_not_mislabelled():
    """A failed instrument lookup must never store the fill under a wrong ticker."""
    pairs = normalize_orders([_stock_order()], [], lambda _url: "")
    assert pairs == []


def test_one_bad_order_does_not_lose_the_others():
    """A malformed payload is isolated so the rest of the day still imports."""
    pairs = normalize_orders(
        [{"id": "broken"}, _stock_order(order_id="good")],
        [],
        lambda _url: "AAPL",
    )
    assert [ext for ext, _ in pairs] == ["rh:stock:good"]


def test_external_ids_are_stable_and_unique_per_leg():
    """Idempotency depends on these keys being deterministic."""
    order = _option_order()
    order["legs"].append(dict(order["legs"][0], strike_price="700.0000"))
    pairs = normalize_orders([], [order], lambda _url: "")
    assert [ext for ext, _ in pairs] == ["rh:option:opt-1:0", "rh:option:opt-1:1"]


# ── Round-trip through the FIFO matcher ──────────────────────────────

def test_buy_then_sell_produces_realized_pnl():
    buy = normalize_stock_order(_stock_order(order_id="b", price="100.0000"), "AAPL")
    sell_order = _stock_order(side="sell", order_id="s", price="110.0000",
                              ts="2026-09-09T15:00:00.000000Z")
    sell = normalize_stock_order(sell_order, "AAPL")

    matched = match_trades_fifo([buy, sell])
    assert len(matched) == 1
    assert matched[0].realized_pnl == pytest.approx(100.0)  # 10 shares x $10
    assert matched[0].holding_days == 1


# ── Sync guards ──────────────────────────────────────────────────────

def test_sync_is_a_no_op_when_disabled(monkeypatch):
    """The feature must stay inert until explicitly armed."""
    import brokers.robinhood_sync as sync
    monkeypatch.setattr(sync, "ROBINHOOD_IMPORT_ENABLED", False)
    result = sync.sync_robinhood_fills(session_date=date(2026, 9, 8))
    assert result.skipped
    assert result.fills_imported == 0


def test_sync_is_a_no_op_without_a_user_id(monkeypatch):
    import brokers.robinhood_sync as sync
    monkeypatch.setattr(sync, "ROBINHOOD_IMPORT_ENABLED", True)
    monkeypatch.setattr(sync, "ROBINHOOD_USER_ID", 0)
    result = sync.sync_robinhood_fills(session_date=date(2026, 9, 8))
    assert "ROBINHOOD_USER_ID" in result.skipped


def test_sync_reports_broker_failure_instead_of_raising(monkeypatch):
    """A Robinhood outage must not take down the scheduler."""
    import brokers.robinhood_sync as sync

    class _Failing:
        def fetch_orders(self):
            raise rh.RobinhoodError("login failed")

        def symbol_for_instrument(self, url):
            return ""

    monkeypatch.setattr(sync, "ROBINHOOD_IMPORT_ENABLED", True)
    result = sync.sync_robinhood_fills(
        session_date=date(2026, 9, 8), user_id=1, client=_Failing()
    )
    assert "login failed" in result.error
    assert result.fills_imported == 0
