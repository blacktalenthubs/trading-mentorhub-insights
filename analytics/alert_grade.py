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


# VOLUME-ONLY grade (2026-06-17). Volume = buy pressure at the bar — the honest
# read of conviction. The old VWAP-slope gate was BACKWARDS for this book: slope is
# steep+up at a high (a chase) and flat-to-down at the pullback you actually buy, so
# it scored chases 'A' and clean support bounces 'C'. Proven in the data — MRVL
# bounced on 5.13x volume and was capped at B purely because slope was -2.2. Drop
# slope; grade on volume tiers.
VOL_A = 2.0      # volume_ratio >= this → strong demand at the level
VOL_B = 1.5      # volume_ratio >= this → above-average demand


def compute_grade(
    volume_ratio: Optional[float],
    vwap_slope_pct: Optional[float] = None,  # kept for call-site compat; ignored
) -> str:
    """Returns 'A', 'B', or 'C' from volume_ratio alone. Never None — an alert
    with no volume data lands a 'C' (bottom of the scale, not absent).
      A = vol >= 2.0   B = vol >= 1.5   C = below / no data
    """
    vr = volume_ratio if volume_ratio is not None else 0.0
    if vr >= VOL_A:
        return "A"
    if vr >= VOL_B:
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
