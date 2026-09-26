"""Shared detector primitives — the pre-filter, the breakout confirmation, swing/line
geometry, and score composition. Every pattern module builds on these so the rules stay
consistent (and tunable only through config)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from patterns.config import PatternConfig

# Ordered so the funnel log reads left-to-right; the FIRST failing gate names the drop.
PREFILTER_GATES = ("price", "liquidity", "above_200", "rising_200", "near_52w_high", "off_52w_low")


def prefilter(df: pd.DataFrame, cfg: PatternConfig) -> str:
    """Return "" if the last bar passes every pre-filter, else the name of the first gate it
    fails (for the funnel counts). Assumes add_indicators() has run."""
    r = df.iloc[-1]
    if not (r["Close"] > cfg.min_close):
        return "price"
    if not (r["avg_vol_50"] > cfg.min_avg_vol):
        return "liquidity"
    if cfg.require_above_sma200 and not (r["Close"] > r["sma200"]):
        return "above_200"
    if cfg.require_rising_sma200 and not (r["sma200_slope"] > 0):
        return "rising_200"
    hi, lo, c = r["hi_52w"], r["lo_52w"], r["Close"]
    if not (hi > 0 and (hi - c) / hi <= cfg.max_pct_below_52w_high):
        return "near_52w_high"
    if not (lo > 0 and (c - lo) / lo >= cfg.min_pct_above_52w_low):
        return "off_52w_low"
    return ""


@dataclass
class Breakout:
    is_breakout: bool
    volume_ok: bool
    rvol: float


def breakout_confirm(df: pd.DataFrame, buy_point: float, cfg: PatternConfig) -> Breakout:
    """The shared breakout test on the MOST RECENT bar: close > buy_point, rvol ≥ threshold,
    close in the upper half of the bar (no fat upper wick), and a green bar. `volume_ok`/`rvol`
    are returned even when it isn't a full breakout so borderline setups are visible."""
    r = df.iloc[-1]
    rvol = float(r["rvol"]) if pd.notna(r["rvol"]) else 0.0
    rng = float(r["High"] - r["Low"])
    upper_ok = rng <= 0 or (float(r["Close"] - r["Low"]) >= cfg.breakout_close_upper_frac * rng)
    volume_ok = rvol >= cfg.breakout_rvol
    is_bk = (float(r["Close"]) > buy_point and volume_ok and upper_ok and float(r["Close"]) > float(r["Open"]))
    return Breakout(is_bk, volume_ok, round(rvol, 2))


def _find_peaks(x: np.ndarray, distance: int) -> np.ndarray:
    """scipy.signal.find_peaks when available; a numpy local-maxima fallback otherwise (same
    behaviour: local maxima, then greedily enforce a minimum spacing keeping the taller peak)."""
    try:
        from scipy.signal import find_peaks
        idx, _ = find_peaks(x, distance=max(1, distance))
        return idx
    except Exception:
        n = len(x)
        cands = [i for i in range(1, n - 1) if x[i] > x[i - 1] and x[i] >= x[i + 1]]
        cands.sort(key=lambda i: -x[i])
        kept: list[int] = []
        for p in cands:
            if all(abs(p - k) >= distance for k in kept):
                kept.append(p)
        return np.array(sorted(kept), dtype=int)


def swing_highs(highs: np.ndarray, distance: int) -> np.ndarray:
    return _find_peaks(np.asarray(highs, float), max(1, distance))


def swing_lows(lows: np.ndarray, distance: int) -> np.ndarray:
    return _find_peaks(-np.asarray(lows, float), max(1, distance))


def linfit(x: np.ndarray, y: np.ndarray):
    """Least-squares line → (slope, intercept, r2). r2 = 0 for a degenerate fit."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 2:
        return 0.0, float(y[-1]) if len(y) else 0.0, 0.0
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return float(slope), float(intercept), float(r2)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def trend_subscore(df: pd.DataFrame) -> float:
    """0..1 trend strength for the score: 200-SMA slope + distance above it + a constructive
    RSI band (breakouts want strength but not blow-off)."""
    r = df.iloc[-1]
    slope = float(r["sma200_slope"]) if pd.notna(r["sma200_slope"]) else 0.0
    dist = (float(r["Close"]) - float(r["sma200"])) / float(r["sma200"]) if r["sma200"] else 0.0
    rsi = float(r["rsi14"]) if pd.notna(r["rsi14"]) else 50.0
    s_slope = _clamp01(slope / 3.0)            # +3% over 10 bars = full marks
    s_dist = _clamp01(dist / 0.15)             # 15% above the 200 = full marks
    s_rsi = _clamp01(1.0 - abs(rsi - 60.0) / 40.0)  # best around 60, fades toward 20/100
    return _clamp01(0.4 * s_slope + 0.35 * s_dist + 0.25 * s_rsi)


def compose_score(parts: dict, df: pd.DataFrame, cfg: PatternConfig) -> int:
    """0-100 composite. parts carries 0..1 sub-scores from the detector: volume_dryup,
    tightness, duration. Trend is measured here. Weights live in config."""
    trend = trend_subscore(df)
    total = (cfg.w_volume * _clamp01(parts.get("volume_dryup", 0.0))
             + cfg.w_tight * _clamp01(parts.get("tightness", 0.0))
             + cfg.w_duration * _clamp01(parts.get("duration", 0.0))
             + cfg.w_trend * trend)
    return int(round(100 * total))


def duration_subscore(days: int, cfg: PatternConfig) -> float:
    """Longer bases score higher, capped at duration_full_days."""
    return _clamp01(days / float(cfg.duration_full_days))


def finalize(df, cfg, *, pattern, buy_point, suggested_stop, base_depth_pct,
             base_length_days, dryup, tightness, reason_bits):
    """Every detector returns THIS shape. Runs the shared breakout confirm to set stage +
    volume_ok/rvol, packs the 0..1 score sub-parts, and carries reason fragments the screener
    stitches into the plain-English string."""
    bk = breakout_confirm(df, buy_point, cfg)
    return {
        "pattern": pattern,
        "stage": "breakout" if bk.is_breakout else "forming",
        "buy_point": round(float(buy_point), 2),
        "suggested_stop": round(float(suggested_stop), 2),
        "base_depth_pct": round(float(base_depth_pct) * 100.0, 1),
        "base_length_days": int(base_length_days),
        "volume_ok": bool(bk.volume_ok),
        "rvol": bk.rvol,
        "_parts": {"volume_dryup": _clamp01(dryup), "tightness": _clamp01(tightness),
                   "duration": duration_subscore(base_length_days, cfg)},
        "reason_bits": list(reason_bits),
    }
