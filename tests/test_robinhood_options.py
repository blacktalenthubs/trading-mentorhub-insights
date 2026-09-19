"""Option-chain narrowing — the 'N nearest strikes each side' filter and greeks passthrough.

Robinhood network calls are monkeypatched; a dummy client is injected so no login
happens. READ-ONLY module — nothing here places an order.
"""
import types

import pytest

import robin_stocks.robinhood as rh
from brokers import robinhood_options as ro


def _chain(strikes, otype="call"):
    """Fake find_options_by_expiration output — one dict per strike."""
    return [
        {
            "chain_symbol": "NVDA", "type": otype, "expiration_date": "2026-09-19",
            "strike_price": str(s), "bid_price": "1.0", "ask_price": "1.2",
            "mark_price": "1.1", "delta": "0.5", "theta": "-0.1", "gamma": "0.02",
            "vega": "0.15", "implied_volatility": "0.42", "volume": "10", "open_interest": "100",
        }
        for s in strikes
    ]


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(rh, "get_latest_price", lambda *_a, **_k: ["220.0"], raising=False)
    strikes = [200, 205, 210, 212.5, 215, 217.5, 220, 222.5, 225, 230, 235, 240, 250, 260]
    monkeypatch.setattr(
        rh, "find_options_by_expiration", lambda *_a, **_k: _chain(strikes), raising=False
    )


def test_near_keeps_n_strikes_each_side_of_spot(patched):
    client = types.SimpleNamespace()  # injected -> no login
    data = ro.fetch_option_greeks("NVDA", "2026-09-19", "call", near=3, client=client)
    kept = sorted(r["strike"] for r in data["rows"])
    assert data["underlying_price"] == 220.0
    # 3 below spot (215, 217.5 ... nearest 3 under 220) and 3 at/above (220, 222.5, 225)
    assert kept == [212.5, 215, 217.5, 220, 222.5, 225]


def test_near_overrides_band(patched):
    client = types.SimpleNamespace()
    # band would keep ±1% (~218-222); near=5 must win and keep 5 each side.
    data = ro.fetch_option_greeks("NVDA", "2026-09-19", "call", moneyness_pct=0.01, near=5, client=client)
    assert len(data["rows"]) == 10  # 5 below + 5 at/above


def test_greeks_pass_through(patched):
    client = types.SimpleNamespace()
    data = ro.fetch_option_greeks("NVDA", "2026-09-19", "call", near=1, client=client)
    r = data["rows"][0]
    assert r["gamma"] == 0.02 and r["vega"] == 0.15 and r["delta"] == 0.5 and r["theta"] == -0.1


def test_fetch_expirations_returns_sorted_listed_dates(monkeypatch):
    monkeypatch.setattr(
        rh, "get_chains",
        lambda *_a, **_k: {"expiration_dates": ["2027-01-15", "2026-10-16", "2026-09-25", ""]},
        raising=False,
    )
    client = types.SimpleNamespace()  # injected -> no login
    exps = ro.fetch_expirations("CRDO", client=client)
    assert exps == ["2026-09-25", "2026-10-16", "2027-01-15"]  # sorted, blanks dropped


def test_band_still_works_when_near_zero(patched):
    client = types.SimpleNamespace()
    data = ro.fetch_option_greeks("NVDA", "2026-09-19", "call", moneyness_pct=0.05, near=0, client=client)
    # ±5% of 220 = 209..231
    kept = sorted(r["strike"] for r in data["rows"])
    assert min(kept) >= 209 and max(kept) <= 231
