"""Volume-profile signal engine — POC math and the reclaim/confluence triggers."""
import pandas as pd
import pytest

from analytics.volume_profile_signals import (
    compute_profile,
    detect_signals,
    rolling_vwap,
)


def _df(rows):
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])


def _base(n=150, price=100.0, vol=10.0):
    """n bars tightly around `price` — concentrates volume there (a fat POC)."""
    return [[price, price + 1, price - 1, price, vol] for _ in range(n)]


def test_poc_lands_where_volume_concentrates():
    rows = _base(120, price=100.0, vol=20.0) + _base(30, price=80.0, vol=1.0)
    prof = compute_profile(_df(rows))
    assert prof is not None
    assert 98.0 <= prof.poc <= 102.0          # POC at the high-volume price
    assert prof.val < prof.poc < prof.vah      # value area brackets the POC


def test_poc_reclaim_fires_with_open_above():
    rows = _base(150, price=100.0, vol=20.0)
    # Last bar: dips to the POC, OPENS above it, holds above → reclaim.
    rows[-1] = [100.5, 102.0, 99.6, 101.5, 15.0]
    sigs = detect_signals(_df(rows), "TEST")
    kinds = {s.kind for s in sigs}
    assert "poc_reclaim" in kinds


def test_poc_reclaim_needs_open_above_not_a_pokethrough():
    rows = _base(150, price=100.0, vol=20.0)
    # Opens BELOW the POC and closes below → not a hold, must not fire poc_reclaim.
    rows[-1] = [98.0, 100.2, 97.0, 98.5, 15.0]
    sigs = detect_signals(_df(rows), "TEST")
    assert "poc_reclaim" not in {s.kind for s in sigs}


def test_confluence_tags_a_nearby_ma():
    # Flat at 100 → 20 SMA ≈ 100 ≈ POC, so a POC reclaim should tag the 20 SMA.
    rows = _base(150, price=100.0, vol=20.0)
    rows[-1] = [100.3, 101.5, 99.7, 101.0, 15.0]
    sigs = detect_signals(_df(rows), "TEST")
    poc = next(s for s in sigs if s.kind == "poc_reclaim")
    assert "20 SMA" in poc.confluence


def test_vwap_loss_is_gated_to_short_universe():
    rows = _base(150, price=100.0, vol=20.0)
    # Gap-and-close below VWAP.
    rows[-1] = [95.0, 96.0, 93.0, 94.0, 30.0]
    assert "vwap_loss" not in {s.kind for s in detect_signals(_df(rows), "AAPL", short_ok=False)}
    assert "vwap_loss" in {s.kind for s in detect_signals(_df(rows), "SPY", short_ok=True)}


def test_rolling_vwap_matches_manual():
    rows = [[10, 10, 10, 10, 2], [20, 20, 20, 20, 3]]
    # hlc3 = 10 and 20; vwap = (10*2 + 20*3)/5 = 16
    assert rolling_vwap(_df(rows)) == pytest.approx(16.0)
