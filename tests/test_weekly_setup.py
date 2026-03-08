"""Tests for weekly swing-trade setup detection (analyze_weekly_setup)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helper: build synthetic weekly OHLCV data
# ---------------------------------------------------------------------------

def _make_weekly_df(
    n: int = 12,
    base_price: float = 100.0,
    volatility_pct: float = 0.02,
    trend_pct: float = 0.0,
    base_volume: int = 1_000_000,
    volume_pattern: str = "flat",
    breakout_last: bool = False,
    breakout_volume_mult: float = 1.5,
) -> pd.DataFrame:
    """Build synthetic weekly OHLCV DataFrame.

    Parameters
    ----------
    n : int
        Number of weekly bars.
    base_price : float
        Starting close price.
    volatility_pct : float
        Max high-low range as fraction of close.
    trend_pct : float
        Per-bar trend (0.01 = +1% per bar).
    base_volume : int
        Average volume per bar.
    volume_pattern : str
        "flat" = constant, "contracting" = base bars at 70% of prior.
    breakout_last : bool
        If True, last bar closes above base_high with volume spike.
    breakout_volume_mult : float
        Volume multiplier for breakout bar.
    """
    dates = pd.date_range("2025-06-06", periods=n, freq="W-FRI")
    rows = []
    price = base_price

    for i in range(n):
        price *= (1 + trend_pct)
        half_range = price * volatility_pct / 2
        o = price - half_range * 0.3
        h = price + half_range
        lo = price - half_range
        c = price

        if volume_pattern == "contracting" and i >= n // 2:
            vol = int(base_volume * 0.70)
        else:
            vol = base_volume

        if breakout_last and i == n - 1:
            # Breakout: close above prior highs
            c = price + half_range * 1.5
            h = c + half_range * 0.5
            vol = int(base_volume * breakout_volume_mult)

        rows.append({"Open": o, "High": h, "Low": lo, "Close": c, "Volume": vol})

    return pd.DataFrame(rows, index=dates)


def _default_wmas(aligned: bool = True) -> dict:
    """Return WMA dict. If aligned, WMA10 > WMA20 > WMA50."""
    if aligned:
        return {"wma10": 102.0, "wma20": 100.0, "wma50": 96.0}
    return {"wma10": 96.0, "wma20": 100.0, "wma50": 102.0}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBaseDetection:
    """Phase 1: base detection logic."""

    def test_tight_base_detected(self):
        from analytics.intel_hub import analyze_weekly_setup

        # 12 bars, ~2% volatility = tight range well under 12%
        df = _make_weekly_df(n=12, volatility_pct=0.02)
        result = analyze_weekly_setup(df, _default_wmas())

        assert result["setup_type"] == "BASE_FORMING"
        assert result["base_weeks"] >= 3

    def test_wide_range_no_base(self):
        from analytics.intel_hub import analyze_weekly_setup

        # 20% volatility = range too wide for base
        df = _make_weekly_df(n=12, volatility_pct=0.25)
        result = analyze_weekly_setup(df, _default_wmas())

        assert result["setup_type"] != "BASE_FORMING"
        assert result["setup_type"] != "BREAKOUT"

    def test_minimum_weeks_required(self):
        from analytics.intel_hub import analyze_weekly_setup

        # Only 3 total bars = only 2 lookback bars (excluding current)
        # Not enough for 3-week minimum base
        df = _make_weekly_df(n=3, volatility_pct=0.02)
        # Need at least WEEKLY_BASE_LOOKBACK+1 bars; with only 3, it returns
        # NO_SETUP due to insufficient data
        result = analyze_weekly_setup(df, _default_wmas())

        assert result["setup_type"] == "NO_SETUP"

    def test_volume_contraction_detected(self):
        from analytics.intel_hub import analyze_weekly_setup

        # Build a 12-bar DataFrame where first 5 bars are wide-range (no base)
        # and last 7 bars are tight-range with lower volume.
        # This ensures the base is detected in the tight region with prior bars
        # available for volume comparison.
        dates = pd.date_range("2025-06-06", periods=12, freq="W-FRI")
        rows = []
        for i in range(12):
            if i < 5:
                # Wide range, high volume — excluded from base
                rows.append({
                    "Open": 95 + i, "High": 110 + i, "Low": 85 + i,
                    "Close": 100 + i, "Volume": 2_000_000,
                })
            else:
                # Tight range, low volume — forms the base
                rows.append({
                    "Open": 104.5, "High": 105.5, "Low": 104.0,
                    "Close": 105.0, "Volume": 500_000,
                })
        df = pd.DataFrame(rows, index=dates)
        result = analyze_weekly_setup(df, _default_wmas())

        assert result["volume_contracting"] is True
        assert result["volume_ratio"] < 0.85


class TestSetupClassification:
    """Phase 2: setup type classification."""

    def test_breakout_above_base(self):
        from analytics.intel_hub import analyze_weekly_setup

        df = _make_weekly_df(
            n=12, volatility_pct=0.02,
            breakout_last=True, breakout_volume_mult=1.5,
        )
        result = analyze_weekly_setup(df, _default_wmas())

        assert result["setup_type"] == "BREAKOUT"

    def test_breakout_without_volume(self):
        from analytics.intel_hub import analyze_weekly_setup

        # Breakout price but volume only 0.8x (below 1.2x threshold)
        df = _make_weekly_df(
            n=12, volatility_pct=0.02,
            breakout_last=True, breakout_volume_mult=0.8,
        )
        result = analyze_weekly_setup(df, _default_wmas())

        # Without volume, it should NOT be classified as BREAKOUT
        assert result["setup_type"] != "BREAKOUT"

    def test_pullback_to_wma(self):
        from analytics.intel_hub import analyze_weekly_setup

        # Wide range so no base forms, but price near WMA20 in uptrend
        df = _make_weekly_df(n=12, volatility_pct=0.25, base_price=100.0)
        close = float(df.iloc[-1]["Close"])

        # Set WMAs so price is within 2% of WMA20, above WMA50, aligned
        wmas = {
            "wma10": close * 1.01,
            "wma20": close * 1.005,  # within 2%
            "wma50": close * 0.95,
        }

        result = analyze_weekly_setup(df, wmas)
        assert result["setup_type"] == "PULLBACK"

    def test_pullback_below_wma50_no_setup(self):
        from analytics.intel_hub import analyze_weekly_setup

        df = _make_weekly_df(n=12, volatility_pct=0.25, base_price=100.0)
        close = float(df.iloc[-1]["Close"])

        # Price near WMA20 but BELOW WMA50
        wmas = {
            "wma10": close * 1.01,
            "wma20": close * 1.005,
            "wma50": close * 1.10,  # above price
        }

        result = analyze_weekly_setup(df, wmas)
        assert result["setup_type"] != "PULLBACK"


class TestLevelComputation:
    """Phase 3: entry/stop/target level computation."""

    def test_base_forming_levels(self):
        from analytics.intel_hub import analyze_weekly_setup

        df = _make_weekly_df(n=12, volatility_pct=0.02)
        result = analyze_weekly_setup(df, _default_wmas())

        assert result["setup_type"] == "BASE_FORMING"
        assert result["entry"] == result["base_high"]
        assert result["stop"] == result["base_low"]
        assert result["target_1"] is not None
        assert result["target_2"] is not None
        # T1 = base_high + range, T2 = base_high + 2*range
        base_range = result["base_high"] - result["base_low"]
        assert abs(result["target_1"] - (result["base_high"] + base_range)) < 0.1
        assert abs(result["target_2"] - (result["base_high"] + 2 * base_range)) < 0.1

    def test_breakout_levels(self):
        from analytics.intel_hub import analyze_weekly_setup

        df = _make_weekly_df(
            n=12, volatility_pct=0.02,
            breakout_last=True, breakout_volume_mult=1.5,
        )
        result = analyze_weekly_setup(df, _default_wmas())

        assert result["setup_type"] == "BREAKOUT"
        close = float(df.iloc[-1]["Close"])
        assert result["entry"] == round(close, 2)
        assert result["stop"] == result["base_high"]

    def test_no_setup_none_levels(self):
        from analytics.intel_hub import analyze_weekly_setup

        # Too few bars -> NO_SETUP
        df = _make_weekly_df(n=3, volatility_pct=0.02)
        result = analyze_weekly_setup(df, _default_wmas())

        assert result["setup_type"] == "NO_SETUP"
        assert result["entry"] is None
        assert result["stop"] is None
        assert result["target_1"] is None
        assert result["target_2"] is None


class TestScoring:
    """Phase 4: score calculation."""

    def test_scoring_tight_base_high(self):
        from analytics.intel_hub import analyze_weekly_setup

        # Tight base + contracting volume + aligned WMAs
        df = _make_weekly_df(
            n=12, volatility_pct=0.02, volume_pattern="contracting",
        )
        wmas = _default_wmas(aligned=True)
        result = analyze_weekly_setup(df, wmas)

        # tight base (30) + vol contraction (15) + aligned (25) + candle (5-15) + R:R
        assert result["score"] >= 70
        assert result["score_label"] in ("A+", "A")

    def test_insufficient_data(self):
        from analytics.intel_hub import analyze_weekly_setup

        df = _make_weekly_df(n=5, volatility_pct=0.02)
        result = analyze_weekly_setup(df, {})

        assert result["setup_type"] == "NO_SETUP"
        assert result["score"] == 0


class TestEdgeDescription:
    """Phase 6: edge text content."""

    def test_edge_description_content(self):
        from analytics.intel_hub import analyze_weekly_setup

        df = _make_weekly_df(n=12, volatility_pct=0.02)
        result = analyze_weekly_setup(df, _default_wmas())

        assert result["setup_type"] == "BASE_FORMING"
        edge = result["edge"]
        # Should mention base weeks and price range
        assert "week base" in edge.lower() or "base" in edge.lower()
        assert result["base_low"] is not None
        # Edge should contain the base_low value (formatted)
        assert f"{result['base_low']:.2f}" in edge

    def test_no_setup_edge(self):
        from analytics.intel_hub import analyze_weekly_setup

        df = _make_weekly_df(n=3, volatility_pct=0.02)
        result = analyze_weekly_setup(df, {})

        assert "no weekly setup" in result["edge"].lower()
