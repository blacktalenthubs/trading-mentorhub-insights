# Sub-spec D — Canonical Pattern Playbook (P2)

**Parent:** #64 Launch Value Master · **Pillar:** Backbone · **Priority:** P2

## Overview
The single source of truth for **the patterns we actually trade** — the kept-only-the-best set, organized by intent (day / swing / trend), each mapped to its alert, its lesson, its grade rubric, and its stop logic. Sub-specs A (what fires) and C (how we teach it) both reference this playbook. Library patterns not in the playbook are retired.

## Problem (current state)
There are 30 patterns in the content library, ~31 alert types, and overlapping "ideas" tabs — but **no canonical statement of "these are the patterns this platform stands behind."** Some library patterns are noise (the things Sub-spec A retires); some traded setups (RC-H, weekly RC) aren't cleanly represented as teachable patterns; day vs swing vs trend isn't an organizing axis the user can navigate.

## Target state
A curated, navigable playbook with three shelves — **Day, Swing, Trend** — each pattern carrying: what it is, when it works, when it fails, the grade rubric, the stop logic, and a link to live + historical examples. One-to-one with the default-on alerts. No orphans (every default alert maps to a pattern; every playbook pattern can fire or be a confluence flag).

## Scope

**Day-trade shelf (intraday, defined-risk):**
- Level **reclaim** / **hold** (PDH/PDL and weekly/monthly equivalents) — buy support defended from above.
- **4h RC** (undercut & reclaim of the prior 4h low) and **RC-H** (breakout-retest of a reclaimed high) — the cornerstone.
- **Gap-and-go** (opened above PDH, held) and **ORL held** (opening-range low).

**Swing shelf (multi-day):**
- **RSI-70 ignition** (parabolic kickoff), **5/20 EMA cross** (Burns), **RSI-30–35 oversold reclaim** (mega-cap washout recovery).
- **Weekly RC** (prior-week low reclaim, green weekly close).
- **Conviction** (analyst + 50-MA persistence mid-caps).

**Trend shelf (structure / regime):**
- **Higher-low / lower-high structure** (the swing-structure read: who's basing vs rolling over).
- **Stage analysis** (Weinstein 30-week: Stage 2 advancing = ownable).
- **Dual-role levels** (a broken high becomes support; a lost low becomes resistance) as the governing principle across shelves.

**For each pattern:** what it is · how to identify · why it works · when it fails · common mistakes · the **grade rubric** (volume/slope/trend/confluence thresholds) · the **stop logic** · difficulty · live + historical examples.

**Retire:** library patterns that map to no kept alert and teach nothing actionable (the noise set from Sub-spec A).

## Acceptance criteria
- **D-1:** Every default-on alert maps to exactly one playbook pattern.
- **D-2:** Every playbook pattern states its grade rubric and stop logic.
- **D-3:** The playbook is navigable by Day / Swing / Trend intent.
- **D-4:** No orphan patterns (in the library but trade-able by nothing) and no orphan alerts (fires but no lesson).

## Out of scope
- The gating/firing logic itself (Sub-spec A) and the in-flow teaching surfaces (Sub-spec C) — this defines the *content* they reference.

## Notes
This is the connective document: it makes A (what fires) and C (how we teach) consistent, and gives the landing (G) a concrete "here's exactly what we trade and why" to point at.
