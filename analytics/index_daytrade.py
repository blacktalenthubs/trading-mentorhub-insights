"""Core-Index Day-Trade Desk — boundary engine + backtest (#65).

The day book for SPY / QQQ / DRAM, both directions, built for a non-trending tape.
It fires ONLY at a structural boundary (ORH/ORL · PDH/PDL), on one of two triggers:

  • Continuation — boundary breaks, price RETESTS AND HOLDS it → enter with the break.
  • Failed break — boundary breaks, the retest FAILS, price reclaims back → fade to
    the other boundary (the A-trade).

VWAP is a FILTER (long must be above it, short below), never a trigger — that kills the
mid-range chop. Stop = the boundary; target = the next boundary; flat by the close.

This module is pure + deterministic so it backtests: `find_trades(day_bars, pdh, pdl)`
returns the day's trades with entry/stop/target/exit/R. `backtest()` runs it over
15-min history and reports count · win% · avg-R · expectancy per (symbol, trigger, dir).
Risk (entry→stop) = 1R; the weekly-ATM option overlay is a later layer — here we prove
the underlying edge in R first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

# ── Tunables (top-of-file so the backtest is easy to sweep) ──────────────────
OR_BARS       = 2        # opening-range = first N bars (2 × 15m = 30 min)
LOOKFWD       = 4        # bars to watch for a retest/fail after a break (≈1h)
BUF_PCT       = 0.0005   # 0.05% — a break must close beyond the level by this
RETEST_PCT    = 0.0008   # retest must come back within ~0.08% of the level
MIN_RISK_PCT  = 0.0004   # skip if entry→stop is tighter than this (noise)
TARGET_FB_R   = 2.0      # if no next boundary (blue sky), target = this many R
USE_VWAP_FILTER = True

# v2 levers (2026-06-24): exit by trailing, gate the failed-break on real extension,
# and only trade the active windows.
USE_TRAIL     = True     # trail under EMA8 once in profit (vs fixed next-boundary target)
TRAIL_EMA     = 8        # the EMA the runner trails
ARM_R         = 0.5      # arm the trail only after the trade is +this many R (let it breathe)
EXT_PCT       = 0.0012   # a "failed break" only counts if price first poked ≥0.12% past the level
USE_TIME_FILTER = True   # only enter in the open (first MORNING_BARS) or the power hour
MORNING_BARS  = 8        # 9:30–11:30 on 15m
POWERHOUR_BARS = 4       # last 4 bars (3:00–4:00)


@dataclass
class Trade:
    symbol: str
    date: str
    boundary: str          # which level triggered (ORH/ORL/PDH/PDL)
    trigger: str           # cont_long / cont_short / failed_long / failed_short
    direction: int         # +1 long, -1 short
    entry_idx: int
    entry: float
    stop: float
    target: float
    exit: float = field(default=np.nan)
    exit_idx: int = -1
    exit_reason: str = ""  # stop / target / eod / trail
    r: float = field(default=np.nan)

    def valid(self) -> bool:
        if self.direction > 0:
            return self.stop < self.entry < self.target
        return self.target < self.entry < self.stop


def add_vwap(day: pd.DataFrame) -> pd.DataFrame:
    """Intraday VWAP for one session (resets each day, since `day` is one date)."""
    tp = (day["High"] + day["Low"] + day["Close"]) / 3.0
    pv = (tp * day["Volume"]).cumsum()
    vol = day["Volume"].cumsum().replace(0, np.nan)
    day = day.copy()
    day["vwap"] = (pv / vol).ffill().bfill()
    return day


def _next_above(levels, v):
    above = [x for x in levels if x > v * (1 + BUF_PCT)]
    return min(above) if above else None


def _next_below(levels, v):
    below = [x for x in levels if x < v * (1 - BUF_PCT)]
    return max(below) if below else None


def _simulate(t: Trade, H, L, C, ema, n) -> None:
    """Walk bars after entry. Hard stop = the boundary. With USE_TRAIL, once the
    trade is +ARM_R in favor, exit on the first CLOSE back across EMA8 (let the
    runner run, then trail). Otherwise the fixed next-boundary target applies.
    Always flat at the close. Sets exit/reason/r."""
    risk = (t.entry - t.stop) if t.direction > 0 else (t.stop - t.entry)
    if risk <= 0:
        return
    armed = False
    arm_level = t.entry + ARM_R * risk * t.direction
    for k in range(t.entry_idx + 1, n):
        if t.direction > 0:
            if L[k] <= t.stop:
                t.exit, t.exit_idx, t.exit_reason = t.stop, k, "stop"; break
            if not USE_TRAIL and H[k] >= t.target:
                t.exit, t.exit_idx, t.exit_reason = t.target, k, "target"; break
            if USE_TRAIL:
                if H[k] >= arm_level:
                    armed = True
                if armed and C[k] < ema[k]:
                    t.exit, t.exit_idx, t.exit_reason = C[k], k, "trail"; break
        else:
            if H[k] >= t.stop:
                t.exit, t.exit_idx, t.exit_reason = t.stop, k, "stop"; break
            if not USE_TRAIL and L[k] <= t.target:
                t.exit, t.exit_idx, t.exit_reason = t.target, k, "target"; break
            if USE_TRAIL:
                if L[k] <= arm_level:
                    armed = True
                if armed and C[k] > ema[k]:
                    t.exit, t.exit_idx, t.exit_reason = C[k], k, "trail"; break
    if t.exit_reason == "":
        t.exit, t.exit_idx, t.exit_reason = C[n - 1], n - 1, "eod"
    t.r = ((t.exit - t.entry) / risk) if t.direction > 0 else ((t.entry - t.exit) / risk)


def find_trades(day: pd.DataFrame, pdh: Optional[float], pdl: Optional[float],
                symbol: str = "", date: str = "") -> list[Trade]:
    """All boundary trades for ONE session. Pure — given the day's bars + PDH/PDL."""
    if day is None or len(day) < OR_BARS + 3:
        return []
    day = add_vwap(day)
    O, H, L, C = (day[c].values.astype(float) for c in ("Open", "High", "Low", "Close"))
    Vw = day["vwap"].values.astype(float)
    ema = day["Close"].ewm(span=TRAIL_EMA, adjust=False).mean().values.astype(float)
    n = len(C)

    def in_window(j):  # only the open + the power hour; skip midday chop
        return (not USE_TIME_FILTER) or (j < MORNING_BARS) or (j >= n - POWERHOUR_BARS)

    orh = float(H[:OR_BARS].max())
    orl = float(L[:OR_BARS].min())
    bmap = {"ORH": orh, "ORL": orl, "PDH": pdh, "PDL": pdl}
    bmap = {k: v for k, v in bmap.items() if v is not None and v == v}
    levels = sorted(set(bmap.values()))
    start = OR_BARS

    out: list[Trade] = []

    def vwap_ok(j, direction):
        if not USE_VWAP_FILTER:
            return True
        return (C[j] > Vw[j]) if direction > 0 else (C[j] < Vw[j])

    for name, v in bmap.items():
        buf = v * BUF_PCT
        # ── break ABOVE the level ────────────────────────────────────────
        bi = next((i for i in range(max(start, 1), n)
                   if C[i] > v + buf and C[i - 1] <= v + buf), None)
        if bi is not None:
            brk_high = H[bi]
            for j in range(bi + 1, min(bi + 1 + LOOKFWD, n)):
                brk_high = max(brk_high, H[j])
                if C[j] < v - buf:                                   # FAILED → short
                    ext = (brk_high - v) / v                          # how far it poked first
                    if vwap_ok(j, -1) and in_window(j) and ext >= EXT_PCT:
                        tgt = _next_below(levels, v)
                        out.append(Trade(symbol, date, name, "failed_short", -1, j,
                                         float(C[j]), float(brk_high),
                                         float(tgt) if tgt else float(C[j]) - TARGET_FB_R * (brk_high - C[j])))
                    break
                if L[j] <= v * (1 + RETEST_PCT) and C[j] > v:        # RETEST HOLD → long
                    if vwap_ok(j, 1) and in_window(j):
                        stop = min(L[j], v - buf)
                        tgt = _next_above(levels, v)
                        out.append(Trade(symbol, date, name, "cont_long", 1, j,
                                         float(C[j]), float(stop),
                                         float(tgt) if tgt else float(C[j]) + TARGET_FB_R * (C[j] - stop)))
                    break
        # ── break BELOW the level (mirror) ───────────────────────────────
        bi = next((i for i in range(max(start, 1), n)
                   if C[i] < v - buf and C[i - 1] >= v - buf), None)
        if bi is not None:
            brk_low = L[bi]
            for j in range(bi + 1, min(bi + 1 + LOOKFWD, n)):
                brk_low = min(brk_low, L[j])
                if C[j] > v + buf:                                   # FAILED → long
                    ext = (v - brk_low) / v
                    if vwap_ok(j, 1) and in_window(j) and ext >= EXT_PCT:
                        tgt = _next_above(levels, v)
                        out.append(Trade(symbol, date, name, "failed_long", 1, j,
                                         float(C[j]), float(brk_low),
                                         float(tgt) if tgt else float(C[j]) + TARGET_FB_R * (C[j] - brk_low)))
                    break
                if H[j] >= v * (1 - RETEST_PCT) and C[j] < v:        # RETEST HOLD → short
                    if vwap_ok(j, -1) and in_window(j):
                        stop = max(H[j], v + buf)
                        tgt = _next_below(levels, v)
                        out.append(Trade(symbol, date, name, "cont_short", -1, j,
                                         float(C[j]), float(stop),
                                         float(tgt) if tgt else float(C[j]) - TARGET_FB_R * (stop - C[j])))
                    break

    # validity + risk floor, then simulate
    keep = []
    for t in out:
        if not t.valid():
            continue
        risk = (t.entry - t.stop) if t.direction > 0 else (t.stop - t.entry)
        if risk < t.entry * MIN_RISK_PCT:
            continue
        _simulate(t, H, L, C, ema, n)
        if t.r == t.r:  # not nan
            keep.append(t)
    return keep


# ── Backtest runner ──────────────────────────────────────────────────────────
def _fetch_15m(symbol: str, period: str = "60d"):
    import yfinance as yf
    df = yf.Ticker(symbol).history(period=period, interval="15m", auto_adjust=False, prepost=False)
    if df is None or df.empty:
        return None
    df = df.rename(columns=str.title)[["Open", "High", "Low", "Close", "Volume"]]
    return df


def backtest_symbol(symbol: str, period: str = "60d") -> list[Trade]:
    df = _fetch_15m(symbol, period)
    if df is None:
        return []
    df["d"] = df.index.date
    days = list(df.groupby("d"))
    trades: list[Trade] = []
    prev_h = prev_l = None
    for d, day in days:
        day = day.drop(columns=["d"])
        trades += find_trades(day, prev_h, prev_l, symbol, str(d))
        prev_h, prev_l = float(day["High"].max()), float(day["Low"].min())
    return trades


def report(trades: list[Trade]) -> None:
    import collections
    if not trades:
        print("  no trades")
        return
    groups = collections.defaultdict(list)
    for t in trades:
        groups[(t.symbol, t.trigger)].append(t.r)
    print(f"{'symbol':6} {'trigger':13} {'n':>3} {'win%':>6} {'avgR':>7} {'totR':>7}")
    print("  " + "-" * 46)
    for (sym, trig), rs in sorted(groups.items()):
        rs = np.array(rs)
        win = (rs > 0).mean() * 100
        print(f"{sym:6} {trig:13} {len(rs):>3} {win:>5.0f}% {rs.mean():>+7.2f} {rs.sum():>+7.1f}")
    allr = np.array([t.r for t in trades])
    print("  " + "-" * 46)
    print(f"{'ALL':6} {'':13} {len(allr):>3} {(allr>0).mean()*100:>5.0f}% {allr.mean():>+7.2f} {allr.sum():>+7.1f}")


# ── Weekly-ATM option overlay (path B: what survives real frictions) ─────────
# Translates each underlying trade into a nearest-weekly ATM call/put via
# Black-Scholes, applies the bid/ask spread (buy ask, sell bid), intraday theta,
# and commission, and reports the RETURN ON PREMIUM. The underlying R is the
# edge; this is what's left after you actually trade it through options.
import math

OPT_DTE_DAYS   = 3       # nearest weekly ≈ 3 calendar days at entry
OPT_IV         = {"SPY": 0.15, "QQQ": 0.19, "DRAM": 0.45}  # annualized; tune per regime
OPT_HALF_SPREAD = 0.025  # 2.5% each way (≈5% round-trip) — liquid weeklies
OPT_COMMISH_PCT = 0.004  # ~0.4% of premium round-trip (contract fees)
BARS_PER_DAY   = 26      # 15m regular-session bars


def _bs(S, K, T, sigma, call=True, r=0.0):
    if T <= 0 or sigma <= 0:
        return max(0.0, (S - K) if call else (K - S))
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    nd = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
    if call:
        return S * nd(d1) - K * math.exp(-r * T) * nd(d2)
    return K * math.exp(-r * T) * nd(-d2) - S * nd(-d1)


def option_overlay(trades: list[Trade]) -> list[tuple]:
    """Per trade → (symbol, trigger, option_return_pct, underlying_r). Buys ATM at
    the ask, sells at the bid, decays T by the hours held (intraday theta), nets
    commission. K = round(entry) ≈ ATM."""
    rows = []
    for t in trades:
        iv = OPT_IV.get(t.symbol, 0.20)
        call = t.direction > 0
        K = round(t.entry)
        T0 = OPT_DTE_DAYS / 365.0
        held_bars = max(1, t.exit_idx - t.entry_idx)
        held_years = held_bars * 0.25 / (365 * 24)           # 15m = 0.25h of calendar time
        T1 = max(0.5 / 365.0, T0 - held_years)
        entry_px = _bs(t.entry, K, T0, iv, call) * (1 + OPT_HALF_SPREAD)   # buy ask
        exit_px = _bs(t.exit, K, T1, iv, call) * (1 - OPT_HALF_SPREAD)     # sell bid
        if entry_px <= 0:
            continue
        ret = (exit_px - entry_px) / entry_px - OPT_COMMISH_PCT
        rows.append((t.symbol, t.trigger, ret * 100, t.r))
    return rows


def option_report(rows: list[tuple]) -> None:
    import collections
    if not rows:
        print("  no option trades"); return
    g = collections.defaultdict(list)
    for sym, trig, ret, r in rows:
        g[(sym, trig)].append(ret)
    print(f"{'symbol':6} {'trigger':13} {'n':>3} {'win%':>6} {'avg%':>8} {'tot%':>8}")
    print("  " + "-" * 50)
    for (sym, trig), rs in sorted(g.items()):
        rs = np.array(rs)
        print(f"{sym:6} {trig:13} {len(rs):>3} {(rs>0).mean()*100:>5.0f}% {rs.mean():>+7.1f}% {rs.sum():>+7.0f}%")
    allr = np.array([x[2] for x in rows])
    print("  " + "-" * 50)
    print(f"{'ALL':6} {'':13} {len(allr):>3} {(allr>0).mean()*100:>5.0f}% {allr.mean():>+7.1f}% {allr.sum():>+7.0f}%")


if __name__ == "__main__":
    import warnings; warnings.filterwarnings("ignore")
    import sys
    syms = sys.argv[1:] or ["SPY", "QQQ", "DRAM"]
    all_trades: list[Trade] = []
    for s in syms:
        ts = backtest_symbol(s)
        print(f"\n=== {s}: {len(ts)} trades ===")
        all_trades += ts
    print("\n========== UNDERLYING (R-multiples, 15m, ~60d) ==========")
    report(all_trades)
    print("\n========== WEEKLY-ATM OPTION OVERLAY (return on premium, net of spread+theta+fees) ==========")
    option_report(option_overlay(all_trades))
