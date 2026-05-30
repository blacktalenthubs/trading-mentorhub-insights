"""Alert grade — single letter (A/B/C) computed from the two quality
signals that the v2 pipeline already gates on: volume ratio and VWAP
slope.

Used everywhere a busy user wants one-glance triage:
  - Settings: filter to "A only" / "A+B only" / "All"
  - Signal feed: badge on every card
  - Performance / Weekly tabs: badge per fire
  - Push + Telegram routing: skip below user's minimum
  - AI Friday retrospective: ranks by grade

Definitions (v1 — pure thresholds, no pattern-history component yet):
  A = volume_ratio >= 2.0  AND  vwap_slope_pct >= 0.05  (both gates pass)
  B = exactly ONE of the two gates passes
  C = neither gate passes

Null treatment: a missing field is treated as a failed gate. An alert
with no volume_ratio data gets at best a B (if slope passes), worst C.
"""

from __future__ import annotations

from typing import Optional


VOL_GATE = 2.0      # volume_ratio >= this
SLOPE_GATE = 0.05   # vwap_slope_pct >= this (in percent)


def compute_grade(
    volume_ratio: Optional[float],
    vwap_slope_pct: Optional[float],
) -> str:
    """Returns 'A', 'B', or 'C'. Never None — even an alert with no
    quality data lands a 'C' (it's the bottom of the scale, not absent).
    """
    vol_pass = volume_ratio is not None and volume_ratio >= VOL_GATE
    slope_pass = vwap_slope_pct is not None and vwap_slope_pct >= SLOPE_GATE
    passes = int(vol_pass) + int(slope_pass)
    if passes == 2:
        return "A"
    if passes == 1:
        return "B"
    return "C"


# Filter helpers. The user's setting `min_alert_grade` is one of A/B/C.
# A grade "passes" the filter when it's at or above the user's minimum.
# 'A' is the highest; 'C' is the lowest (everything passes).
_RANK = {"A": 3, "B": 2, "C": 1}


def grade_passes(alert_grade: Optional[str], min_grade: Optional[str]) -> bool:
    """True when the alert's grade meets or beats the user's minimum.
    Defaults: if min_grade is missing/invalid, treat as 'C' (no filter).
    If alert_grade is missing, treat as 'C' (lowest — only passes when
    user is on 'C'/all).
    """
    a = _RANK.get((alert_grade or "C").upper(), 1)
    m = _RANK.get((min_grade or "C").upper(), 1)
    return a >= m
