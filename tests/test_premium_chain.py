"""Premium Desk live-chain parsing — Alpaca snapshots → sized put rows (no network)."""
import datetime as dt
from analytics.premium_chain import _occ_parse, _build_from_chain, NEAR


class _Q:
    def __init__(self, bid, ask): self.bid_price, self.ask_price = bid, ask

class _G:
    def __init__(self, delta, theta): self.delta, self.theta = delta, theta

class _Snap:
    def __init__(self, bid, ask, delta, iv, theta=-0.05):
        self.latest_quote = _Q(bid, ask)
        self.greeks = _G(delta, theta)
        self.implied_volatility = iv


def test_occ_parse():
    assert _occ_parse("GOOGL261107P00330000") == ("2026-11-07", "P", 330.0)
    assert _occ_parse("SPY261031P00731000") == ("2026-10-31", "P", 731.0)
    assert _occ_parse("junk") is None


def test_build_picks_30dte_and_shapes_rows():
    today = dt.date(2026, 10, 3)
    # two expirations: ~7 DTE and ~35 DTE → the 35-DTE one wins (closest to 30)
    raw = {
        "GOOGL261010P00320000": _Snap(1.0, 1.2, -0.18, 0.22),   # 7 DTE
        "GOOGL261107P00320000": _Snap(4.1, 4.5, -0.30, 0.26),   # 35 DTE
        "GOOGL261107P00330000": _Snap(6.0, 6.4, -0.40, 0.27),   # 35 DTE
    }
    out = _build_from_chain(raw, price=343.0, today=today)
    assert out["available"] is True
    assert out["source"] == "alpaca"
    assert out["expiration"] == "2026-11-07" and out["dte"] == 35
    # only the 35-DTE puts, sorted by strike, correctly shaped
    assert [r["strike"] for r in out["rows"]] == [320.0, 330.0]
    r0 = out["rows"][0]
    assert r0["bid"] == 4.1 and r0["ask"] == 4.5 and r0["mark"] == 4.3
    assert r0["delta"] == -0.3 and r0["iv"] == 26.0   # iv scaled to %


def test_build_empty_chain():
    assert _build_from_chain({}, price=100.0)["available"] is False


def test_build_skips_calls_and_bad_strikes():
    today = dt.date(2026, 10, 3)
    raw = {"X261107C00100000": _Snap(1, 1.1, 0.3, 0.2)}  # a CALL → ignored
    assert _build_from_chain(raw, price=100.0, today=today)["available"] is False
