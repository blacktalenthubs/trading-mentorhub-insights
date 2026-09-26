"""Pattern 4 — bull flag.

In the last ``lookback_bars`` bars: a pole of 4-15 bars gaining >= 15% on
average rvol >= 1.3, immediately followed by a 3-12 bar flag that gives back
<= 50% of the pole, drifts flat or down, spans <= 40% of the pole's range, and
trades at average rvol <= 0.8. When several pole/flag splits qualify, the one
with the steepest pole (gain per bar) wins.

Scoring inputs written to ``PatternHit.metrics``:
    volume_dryup  = 1 - flag_avg_rvol / pole_avg_rvol        (clipped 0..1)
    tightness     = mean(1 - retracement / max_retracement,
                         1 - flag_range_ratio / max_flag_range_vs_pole)
    duration      = min(1, pole_gain / (2 * pole_min_gain))  — a 30% pole earns full marks
                    (for a flag the pole, not the flag length, is what was "built")
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from patterns.common import PATTERN_BULL_FLAG, PatternHit, classify_stage, linear_fit
from patterns.config import BreakoutConfig, BullFlagConfig


def _candidate(
    s: int, e: int, fs: int, f: int, high: np.ndarray, low: np.ndarray, close: np.ndarray,
    rvol: np.ndarray, cfg: BullFlagConfig,
) -> Optional[dict]:
    pole_start = float(low[s])
    pole_high = float(high[s: e + 1].max())
    if pole_start <= 0:
        return None
    gain = pole_high / pole_start - 1.0
    if gain < cfg.pole_min_gain:
        return None
    # The pole must END at its high (within tolerance) — otherwise it's a spike + fade.
    if high[e] < pole_high * (1.0 - cfg.pole_end_tolerance):
        return None
    pole_rvol = rvol[s: e + 1]
    if np.isnan(pole_rvol).any() or pole_rvol.mean() < cfg.pole_min_avg_rvol:
        return None

    flag_low = float(low[fs: f + 1].min())
    flag_high = float(high[fs: f + 1].max())
    pole_range = pole_high - pole_start
    retr = (pole_high - flag_low) / pole_range
    if retr > cfg.max_retracement:
        return None
    fc = close[fs: f + 1]
    slope, _, _ = linear_fit(fc)
    if slope / float(fc.mean()) > cfg.max_flag_slope_per_bar:
        return None
    range_ratio = (flag_high - flag_low) / pole_range
    if range_ratio > cfg.max_flag_range_vs_pole:
        return None
    flag_rvol = rvol[fs: f + 1]
    if np.isnan(flag_rvol).any() or flag_rvol.mean() > cfg.max_flag_avg_rvol:
        return None
    return {
        "s": s, "e": e, "fs": fs, "f": f, "pole_start": pole_start, "pole_high": pole_high,
        "gain": gain, "pole_rvol": float(pole_rvol.mean()), "flag_low": flag_low,
        "flag_high": flag_high, "retracement": retr, "range_ratio": range_ratio,
        "flag_rvol": float(flag_rvol.mean()), "pole_bars": e - s + 1, "flag_bars": f - fs + 1,
    }


def detect_bull_flag(
    df: pd.DataFrame, cfg: BullFlagConfig, bcfg: BreakoutConfig, ticker: str = "",
) -> Optional[PatternHit]:
    """Return the strongest valid bull flag in the last ``lookback_bars`` bars, or None."""
    n = len(df)
    if n < cfg.pole_min_bars + cfg.flag_min_bars + 1:
        return None
    high = df["High"].to_numpy(float)
    low = df["Low"].to_numpy(float)
    close = df["Close"].to_numpy(float)
    rvol = df["rvol"].to_numpy(float) if "rvol" in df.columns else np.full(n, np.nan)
    floor = max(0, n - cfg.lookback_bars)

    for variant, f in (("breakout", n - 2), ("forming", n - 1)):
        best: Optional[dict] = None
        for flag_len in range(cfg.flag_min_bars, cfg.flag_max_bars + 1):
            fs = f - flag_len + 1
            e = fs - 1
            for pole_len in range(cfg.pole_min_bars, cfg.pole_max_bars + 1):
                s = e - pole_len + 1
                if s < floor:
                    continue
                c = _candidate(s, e, fs, f, high, low, close, rvol, cfg)
                if c is None:
                    continue
                # Prefer the STEEPEST pole (gain per bar) so the pole is the impulse
                # itself, not the impulse plus the tail of the prior trend.
                if best is None or c["gain"] / c["pole_bars"] > best["gain"] / best["pole_bars"]:
                    best = c
        if best is None:
            continue
        if variant == "breakout" and close[-1] <= best["flag_high"]:
            continue
        staged = classify_stage(df, best["flag_high"], best["flag_low"], bcfg)
        if staged is None:
            continue
        stage, volume_ok, rv = staged
        tight = 0.5 * (1.0 - best["retracement"] / cfg.max_retracement) \
            + 0.5 * (1.0 - best["range_ratio"] / cfg.max_flag_range_vs_pole)
        dryup = 1.0 - best["flag_rvol"] / best["pole_rvol"] if best["pole_rvol"] > 0 else 0.0
        return PatternHit(
            ticker=ticker,
            pattern=PATTERN_BULL_FLAG,
            stage=stage,
            buy_point=best["flag_high"],
            suggested_stop=best["flag_low"],
            last_close=float(close[-1]),
            rvol=rv,
            volume_ok=volume_ok,
            base_depth_pct=(best["flag_high"] - best["flag_low"]) / best["flag_high"] * 100.0,
            base_length_days=best["pole_bars"] + best["flag_bars"],
            start_idx=best["s"],
            end_idx=best["f"],
            metrics={
                "volume_dryup": float(np.clip(dryup, 0.0, 1.0)),
                "tightness": float(np.clip(tight, 0.0, 1.0)),
                "duration": float(min(1.0, best["gain"] / (2.0 * cfg.pole_min_gain))),
                "pole_gain": best["gain"],
                "pole_bars": best["pole_bars"],
                "flag_bars": best["flag_bars"],
                "retracement": best["retracement"],
                "flag_rvol": best["flag_rvol"],
                "pole_rvol": best["pole_rvol"],
            },
            lines=[
                ("pole", best["s"], best["pole_start"], best["e"], best["pole_high"]),
                ("flag high / buy", best["fs"], best["flag_high"], best["f"], best["flag_high"]),
                ("flag low / stop", best["fs"], best["flag_low"], best["f"], best["flag_low"]),
            ],
        )
    return None
