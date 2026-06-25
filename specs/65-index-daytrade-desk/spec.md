# Feature Specification: Core-Index Day-Trade Desk (SPY · QQQ · DRAM)

**Status**: Draft → MVP/backtest
**Created**: 2026-06-24
**Author**: Victor B (blacktalenthubs)

## Overview
One repeatable daily system for **3 core index names only** — SPY, QQQ, DRAM — that
fires **long and short** day-trade signals off **structural boundaries**, never off
VWAP touches. It's built for a **non-trending market**, when single-stock day trades
dry up and the edge is in the index. Each signal is a complete plan: underlying
entry · stop · target, plus the **weekly ATM option** to take it with. Default is
**no trade** — it only speaks at a boundary, on a held break or a failed break.

## Problem
VWAP-as-a-trigger chops: price oscillates around VWAP, so "VWAP hold" fires endlessly
in balance and every fire is a coin flip. Single-stock day-trading also thins out in a
weak tape. The trader needs a **tight, both-sided index system** that ignores the
middle and only acts at the day's real boundaries — and a way to **prove it pays**
before trading size.

## The setup (the whole system)
**Map (per symbol, pre-open):** 30-min **ORH/ORL**, **PDH/PDL**, any live multi-day
range, **VWAP** (a *filter*, not a trigger).

**The only two triggers — at a boundary, both directions:**
- **Continuation** — boundary breaks → price **retests and holds** it → enter with the
  break. Long above a reclaimed boundary, short below.
- **Reversal (the A-trade)** — boundary breaks → **retest fails** → price reclaims back
  through → fade to the *other* boundary.

**Filters that keep it silent:** entry must be **at a boundary** · **VWAP on the right
side** (long > VWAP, short < VWAP) · the break must **expand** out of balance (no flat-
VWAP-mid-range fires) · **once per boundary per direction per day.**

**Management:** stop = the **underlying boundary** (never a premium %); target = the
**next boundary**; trail the runner under VWAP/8-EMA; **flat by the close.**

**Option translation:** long → **nearest-weekly ATM (~0.50δ) call**; short → weekly ATM
put. Entry when the underlying triggers; stop/target driven by the underlying levels.

## Backtest (this milestone)
Prove the **underlying setup's edge in R-multiples** first (the option just leverages
it). Over available intraday history (15-min bars), for each symbol × trigger type:
- entries from the rules above; risk = entry→stop = **1R**; outcome = R captured
  (stop = −1R, target = +(target−entry)/risk, else exit at the close).
- Report **count · win% · avg R · expectancy** per (symbol, trigger, direction).

## Acceptance criteria
- **A-1:** A pure, testable engine takes a day's intraday bars + PDH/PDL and returns the
  trades (continuation + failed-break, long + short) with entry/stop/target/exit/R.
- **A-2:** It fires **only at a boundary**, with the VWAP-side and expansion filters —
  no mid-range/VWAP-hold signals. Once per boundary/direction/day.
- **A-3:** A backtest runner fetches 15-min history for SPY/QQQ/DRAM, runs the engine
  per day, and prints per-(symbol, trigger, direction) **count · win% · avg R ·
  expectancy.**
- **A-4:** Results are reproducible from one command; parameters (OR window, retest
  band, look-forward, buffer) are top-of-file constants for tuning.

## Out of scope (this milestone)
- Full option Greeks / theta-decay modelling — backtest the underlying R first; the
  weekly-ATM overlay is a later layer.
- Live alert wiring + the desk UI — prove the edge first, then wire.
- More than the 3 symbols (add 1–2 later once mastered).

## Notes
This is the distilled day-book from the 2026-06-24 design session: boundaries +
retest-hold/failed-break, VWAP demoted to a filter, both directions, weekly-ATM
options, flat by close. No SPY-regime gate — it's intraday ([[feedback_spy_pdl_hard_block]]
is a *swing* filter, not a day-trade one).
