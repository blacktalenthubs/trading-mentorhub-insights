"""Flat base — a tight, shallow, volume-contracting consolidation AFTER a ≥20% advance (a
continuation pattern, not a bottom). buy_point = base high, stop = base low."""
from __future__ import annotations

from patterns.config import PatternConfig
from patterns.detect_utils import finalize


def detect(df, cfg: PatternConfig):
    n = len(df)
    highs, lows, closes, vols = df["High"].values, df["Low"].values, df["Close"].values, df["Volume"].values
    sma50 = df["sma50"].values

    best = None
    # Windows of fb_min..fb_max bars ending at the most recent bar; take the best (deepest funnel
    # of tightness/dry-up). Prefer the LONGER valid base (more constructive).
    for wlen in range(cfg.fb_min_bars, cfg.fb_max_bars + 1):
        if n < wlen + cfg.fb_prior_advance_bars:
            break
        s = n - wlen
        w_high, w_low = highs[s:].max(), lows[s:].min()
        depth = (w_high - w_low) / w_high if w_high else 1.0
        if depth > cfg.fb_depth_max:
            continue
        # Prior advance: ≥20% run in the fb_prior_advance_bars before the window.
        p0, p1 = closes[s - cfg.fb_prior_advance_bars], closes[s]
        if p0 <= 0 or (p1 - p0) / p0 < cfg.fb_prior_advance:
            continue
        # Contraction: second half's range ≤ first half's range.
        mid = s + wlen // 2
        r1 = highs[s:mid].max() - lows[s:mid].min()
        r2 = highs[mid:].max() - lows[mid:].min()
        if not (r2 <= r1) or r1 <= 0:
            continue
        # Volume dry-up: second-half avg volume below first-half.
        v1, v2 = vols[s:mid].mean(), vols[mid:].mean()
        if not (v2 < v1) or v1 <= 0:
            continue
        # No close below the 50-SMA inside the base.
        if (closes[s:] < sma50[s:]).any():
            continue
        dryup = (v1 - v2) / v1
        tightness = 1.0 - depth / cfg.fb_depth_max
        cand = finalize(
            df, cfg, pattern="flat_base", buy_point=w_high, suggested_stop=w_low,
            base_depth_pct=depth, base_length_days=wlen,
            dryup=dryup, tightness=tightness,
            reason_bits=[f"{wlen // 5}-week flat base, {depth*100:.1f}% deep",
                         "range + volume contracting"])
        # Keep the longest qualifying base.
        best = cand
    return best
