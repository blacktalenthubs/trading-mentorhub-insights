"""Unit tests for the Weekly Stage scanner's 30-week-MA classification +
bucketing (Python port of pine_scripts/visual/weekly_stage.pine f_wk).

Synthetic weekly close series → expected stage / bucket.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

# The scanner lives in the API package; put it on the path (mirrors test_focus_list).
_HERE = os.path.dirname(os.path.abspath(__file__))
_API = os.path.join(_HERE, "..", "api")
if _API not in sys.path:
    sys.path.insert(0, _API)

from app.services.scanner import classify_weekly_stage  # noqa: E402


def _series(values) -> pd.Series:
    return pd.Series([float(v) for v in values])


def test_too_short_returns_none():
    assert classify_weekly_stage(_series(np.linspace(10, 20, 30))) is None


def test_stage2_advancing_is_own():
    # Steady advance well above a rising 30wMA → Stage 2, far from MA → "own".
    px = np.linspace(50, 120, 80)
    c = classify_weekly_stage(_series(px))
    assert c is not None
    assert c.stage == 2
    assert c.bucket == "own"
    assert c.slope_pct > 0.5
    assert c.dist_vs_ma_pct > 3.0
    assert "Advancing" in c.stage_label


def test_stage2_pullback_to_ma_is_add():
    # Long advance (rising MA, price above), then a small dip back toward the MA
    # so the last close sits 0–3% above it → Stage 2 "add".
    # Construct the tail so close lands ~2% over the 30wMA.
    base = list(np.linspace(50, 120, 79))
    s = pd.Series([float(v) for v in base])
    ma = float(s.rolling(30).mean().iloc[-1])
    s.iloc[-1] = ma * 1.02  # pull last close to +2% vs MA
    c = classify_weekly_stage(s)
    assert c is not None
    assert c.stage == 2
    assert c.bucket == "add"
    assert 0.0 <= c.dist_vs_ma_pct <= 3.0


def test_stage4_declining_hard_is_excluded():
    # Persistent decline, price far below a falling MA → Stage 4 but not turning
    # up (slope not improving / too far from MA) → excluded (None).
    px = np.linspace(120, 50, 80)
    c = classify_weekly_stage(_series(px))
    assert c is None


def test_basing_turning_up_near_ma_is_watch():
    # Decline that decelerates and flattens near the MA: the recent 4-week slope
    # is improving vs the prior 4-week slope, price within ~8% of the MA → WATCH.
    down = list(np.linspace(120, 80, 50))      # falling leg
    flat = list(np.linspace(80, 82, 30))        # flatten/curl near the lows
    c = classify_weekly_stage(_series(down + flat))
    assert c is not None
    assert c.stage in (1, 4)
    assert c.bucket == "watch"
    assert -8.0 <= c.dist_vs_ma_pct <= 8.0


def test_to_dict_shape():
    c = classify_weekly_stage(_series(np.linspace(50, 120, 80)))
    assert c is not None
    d = c.to_dict()
    assert set(d) == {
        "symbol", "stage", "stage_label", "bucket",
        "ma", "slope_pct", "price", "dist_vs_ma_pct",
    }
