"""Premium Desk S2 scoring engine — pure logic, no network/DB.

Tests the risk-tier classification, the qualify gate, IV-warming fallback, score
bounds, and the rank ordering. The sub-scorers (_tier/_trend_score/_rsi_score) are
deterministic given posture, so we drive them directly; score_candidate is exercised
on synthetic OHLC frames for the end-to-end shape.
"""
import numpy as np
import pandas as pd

from analytics import premium_score as ps
from analytics.premium_score import PremiumCandidate, rank, score_candidate


# --- tier classification -----------------------------------------------------

def test_tier_high_when_below_200():
    # Structure broken → high risk regardless of everything else.
    assert ps._tier(above200=False, above50=True, r50=True, rd=55, rw=55, rev_d=False) == "high"


def test_tier_high_on_falling_knife():
    # Deep daily RSI, no reversal, above the 200 but still a knife.
    assert ps._tier(above200=True, above50=False, r50=False, rd=22, rw=45, rev_d=False) == "high"


def test_tier_low_on_clean_uptrend():
    assert ps._tier(above200=True, above50=True, r50=True, rd=58, rw=52, rev_d=False) == "low"


def test_tier_low_blocked_when_overbought():
    # Above structure but stretched (rd>70) → not low, drops to med.
    assert ps._tier(above200=True, above50=True, r50=True, rd=78, rw=52, rev_d=False) == "med"


def test_tier_med_default():
    # Above 200 but below a rising 50 → neither clean nor broken.
    assert ps._tier(above200=True, above50=False, r50=False, rd=50, rw=50, rev_d=False) == "med"


# --- component score bounds --------------------------------------------------

def test_trend_score_bounds_and_direction():
    strong = ps._trend_score(100, 90, 85, 80, True, True, True, True, True)
    weak = ps._trend_score(70, 90, 95, 100, False, False, False, False, False)
    assert 0 <= weak < strong <= 100
    assert strong > 70 and weak < 40


def test_rsi_score_rewards_reversal_penalizes_overbought():
    rev = ps._rsi_score(rd=35, rw=45, rev_d=True, rev_w=False)
    ob = ps._rsi_score(rd=80, rw=72, rev_d=False, rev_w=False)
    assert rev > ob
    assert 0 <= ob <= 100 and 0 <= rev <= 100


# --- score_candidate end-to-end ----------------------------------------------

def _frame(closes):
    n = len(closes)
    c = np.asarray(closes, float)
    # green last bar, low wicks a hair under the open
    o = c * 0.995
    o[-1] = c[-1] * 0.99
    low = np.minimum(o, c) * 0.99
    high = np.maximum(o, c) * 1.01
    vol = np.full(n, 1_000_000.0)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame({"Open": o, "High": high, "Low": low, "Close": c, "Volume": vol}, index=idx)


def test_uptrend_qualifies_with_rich_iv():
    # 260 rising bars → above a rising 200/50/20; give it a rich IV rank.
    daily = _frame(np.linspace(50, 150, 260))
    weekly = _frame(np.linspace(50, 150, 60))
    iv = {"symbol": "NVDL", "iv": 55.0, "rank": 72.0, "percentile": 68.0, "n": 90,
          "low": 40.0, "high": 80.0}
    c = score_candidate(daily, weekly, "NVDL", iv, theme="Nvidia 2x")
    assert c is not None
    assert c.above_200 and c.qualifies and not c.iv_warming
    assert 0 <= c.score <= 100
    assert c.side == "put" and c.strike < c.price
    assert any("IV rank" in r for r in c.rationale)


def test_thin_iv_does_not_qualify():
    daily = _frame(np.linspace(50, 150, 260))
    weekly = _frame(np.linspace(50, 150, 60))
    iv = {"symbol": "AAPU", "iv": 30.0, "rank": 20.0, "percentile": 25.0, "n": 90,
          "low": 25.0, "high": 60.0}
    c = score_candidate(daily, weekly, "AAPU", iv, theme="Apple 2x")
    assert c is not None and not c.qualifies  # rank 20 < QUALIFY_IVR


def test_warming_qualifies_and_flags():
    # No IV history yet → warming: still shown (qualifies), rank neutralized.
    daily = _frame(np.linspace(50, 150, 260))
    weekly = _frame(np.linspace(50, 150, 60))
    c = score_candidate(daily, weekly, "METU", None, theme="Meta 2x")
    assert c is not None and c.iv_warming and c.qualifies and c.iv_rank == 0.0
    assert any("warming" in r for r in c.rationale)


def test_downtrend_is_high_tier():
    daily = _frame(np.linspace(150, 60, 260))  # falling → below 200
    weekly = _frame(np.linspace(150, 60, 60))
    iv = {"symbol": "TSLL", "iv": 90.0, "rank": 85.0, "percentile": 80.0, "n": 90,
          "low": 50.0, "high": 100.0}
    c = score_candidate(daily, weekly, "TSLL", iv, theme="Tesla 2x")
    assert c is not None and not c.above_200 and c.tier == "high"
    assert c.strike < c.price * 0.95  # high tier sits further OTM


def test_short_frame_returns_none():
    assert score_candidate(_frame([1, 2, 3]), _frame([1, 2, 3]), "X", None) is None


# --- rank ordering -----------------------------------------------------------

def _cand(sym, tier, score, qualifies=True):
    return PremiumCandidate(
        symbol=sym, theme="", price=100, iv=50, iv_rank=60, iv_pct=60, iv_n=90,
        iv_warming=False, rsi_d=50, rsi_w=50, above_200=True, above_50=True, above_20=True,
        score=score, tier=tier, qualifies=qualifies,
    )


def test_rank_qualifiers_first_then_tier_then_score():
    out = rank([
        _cand("A", "high", 90),
        _cand("B", "low", 40),
        _cand("C", "med", 80),
        _cand("D", "low", 70),
        _cand("E", "low", 95, qualifies=False),  # non-qualifier sinks despite top score
    ])
    assert [c.symbol for c in out] == ["D", "B", "C", "A", "E"]
