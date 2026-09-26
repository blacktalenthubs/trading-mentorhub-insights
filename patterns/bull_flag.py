"""Bull flag — a sharp high-volume pole then a shallow, quiet, drifting-down flag. buy_point =
flag high, stop = flag low."""
from __future__ import annotations

import numpy as np

from patterns.config import PatternConfig
from patterns.detect_utils import finalize, linfit


def detect(df, cfg: PatternConfig):
    seg = df.tail(cfg.bf_search_bars).reset_index(drop=True)
    n = len(seg)
    if n < cfg.bf_pole_min_bars + cfg.bf_flag_min_bars:
        return None
    closes, highs, lows, rvol = seg["Close"].values, seg["High"].values, seg["Low"].values, seg["rvol"].values

    best, best_gain = None, 0.0
    # Flag = the last `flen` bars; pole = the `plen` bars immediately before it.
    for flen in range(cfg.bf_flag_min_bars, cfg.bf_flag_max_bars + 1):
        f0 = n - flen
        if f0 <= cfg.bf_pole_min_bars:
            continue
        for plen in range(cfg.bf_pole_min_bars, cfg.bf_pole_max_bars + 1):
            p0 = f0 - plen
            if p0 < 0:
                continue
            pole_start, pole_high = closes[p0], highs[f0 - plen:f0].max()
            gain = (pole_high - pole_start) / pole_start if pole_start > 0 else 0.0
            if gain < cfg.bf_pole_gain:
                continue
            pole_rvol = np.nanmean(rvol[p0:f0])
            if not (pole_rvol >= cfg.bf_pole_rvol):
                continue
            flag = seg.iloc[f0:]
            flag_high, flag_low = highs[f0:].max(), lows[f0:].min()
            pole_range = pole_high - pole_start
            retrace = (pole_high - flag_low) / pole_range if pole_range > 0 else 1.0
            if retrace > cfg.bf_flag_retrace_max:
                continue
            fslope, _, _ = linfit(np.arange(flen, dtype=float), flag["Close"].values)
            if fslope > 0:                                     # flag must be flat or down
                continue
            flag_range = flag_high - flag_low
            if not (flag_range <= cfg.bf_flag_range_frac * pole_range):
                continue
            flag_rvol = np.nanmean(rvol[f0:])
            if not (flag_rvol <= cfg.bf_flag_rvol_max):
                continue
            if gain > best_gain:                               # keep the strongest pole
                best_gain = gain
                depth = (flag_high - flag_low) / flag_high if flag_high else 0.0
                dryup = 1.0 - flag_rvol / cfg.bf_flag_rvol_max
                tightness = 1.0 - (flag_range / pole_range) / cfg.bf_flag_range_frac
                best = finalize(
                    df, cfg, pattern="bull_flag", buy_point=flag_high, suggested_stop=flag_low,
                    base_depth_pct=depth, base_length_days=flen, dryup=dryup, tightness=tightness,
                    reason_bits=[f"{gain*100:.0f}% pole on {pole_rvol:.1f}x volume",
                                 f"quiet flag ({flag_rvol:.1f}x), {retrace*100:.0f}% retrace"])
    return best
