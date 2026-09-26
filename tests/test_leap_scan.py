"""LEAP scan — quality gate, index exemption, grade, and quality-scaled RSI trigger."""
import numpy as np
import pandas as pd

from analytics import leap_scan as L
from analytics import leap_universe as U


def _bars(start, end, n, freq):
    idx = pd.date_range("2021-01-01", periods=n, freq=freq)
    c = pd.Series(np.linspace(start, end, n), index=idx)
    return pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c, "Volume": 1e6}, index=idx)


ELITE = {"market_cap": 1.5e12, "revenue_growth_pct": 22, "net_margin_pct": 25,
         "gross_margin_pct": 70, "eps_growth_pct": 15, "consensus": "Strong Buy"}


def test_grade_boundaries():
    assert L._grade(90) == "A"
    assert L._grade(70) == "B"
    assert L._grade(55) == "C"
    assert L._grade(20) == "D"


def test_falling_knife_dropped():
    d = _bars(200, 120, 260, "D"); w = _bars(180, 120, 60, "W")
    bad = {"market_cap": 5e9, "revenue_growth_pct": -8, "net_margin_pct": -3,
           "gross_margin_pct": 20, "consensus": "Sell"}
    assert L.score_leap("XYZ", d, w, bad, None, False) is None


def test_index_skips_gate_and_is_elite():
    d = _bars(200, 150, 260, "D"); w = _bars(180, 150, 60, "W")
    r = L.score_leap("SPY", d, w, None, None, True)
    assert r is not None and r["kind"] == "index" and r["grade"] == "A"
    assert r["quality_tier"] == "elite"


def test_elite_rsi_gate_reaches_35():
    # An elite name at daily RSI ~34 should qualify (gate = 30 + bonus 5 = 35),
    # where a merely-strong name (gate ~30) would not.
    score, bonus, tier, passes, warming, _ = L._quality(ELITE, False)
    assert tier == "elite" and bonus == 5


def test_breadth_divergence_flagged():
    # RSP oversold (RSI ~38) while cap-weight SPY holds up (RSI ~50) → breadth flag + note.
    d = _bars(230, 210, 260, "D"); w = _bars(240, 210, 60, "W")
    r = L.score_leap("RSP", d, w, None, None, True, spy_rsi_d=50.0)
    assert r is not None and r["breadth"] is True
    assert any("breadth washout" in s for s in r["rationale"])
    # No SPY reference → no breadth claim.
    r2 = L.score_leap("RSP", d, w, None, None, True, spy_rsi_d=None)
    assert r2["breadth"] is False


def test_universe_has_indexes_and_stocks():
    assert U.is_index("SPY") and not U.is_index("AAPL")
    assert "ABNB" in U.UNIVERSE and "QQQ" in U.UNIVERSE
