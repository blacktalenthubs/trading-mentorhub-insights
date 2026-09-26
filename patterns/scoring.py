"""Composite 0-100 score and the plain-English reason string.

Score = sum(weight_i * component_i) with every component in 0..1 and the
weights from ``ScoreWeights`` (defaults sum to 100):

    volume_dryup  30   how much volume contracted through the consolidation
    tightness     30   how tight/shallow the consolidation is vs its allowed max
    duration      20   how "built" the base is (length, or pole strength for a flag)
    trend         20   strength of the trend filter on the LAST bar (below)

The first three come from each detector's ``metrics`` (each module's docstring
documents its own normalization). ``trend`` is computed here, the same way for
every pattern, as the mean of four 0..1 parts:

    sma200 slope    clip(sma200_slope / 0.02)         +2% over 10 bars = full marks
    above 200 SMA   clip(dist_from_200sma / 0.15)      15% above = full marks
    50 over 200     1 if sma50 > sma200 else 0
    near 52w high   1 - clip(pct_below_52w_high / 0.25)

Tune by editing ``ScoreWeights`` in ``patterns/config.py``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from patterns.common import (
    PATTERN_ASCENDING_TRIANGLE,
    PATTERN_BULL_FLAG,
    PATTERN_CUP_HANDLE,
    PATTERN_FLAT_BASE,
    STAGE_BREAKOUT,
    PatternHit,
)
from patterns.config import ScoreWeights


def _clip01(x: float) -> float:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return 0.0
    return float(min(1.0, max(0.0, x)))


def trend_strength(df: pd.DataFrame) -> float:
    """0..1 strength of the long-term trend on the last bar (see module docstring)."""
    last = df.iloc[-1]
    close = float(last["Close"])
    sma50, sma200 = last.get("sma50"), last.get("sma200")
    slope = last.get("sma200_slope")
    hi52 = last.get("high_52w")
    parts = [
        _clip01(float(slope) / 0.02) if pd.notna(slope) else 0.0,
        _clip01((close / float(sma200) - 1.0) / 0.15) if pd.notna(sma200) and sma200 else 0.0,
        1.0 if (pd.notna(sma50) and pd.notna(sma200) and float(sma50) > float(sma200)) else 0.0,
        1.0 - _clip01((float(hi52) - close) / float(hi52) / 0.25) if pd.notna(hi52) and hi52 else 0.0,
    ]
    return float(np.mean(parts))


def score_hit(hit: PatternHit, df: pd.DataFrame, weights: ScoreWeights) -> float:
    """Composite score, rounded to one decimal."""
    m = hit.metrics
    total = (
        weights.volume_dryup * _clip01(m.get("volume_dryup", 0.0))
        + weights.tightness * _clip01(m.get("tightness", 0.0))
        + weights.duration * _clip01(m.get("duration", 0.0))
        + weights.trend * trend_strength(df)
    )
    denom = weights.volume_dryup + weights.tightness + weights.duration + weights.trend
    return round(100.0 * total / denom, 1) if denom else 0.0


def _weeks(bars: int) -> str:
    w = max(1, round(bars / 5))
    return f"{w}-week"


def _stage_clause(hit: PatternHit) -> str:
    if hit.stage == STAGE_BREAKOUT:
        return f"breakout on {hit.rvol:.1f}x volume"
    if hit.last_close > hit.buy_point:
        return f"above buy point on {hit.rvol:.1f}x volume (unconfirmed)"
    gap = (hit.buy_point - hit.last_close) / hit.last_close * 100.0
    return f"forming, {gap:.1f}% below buy point"


def reason_for(hit: PatternHit) -> str:
    """Plain-English one-liner, e.g.
    ``"6-week flat base, 8.2% deep, volume contracting, breakout on 2.1x volume"``."""
    m = hit.metrics
    if hit.pattern == PATTERN_FLAT_BASE:
        vol = "volume contracting" if m.get("vol_ratio", 1.0) < 1.0 else "volume flat"
        head = f"{_weeks(hit.base_length_days)} flat base, {hit.base_depth_pct:.1f}% deep, {vol}"
    elif hit.pattern == PATTERN_CUP_HANDLE:
        head = (
            f"{_weeks(m.get('cup_bars', 0))} cup {hit.base_depth_pct:.0f}% deep, "
            f"{m.get('handle_bars', 0)}-day handle {m.get('handle_depth', 0.0) * 100:.1f}% deep, "
            f"handle volume {m.get('handle_vol_ratio', 1.0) * 100:.0f}% of cup"
        )
    elif hit.pattern == PATTERN_ASCENDING_TRIANGLE:
        head = (
            f"{_weeks(hit.base_length_days)} ascending triangle, {m.get('touches', 0)} ceiling touches, "
            f"rising lows R² {m.get('lows_r2', 0.0):.2f}, volume declining"
        )
    elif hit.pattern == PATTERN_BULL_FLAG:
        head = (
            f"{m.get('pole_gain', 0.0) * 100:.0f}% pole in {m.get('pole_bars', 0)} days, "
            f"{m.get('flag_bars', 0)}-day flag retraced {m.get('retracement', 0.0) * 100:.0f}%, "
            f"flag volume {m.get('flag_rvol', 0.0):.2f}x avg"
        )
    else:
        head = hit.pattern
    return f"{head}, {_stage_clause(hit)}"
