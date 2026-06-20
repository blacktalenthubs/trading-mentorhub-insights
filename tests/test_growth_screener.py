"""Tests for the Growth Leaders scorer (#64-M)."""

import numpy as np
import pandas as pd

from analytics.growth_screener import evaluate_growth, rank_growth


def _df(closes, vols=None):
    return pd.DataFrame({
        "Close": closes,
        "Volume": vols if vols is not None else np.full(len(closes), 1_000_000.0),
    })


def _uptrend(n=260, start=100.0, end=220.0):
    # steady rise → Stage 2 (close > rising 150MA, 50MA > 150MA), near 52w high.
    closes = np.linspace(start, end, n)
    # up-biased volume so accumulation (up-vol / down-vol) > 1
    vols = np.where(np.diff(closes, prepend=closes[0]) >= 0, 1_500_000.0, 600_000.0)
    return _df(closes, vols)


def _downtrend(n=260, start=220.0, end=100.0):
    closes = np.linspace(start, end, n)
    return _df(closes)


STRONG_FUND = {
    "rev_growth_pct": 42.0, "rev_accelerating": True,
    "eps_growth_pct": 35.0, "gross_margin_pct": 62.0, "consensus": "Buy",
}


def test_strong_growth_leader_scores_high():
    c = evaluate_growth("NVDA", "Tech", _uptrend(), spy_ret_window=5.0, fund=STRONG_FUND)
    assert c is not None
    assert c.stage2 is True
    assert c.grade == "A"
    assert c.score >= 80
    assert c.scorecard["rev_growth"] == "pass"
    assert c.scorecard["stage2"] == "pass"
    assert c.scorecard["rs_leadership"] == "pass"


def test_insufficient_bars_returns_none():
    short = _df(np.linspace(100, 120, 100))
    assert evaluate_growth("X", "Tech", short, 5.0, STRONG_FUND) is None


def test_missing_fundamentals_are_pending_not_faked():
    c = evaluate_growth("X", "Tech", _uptrend(), 5.0, fund={})
    assert c is not None
    assert c.scorecard["rev_growth"] == "pending"
    assert c.scorecard["earnings"] == "pending"
    assert c.scorecard["gross_margin"] == "pending"
    # technical criteria still score
    assert c.scorecard["stage2"] == "pass"
    # never-measurable always pending
    assert c.scorecard["roic"] == "pending" and c.scorecard["moat"] == "pending"


def test_downtrend_fails_stage2_and_scores_low():
    c = evaluate_growth("X", "Tech", _downtrend(), 5.0, STRONG_FUND)
    assert c is not None
    assert c.stage2 is False
    assert c.scorecard["stage2"] == "fail"
    assert c.grade != "A"


def test_accelerating_revenue_beats_non_accelerating():
    fast = {**STRONG_FUND, "rev_accelerating": True}
    slow = {**STRONG_FUND, "rev_accelerating": False}
    cf = evaluate_growth("A", "Tech", _uptrend(), 5.0, fast)
    cs = evaluate_growth("B", "Tech", _uptrend(), 5.0, slow)
    assert cf.score > cs.score


def test_weak_revenue_fails_criterion():
    weak = {**STRONG_FUND, "rev_growth_pct": 8.0}
    c = evaluate_growth("X", "Tech", _uptrend(), 5.0, weak)
    assert c.scorecard["rev_growth"] == "fail"


def test_rank_orders_by_score_and_assigns_rank():
    a = evaluate_growth("A", "Tech", _uptrend(), 5.0, STRONG_FUND)
    b = evaluate_growth("B", "Tech", _uptrend(), 5.0, {"rev_growth_pct": 8.0})
    ranked = rank_growth([b, a])
    assert ranked[0].symbol == "A"
    assert ranked[0].rank == 1 and ranked[1].rank == 2
