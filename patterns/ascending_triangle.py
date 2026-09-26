"""Pattern 3 — ascending triangle.

Windows of 20-60 bars. A flat ceiling (>= 3 ``find_peaks`` swing highs within
2% of each other, nothing in the window meaningfully above it) with rising
swing lows (least-squares slope > 0, R² >= 0.6) converging on the ceiling
(last swing low within 10%), on declining volume. Longest valid window wins.

Scoring inputs written to ``PatternHit.metrics``:
    volume_dryup  = 1 - second_half_avg_vol / first_half_avg_vol   (clipped 0..1)
    tightness     = mean(lows_r2, 1 - last_low_gap / max_last_low_gap)
    duration      = (bars - min_bars) / (max_bars - min_bars)
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from patterns.common import PATTERN_ASCENDING_TRIANGLE, PatternHit, classify_stage, linear_fit
from patterns.config import AscendingTriangleConfig, BreakoutConfig


def _largest_cluster(values: np.ndarray, tol: float) -> np.ndarray:
    """Indexes (into ``values``) of the largest subset whose max/min - 1 <= tol.

    Ties go to the higher-priced cluster (the true ceiling).
    """
    order = np.argsort(values)
    sv = values[order]
    best: tuple[int, int] = (0, 0)  # (start, end) inclusive in sorted order
    j = 0
    for i in range(len(sv)):
        if j < i:
            j = i
        while j + 1 < len(sv) and sv[j + 1] / sv[i] - 1.0 <= tol:
            j += 1
        if (j - i) >= (best[1] - best[0]):
            best = (i, j)
    return order[best[0]: best[1] + 1]


def _window_metrics(
    start: int, end: int, high: np.ndarray, low: np.ndarray, vol: np.ndarray,
    cfg: AscendingTriangleConfig,
) -> Optional[dict]:
    h = high[start: end + 1]
    l = low[start: end + 1]
    v = vol[start: end + 1]
    length = len(h)

    peaks, _ = find_peaks(h, distance=cfg.peak_distance)
    if len(peaks) < cfg.min_ceiling_touches:
        return None
    cluster = _largest_cluster(h[peaks], cfg.ceiling_tolerance)
    if len(cluster) < cfg.min_ceiling_touches:
        return None
    touch_idx = np.sort(peaks[cluster])
    ceiling = float(h[touch_idx].mean())
    if h.max() > ceiling * (1.0 + cfg.max_high_over_ceiling):
        return None
    if cfg.require_touches_span and not (touch_idx[0] < length / 2 <= touch_idx[-1]):
        return None
    if touch_idx[0] > cfg.max_first_touch_pos * length:
        return None  # the window starts well before the pattern — a shorter one fits better

    troughs, _ = find_peaks(-l, distance=cfg.peak_distance)
    if len(troughs) < cfg.min_swing_lows:
        return None
    slope, _, r2 = linear_fit(l[troughs], troughs.astype(float))
    if slope <= 0 or r2 < cfg.min_lows_r2:
        return None
    last_low = float(l[troughs[-1]])
    if last_low >= ceiling:
        return None
    gap = (ceiling - last_low) / ceiling
    if gap > cfg.max_last_low_gap:
        return None

    vslope, _, _ = linear_fit(v)
    if cfg.require_volume_decline and vslope >= 0:
        return None
    half = length // 2
    v1, v2 = float(v[:half].mean()), float(v[half:].mean())

    return {
        "ceiling": ceiling, "last_low": last_low, "gap": gap, "lows_r2": r2, "lows_slope": slope,
        "touches": int(len(touch_idx)), "touch_idx": touch_idx, "troughs": troughs,
        "vol_ratio": v2 / v1 if v1 else 1.0, "min_low": float(l.min()),
    }


def detect_ascending_triangle(
    df: pd.DataFrame, cfg: AscendingTriangleConfig, bcfg: BreakoutConfig, ticker: str = "",
) -> Optional[PatternHit]:
    """Return the longest valid ascending triangle ending now, or None."""
    n = len(df)
    if n < cfg.min_bars + 1:
        return None
    high = df["High"].to_numpy(float)
    low = df["Low"].to_numpy(float)
    close = df["Close"].to_numpy(float)
    vol = df["Volume"].to_numpy(float)

    for variant, end in (("breakout", n - 2), ("forming", n - 1)):
        for length in range(cfg.max_bars, cfg.min_bars - 1, -1):
            start = end - length + 1
            if start < 0:
                continue
            m = _window_metrics(start, end, high, low, vol, cfg)
            if m is None:
                continue
            if variant == "breakout" and close[-1] <= m["ceiling"]:
                continue
            staged = classify_stage(df, m["ceiling"], m["last_low"], bcfg)
            if staged is None:
                continue
            stage, volume_ok, rvol = staged
            tight = 0.5 * m["lows_r2"] + 0.5 * (1.0 - m["gap"] / cfg.max_last_low_gap)
            tr = m["troughs"]
            lows_y0 = m["lows_slope"] * tr[0] + (m["last_low"] - m["lows_slope"] * tr[-1])
            return PatternHit(
                ticker=ticker,
                pattern=PATTERN_ASCENDING_TRIANGLE,
                stage=stage,
                buy_point=m["ceiling"],
                suggested_stop=m["last_low"],
                last_close=float(close[-1]),
                rvol=rvol,
                volume_ok=volume_ok,
                base_depth_pct=(m["ceiling"] - m["min_low"]) / m["ceiling"] * 100.0,
                base_length_days=length,
                start_idx=start,
                end_idx=end,
                metrics={
                    "volume_dryup": float(np.clip(1.0 - m["vol_ratio"], 0.0, 1.0)),
                    "tightness": float(np.clip(tight, 0.0, 1.0)),
                    "duration": float(np.clip((length - cfg.min_bars) / max(1, cfg.max_bars - cfg.min_bars), 0.0, 1.0)),
                    "touches": m["touches"],
                    "lows_r2": m["lows_r2"],
                    "last_low_gap": m["gap"],
                    "vol_ratio": m["vol_ratio"],
                },
                lines=[
                    ("ceiling / buy", start, m["ceiling"], end, m["ceiling"]),
                    ("rising lows", start + int(tr[0]), float(lows_y0), start + int(tr[-1]), m["last_low"]),
                ],
            )
    return None
