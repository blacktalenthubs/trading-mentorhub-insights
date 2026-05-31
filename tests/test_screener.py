"""Tests for the In-Play Volume Screener core (spec 62).

Covers the deterministic, offline-verifiable logic: universe filtering, RVOL,
ranking, refine-filter presets (direction-aware), and read-only setup mapping.
Live yfinance/Alpaca fetch + the API/scheduler are covered separately.
"""

from datetime import datetime, time as dt_time
from types import SimpleNamespace

import numpy as np
import pandas as pd

from analytics.screener import (
    InPlayEntry,
    UniverseRow,
    apply_refine_filters,
    apply_user_view,
    effective_settings,
    filter_universe,
    is_market_open,
    rank_in_play,
    rank_swing,
    relative_volume,
    scan_setups,
    session_fraction,
    swing_signals,
    _result_to_setup,
)


# --- FR-1: universe filtering ------------------------------------------------

def _universe():
    return [
        UniverseRow("BIG", market_cap=50e9, last_price=200, avg_dollar_vol=500e6),
        UniverseRow("MID", market_cap=3e9, last_price=40, avg_dollar_vol=50e6),
        UniverseRow("PENNY", market_cap=3e9, last_price=2.5, avg_dollar_vol=50e6),   # price floor
        UniverseRow("THIN", market_cap=3e9, last_price=40, avg_dollar_vol=1e6),      # $-vol floor
        UniverseRow("SMALL", market_cap=500e6, last_price=40, avg_dollar_vol=50e6),  # cap floor
    ]


def test_filter_universe_enforces_all_floors():
    kept = {r.symbol for r in filter_universe(_universe())}
    assert kept == {"BIG", "MID"}


def test_raising_cap_floor_shrinks_universe():
    base = len(filter_universe(_universe(), market_cap_floor=2e9))
    higher = len(filter_universe(_universe(), market_cap_floor=10e9))
    assert higher < base


# --- FR-2: relative volume + ranking ----------------------------------------

def test_session_fraction_bounds():
    assert session_fraction(dt_time(9, 0)) == 0.0          # pre-open
    assert session_fraction(dt_time(16, 30)) == 1.0        # post-close
    mid = session_fraction(dt_time(12, 45))                # ~half session
    assert 0.4 < mid < 0.6


def test_relative_volume_detects_unusual_activity():
    # half the session elapsed; a stock already at its full average daily volume
    # is running ~2x normal pace.
    rv = relative_volume(today_cum_vol=1_000_000, avg_daily_vol=1_000_000, session_frac=0.5)
    assert round(rv, 1) == 2.0
    # a normal-pace stock sits near 1.0
    assert round(relative_volume(500_000, 1_000_000, 0.5), 1) == 1.0


def test_rank_orders_by_rvol_then_dollar_vol():
    entries = [
        InPlayEntry("A", 10, 1.0, rvol=1.2, dollar_vol=900e6, market_cap=9e9),   # huge $vol, normal rvol
        InPlayEntry("B", 10, 1.0, rvol=3.5, dollar_vol=80e6, market_cap=5e9),    # smaller $vol, high rvol
        InPlayEntry("C", 10, 1.0, rvol=3.5, dollar_vol=120e6, market_cap=6e9),   # tie rvol, bigger $vol
    ]
    ranked = rank_in_play(entries, top_n=3)
    assert [e.symbol for e in ranked] == ["C", "B", "A"]   # high rvol first; $vol breaks the C/B tie
    assert [e.rank for e in ranked] == [1, 2, 3]


def test_rank_respects_top_n():
    entries = [InPlayEntry(f"S{i}", 10, 0, rvol=float(i), dollar_vol=1, market_cap=9e9) for i in range(10)]
    assert len(rank_in_play(entries, top_n=3)) == 3


# --- FR-4: setup mapping (read-only signal_engine reuse) --------------------

def test_result_to_setup_maps_actionable_status():
    res = SimpleNamespace(support_status="AT SUPPORT", support_label="PDL Bounce",
                          entry=480.5, stop=476.0, target_1=489.0, score_label="Strong",
                          score=82, bias="long", pattern="normal")
    setup = _result_to_setup(res)
    assert setup and setup["pattern"] == "PDL Bounce" and setup["entry"] == 480.5


def test_result_to_setup_none_when_no_setup():
    assert _result_to_setup(SimpleNamespace(support_status="BROKEN")) is None
    assert _result_to_setup(None) is None


def test_scan_setups_uses_injected_analyzer_readonly():
    entries = [InPlayEntry("CRWD", 480, 2.1, rvol=3.2, dollar_vol=1.4e9, market_cap=116e9),
               InPlayEntry("XYZ", 30, -1.0, rvol=2.5, dollar_vol=50e6, market_cap=5e9)]
    fake = {"CRWD": SimpleNamespace(support_status="AT SUPPORT", support_label="PDL Bounce",
                                    entry=480.5, stop=476, target_1=489, score_label="Strong",
                                    score=82, bias="long", pattern="normal"),
            "XYZ": SimpleNamespace(support_status="BROKEN")}
    scan_setups(entries, hist_provider=lambda s: object(), analyzer=lambda hist, sym: fake[sym])
    assert entries[0].setup is not None      # CRWD has a setup
    assert entries[1].setup is None          # XYZ listed as mover, no setup


# --- FR-9: refine filters / presets (direction-aware) -----------------------

def _refine_set():
    return [
        InPlayEntry("LONGY", 100, 2, rvol=3.0, dollar_vol=1e8, market_cap=9e9, direction="long",
                    refine={"above_ema50": True, "above_vwap": True, "rsi": 60, "rs_vs_spy": 1.2}),
        InPlayEntry("SHORTY", 100, -3, rvol=3.0, dollar_vol=1e8, market_cap=9e9, direction="short",
                    refine={"above_ema50": False, "above_vwap": False, "rsi": 40, "rs_vs_spy": -0.5}),
        InPlayEntry("NEUTRAL", 100, 0, rvol=3.0, dollar_vol=1e8, market_cap=9e9, direction="long",
                    refine={"above_ema50": True, "above_vwap": False, "rsi": 80, "rs_vs_spy": 0.1}),
    ]


def test_momentum_long_preset_keeps_only_clean_longs():
    kept = {e.symbol for e in apply_refine_filters(_refine_set(), preset="momentum_long")}
    assert kept == {"LONGY"}


def test_short_preset_surfaces_short_setups():
    kept = {e.symbol for e in apply_refine_filters(_refine_set(), preset="short")}
    assert kept == {"SHORTY"}


def test_clearing_filters_returns_full_shortlist():
    assert len(apply_refine_filters(_refine_set(), preset="any")) == 3


def test_market_hours_gate():
    assert is_market_open(datetime(2026, 6, 1, 10, 0)) is True    # Mon 10:00 ET
    assert is_market_open(datetime(2026, 6, 1, 8, 0)) is False    # Mon pre-open
    assert is_market_open(datetime(2026, 6, 1, 16, 30)) is False  # Mon after close
    assert is_market_open(datetime(2026, 5, 30, 12, 0)) is False  # Saturday


def test_effective_settings_overlays_user_overrides():
    defaults = {"market_cap_floor": 2e9, "top_n": 30}
    assert effective_settings(defaults, {"top_n": 15}) == {"market_cap_floor": 2e9, "top_n": 15}
    assert effective_settings(defaults, {"top_n": None}) == defaults  # None ignored
    assert effective_settings(defaults, None) == defaults


def test_apply_user_view_filters_cap_and_trims():
    entries = [
        InPlayEntry("A", 10, 0, rvol=3, dollar_vol=1, market_cap=50e9),
        InPlayEntry("B", 10, 0, rvol=2, dollar_vol=1, market_cap=3e9),
        InPlayEntry("C", 10, 0, rvol=1, dollar_vol=1, market_cap=1e9),
    ]
    assert {e.symbol for e in apply_user_view(entries, market_cap_floor=2e9)} == {"A", "B"}
    assert [e.symbol for e in apply_user_view(entries, top_n=1)] == ["A"]


# --- swing screener (daily-bar Trend + MA defense) -------------------------

def _daily(closes):
    c = np.array(closes, dtype=float)
    return pd.DataFrame({"Close": c, "Low": c * 0.97, "High": c * 1.01, "Volume": np.full(len(c), 1e6)})


def test_swing_qualifies_when_closing_at_a_key_ma():
    # rise, then flat — the EMA catches up so price closes right at it (a pullback hold)
    series = [100 + 0.5 * i for i in range(200)] + [200.0] * 50
    cand = swing_signals(_daily(series), spy_ret_20d=0.0, symbol="PB")
    assert cand is not None and cand.setup is not None
    assert "EMA hold" in cand.setup["pattern"]
    assert cand.setup["stop"] < cand.setup["entry"] < cand.setup["target"]
    # tight stop: risk well under 5% (it's anchored just below the MA, not a far MA)
    assert (cand.setup["entry"] - cand.setup["stop"]) / cand.setup["entry"] < 0.05


def test_swing_rejects_extended_stock():
    # steep ramp → price is well above every MA → not a swing, must be rejected
    cand = swing_signals(_daily([100 + 1.5 * i for i in range(250)]), spy_ret_20d=0.0, symbol="EXT")
    assert cand is not None and cand.setup is None


def test_swing_rejects_downtrend():
    cand = swing_signals(_daily([200 - 0.3 * i for i in range(250)]), spy_ret_20d=0.0, symbol="DN")
    assert cand is not None and cand.setup is None


def test_swing_needs_enough_history():
    assert swing_signals(_daily([100 + i for i in range(30)]), symbol="SHORT") is None


def test_rank_swing_keeps_only_setups_sorted_by_rs():
    from analytics.screener import SwingCandidate
    a = SwingCandidate("A", 100, 5, 3.0, True, True, True, True, setup={"pattern": "20 EMA hold", "entry": 100, "stop": 98, "target": 106, "conviction": "High"})
    b = SwingCandidate("B", 100, 4, 1.0, True, True, True, True, setup={"pattern": "50 EMA hold", "entry": 100, "stop": 98, "target": 106, "conviction": "Moderate"})
    no = SwingCandidate("NO", 100, -2, -1.0, False, False, False, False, setup=None)
    ranked = rank_swing([no, b, a], top_n=10)
    assert [c.symbol for c in ranked] == ["A", "B"]  # no-setup dropped; stronger RS first
    assert ranked[0].rank == 1


def test_presets_are_none_safe():
    # live service sets rs_vs_spy / atr_pct to None — predicates must not raise.
    e = InPlayEntry("X", 100, 1, rvol=3.0, dollar_vol=1e8, market_cap=9e9, direction="long",
                    refine={"above_ema50": True, "above_vwap": True, "rsi": None, "rs_vs_spy": None})
    for preset in ("momentum_long", "pullback", "breakout", "short", "any"):
        apply_refine_filters([e], preset=preset)  # must not raise TypeError


def test_direction_filter_does_not_destroy_short_setups():
    # a long preset hides shorts, but they remain reachable (preserved) via 'short'
    long_view = apply_refine_filters(_refine_set(), preset="momentum_long")
    short_view = apply_refine_filters(_refine_set(), preset="short")
    assert "SHORTY" not in {e.symbol for e in long_view}
    assert "SHORTY" in {e.symbol for e in short_view}
