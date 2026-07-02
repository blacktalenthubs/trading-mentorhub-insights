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

## What makes a name "worth focusing tomorrow" — criteria + weighting

This is the heart of the agent. It deliberately **ignores the mechanical entry rules**
(MA-bounce / VWAP / PDH triggers). Those answer *"what fired today?"* — backward-looking.
A nightly focus agent answers a different question: **"which 5 are most loaded to give a
clean, definable-risk move tomorrow?"** — anticipation, not triggering.

### The book it scans (drives the weighting)

The watchlist (`sectors/all_sectors_grouped.txt` + user's 80) is a **high-beta momentum /
growth book**: mega-tech anchors (NVDA/AAPL/AMZN/GOOGL/META), a deep chips/AI-infra bench
(AVGO/AMD/MRVL/ARM/ALAB/CRDO/ANET/CIEN + small movers AAOI/AEHR/AOSL/ACLS/APLD), memory,
optics, crypto proxies (BTC/MSTR/IREN), a nuclear/AI-power theme (CEG/LEU/CCJ/GEV),
fintech/space/spec, and macro refs (SPY/QQQ). Two facts drive the design: these names
**trend hard then coil**, and they are **heavily theme-correlated** (AVGO/AMD/MRVL/ALAB ≈
one bet on a given day).

### The seven criteria (all from daily bars + an earnings date)

| # | Criterion | What's measured | Weight (this book) |
|---|---|---|---|
| 1 | **Relative strength / leadership** | RS vs SPY **and** vs its sector group; above rising 20/50-DMA; sector green | **Primary** |
| 2 | **Location at a decision point** | Distance to nearest meaningful level — support in uptrend, base top, prior high | **Primary** |
| 3 | **Compression / coiled energy** | ATR contraction, range tightening, inside days, narrowing N-day range | **High** |
| 4 | **Risk geometry** | Clean invalidation *just below* → tight stop, asymmetric R:R to next target | Quality gate / tiebreaker |
| 5 | **Volume signature** | Up-vs-down-day volume (accumulation), dry-up on pullback, recent thrust | Medium |
| 6 | **Momentum posture** | Distance from MAs, RSI — primed but **not extended** | Guard rail (penalize extension) |
| 7 | **Event awareness** | Earnings within ~1–2 days; BTC posture for the crypto cluster | **Flag, not scored** |

### Weighting decision (2026-06-28) — my call, per the user's delegation

For a high-beta, theme-rotating momentum book, **leadership (1) and location (2) are the
two primary drivers**: in momentum names RS *is* the edge (themes rotate semis → nuclear →
crypto → space; you want the leader of whatever's working), and location decides whether
tomorrow is actually *actionable*. **Compression (3)** is the third driver — it's the tell
that a big move is loading in names that trend-then-coil. **Risk geometry (4)** is a
quality gate/tiebreaker (makes it tradeable, defines the stop). **Volume (5)** and
**posture (6)** are confirmation and a guard-rail against chasing. **Earnings (7)** is
flagged, never silently excluded.

Indicative readiness score (pre-LLM shortlist): `RS 30 · Location 25 · Compression 20 ·
RiskGeometry 12 · Volume 8 · Posture 5` (−penalty if extended), max 100.

### De-correlation is a hard structural rule

On a theme-correlated book, five names from one theme is really *one* bet. The Top 5 must
spread across themes — **cap ~2 per sector group**, prefer the leader of each. This matters
as much as the per-name score.

### Decision engine — features + LLM judgment (chosen)

The user framed it as *"what the agent **thinks**."* So: compute criteria 1–6 as objective
features (pure math, daily bars), use the readiness score to **shortlist the top ~15**,
then hand that feature table to the agent (Sonnet via the existing `analytics/ai_best_setups.py`)
to **weigh, rank, de-correlate, and write the "why now."** Deterministic features keep it
explainable and stop the LLM hallucinating prices; the LLM supplies the theme-rotation and
de-correlation judgment a rigid formula can't. This is the engine for both lenses.

## Classification model — three independent axes (output tags)

The criteria above decide *what gets picked*; these axes are how each pick is *labeled* in
the output. An entry candidate is `(Horizon) × (Trigger state) × (Conviction)`. These are
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
