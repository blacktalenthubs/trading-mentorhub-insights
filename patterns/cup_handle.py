"""Cup-and-handle. Rounded cup (not a V) + a shallow, low-volume handle in the cup's upper
half. buy_point = handle high, stop = handle low. See config for every threshold."""
from __future__ import annotations

import numpy as np

from patterns.config import PatternConfig
from patterns.detect_utils import finalize


def detect(df, cfg: PatternConfig):
    seg = df.tail(cfg.ch_search_bars).reset_index(drop=True)
    n = len(seg)
    if n < cfg.ch_min_cup_days + cfg.ch_handle_min_days + 5:
        return None
    highs, lows, closes, vols = seg["High"].values, seg["Low"].values, seg["Close"].values, seg["Volume"].values
    w = cfg.ch_rim_side_bars

    # Left rim = a bar whose high is the max of `w` bars each side. Try the tallest rims first.
    rims = [i for i in range(w, n - w) if highs[i] >= highs[i - w:i + w + 1].max()]
    rims.sort(key=lambda i: highs[i], reverse=True)

    for rim in rims:
        rim_high = highs[rim]
        after_lows = lows[rim + 1:]
        if len(after_lows) < cfg.ch_min_cup_days:
            continue
        cup_low_idx = rim + 1 + int(np.argmin(after_lows))
        cup_low = lows[cup_low_idx]
        depth = (rim_high - cup_low) / rim_high
        if not (cfg.ch_depth_min <= depth <= cfg.ch_depth_max):
            continue
        # Recovery = first close back within recover_pct of the rim, after the cup low.
        rec_idx = None
        for j in range(cup_low_idx + 1, n):
            if closes[j] >= rim_high * (1 - cfg.ch_recover_pct):
                rec_idx = j
                break
        if rec_idx is None:
            continue
        span = rec_idx - rim
        if span < cfg.ch_min_cup_days:
            continue
        # Rounded, not a V: middle third lower than both outer thirds.
        t1, t2 = rim + span // 3, rim + 2 * span // 3
        if not (t1 > rim and t2 > t1 and rec_idx > t2):
            continue
        left_avg, mid_avg, right_avg = closes[rim:t1].mean(), closes[t1:t2].mean(), closes[t2:rec_idx + 1].mean()
        if not (mid_avg < left_avg and mid_avg < right_avg):
            continue
        # The low must sit in the middle, not the first/last quarter of the span.
        low_frac = (cup_low_idx - rim) / span
        if low_frac < cfg.ch_low_exclude_edge_frac or low_frac > 1 - cfg.ch_low_exclude_edge_frac:
            continue

        # Handle = bars from recovery to the current bar. buy_point excludes the current bar
        # (so a breakout bar doesn't inflate the trigger).
        handle_len = n - rec_idx
        if not (cfg.ch_handle_min_days <= handle_len <= cfg.ch_handle_max_days + 1):
            continue
        h_high = highs[rec_idx:n - 1].max() if n - 1 > rec_idx else highs[rec_idx]
        h_low = lows[rec_idx:n].min()
        h_depth = (h_high - h_low) / h_high if h_high else 1.0
        if not (cfg.ch_handle_depth_min <= h_depth <= cfg.ch_handle_depth_max):
            continue
        if not (h_low > cup_low + cfg.ch_handle_upper_half_frac * (rim_high - cup_low)):
            continue
        # Volume dry-up: handle volume below the cup's right side.
        cup_right_vol = vols[t2:rec_idx + 1].mean()
        handle_vol = vols[rec_idx:n].mean()
        if not (handle_vol < cup_right_vol) or cup_right_vol <= 0:
            continue
        dryup = (cup_right_vol - handle_vol) / cup_right_vol
        tightness = 1.0 - (h_depth - cfg.ch_handle_depth_min) / (cfg.ch_handle_depth_max - cfg.ch_handle_depth_min)

        return finalize(
            df, cfg, pattern="cup_handle", buy_point=h_high, suggested_stop=h_low,
            base_depth_pct=depth, base_length_days=span,
            dryup=dryup, tightness=tightness,
            reason_bits=[f"cup {depth*100:.0f}% deep over {span} days",
                         f"handle {h_depth*100:.0f}% on drying volume"])
    return None
