# Feature Specification: Entry-Setup Classification + Two-Lens Auto-Focus

**Status**: Draft (design — for review)
**Created**: 2026-06-28
**Author**: Victor B (blacktalenthubs)
**Builds on**: spec 55 (Best-Setup Focus List), spec 56 (Swing criteria), the daily
auto-focus agent (`analytics/auto_focus.py`), and the premarket gap board
(`analytics/premarket_gaps.py`).

## Overview

The daily auto-focus agent today stars each user's Top 5 watchlist names by the
single 0–100 daily-plan score. This spec splits that into **two complementary lenses**
on the *same* watchlist and introduces a **shared entry classifier** so every pick
carries a consistent, queryable tag: *what kind of trade is this, where is price
relative to the entry, and how strong is the alignment.*

- **Lens A — "Structure"** (no premarket): where price sits in its daily/weekly
  structure right now → mostly **swing** and **long-term-hold** setups.
- **Lens B — "Premarket"**: what moved overnight and whether it is moving *into* a
  setup → mostly **day-trade / momentum** setups.

Each lens emits a **Top 5**. The deliverable answers one trader question per lens:
*"Of my watchlist, which 5 are worth my attention today, and why?"*

## Problem Statement

"Best setup" is not one thing. A name pulling back to a rising 50-EMA in a Stage-2
uptrend (swing), a name basing above its 200-DMA with accelerating revenue (long-term),
and a name gapping +4% on volume and reclaiming yesterday's high (day-trade) are all
"worth attention" — but for different reasons, on different horizons, with different
risk. Collapsing them into one score loses the *why*. And the single score ignores
premarket movement entirely, so the watchlist's biggest overnight movers never surface
until the user opens a chart. We need a classification that names the horizon, the
trigger state, and the conviction — and two run cadences (pre-open structure scan +
premarket movers scan) that feed it.

## Classification model — three independent axes

An entry candidate is `(Horizon) × (Trigger state) × (Conviction)`. These are
orthogonal: a setup can be swing + approaching + HIGH, or day-trade + at-entry + MED.

### Axis 1 — Horizon (which structure are we reading?)

| Horizon | Holding | Structure read | Existing code |
|---|---|---|---|
| **day_trade** | hours | VWAP, ORH/ORL, PDH/PDL, gap-and-go, session levels | `intraday_rules.py` AlertTypes; `premarket_gaps.py` |
| **swing** | days–weeks | Daily MA stack (EMA 8/21/50/200, SMA 50/200), pullback hold/reclaim, RSI(14) recovery, golden-cross retest, 52w-high retest | `analytics/swing_quality.py` (`SwingQualification`, `SwingRuleHit`) |
| **long_term** | months+ | Stage-2 uptrend, RS vs SPY, fundamentals (rev/EPS growth, margins), analyst backing | `growth_screener.py` / `conviction_screener.py` / `emerging_screener.py` |

**Horizon decision (per symbol, first match wins for the lens):**
- Lens B (premarket) → default `day_trade`; promote to `swing` when the gap is *into*
  a daily swing level (e.g. gapping up to reclaim the 50-DMA → swing reclaim).
- Lens A (structure) →
  1. `long_term` if a growth/conviction/emerging candidate qualifies (Stage-2 + RS +
     fundamentals/analyst gates already defined in those screeners), else
  2. `swing` if `swing_quality` returns a qualification, else
  3. `day_trade` if only intraday/level structure applies (rare in a pre-open scan).

### Axis 2 — Trigger state (where is price *relative* to the entry?)

This is the "worth paying attention" axis. Reuse existing proximity/score gates:

| State | Meaning | Source signal |
|---|---|---|
| **at_entry** | Triggered + confirmed; actionable now | `support_status == "AT SUPPORT"` & score ≥ 65 (`_POTENTIAL_ENTRY_MIN_SCORE`); confirmed MA bounce; gap-and-go |
| **approaching** | Near but not triggered; watch | `PULLBACK WATCH`; within the rule's proximity % (e.g. `MA_BOUNCE_PROXIMITY_PCT = 3.0`, `VWAP_BOUNCE_MAX_DISTANCE_PCT = 1.0`) |
| **extended** | Already ran past the level; skip | staleness > `BREAKOUT_STALENESS_PCT = 3.0` |

A pick **qualifies for a Top 5 only if** `trigger_state ∈ {at_entry, approaching}`.

### Axis 3 — Conviction (how many independent factors align?)

Reuse the established rule: **HIGH = 2+** aligned signals (confluence), **MED = 1**,
**LOW** otherwise (`swing_scanner.py` already computes "2+ rules → HIGH"). Confluence
list = the named levels/rules that aligned (e.g. `["50-EMA", "prior-day-low", "RS>SPY"]`).

### The qualification rule (plain language)

> A symbol is **worth attention** when it sits in a valid structure **for its horizon**
> (uptrend MA stack for swing; Stage-2 + RS for long-term), **AND** trigger_state is
> `at_entry` or `approaching` (not `extended`), **AND** conviction ≥ MEDIUM.

Rank the qualifiers (score, then conviction, then proximity) and take the Top 5.

## Output schema (reuse spec 55's recommendation shape)

Each pick is emitted as the existing `FocusList` recommendation dict
(`focus_list_service.py`) so dashboards, Telegram, and the watchlist drawer all share
one shape:

```python
{
  "symbol": "NVDA",
  "lens": "structure" | "premarket",          # NEW — which agent produced it
  "trade_horizon": "day_trade" | "swing" | "long_term",
  "setup_type": "50-EMA bounce",              # the trigger that fired
  "trigger_state": "at_entry" | "approaching", # NEW — Axis 2
  "conviction": "HIGH" | "MEDIUM" | "LOW",
  "direction": "LONG",
  "entry": 120.5, "stop": 119.0, "t1": 124.0, "t2": 128.0,
  "current_price": 119.8, "distance_to_entry_pct": -0.58,
  "confluence": ["50-EMA", "prior-day-low", "RS>SPY"],
  "why_now": "Pulled back to a rising 50-EMA in a Stage-2 uptrend; RSI recovered from 38.",
  "score": 86,
}
```

(`lens` and `trigger_state` are the only additions to the spec-55 schema.)

## Architecture

```
                       ┌──────────────────────────┐
   daily/EOD bars ───► │  Lens A: structure_scan   │ ─┐
   (no premarket)      │  signal_engine + swing_   │  │
                       │  quality + LT screeners   │  │
                       └──────────────────────────┘  │
                                                      ├─► entry_classifier ─► Top 5 (per lens, per user)
                       ┌──────────────────────────┐  │      (3-axis tagging,        │
   premarket bars ───► │  Lens B: premarket_scan   │ ─┘       qualification gate)    ▼
   + prior levels      │  premarket_gaps + level   │              auto_focus: star + (optional) Telegram digest
                       │  reclaim classification   │
                       └──────────────────────────┘
```

- **`analytics/entry_classifier.py`** (new, pure/deterministic): given a symbol's
  computed signals from a lens, returns the tagged candidate (or None if it doesn't
  qualify). No I/O, unit-testable — same discipline as `swing_quality.py`.
- **Lens A** = today's `auto_focus` current-setup path, enriched: rank by score, then
  classify each pick (horizon + trigger_state + conviction).
- **Lens B** = new premarket path built on `premarket_gaps.py` (`PremarketGapSnapshot`,
  `passes_gap_filters`: gap ≥ 2%, $vol ≥ 100k, price ≥ $2), adding "is the gap moving
  *into* a known level (PDH/PDL/PWH/PWL/MA)?" to assign trigger_state + horizon.

### Run cadence (API lifespan scheduler — non-protected `api/app/main.py`)

| Job | Time (ET, Mon–Fri) | Lens | Notes |
|---|---|---|---|
| `auto_focus_structure` | ~9:00 (pre-open) | A | After EOD/overnight; uses prior close structure. (Today's job at 9:45 folds into this.) |
| `auto_focus_premarket` | ~9:15 | B | Premarket window, before the open. Needs premarket bars. |

Both reuse the existing focus-star write (`db.set_auto_focus` / `clear_auto_focus`,
`focus_source='auto'`) and the optional digest (`auto_focus._notify_user`, gated by
`AUTO_FOCUS_NOTIFY`). No protected business-logic file is modified.

## Open product decisions (need sign-off)

1. **Lens A slicing** — one Top 5 mixing swing + long-term (tagged), OR two separate
   Top 5s (5 swing + 5 long-term)? *Recommendation: ship one tagged list first, split
   later if the mix feels noisy.*
2. **Premarket digest timing/loudness** — separate "⭐ Premarket Movers" message at
   ~9:15, or fold into one combined morning digest? Premarket is noisier — consider
   `conviction ≥ HIGH` or a tighter gap+volume gate before it pushes to phones.
3. **Long-term gating cost** — the growth/conviction screeners pull fundamentals/analyst
   data (heavier, rate-limited). Cache daily, or restrict long_term classification to a
   nightly batch rather than the 9:00 run?
4. **focus_source granularity** — keep one `'auto'` source, or split into
   `'auto_structure'` / `'auto_premarket'` so the UI can badge them differently?

## Phased build plan

- **P1 — `entry_classifier.py` + enrich Lens A.** Shared 3-axis classifier; current-setup
  agent emits tagged picks. Unit tests for the qualification gate + each horizon path.
  *(No new screeners wired yet — swing via `swing_quality`, long_term stubbed/optional.)*
- **P2 — Long-term wiring.** Connect growth/conviction/emerging screeners as the
  `long_term` horizon source (with daily caching for fundamentals).
- **P3 — Lens B premarket agent.** Build `premarket_scan` on `premarket_gaps`, add the
  9:15 cron + (optional) premarket digest.
- **P4 — UI.** Horizon/conviction/trigger badges in the watchlist drawer + a "why now"
  on tap; optional split lists.

## Out of scope

- No new entry *rules* — this composes the rules/screeners that already exist.
- No change to alert routing or the live monitor (`monitor.py`/`worker.py` untouched).
- No automated order placement — these are attention signals, not buy instructions.
