"""Pattern 1 — cup and handle.

Searches the last ``lookback_bars`` bars for a rounded cup (15-35% deep, at
least 35 bars rim-to-recovery, low in the middle half of the span, middle
third lower than both outer thirds) followed by a 5-15 bar handle in the upper
half of the cup whose volume dries up versus the cup's right side.

Scoring inputs written to ``PatternHit.metrics``:
    volume_dryup  = 1 - handle_avg_vol / cup_right_side_avg_vol   (clipped 0..1)
    tightness     = (handle_max_depth - handle_depth) / (handle_max_depth - handle_min_depth)
    duration      = min(1, cup_bars / 70)   — a 14-week cup earns full marks
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from patterns.common import PATTERN_CUP_HANDLE, PatternHit, classify_stage
from patterns.config import BreakoutConfig, CupHandleConfig


def _rim_candidates(high: np.ndarray, k: int) -> list[int]:
    """Bars whose high is the max of the ``k`` bars on each side."""
    n = len(high)
    out = []
    for i in range(k, n - k):
        if high[i] >= high[i - k: i + k + 1].max():
            out.append(i)
    return out


def _handle_metrics(
    hs: int, he: int, high: np.ndarray, low: np.ndarray, vol: np.ndarray,
    rim_high: float, cup_low: float, cup_low_idx: int, rec: int, cfg: CupHandleConfig,
) -> Optional[dict]:
    """Validate the handle spanning bars ``hs..he`` (inclusive). None if it fails."""
    length = he - hs + 1
    if length < cfg.handle_min_bars or length > cfg.handle_max_bars:
        return None
    hh = float(high[hs: he + 1].max())
    hl = float(low[hs: he + 1].min())
    if hh <= 0:
        return None
    depth = (hh - hl) / hh
    if depth < cfg.handle_min_depth or depth > cfg.handle_max_depth:
        return None
    if hl <= cup_low + cfg.handle_low_min_cup_fraction * (rim_high - cup_low):
        return None
    if hh > rim_high * (1.0 + cfg.handle_max_over_rim):
        return None
    handle_vol = float(vol[hs: he + 1].mean())
    right_vol = float(vol[cup_low_idx: rec + 1].mean())
    if cfg.require_handle_volume_dryup and not (right_vol > 0 and handle_vol < right_vol):
        return None
    return {
        "handle_high": hh, "handle_low": hl, "handle_depth": depth, "handle_bars": length,
        "handle_vol": handle_vol, "cup_right_vol": right_vol,
    }


def _try_rim(
    r: int, w: pd.DataFrame, arrays: dict, cfg: CupHandleConfig, bcfg: BreakoutConfig,
    ticker: str, offset: int,
) -> Optional[PatternHit]:
    high, low, close, vol = arrays["high"], arrays["low"], arrays["close"], arrays["vol"]
    n = len(high)
    rim_high = float(high[r])
    recover_at = rim_high * (1.0 - cfg.recovery_tolerance)
    dip_at = rim_high * (1.0 - cfg.min_depth)

    # Walk forward: the cup must first dip at least min_depth, then close back
    # within recovery_tolerance of the rim. Nothing inside the cup may exceed the rim.
    dipped = False
    cup_low, cup_low_idx, rec = np.inf, -1, -1
    for j in range(r + 1, n):
        if high[j] > rim_high:
            return None
        if low[j] < cup_low:
            cup_low, cup_low_idx = float(low[j]), j
        if not dipped and low[j] <= dip_at:
            dipped = True
        if dipped and close[j] >= recover_at:
            rec = j
            break
    if rec < 0:
        return None

    depth = (rim_high - cup_low) / rim_high
    if depth < cfg.min_depth or depth > cfg.max_depth:
        return None
    cup_bars = rec - r
    if cup_bars < cfg.min_cup_bars:
        return None

    # Rounded, not a V: middle third's mean close below both outer thirds, and the
    # low sits in the middle half of the span.
    span = close[r: rec + 1]
    t = len(span) // 3
    first, mid, last = span[:t], span[t: 2 * t], span[2 * t:]
    if not (mid.mean() < first.mean() and mid.mean() < last.mean()):
        return None
    low_pos = (cup_low_idx - r) / cup_bars
    if low_pos < cfg.low_position_min or low_pos > cfg.low_position_max:
        return None

    hs = rec + 1
    if hs > n - 1:
        return None

    # Breakout variant first: handle = bars after recovery excluding the last bar,
    # and the last close cleared that handle's high. Else forming: handle runs to now.
    variants = []
    if n - 2 >= hs:
        variants.append(("breakout", n - 2))
    variants.append(("forming", n - 1))
    for variant, he in variants:
        hm = _handle_metrics(hs, he, high, low, vol, rim_high, cup_low, cup_low_idx, rec, cfg)
        if hm is None:
            continue
        if variant == "breakout" and close[-1] <= hm["handle_high"]:
            continue
        staged = classify_stage(w, hm["handle_high"], hm["handle_low"], bcfg)
        if staged is None:
            return None
        stage, volume_ok, rvol = staged
        dryup = 1.0 - hm["handle_vol"] / hm["cup_right_vol"] if hm["cup_right_vol"] > 0 else 0.0
        tight = (cfg.handle_max_depth - hm["handle_depth"]) / (cfg.handle_max_depth - cfg.handle_min_depth)
        return PatternHit(
            ticker=ticker,
            pattern=PATTERN_CUP_HANDLE,
            stage=stage,
            buy_point=hm["handle_high"],
            suggested_stop=hm["handle_low"],
            last_close=float(close[-1]),
            rvol=rvol,
            volume_ok=volume_ok,
            base_depth_pct=depth * 100.0,
            base_length_days=cup_bars + hm["handle_bars"],
            start_idx=r + offset,
            end_idx=he + offset,
            metrics={
                "volume_dryup": float(np.clip(dryup, 0.0, 1.0)),
                "tightness": float(np.clip(tight, 0.0, 1.0)),
                "duration": float(min(1.0, cup_bars / 70.0)),
                "cup_depth": depth,
                "cup_bars": cup_bars,
                "handle_bars": hm["handle_bars"],
                "handle_depth": hm["handle_depth"],
                "handle_vol_ratio": hm["handle_vol"] / hm["cup_right_vol"] if hm["cup_right_vol"] else 1.0,
            },
            lines=[
                ("rim", r + offset, rim_high, rec + offset, rim_high),
                ("cup low", cup_low_idx + offset, cup_low, cup_low_idx + offset, cup_low),
                ("handle high / buy", hs + offset, hm["handle_high"], he + offset, hm["handle_high"]),
                ("handle low / stop", hs + offset, hm["handle_low"], he + offset, hm["handle_low"]),
            ],
        )
    return None


def detect_cup_handle(
    df: pd.DataFrame, cfg: CupHandleConfig, bcfg: BreakoutConfig, ticker: str = "",
) -> Optional[PatternHit]:
    """Return the most recent valid cup-and-handle in the last ``lookback_bars`` bars."""
    if len(df) < cfg.min_cup_bars + cfg.handle_min_bars + 2 * cfg.rim_neighborhood:
        return None
    w = df.iloc[-cfg.lookback_bars:]
    offset = len(df) - len(w)
    w = w.reset_index(drop=True)
    arrays = {
        "high": w["High"].to_numpy(float),
        "low": w["Low"].to_numpy(float),
        "close": w["Close"].to_numpy(float),
        "vol": w["Volume"].to_numpy(float),
    }
    min_room = cfg.min_cup_bars + cfg.handle_min_bars
    for r in reversed(_rim_candidates(arrays["high"], cfg.rim_neighborhood)):
        if len(w) - 1 - r < min_room:
            continue
        hit = _try_rim(r, w, arrays, cfg, bcfg, ticker, offset)
        if hit is not None:
            return hit
    return None
