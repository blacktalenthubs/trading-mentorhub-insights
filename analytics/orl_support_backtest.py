"""ORL-as-support bounce — does it earn an alert? (#65 follow-up)

The user's chart observation: most days the opening-range LOW (ORL) holds as support —
price establishes above it, pulls back to test it, and bounces. That is a DISTINCT
mechanic from the reclaim_long alert:

  • reclaim_long  = price UNDERCUTS the level (shakeout), then RECLAIMS it  → long
  • orl_bounce    = price stays ABOVE the level, pulls back to TOUCH it, HOLDS → long

This script tests the bounce the same rigorous way the reclaim earned its alert:
3 years of 15-min RTH bars, headroom gate (≥1R of room to the next resistance),
take-profit INTO that resistance, long-only, and a weekly-ATM option overlay net of
spread + theta + commission. If it doesn't clear a real bar, it does NOT get an alert.

Run:  python3 analytics/orl_support_backtest.py
      python3 analytics/orl_support_backtest.py SPY QQQ IWM SMH
"""
from __future__ import annotations

import collections
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

# reuse the proven data fetch + vwap + black-scholes from the reclaim engine
from index_daytrade import _fetch_15m_alpaca, _fetch_15m, add_vwap, _bs

# ── Tunables ─────────────────────────────────────────────────────────────────
OR_BARS        = 2        # opening range = first 2 × 15m = 30 min
TOUCH_PCT      = 0.0015   # the pullback low must come within 0.15% of ORL (a real test)
HOLD_BUF       = 0.0005   # ...and the bar must CLOSE ≥0.05% above ORL (it held)
MORNING_BARS   = 12       # only take the bounce in the active session (9:30–12:30)
HEADROOM_MIN_R = 1.0      # need ≥1R of room to the next resistance — no ceiling buys
MIN_RISK_PCT   = 0.0004   # skip hair-tight stops (noise)
USE_VWAP       = True      # require the bounce close above VWAP (toggleable below)

# weekly-ATM option overlay (same frictions as the reclaim test)
OPT_DTE_DAYS    = 3
OPT_IV          = {"SPY": 0.15, "QQQ": 0.19, "IWM": 0.20, "SMH": 0.28,
                   "DRAM": 0.45, "MU": 0.40, "SOXL": 0.70}
OPT_HALF_SPREAD = 0.025
OPT_COMMISH_PCT = 0.004


@dataclass
class Trade:
    symbol: str
    date: str
    entry_idx: int
    entry: float
    stop: float
    target: float
    exit: float = field(default=np.nan)
    exit_idx: int = -1
    exit_reason: str = ""
    r: float = field(default=np.nan)


def _next_above(levels, v):
    above = [x for x in levels if x > v * 1.0008]
    return min(above) if above else None


def find_orl_bounce(day: pd.DataFrame, pdh: Optional[float], pdl: Optional[float],
                    symbol: str = "", date: str = "", use_vwap: bool = USE_VWAP) -> Optional[Trade]:
    """ONE session. The ORL must be INTACT (no close below it) when price pulls back
    to test it and HOLDS (close stays above) → long, TP into the next resistance.
    Returns the (at most one) bounce trade for the day, or None."""
    if day is None or len(day) < OR_BARS + 3:
        return None
    day = add_vwap(day)
    O, H, L, C = (day[c].values.astype(float) for c in ("Open", "High", "Low", "Close"))
    Vw = day["vwap"].values.astype(float)
    n = len(C)

    orh = float(H[:OR_BARS].max())
    orl = float(L[:OR_BARS].min())
    # resistances ABOVE that can serve as the take-profit target
    res = sorted(x for x in (orh, pdh, pdl) if x is not None and x == x and x > orl)

    intact = True  # ORL has not been lost (no decisive close below it)
    for j in range(OR_BARS, min(MORNING_BARS, n)):
        if C[j] < orl * (1 - HOLD_BUF):       # lost the level → it's no longer support
            intact = False
            break
        touched = L[j] <= orl * (1 + TOUCH_PCT)   # came down and tested ORL
        held    = C[j] > orl * (1 + HOLD_BUF)     # but closed back above it
        pulled_in = L[j] < L[j - 1]               # this bar dipped (a pullback, not a rip)
        if intact and touched and held and pulled_in:
            entry = float(C[j])
            stop  = float(min(L[j], orl) * (1 - HOLD_BUF))
            risk  = entry - stop
            if risk < entry * MIN_RISK_PCT:
                return None
            tgt = _next_above(res, entry)
            if tgt is None:
                return None                        # no defined resistance to take profit into
            if (tgt - entry) / risk < HEADROOM_MIN_R:
                return None                        # ceiling overhead — skip
            if use_vwap and not (entry > Vw[j]):
                return None
            return Trade(symbol, date, j, entry, stop, float(tgt))
    return None


def simulate(t: Trade, H, L, C, n) -> None:
    """Long only. Hard stop = below ORL; take profit INTO the next resistance; else
    flat at the close."""
    risk = t.entry - t.stop
    if risk <= 0:
        return
    for k in range(t.entry_idx + 1, n):
        if L[k] <= t.stop:
            t.exit, t.exit_idx, t.exit_reason = t.stop, k, "stop"; break
        if H[k] >= t.target:
            t.exit, t.exit_idx, t.exit_reason = t.target, k, "target"; break
    if t.exit_reason == "":
        t.exit, t.exit_idx, t.exit_reason = C[n - 1], n - 1, "eod"
    t.r = (t.exit - t.entry) / risk


def backtest_symbol(symbol: str, use_vwap: bool = USE_VWAP) -> list[Trade]:
    df = _fetch_15m_alpaca(symbol)
    if df is None or df.empty:
        df = _fetch_15m(symbol, "60d")
    if df is None or df.empty:
        return []
    df = df.copy()
    df["d"] = df.index.date
    out: list[Trade] = []
    prev_h = prev_l = None
    for d, day in df.groupby("d"):
        day = day.drop(columns=["d"])
        t = find_orl_bounce(day, prev_h, prev_l, symbol, str(d), use_vwap)
        if t is not None:
            H, L, C = (day[c].values.astype(float) for c in ("High", "Low", "Close"))
            simulate(t, H, L, C, len(C))
            if t.r == t.r:
                out.append(t)
        prev_h, prev_l = float(day["High"].max()), float(day["Low"].min())
    return out


def option_overlay(trades: list[Trade]) -> list[tuple]:
    rows = []
    for t in trades:
        iv = OPT_IV.get(t.symbol, 0.25)
        K = round(t.entry)
        T0 = OPT_DTE_DAYS / 365.0
        held_bars = max(1, t.exit_idx - t.entry_idx)
        held_years = held_bars * 0.25 / (365 * 24)
        T1 = max(0.5 / 365.0, T0 - held_years)
        entry_px = _bs(t.entry, K, T0, iv, call=True) * (1 + OPT_HALF_SPREAD)
        exit_px = _bs(t.exit, K, T1, iv, call=True) * (1 - OPT_HALF_SPREAD)
        if entry_px <= 0:
            continue
        ret = (exit_px - entry_px) / entry_px - OPT_COMMISH_PCT
        rows.append((t.symbol, ret * 100, t.r))
    return rows


def report(trades: list[Trade], title: str) -> None:
    print(f"\n========== {title} ==========")
    if not trades:
        print("  no trades"); return
    g = collections.defaultdict(list)
    for t in trades:
        g[t.symbol].append(t.r)
    print(f"{'symbol':6} {'n':>4} {'win%':>6} {'avgR':>7} {'totR':>8}")
    print("  " + "-" * 36)
    for sym, rs in sorted(g.items()):
        rs = np.array(rs)
        print(f"{sym:6} {len(rs):>4} {(rs>0).mean()*100:>5.0f}% {rs.mean():>+7.2f} {rs.sum():>+8.1f}")
    allr = np.array([t.r for t in trades])
    print("  " + "-" * 36)
    print(f"{'ALL':6} {len(allr):>4} {(allr>0).mean()*100:>5.0f}% {allr.mean():>+7.2f} {allr.sum():>+8.1f}")


def option_report(rows: list[tuple], title: str) -> None:
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
    syms = sys.argv[1:] or ["SPY", "QQQ", "IWM", "SMH", "MU", "DRAM"]

    # A) with the VWAP filter (bounce must be above VWAP)
    with_vwap: list[Trade] = []
    for s in syms:
        ts = backtest_symbol(s, use_vwap=True)
        print(f"{s:6} {len(ts):>3} ORL-bounce trades (VWAP filter ON)")
        with_vwap += ts
    report(with_vwap, "ORL-SUPPORT BOUNCE — UNDERLYING R (VWAP ON, 3yr, 15m)")
    option_report(option_overlay(with_vwap), "ORL BOUNCE — WEEKLY-ATM OPTIONS (net spread+theta+fees)")

    # B) without the VWAP filter (the level alone) — does VWAP help or hurt here?
    no_vwap: list[Trade] = []
    for s in syms:
        no_vwap += backtest_symbol(s, use_vwap=False)
    report(no_vwap, "ORL-SUPPORT BOUNCE — UNDERLYING R (VWAP OFF, level only)")
    option_report(option_overlay(no_vwap), "ORL BOUNCE (VWAP OFF) — WEEKLY-ATM OPTIONS")
