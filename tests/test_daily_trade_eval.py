"""Daily trade evaluation — session aggregation and plan-discipline classification.

The AI narrative is not tested (it is a model call); what IS tested is the data
layer underneath it, because that is what decides whether a trade is reported as
on-plan or off-plan.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from analytics import daily_trade_eval as dte

SESSION = date(2026, 9, 8)


def _matched(**kw):
    row = {
        "account": "Robinhood", "symbol": "AAPL", "buy_date": "2026-09-08",
        "sell_date": "2026-09-08", "quantity": 10.0, "buy_price": 100.0,
        "sell_price": 110.0, "realized_pnl": 100.0, "holding_days": 0,
    }
    row.update(kw)
    return row


def _fill(**kw):
    row = {
        "account": "Robinhood", "symbol": "AAPL", "transaction_type": "Buy",
        "trade_date": pd.Timestamp("2026-09-08"), "quantity": 10.0,
        "price": 100.0, "underlying_symbol": "AAPL",
    }
    row.update(kw)
    return row


@pytest.fixture
def patched(monkeypatch):
    """Drive collect_session_trades off in-memory frames instead of the DB."""
    def _install(matched_rows, fill_rows, alerts):
        monkeypatch.setattr(dte, "get_matched_trades",
                            lambda _uid: pd.DataFrame(matched_rows))
        monkeypatch.setattr(dte, "get_trades_monthly",
                            lambda _uid, account=None: pd.DataFrame(fill_rows))
        monkeypatch.setattr(dte, "_alerts_by_symbol", lambda _d: alerts)
    return _install


def test_realized_pnl_and_win_rate(patched):
    patched(
        [_matched(realized_pnl=100.0), _matched(symbol="MSFT", realized_pnl=-40.0)],
        [], {},
    )
    data = dte.collect_session_trades(1, SESSION, "Robinhood")
    assert data["realized_pnl"] == pytest.approx(60.0)
    assert (data["win_count"], data["loss_count"]) == (1, 1)
    assert data["win_rate"] == 50.0


def test_only_trades_closed_today_count_toward_realized(patched):
    """A round-trip closed yesterday must not inflate today's P&L."""
    patched(
        [_matched(realized_pnl=100.0),
         _matched(symbol="NVDA", sell_date="2026-09-05", realized_pnl=999.0)],
        [], {},
    )
    data = dte.collect_session_trades(1, SESSION, "Robinhood")
    assert data["realized_pnl"] == pytest.approx(100.0)


def test_another_accounts_trades_are_excluded(patched):
    """matched_trades holds every brokerage — the Robinhood review is Robinhood only."""
    patched(
        [_matched(realized_pnl=100.0),
         _matched(account="Fidelity", symbol="TSLA", realized_pnl=500.0)],
        [], {},
    )
    data = dte.collect_session_trades(1, SESSION, "Robinhood")
    assert data["realized_pnl"] == pytest.approx(100.0)


def test_entry_with_an_alert_is_on_plan(patched):
    patched([], [_fill()], {"AAPL": [{"alert_type": "ema_reclaim_21", "entry": 100.0,
                                      "stop": 99.0, "target_1": 103.0, "score": 78}]})
    data = dte.collect_session_trades(1, SESSION, "Robinhood")
    assert len(data["on_plan"]) == 1
    assert data["off_plan"] == []


def test_entry_without_an_alert_is_off_plan(patched):
    """The number the review is built to surface."""
    patched([], [_fill(symbol="GME", underlying_symbol="GME")], {"AAPL": [{}]})
    data = dte.collect_session_trades(1, SESSION, "Robinhood")
    assert len(data["off_plan"]) == 1
    assert data["on_plan"] == []


def test_option_fill_matches_an_alert_on_its_underlying(patched):
    """An option's symbol is a contract key, so plan-matching uses the underlying."""
    patched([], [_fill(symbol="SPY 2026-09-19 C 696", underlying_symbol="SPY",
                       transaction_type="BTO")], {"SPY": [{"alert_type": "pdh_retest_hold"}]})
    data = dte.collect_session_trades(1, SESSION, "Robinhood")
    assert len(data["on_plan"]) == 1


def test_sells_are_not_counted_as_entries(patched):
    """Only opening transactions are 'entries taken' — a close is an exit."""
    patched([], [_fill(transaction_type="Sell"), _fill(transaction_type="STC")], {})
    data = dte.collect_session_trades(1, SESSION, "Robinhood")
    assert data["opened"] == []


def test_no_trades_yields_no_review(monkeypatch):
    """A day with no activity should stay silent, not send an empty message."""
    monkeypatch.setattr(dte, "collect_session_trades",
                        lambda *a, **k: {"closed": [], "opened": [], "realized_pnl": 0.0,
                                         "win_count": 0, "loss_count": 0, "win_rate": 0.0,
                                         "on_plan": [], "off_plan": [],
                                         "alerts_by_symbol": {}, "session_date": SESSION,
                                         "account": "Robinhood"})
    assert dte.build_daily_eval(1, session_date=SESSION) is None


def test_review_falls_back_to_the_scorecard_without_an_api_key(patched, monkeypatch):
    """No Anthropic key still delivers the numbers — they are the point."""
    patched([_matched(realized_pnl=100.0)], [_fill()], {})
    monkeypatch.setattr(dte, "_resolve_api_key", lambda: "")
    review = dte.build_daily_eval(1, session_date=SESSION)
    assert "TRADE REVIEW" in review
    assert "$100.00" in review


def test_prompt_flags_off_plan_entries_explicitly(patched):
    """The model must be told which entries had no signal — not left to infer it."""
    patched([], [_fill(symbol="GME", underlying_symbol="GME")], {})
    data = dte.collect_session_trades(1, SESSION, "Robinhood")
    prompt = dte.build_eval_prompt(data)
    assert "NO ALERT — off-plan entry" in prompt
    assert "Entries with no alert (off-plan): 1" in prompt
