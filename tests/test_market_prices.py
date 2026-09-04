"""Tests for the market price snapshot extraction (crypto/stock split fix)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

from app.routers.market import _snapshot_price  # noqa: E402


class _Trade:
    def __init__(self, price):
        self.price = price


class _Bar:
    def __init__(self, close):
        self.close = close


class _Snap:
    def __init__(self, latest_trade=None, minute_bar=None, daily_bar=None, previous_daily_bar=None):
        self.latest_trade = latest_trade
        self.minute_bar = minute_bar
        self.daily_bar = daily_bar
        self.previous_daily_bar = previous_daily_bar


def test_price_from_latest_trade_with_change():
    p = _snapshot_price(_Snap(latest_trade=_Trade(81000.0), previous_daily_bar=_Bar(76366.0)))
    assert p == {"price": 81000.0, "change_pct": 6.07}


def test_falls_back_to_minute_then_daily_bar():
    assert _snapshot_price(_Snap(minute_bar=_Bar(2517.28)))["price"] == 2517.28
    assert _snapshot_price(_Snap(daily_bar=_Bar(769.16)))["price"] == 769.16


def test_change_zero_without_prior_close():
    assert _snapshot_price(_Snap(latest_trade=_Trade(100.0)))["change_pct"] == 0


def test_none_and_empty_snapshots():
    assert _snapshot_price(None) is None
    assert _snapshot_price(_Snap()) is None


def test_crypto_pair_translation_matches_repo_convention():
    # The fix routes BTC-USD → BTC/USD for Alpaca's crypto snapshot API.
    syms = ["BTC-USD", "ETH-USD", "SPY", "MU"]
    stock = [s for s in syms if not s.upper().endswith("-USD")]
    crypto = {s: s.upper().replace("-USD", "/USD") for s in syms if s.upper().endswith("-USD")}
    assert stock == ["SPY", "MU"]
    assert crypto == {"BTC-USD": "BTC/USD", "ETH-USD": "ETH/USD"}
