"""Ascending triangle — a flat ceiling (≥3 highs within tol) with rising lows converging into
it on declining volume. buy_point = ceiling, stop = last swing low."""
from __future__ import annotations

import numpy as np

from patterns.config import PatternConfig
from patterns.detect_utils import finalize, linfit, swing_highs, swing_lows


def _ceiling(highs_at_peaks: np.ndarray, tol: float, min_touches: int):
    """Highest level where ≥min_touches swing highs sit within ±tol of each other → (level, count)."""
    best = None
    for anchor in sorted(highs_at_peaks, reverse=True):
        group = [h for h in highs_at_peaks if abs(h - anchor) / anchor <= tol]
        if len(group) >= min_touches:
            return float(np.mean(group)), len(group)
    return best


def detect(df, cfg: PatternConfig):
    n = len(df)
    best, best_q = None, -1.0
    for wlen in range(cfg.at_min_bars, cfg.at_max_bars + 1):
        if n < wlen:
            break
        seg = df.iloc[n - wlen:]
        highs, lows, vols = seg["High"].values, seg["Low"].values, seg["Volume"].values
        ph = swing_highs(highs, cfg.at_peak_distance)
        if len(ph) < cfg.at_min_ceiling_touches:
            continue
        ceil_res = _ceiling(highs[ph], cfg.at_ceiling_tol, cfg.at_min_ceiling_touches)
        if ceil_res is None:
            continue
        ceiling, touches = ceil_res
        pl = swing_lows(lows, cfg.at_peak_distance)
        if len(pl) < cfg.at_min_low_touches:
            continue
        slope, _, r2 = linfit(pl.astype(float), lows[pl])
        if not (slope > 0 and r2 >= cfg.at_lows_r2_min):
            continue
        last_low = float(lows[pl][-1])
        if not (abs(ceiling - last_low) / ceiling <= cfg.at_converge_pct):
            continue
        vslope, _, _ = linfit(np.arange(wlen, dtype=float), vols)
        if not (vslope < 0):
            continue
        depth = (ceiling - float(lows.min())) / ceiling
        v1, v2 = vols[:wlen // 2].mean(), vols[wlen // 2:].mean()
        dryup = (v1 - v2) / v1 if v1 > 0 else 0.0
        tightness = 1.0 - abs(ceiling - last_low) / ceiling / cfg.at_converge_pct
        q = touches + r2                                  # prefer more touches + a cleaner low fit
        if q > best_q:
            best_q = q
            best = finalize(
                df, cfg, pattern="ascending_triangle", buy_point=ceiling, suggested_stop=last_low,
                base_depth_pct=depth, base_length_days=wlen, dryup=dryup, tightness=tightness,
                reason_bits=[f"ascending triangle, {touches} touches of ${ceiling:.2f}",
                             "rising lows, volume declining"])
    return best
