# Planned Level Touch Alert — Wire Scanner Trade Plans into Intraday Alerts

## Problem

The Scanner generates pre-market trade plans with optimal entry levels (e.g., SPY entry at $681.65 on 2026-02-27), but the intraday alert engine doesn't know about these levels. When price reaches the planned entry, no alert fires.

Today's example: Scanner identified SPY $681.65 as the entry (first test of support, 4:1 R:R). SPY dropped to exactly $681, bounced perfectly, recovered to $690+. The alert engine only fired a PDL reclaim at $684.35 — a materially worse entry than the planned $681.65.

## Root Cause

The Scanner and Alert engine are two independent systems:
- **Scanner** (`signal_engine.py` / page 1): Runs pre-market, identifies support levels, generates trade plans with entry/stop/target
- **Alerts** (`intraday_rules.py` / monitor): Runs real-time, fires rules (MA bounce, PDL reclaim, session low double-bottom, etc.) based on its own level detection

Neither system consumes the other's output.

## Proposed Solution

New intraday rule: `check_planned_level_touch()` — reads the active trade plans and fires a BUY alert when price reaches a planned entry level.

**Logic:**
1. On each poll cycle, load active trade plans for the symbol (from Scanner output / DB)
2. If last bar low is within proximity of planned entry AND close > planned entry (bounce confirmed)
3. Fire BUY alert with the trade plan's entry/stop/target/R:R already computed
4. Confidence = "high" (pre-validated by Scanner analysis)

**Key decisions needed:**
- Where to store/read active trade plans (DB table? session state? file?)
- Proximity threshold for "reached planned level" (0.2-0.3%?)
- Should it fire on first touch or require bounce confirmation?
- How to handle stale plans (plans from 3 days ago still active?)

## Impact

This bridges the gap between pre-market analysis and real-time execution. The Scanner already does the hard work of identifying levels — the alerts just need to watch them.

## Observed on

2026-02-27 — SPY $681.65 entry, META similar pattern at $650 level.
