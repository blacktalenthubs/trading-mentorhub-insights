# Swing Patterns — Character Change + Buying in Bases

**Status:** Validated, ready to build · **Created:** 2026-07-06 · **Owner:** admin (vbolofinde)
**Source:** Nick Schmidt's concepts (nickschmidt.so/concepts), rules validated independently in Python.

## Overview
Two weekly-chart swing setups, both **backtested and confirmed +EV out-of-sample** before any build.
They run as **EOD weekly scanners on the MASTER universe** (the 82-name discovery list) and emit
two new **swing** alert types. They are *not* day-trade signals — they surface longer-term entries
for the admin/agents to evaluate. Default OFF; proven live on the Performance page like everything else.

## Validated edge (Python, R-based, in/out-of-sample)
Method: encode rules → scan ~90 cross-sector names over 9y weekly bars → score each trigger by
R-multiple (entry, stop below the MA/higher-low, +2R target, 26-week window), split in-sample vs
out-of-sample.

| Setup | Expectancy | +2R rate | Sample | In → Out of sample | Cadence |
|---|---|---|---|---|---|
| **Character Change** | **+0.48R** | 37% | 30 (rare) | +0.35 → +0.54R ✓ holds | few/year — home run |
| **Buying in Bases** (tightened) | **+0.22R** | 38% | 489 | +0.17 → +0.19R ✓ rock-solid | ~0.6/name/yr — workhorse |

Both beat the current live reclaim edge (~+0.12R). The edge is the **tight stop** (below the MA /
higher low) → small losers, running winners — the same DNA as the platform's existing stop rule.

## Setup 1 — Character Change (rare, high-conviction reversal)
Fires when, after a downtrend/base, ALL three align on the **weekly** chart:
1. **Volume surge** — the week's volume ≥ ~1.7× its 20-week average (institutional footprint).
2. **First 10-week reclaim** — close crosses back above the 10w MA (prior week was below).
3. **Higher swing low** — the recent 4-week low is above the prior 8-week low (sellers exhausting).
- Context filter: price was below the 30w MA within the last ~10 weeks (i.e. it *was* in a downtrend).
- **Entry:** the reclaim week's close · **Stop:** just below the 30w MA (or the trigger-week low).
- **Target/manage:** runner — trail; the tested edge assumes a +2R objective.

## Setup 2 — Buying in Bases (frequent, bread-and-butter)
Fires when a **proven uptrend** is digesting and the right side of the base starts to lift:
1. **Proven uptrend** — price above the 30w MA and ≥ +25% off its base ~15–40 weeks ago.
2. **Sideways base** — roughly flat over the last ~10 weeks (|Δ| < 12%).
3. **Tightening** — the recent 6-week range is < 85% of the prior 8-week range (contraction).
4. **Higher lows** — recent 3-week low above the prior 5-week low.
5. **Volume drying** — recent 6-week avg volume < prior 8-week avg.
- Filters: liquidity ≥ $50M/day; **dedup to one signal per base** (≥6 weeks since the last).
- **Entry:** on weakness near the higher low / base pivot · **Stop:** ~1.5% below the higher low.

## Build plan
1. **Python EOD weekly detectors** — `analytics/character_change_scan.py` + `analytics/base_buy_scan.py`
   (same shape as the WkStage/WkPos weekly system). Run nightly on the triage worker over the master.
2. **Two new alert types** — `character_change`, `base_buy` — style = **Swing**, **default OFF** in
   `alert_type_config`, so they eval before anyone opts in.
3. **Emit** — the triage scanner writes them like the other swing alerts (entry/stop/target), scored
   nightly by the Performance pipeline (already crypto-split + entry-timestamped).
4. **Frontend** — surface under the Swing style panel + Today's Focus swing section; click → chart.

## Success criteria
- **SC1** Detectors reproduce the backtest triggers on historical data (sanity check vs the Python).
- **SC2** Live alerts fire at the validated cadence (CC: a few/mo across 82; BB: a handful/wk).
- **SC3** After ~1 month live, the Performance page shows expectancy in the ballpark of the backtest
  (CC ~+0.4R, BB ~+0.2R). If live diverges hard from the backtest, we pause, not expand.

## Risks / caveats
- **Character Change is rare** (30 triggers/9y) — high per-trade edge but low statistical confidence;
  treat as a watch-closely signal, size accordingly.
- **9 years is one bull-heavy regime** — the live eval is the real out-of-sample test.
- Weekly cadence means slow feedback; that's the point (fewer, better decisions), not a bug.

## Out of scope
- No Pine (these are Python EOD scanners, not intraday). No changes to the day-trade book or the
  master universe. The Feedback Loop concept (participation gating) is deferred — it's a discipline
  rule, not a pattern.
