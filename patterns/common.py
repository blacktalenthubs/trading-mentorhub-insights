"""Shared building blocks for the pattern detectors.

* ``PatternHit`` — the one result type every detector returns.
* ``confirm_breakout`` — the shared breakout-bar test.
* ``classify_stage`` — turns a detected buy point + the last bar into
  ``forming`` / ``breakout`` / rejected, using the shared confirmation rules.
* small numeric helpers (linear fit, R²).

Detectors receive a DataFrame that already carries the derived columns from
``analytics.indicators.add_derived_columns`` (lowercase) alongside Title-case
OHLCV. They return ``None`` when the pattern is absent or fails a rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from patterns.config import BreakoutConfig

PATTERN_CUP_HANDLE = "cup_handle"
PATTERN_FLAT_BASE = "flat_base"
PATTERN_ASCENDING_TRIANGLE = "ascending_triangle"
PATTERN_BULL_FLAG = "bull_flag"

STAGE_FORMING = "forming"
STAGE_BREAKOUT = "breakout"


@dataclass
class PatternHit:
    """One detected pattern on one symbol.

    ``metrics`` holds pattern-specific normalized quality inputs (0..1) that the
    scorer reads, plus any raw numbers the reason string wants. ``start_idx`` /
    ``end_idx`` are positional bar indexes into the scanned frame for charting.
    """

    ticker: str
    pattern: str
    stage: str
    buy_point: float
    suggested_stop: float
    last_close: float
    rvol: float
    volume_ok: bool
    base_depth_pct: float          # percent, e.g. 8.2
    base_length_days: int
    start_idx: int
    end_idx: int
    metrics: dict = field(default_factory=dict)
    # boundaries for the chart: list of (label, bar_idx_from, bar_idx_to, price)
    lines: list = field(default_factory=list)
    score: float = 0.0
    reason: str = ""


# ── numeric helpers ───────────────────────────────────────────────────────────

def linear_fit(y: np.ndarray, x: Optional[np.ndarray] = None) -> tuple[float, float, float]:
    """Least-squares line through ``y``. Returns (slope, intercept, r_squared).

    With fewer than 2 points returns (0, mean, 0). Two points give r²=1.
    """
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 2:
        return 0.0, float(y.mean()) if n else 0.0, 0.0
    if x is None:
        x = np.arange(n, dtype=float)
    x = np.asarray(x, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 if ss_tot == 0 else max(0.0, 1.0 - ss_res / ss_tot)
    return float(slope), float(intercept), r2


def close_range_position(bar: pd.Series) -> float:
    """Where the close sits in the bar's range: 0 = at the low, 1 = at the high."""
    rng = float(bar["High"] - bar["Low"])
    if rng <= 0:
        return 0.5
    return float((bar["Close"] - bar["Low"]) / rng)


# ── breakout confirmation (shared) ───────────────────────────────────────────

def confirm_breakout(df: pd.DataFrame, buy_point: float, cfg: BreakoutConfig) -> tuple[bool, bool, float]:
    """Test the most recent bar against the shared breakout rules.

    Returns ``(confirmed, volume_ok, rvol)``. ``confirmed`` requires ALL of:
    close > buy_point, rvol >= min_rvol, close in the upper part of the range,
    close > open. ``volume_ok`` is just the rvol leg so borderline cases stay visible.
    """
    bar = df.iloc[-1]
    rvol = float(bar["rvol"]) if pd.notna(bar.get("rvol", np.nan)) else 0.0
    volume_ok = rvol >= cfg.min_rvol
    above = float(bar["Close"]) > buy_point
    strong_close = close_range_position(bar) >= cfg.min_close_range_pos
    up_bar = (float(bar["Close"]) > float(bar["Open"])) or not cfg.require_close_above_open
    confirmed = bool(above and volume_ok and strong_close and up_bar)
    return confirmed, volume_ok, rvol


def classify_stage(
    df: pd.DataFrame, buy_point: float, suggested_stop: float, cfg: BreakoutConfig,
) -> Optional[tuple[str, bool, float]]:
    """Decide the stage for a detected pattern from the last bar.

    * close <= buy_point           → ``forming`` (must still be above the stop)
    * close > buy_point, confirmed → ``breakout``
    * close > buy_point, NOT confirmed → ``forming`` with ``volume_ok=False``
      (the row is kept so the borderline case is visible; pct_to_buy goes negative)
    * close beyond buy_point * (1 + max_extension_pct) → rejected (extended)
    * close < suggested_stop → rejected (pattern already failed)

    Returns ``(stage, volume_ok, rvol)`` or ``None`` when rejected.
    """
    last_close = float(df["Close"].iloc[-1])
    if last_close < suggested_stop:
        return None
    if last_close > buy_point * (1.0 + cfg.max_extension_pct):
        return None
    confirmed, volume_ok, rvol = confirm_breakout(df, buy_point, cfg)
    if last_close > buy_point and confirmed:
        return STAGE_BREAKOUT, volume_ok, rvol
    return STAGE_FORMING, volume_ok, rvol


def pct(a: float, b: float) -> float:
    """(a - b) / b as a percent, 0 when b is 0."""
    return 0.0 if b == 0 else (a - b) / b * 100.0
