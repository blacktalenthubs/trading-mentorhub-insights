"""Horizontal resistance / TBA (Dan Zanger) — a flat ceiling touched ≥3 times, sitting near
price, that breaks on volume. buy_point (the "TBA") = the ceiling, stop ("max stop") = the
consolidation low. Like the ascending triangle but the lows need not rise."""
from __future__ import annotations

from patterns.ascending_triangle import _ceiling
from patterns.config import PatternConfig
from patterns.detect_utils import finalize, swing_highs, swing_lows


def detect(df, cfg: PatternConfig):
    n = len(df)
    price = float(df["Close"].iloc[-1])
    best, best_touches = None, -1
    for wlen in range(cfg.ht_min_bars, cfg.ht_max_bars + 1):
        if n < wlen:
            break
        seg = df.iloc[n - wlen:]
        highs, lows, vols = seg["High"].values, seg["Low"].values, seg["Volume"].values
        ph = swing_highs(highs, cfg.ht_peak_distance)
        if len(ph) < cfg.ht_min_touches:
            continue
        ceil_res = _ceiling(highs[ph], cfg.ht_level_tol, cfg.ht_min_touches)
        if ceil_res is None:
            continue
        ceiling, touches = ceil_res
        if ceiling <= 0 or abs(ceiling - price) / price > cfg.ht_max_level_dist:
            continue                                           # ceiling must be near price = actionable
        # Fresh only: the PRIOR bar must still be at/below the line (so we don't flag a name that
        # broke out and ran days ago — that's a chase, not a setup).
        prev_close = float(seg["Close"].iloc[-2])
        if prev_close > ceiling * (1 + cfg.ht_level_tol):
            continue
        base_low = float(lows.min())
        depth = (ceiling - base_low) / ceiling
        v1, v2 = vols[:wlen // 2].mean(), vols[wlen // 2:].mean()
        dryup = (v1 - v2) / v1 if v1 > 0 else 0.0
        pl = swing_lows(lows, cfg.ht_peak_distance)
        stop = float(lows[pl][-1]) if len(pl) > 0 else base_low
        tightness = max(0.0, 1.0 - depth / 0.20)
        if touches > best_touches:
            best_touches = touches
            best = finalize(
                df, cfg, pattern="horizontal_tba", buy_point=ceiling, suggested_stop=stop,
                base_depth_pct=depth, base_length_days=wlen, dryup=dryup, tightness=tightness,
                reason_bits=[f"flat resistance (TBA) ${ceiling:.2f}, {touches} touches",
                             "consolidating below the line"])
    return best
