"""Reclaim-long edge validation across the FULL alert watchlist (#65).

The reclaim_long alert went live on 7 symbols (SPY/QQQ/DRAM/MU/IWM/SMH/SOXL). This
re-runs the EXACT Pine logic (index_reclaim_long.pine) over 3 years on every symbol,
with the blue-sky (no-overhead) reclaims INCLUDED (~2/3 of all fires), under two exits.

FINDINGS (3yr, 15m, modeled weekly-ATM options net of spread+theta+fees):
  • UNDERLYING edge is REAL but MODEST: ~+0.12R avg, ~48–50% win (NOT the 77%/+0.80R
    that was cited from a narrower run — that figure was optimistic).
  • On OPTIONS it is roughly BREAKEVEN overall (+0.2%/trade target-exit, −0.4% trail) —
    the small underlying edge gets eaten by option spread+theta on the low-vol names.
  • SOXL is the consistent standout (+3.4 to +4.3%/trade) — high vol = the move is large
    vs the premium. SPY marginally positive; QQQ/SMH/MU/IWM flat-to-negative on options.
  • Trailing did NOT rescue it (gives back open profit + more theta). Target-exit ≥ trail.
  CAVEAT: option numbers are MODELED (assumed IV/spread), not real fills — live data is
  the arbiter. Likely read: a SHARES edge, and an OPTIONS edge only on high-vol names.

Mirrors the Pine f_reclaim state machine:
  price closes ABOVE the level → dips ~0.18% UNDER it (shakeout) → RECLAIMS (close back
  above) within N bars, in the first 120 min, above VWAP, WITH ≥1R of room to the next
  resistance (or blue sky) → LONG. entry = reclaim close · stop = dip low.

Run:  python3 analytics/reclaim_long_backtest.py
"""
from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from index_daytrade import _fetch_15m_alpaca, _fetch_15m, add_vwap, _bs

# ── mirror the Pine inputs ───────────────────────────────────────────────────
OR_BARS       = 2        # 30 min opening range (orMin=30 / 15m)
DIP_PCT       = 0.0018   # shakeout dip below the level (0.18%)
RECLAIM_BARS  = 6        # reclaim within N bars of the dip
MORNING_BARS  = 8        # first 120 min (morningMin=120 / 15m)
HEADROOM_MIN_R = 1.0
TARGET_FB_R    = 2.0     # blue-sky (no overhead) target in R
USE_VWAP      = True

OPT_DTE_DAYS    = 3
OPT_IV          = {"SPY": 0.15, "QQQ": 0.19, "IWM": 0.20, "SMH": 0.28,
                   "DRAM": 0.45, "MU": 0.40, "SOXL": 0.70}
OPT_HALF_SPREAD = 0.025
OPT_COMMISH_PCT = 0.004


@dataclass
class Trade:
    symbol: str
    date: str
    level: str
    entry_idx: int
    entry: float
    stop: float
    target: float
    exit: float = field(default=np.nan)
    exit_idx: int = -1
    exit_reason: str = ""
    r: float = field(default=np.nan)


def _next_above(levels, p):
    above = [x for x in levels if x is not None and x == x and x > p]
    return min(above) if above else None


def _reclaim_for_level(L, H, Lo, C, Vw, all_levels, n, use_vwap):
    """Pine f_reclaim for one level L. Returns (entry_idx, entry, stop, target) or None."""
    above = dipped = False
    dipbar = 0
    dlow = np.nan
    for j in range(OR_BARS, min(MORNING_BARS, n)):
        if C[j] > L:
            above = True
        if above and not dipped and Lo[j] <= L * (1 - DIP_PCT):
            dipped = True; dipbar = j; dlow = Lo[j]
        if dipped:
            dlow = min(dlow, Lo[j])
            reclaimed = (C[j] > L) and (j - dipbar <= RECLAIM_BARS)
            vwap_ok = (not use_vwap) or (C[j] > Vw[j])
            if reclaimed and vwap_ok and j > dipbar:
                risk = max(C[j] - dlow, 1e-9)
                tgt = _next_above(all_levels, C[j])
                if tgt is None:
                    # blue sky — no overhead resistance (Pine fires with headroom=99);
                    # model the discretionary runner as a 2R target.
                    tgt = C[j] + TARGET_FB_R * risk
                elif (tgt - C[j]) / risk < HEADROOM_MIN_R:
                    return None
                return (j, float(C[j]), float(dlow), float(tgt))
    return None


def find_reclaims(day: pd.DataFrame, pdh, pdl, symbol="", date="", use_vwap=USE_VWAP) -> list[Trade]:
    if day is None or len(day) < OR_BARS + 3:
        return []
    day = add_vwap(day)
    H, Lo, C = (day[c].values.astype(float) for c in ("High", "Low", "Close"))
    Vw = day["vwap"].values.astype(float)
    n = len(C)
    orh = float(H[:OR_BARS].max())
    orl = float(Lo[:OR_BARS].min())
    all_levels = [orh, orl, pdh, pdl]
    out = []
    for name, L in (("ORH", orh), ("PDH", pdh)):
        if L is None or L != L:
            continue
        res = _reclaim_for_level(L, H, Lo, C, Vw, all_levels, n, use_vwap)
        if res:
            j, ent, stp, tgt = res
            out.append(Trade(symbol, date, name, j, ent, stp, tgt))
    return out


def simulate(t: Trade, H, Lo, C, ema, n, mode="target"):
    """mode='target' → take profit INTO the next resistance (conservative, caps the
    winner). mode='trail' → once +0.5R, let it run and exit on the first close back
    below EMA8 (lets a trend day pay). Both hard-stop at the dip low; flat at EOD."""
    risk = t.entry - t.stop
    if risk <= 0:
        return
    armed = False
    arm_level = t.entry + 0.5 * risk
    for k in range(t.entry_idx + 1, n):
        if Lo[k] <= t.stop:
            t.exit, t.exit_idx, t.exit_reason = t.stop, k, "stop"; break
        if mode == "target":
            if H[k] >= t.target:
                t.exit, t.exit_idx, t.exit_reason = t.target, k, "target"; break
        else:
            if H[k] >= arm_level:
                armed = True
            if armed and C[k] < ema[k]:
                t.exit, t.exit_idx, t.exit_reason = C[k], k, "trail"; break
    if t.exit_reason == "":
        t.exit, t.exit_idx, t.exit_reason = C[n - 1], n - 1, "eod"
    t.r = (t.exit - t.entry) / risk


def backtest_symbol(symbol: str, use_vwap=USE_VWAP, mode="target") -> list[Trade]:
    df = _fetch_15m_alpaca(symbol)
    if df is None or df.empty:
        df = _fetch_15m(symbol, "60d")
    if df is None or df.empty:
        return []
    df = df.copy()
    df["d"] = df.index.date
    out, prev_h, prev_l = [], None, None
    for d, day in df.groupby("d"):
        day = day.drop(columns=["d"])
        ts = find_reclaims(day, prev_h, prev_l, symbol, str(d), use_vwap)
        H, Lo, C = (day[c].values.astype(float) for c in ("High", "Low", "Close"))
        ema = pd.Series(C).ewm(span=8, adjust=False).mean().values
        for t in ts:
            simulate(t, H, Lo, C, ema, len(C), mode)
            if t.r == t.r:
                out.append(t)
        prev_h, prev_l = float(day["High"].max()), float(day["Low"].max() if False else day["Low"].min())
    return out


def option_overlay(trades):
    rows = []
    for t in trades:
        iv = OPT_IV.get(t.symbol, 0.25)
        K = round(t.entry)
        T0 = OPT_DTE_DAYS / 365.0
        held = max(1, t.exit_idx - t.entry_idx)
        T1 = max(0.5 / 365.0, T0 - held * 0.25 / (365 * 24))
        ep = _bs(t.entry, K, T0, iv, call=True) * (1 + OPT_HALF_SPREAD)
        xp = _bs(t.exit, K, T1, iv, call=True) * (1 - OPT_HALF_SPREAD)
        if ep <= 0:
            continue
        rows.append((t.symbol, ((xp - ep) / ep - OPT_COMMISH_PCT) * 100, t.r))
    return rows


def report(trades, title):
    print(f"\n========== {title} ==========")
    if not trades:
        print("  no trades"); return
    g = collections.defaultdict(list)
    for t in trades:
        g[t.symbol].append(t.r)
    print(f"{'symbol':6} {'n':>4} {'win%':>6} {'avgR':>7} {'totR':>8} {'/yr':>5}")
    print("  " + "-" * 42)
    for sym, rs in sorted(g.items()):
        rs = np.array(rs)
        print(f"{sym:6} {len(rs):>4} {(rs>0).mean()*100:>5.0f}% {rs.mean():>+7.2f} {rs.sum():>+8.1f} {len(rs)/3.0:>5.0f}")
    allr = np.array([t.r for t in trades])
    print("  " + "-" * 42)
    print(f"{'ALL':6} {len(allr):>4} {(allr>0).mean()*100:>5.0f}% {allr.mean():>+7.2f} {allr.sum():>+8.1f}")


def option_report(rows, title):
    print(f"\n========== {title} ==========")
    if not rows:
        print("  no option trades"); return
    g = collections.defaultdict(list)
    for sym, ret, r in rows:
        g[sym].append(ret)
    print(f"{'symbol':6} {'n':>4} {'win%':>6} {'avg%':>8} {'tot%':>9}")
    print("  " + "-" * 40)
    for sym, rs in sorted(g.items()):
        rs = np.array(rs)
        print(f"{sym:6} {len(rs):>4} {(rs>0).mean()*100:>5.0f}% {rs.mean():>+7.1f}% {rs.sum():>+8.0f}%")
    allr = np.array([x[1] for x in rows])
    print("  " + "-" * 40)
    print(f"{'ALL':6} {len(allr):>4} {(allr>0).mean()*100:>5.0f}% {allr.mean():>+7.1f}% {allr.sum():>+8.0f}%")


if __name__ == "__main__":
    import sys, warnings
    warnings.filterwarnings("ignore")
    syms = sys.argv[1:] or ["SPY", "QQQ", "DRAM", "MU", "IWM", "SMH", "SOXL"]
    for mode in ("target", "trail"):
        trades = []
        for s in syms:
            trades += backtest_symbol(s, mode=mode)
        report(trades, f"RECLAIM-LONG [{mode.upper()}] — UNDERLYING R (3yr, 15m)")
        option_report(option_overlay(trades), f"RECLAIM-LONG [{mode.upper()}] — WEEKLY-ATM OPTIONS")
