"""Descending trendline break (Dan Zanger) — fit a falling line through the swing highs, project
it to today, and fire when price closes above it (a fresh break, not extended). buy_point = the
projected trendline value (the trigger), stop = the recent swing low."""
from __future__ import annotations

import numpy as np

from patterns.config import PatternConfig
from patterns.detect_utils import finalize, linfit, swing_highs, swing_lows


def detect(df, cfg: PatternConfig):
    n = len(df)
    # Prefer the longest well-fit descending line (a "long descending trendline" is the strong break).
    for wlen in range(cfg.tl_max_bars, cfg.tl_min_bars - 1, -1):
        if n < wlen:
            continue
        seg = df.iloc[n - wlen:]
        highs, lows, vols = seg["High"].values, seg["Low"].values, seg["Volume"].values
        ph = swing_highs(highs, cfg.tl_peak_distance)
        if len(ph) < cfg.tl_min_highs:
            continue
        slope, intercept, r2 = linfit(ph.astype(float), highs[ph])
        if not (slope < 0 and r2 >= cfg.tl_r2_min):
            continue
        line_now = slope * (wlen - 1) + intercept              # trendline projected to the current bar
        if line_now <= 0:
            continue
        price = float(seg["Close"].iloc[-1])
        # A FRESH break (just above) OR still forming (just below) — within tl_max_dist_above either way.
        if abs(price - line_now) / line_now > cfg.tl_max_dist_above:
            continue
        pl = swing_lows(lows, cfg.tl_peak_distance)
        stop = float(lows[pl][-1]) if len(pl) > 0 else float(lows.min())
        depth = (float(highs.max()) - float(lows.min())) / float(highs.max())
        vslope, _, _ = linfit(np.arange(wlen, dtype=float), vols)
        dryup = 0.5 if vslope < 0 else 0.2                     # declining volume into the break is a plus
        return finalize(
            df, cfg, pattern="trendline_break", buy_point=line_now, suggested_stop=stop,
            base_depth_pct=depth, base_length_days=wlen, dryup=dryup, tightness=r2,
            reason_bits=[f"broke a {wlen}-bar descending trendline (R²={r2:.2f})",
                         "holding above the line"])
    return None
