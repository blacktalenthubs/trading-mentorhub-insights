"""Pattern 2 — flat base.

Windows of 25-60 bars ending at the most recent bar (or the bar before it for
the breakout variant). Depth <= 15%, preceded by a >= 20% advance in the prior
60 bars, contracting range and volume between the two halves, every close at
or above the 50 SMA. The LONGEST valid window wins — it is the whole base.

Scoring inputs written to ``PatternHit.metrics``:
    volume_dryup  = 1 - second_half_avg_vol / first_half_avg_vol   (clipped 0..1)
    tightness     = 1 - depth / max_depth
    duration      = (bars - min_bars) / (max_bars - min_bars)
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from patterns.common import PATTERN_FLAT_BASE, PatternHit, classify_stage
from patterns.config import BreakoutConfig, FlatBaseConfig


def _window_metrics(
    start: int, end: int, high: np.ndarray, low: np.ndarray, close: np.ndarray,
    vol: np.ndarray, sma50: np.ndarray, cfg: FlatBaseConfig,
) -> Optional[dict]:
    if start - 1 - cfg.prior_advance_bars < 0:
        return None
    bh = float(high[start: end + 1].max())
    bl = float(low[start: end + 1].min())
    if bh <= 0:
        return None
    depth = (bh - bl) / bh
    if depth > cfg.max_depth:
        return None
    # The base begins when price first reaches its top — otherwise this window is
    # the prior advance's tail plus a shorter base (a shorter L will find it).
    if high[start: start + cfg.start_touch_bars].max() < bh * (1.0 - cfg.start_touch_tol):
        return None

    # Continuation, not a bottom: the 60 bars BEFORE the base advanced >= 20%.
    pre_end = close[start - 1]
    pre_start = close[start - 1 - cfg.prior_advance_bars]
    if pre_start <= 0 or (pre_end / pre_start - 1.0) < cfg.min_prior_advance:
        return None

    half = (end - start + 1) // 2
    r1 = float(high[start: start + half].max() - low[start: start + half].min())
    r2 = float(high[start + half: end + 1].max() - low[start + half: end + 1].min())
    if cfg.require_tightening and r2 > r1:
        return None
    v1 = float(vol[start: start + half].mean())
    v2 = float(vol[start + half: end + 1].mean())
    if cfg.require_volume_contraction and not (v1 > 0 and v2 < v1):
        return None

    if cfg.require_closes_above_sma50:
        s = sma50[start: end + 1]
        if np.isnan(s).any() or (close[start: end + 1] < s).any():
            return None

    return {"base_high": bh, "base_low": bl, "depth": depth, "vol_ratio": v2 / v1 if v1 else 1.0,
            "range_ratio": r2 / r1 if r1 else 1.0, "prior_advance": pre_end / pre_start - 1.0}


def detect_flat_base(
    df: pd.DataFrame, cfg: FlatBaseConfig, bcfg: BreakoutConfig, ticker: str = "",
) -> Optional[PatternHit]:
    """Return the longest valid flat base ending now, or None."""
    n = len(df)
    if n < cfg.min_bars + cfg.prior_advance_bars + 1:
        return None
    high = df["High"].to_numpy(float)
    low = df["Low"].to_numpy(float)
    close = df["Close"].to_numpy(float)
    vol = df["Volume"].to_numpy(float)
    sma50 = df["sma50"].to_numpy(float) if "sma50" in df.columns else np.full(n, np.nan)

    # Breakout variant: base excludes the last bar and the last close cleared its high.
    # Forming variant: base includes the last bar.
    for variant, end in (("breakout", n - 2), ("forming", n - 1)):
        for length in range(cfg.max_bars, cfg.min_bars - 1, -1):
            start = end - length + 1
            if start < 0:
                continue
            m = _window_metrics(start, end, high, low, close, vol, sma50, cfg)
            if m is None:
                continue
            if variant == "breakout" and close[-1] <= m["base_high"]:
                continue
            staged = classify_stage(df, m["base_high"], m["base_low"], bcfg)
            if staged is None:
                continue
            stage, volume_ok, rvol = staged
            return PatternHit(
                ticker=ticker,
                pattern=PATTERN_FLAT_BASE,
                stage=stage,
                buy_point=m["base_high"],
                suggested_stop=m["base_low"],
                last_close=float(close[-1]),
                rvol=rvol,
                volume_ok=volume_ok,
                base_depth_pct=m["depth"] * 100.0,
                base_length_days=length,
                start_idx=start,
                end_idx=end,
                metrics={
                    "volume_dryup": float(np.clip(1.0 - m["vol_ratio"], 0.0, 1.0)),
                    "tightness": float(np.clip(1.0 - m["depth"] / cfg.max_depth, 0.0, 1.0)),
                    "duration": float(np.clip((length - cfg.min_bars) / max(1, cfg.max_bars - cfg.min_bars), 0.0, 1.0)),
                    "vol_ratio": m["vol_ratio"],
                    "range_ratio": m["range_ratio"],
                    "prior_advance": m["prior_advance"],
                },
                lines=[
                    ("base high / buy", start, m["base_high"], end, m["base_high"]),
                    ("base low / stop", start, m["base_low"], end, m["base_low"]),
                ],
            )
    return None
