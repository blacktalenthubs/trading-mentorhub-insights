"""LEAP chain — expiration picker + liquidity gate (no network)."""
import datetime as dt

from analytics import leap_chain as C


def test_pick_leap_expiration_prefers_18mo():
    today = dt.date(2026, 9, 25)
    exps = ["2026-10-16", "2027-01-15", "2027-06-18", "2028-01-21", "2028-06-16"]
    e, d = C._pick_leap_expiration(exps, today)
    assert e == "2028-01-21" and 400 < d < 560   # nearest real LEAP to ~540d


def test_pick_falls_back_to_longest_when_no_leap():
    today = dt.date(2026, 9, 25)
    e, d = C._pick_leap_expiration(["2026-10-16", "2026-12-18"], today)
    assert e == "2026-12-18"           # longest available when nothing reaches the LEAP window


def test_pick_none_when_empty():
    assert C._pick_leap_expiration([], dt.date(2026, 9, 25)) is None


def test_liquid_gate():
    assert C._liquid({"open_interest": 200, "ask": 5.0, "spread_pct": 8.0}) is True
    assert C._liquid({"open_interest": 5, "ask": 5.0, "spread_pct": 8.0}) is False    # thin OI
    assert C._liquid({"open_interest": 500, "ask": 5.0, "spread_pct": 40.0}) is False  # wide spread
    assert C._liquid({"open_interest": 500, "ask": 0, "spread_pct": None}) is False    # no ask
