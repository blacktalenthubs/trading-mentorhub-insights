"""Pine TBA engine port — the pattern logic of pines/muse/tba-patterns-anchored-vwap.pine
(repo main v2026.10.29.2) re-implemented on daily bars for the scanner, so the desk no
longer needs a TradingView watchlist alert (Premium) to produce `swing_tba_breakout`.

SPEC SOURCE = the Pine itself. Every threshold below is the Pine input of the same name:
  Swings: pivLen 5, ceiling tolerance 3%
  Flat base / ascending triangle: maxDepth 35%, flatDepth 15%, base length 10..120 bars
  Bull flag: poleMin 12%, poleMax 15 bars, flag 3..12 bars, maxRetrace 50% of the pole
  Cup w/ handle: lookback 80, min cup 20, depth 12..40%, rim tol 5%, handle 3..15 bars,
                 handle depth <= 12%, handle low above the cup midpoint
  Prior-high shelf: lookback 120, arm within 8% below the prior high, staging window
                 8 bars, staging close-range 5% (or the last 5 closes within 4%)
  Pattern priority (Pine order): Bull Flag > Cup w/ Handle > Ascending Triangle >
                 Flat Base > Prior-High Shelf
  Freshness: a pattern only arms while the close is within extPct 5% above its TBA;
                 it is FAILED once price closes below its stop.
  Stop at breakout (Pine stopF, afterBrk branch): max(breakout bar low, pattern stop).

DIFFERENCES from the Pine, stated plainly:
  * The Pine has NO trend prefilter by default (reqTrend=false) — neither does this port.
    The scanner's own detectors in patterns/ DO prefilter (above rising 50/200); the
    Pine port deliberately does not inherit that gate, or it would not be the Pine engine.
  * The Pine webhook fires on a 30m close crossing the LOCKED daily TBA. The scanner
    has no 30m series in this job; analytics.breakout_alerts runs on a :00/:30 cadence
    and fires when the live price crosses the TBA locked from COMPLETED daily bars —
    the same approximation the existing breakout_alerts.detect() already uses.
  * Swing pivots reuse the scanner's settled primitive (detect_utils.swing_highs /
    swing_lows, spacing = pivLen) instead of a second pivot implementation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from patterns.detect_utils import swing_highs, swing_lows

# ── Pine inputs (daily) ──────────────────────────────────────────────────────
PIV_LEN = 5
TOL_PCT = 0.03
MAX_DEPTH = 0.35
FLAT_DEPTH = 0.15
MIN_BASE = 10
MAX_BASE = 120

POLE_MIN = 0.12
POLE_MAX = 15
FLAG_MIN = 3
FLAG_MAX = 12
MAX_RETRACE = 0.50

CUP_LEN = 80
MIN_CUP = 20
CUP_MIN_D = 0.12
CUP_MAX_D = 0.40
RIM_TOL = 0.05
HANDLE_MIN = 3
HANDLE_MAX = 15
HANDLE_MAX_D = 0.12

SHELF_LOOK = 120
SHELF_ZONE = 0.08
SHELF_BARS = 8
SHELF_RNG = 0.05

EXT_PCT = 0.05
MAX_RISK = 0.08


def _pivots(values: np.ndarray, highs: bool) -> list[int]:
    fn = swing_highs if highs else swing_lows
    return [int(i) for i in fn(values, PIV_LEN)]


def detect_locked(df: pd.DataFrame) -> dict | None:
    """The Pine pattern engine on COMPLETED daily bars (the last bar is 'today' as the
    Pine's daily chart would see it). Returns {pattern, tba, stop} with Pine pattern
    labels, or None. This is the LOCKED pattern: callers pass bars through yesterday
    and test today's price against the returned TBA."""
    if df is None or len(df) < MIN_BASE + PIV_LEN + 2:
        return None
    high = df["High"].to_numpy(float)
    low = df["Low"].to_numpy(float)
    close = df["Close"].to_numpy(float)
    n = len(df)
    last = n - 1
    price = float(close[last])

    sh_idx = _pivots(high, True)
    sl_idx = _pivots(low, False)
    sh = [(i, float(high[i])) for i in sh_idx]
    sl = [(i, float(low[i])) for i in sl_idx]

    # ── Flat base / ascending triangle (Pine: ceiling = last swing high, touches
    #    within tolPct walking back until a high breaks the band) ──
    ceil_lvl = None
    touches = 0
    first_touch = None
    lows_from = None
    base_low = first_l = prev_l = last_l = None
    n_lows = 0
    if sh:
        last_h = sh[-1][1]
        ceil_lvl = last_h
        for i, h in reversed(sh):
            if last - i > MAX_BASE:
                break
            if h > last_h * (1 + TOL_PCT):
                lows_from = i
                break
            if h >= last_h * (1 - TOL_PCT):
                touches += 1
                ceil_lvl = max(ceil_lvl, h)
                first_touch = i
        if lows_from is None:
            lows_from = first_touch
        if lows_from is not None:
            for i, l in sl:
                if i > lows_from:
                    base_low = l if base_low is None else min(base_low, l)
                    if first_l is None:
                        first_l = l
                    prev_l = last_l
                    last_l = l
                    n_lows += 1
    base_len = 0 if lows_from is None else last - lows_from
    depth = (ceil_lvl - base_low) / ceil_lvl if base_low and ceil_lvl else None
    rising_lows = n_lows >= 2 and last_l is not None and prev_l is not None \
        and last_l > prev_l and last_l > first_l
    is_tri = touches >= 2 and rising_lows and depth is not None \
        and depth <= MAX_DEPTH and base_len >= MIN_BASE
    is_flat = touches >= 2 and not is_tri and depth is not None \
        and depth <= FLAT_DEPTH and base_len >= MIN_BASE

    # ── Bull flag ──
    win = high[-(FLAG_MAX + 1):]
    k = int((len(win) - 1) - int(np.argmax(win)))          # bars since the flag-window high
    pole_top = float(high[last - k]) if k <= last else float("nan")
    low_pole = low[max(0, last - POLE_MAX + 1): last + 1]
    pole_base_at = last - k
    pole_base = float(low[max(0, pole_base_at - POLE_MAX + 1): pole_base_at + 1].min()) \
        if pole_base_at >= 0 and len(low_pole) else float("nan")
    k_len = max(k, 1)
    flag_low = float(low[last - k_len + 1: last + 1].min()) if k_len <= last else float("nan")
    k_len2 = max(k - 1, 1)
    flag_high = float(high[last - k_len2: last].max()) if last - k_len2 < last else float("nan")
    pole_gain = (pole_top / pole_base - 1) if pole_base and pole_base > 0 else 0.0
    retr = ((pole_top - flag_low) / (pole_top - pole_base)) \
        if pole_top > pole_base else 1.0
    is_flag = FLAG_MIN <= k <= FLAG_MAX and pole_gain >= POLE_MIN and retr <= MAX_RETRACE

    # ── Cup with handle ──
    is_cup = False
    right_rim = handle_low = None
    if n > HANDLE_MAX + MIN_CUP:
        seg_start = max(0, last - HANDLE_MAX - (CUP_LEN - HANDLE_MAX) + 1)
        seg = high[seg_start: last - HANDLE_MAX + 1]
        if len(seg):
            lr_off = int((len(seg) - 1) - int(np.argmax(seg)))   # bars back from the high[HANDLE_MAX] bar
            left_ago = HANDLE_MAX + lr_off
            if left_ago <= last:
                left_rim = float(high[last - left_ago])
                lr_len = max(lr_off, 1)
                cup_low = float(low[max(0, last - HANDLE_MAX - lr_len + 1):
                                    last - HANDLE_MAX + 1].min())
                r_seg = high[last - HANDLE_MAX + 1: last + 1]
                r_off = int((len(r_seg) - 1) - int(np.argmax(r_seg)))
                right_rim = float(high[last - r_off])
                r_len = max(r_off, 1)
                handle_low = float(low[last - r_len + 1: last + 1].min())
                cup_depth = (left_rim - cup_low) / left_rim if left_rim > 0 else 0.0
                h_depth = (right_rim - handle_low) / right_rim if right_rim > 0 else 1.0
                cup_mid = cup_low + (left_rim - cup_low) / 2
                is_cup = (left_ago - r_off >= MIN_CUP
                          and CUP_MIN_D <= cup_depth <= CUP_MAX_D
                          and left_rim * (1 - RIM_TOL) <= right_rim <= left_rim * (1 + RIM_TOL)
                          and r_off >= HANDLE_MIN and h_depth <= HANDLE_MAX_D
                          and handle_low > cup_mid)

    # ── Prior-high shelf ──
    is_shelf = False
    shelf_stp = None
    if n > SHELF_BARS + 2:
        shelf_lvl = float(high[max(0, last - SHELF_LOOK): last].max())   # highest high[1]
        sma50 = float(pd.Series(close).rolling(50).mean().iloc[-1]) \
            if n >= 50 else float("nan")
        shelf_lo_w = float(low[last - SHELF_BARS + 1: last + 1].min())
        c5 = close[last - 4: last + 1]
        cw5 = (c5.max() / c5.min() - 1) if c5.min() > 0 else 1.0
        c8 = close[last - SHELF_BARS + 1: last + 1]
        cw = (c8.max() / c8.min() - 1) if c8.min() > 0 else 1.0
        shelf_tight = cw5 <= 0.04 or cw <= SHELF_RNG
        shelf_rising = False
        if len(sl) >= 2:
            (pi, pl_), (li, ll_) = sl[-2], sl[-1]
            shelf_rising = ll_ > pl_ and last - li <= SHELF_BARS * 3
        is_shelf = (price < shelf_lvl and price >= shelf_lvl * (1 - SHELF_ZONE)
                    and sma50 == sma50 and price > sma50
                    and (shelf_tight or shelf_rising))
        if is_shelf:
            shelf_stp = shelf_lo_w if shelf_tight else (sl[-1][1] if sl else None)
            if shelf_stp is not None and shelf_stp >= price:
                is_shelf = False

    # ── Pick the pattern (Pine priority order) ──
    pat = tba = stp = None
    if is_flag:
        pat, tba, stp = "Bull Flag", flag_high, flag_low
    elif is_cup:
        pat, tba, stp = "Cup w/ Handle", right_rim, handle_low
    elif is_tri:
        pat, tba, stp = "Ascending Triangle", ceil_lvl, last_l
    elif is_flat:
        pat, tba, stp = "Flat Base", ceil_lvl, last_l
    elif is_shelf:
        pat, tba, stp = "Prior-High Shelf", float(high[max(0, last - SHELF_LOOK): last].max()), shelf_stp
    if pat is None or tba is None or not np.isfinite(tba):
        return None
    # Pine freshness + failure: only arm near the TBA; a close below the stop kills it.
    if price > tba * (1 + EXT_PCT):
        return None
    if stp is not None and price <= stp:
        return None
    return {"pattern": pat, "tba": round(float(tba), 2),
            "stop": round(float(stp), 2) if stp is not None else None}


def locked_resistance(df: pd.DataFrame, tba: float) -> float | None:
    """Pine hook target: the nearest locked resistance above the TBA (swing highs /
    swing lows / 10-day high on the completed bars), only when > 0.5% above the TBA."""
    if df is None or len(df) < 11:
        return None
    high = df["High"].to_numpy(float)
    low = df["Low"].to_numpy(float)
    cands: list[float] = []
    for i in _pivots(high, True):
        if len(df) - i <= 120:
            cands.append(float(high[i]))
    for i in _pivots(low, False):
        if len(df) - i <= 120:
            cands.append(float(low[i]))
    cands.append(float(high[-10:].max()))
    above = [c for c in cands if c > tba * 1.005]
    return round(min(above), 2) if above else None
