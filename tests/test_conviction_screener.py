"""Unit tests for the conviction screener scoring + hard gates (synthetic data)."""

import numpy as np
import pandas as pd
import pytest

from analytics.conviction_screener import (
    evaluate_conviction,
    rank_conviction,
    ConvictionCandidate,
    MARKET_CAP_CEILING,
)


def _uptrend(n=250, start=50.0, end=120.0, seed=1):
    """A clean uptrend that sits well above its rising 50-day MA."""
    rng = np.random.default_rng(seed)
    px = np.linspace(start, end, n) * (1 + rng.normal(0, 0.008, n))
    return pd.DataFrame({"Close": px, "Open": px, "High": px * 1.01, "Low": px * 0.99, "Volume": [1e6] * n})


def _downtrend(n=250, start=120.0, end=60.0):
    px = np.linspace(start, end, n)
    return pd.DataFrame({"Close": px, "Open": px, "High": px * 1.01, "Low": px * 0.99, "Volume": [1e6] * n})


STRONG = {"rec_mean": 1.6, "rec_key": "buy", "num_analysts": 14,
          "target_mean": 160.0, "market_cap": 8e9, "sector": "Technology"}


def test_strong_uptrend_passes_and_scores():
    c = evaluate_conviction("CRDO", "AI Chips", _uptrend(), spy_ret_20d=2.0, analyst=STRONG)
    assert c is not None
    assert c.above_ma50 and c.ma_stacked
    assert c.pct_days_above_50 >= 90
    assert c.target_upside_pct is not None and c.target_upside_pct > 0
    assert c.score > 0 and c.grade in ("A", "B", "C")


def test_weak_rating_is_gated_out():
    weak = {**STRONG, "rec_mean": 3.3, "rec_key": "hold"}
    assert evaluate_conviction("X", "AI Chips", _uptrend(), 2.0, weak) is None


def test_thin_coverage_does_not_gate_on_rating():
    # Same weak mean but only 2 analysts → rating shouldn't disqualify it.
    thin = {**STRONG, "rec_mean": 3.3, "num_analysts": 2}
    assert evaluate_conviction("X", "AI Chips", _uptrend(), 2.0, thin) is not None


def test_mega_cap_is_gated_out():
    big = {**STRONG, "market_cap": MARKET_CAP_CEILING + 1}
    assert evaluate_conviction("X", "AI Chips", _uptrend(), 2.0, big) is None


def test_below_50ma_is_gated_out():
    assert evaluate_conviction("X", "AI Chips", _downtrend(), 2.0, STRONG) is None


def test_missing_analyst_still_included_but_lower_score():
    full = evaluate_conviction("X", "AI Chips", _uptrend(), 2.0, STRONG)
    bare = evaluate_conviction("X", "AI Chips", _uptrend(), 2.0, {})
    assert bare is not None
    assert bare.rec_mean is None
    assert bare.score < full.score  # analyst conviction contributes to the score


def test_too_little_history_returns_none():
    short = _uptrend(n=40)
    assert evaluate_conviction("X", "AI Chips", short, 2.0, STRONG) is None


def test_rank_assigns_descending_rank_by_score():
    a = evaluate_conviction("A", "AI Chips", _uptrend(seed=1), 2.0, STRONG)
    b = evaluate_conviction("B", "AI Chips", _uptrend(seed=2), 2.0, {**STRONG, "rec_mean": 2.4})
    ranked = rank_conviction([b, a])
    assert [c.rank for c in ranked] == [1, 2]
    assert ranked[0].score >= ranked[1].score
