# Sub-spec C — Education in the Flow: Every Alert Teaches (P1)

**Parent:** #64 Launch Value Master · **Pillar:** Teach · **Priority:** P1 (launch-critical)

## Overview
Make the landing's promise literally true: **every alert teaches.** The reasoning ships *with* the signal, the grade explains itself, the alert links to its lesson, and after it resolves the user gets an autopsy. Education stops being a separate tab and becomes the product's connective tissue — the thing that turns a busy trader into a better one over time.

## Problem (current state)
The landing leads with education ("Every signal links to a teachable pattern," "Learn from transparent outcomes," "not another inbox of buy/sell calls") and a real **30-pattern library** exists. **But the promise breaks at the moment of the alert.** A live alert delivers *setup data, not reasoning.* Missing:
- **No "why THIS fired now"** at delivery (which gates passed, what the context was).
- **No grade breakdown** — users see A/B/C but not *why* it's a B.
- **No learn-bridge** — no one-tap link from the alert to its pattern lesson.
- **No autopsy** — after target/stop, no "won because / failed because."
- **No "why not"** — skipped/suppressed setups teach nothing.
- **No beginner glossary** — terms like "VWAP slope" are undefined for newcomers.
- **No guided replay** — replays exist but aren't narrated.

## Target state
Every alert — in-app and Telegram — arrives as a **micro-lesson**: a plain-English reason, a self-explaining grade, a link to learn the pattern, and (after it resolves) an autopsy. Suppressed setups produce a teachable "why not." A beginner can understand any term in one tap.

## Scope
- **Reasoning at delivery**: each alert states *why it fired now* — the specific gates that passed and the market context (e.g. "Reclaimed the prior-day low at $174.20 on 1.8× volume, VWAP turning up; SPY healthy").
- **Grade breakdown**: expose the factors behind A/B/C (volume × slope × own-trend × confluence) inline.
- **Learn-bridge**: one tap from any alert → its pattern page (the library already has the depth: what it is, why it works, when it fails, common mistakes, pro tips, real stats).
- **Autopsy on resolution**: after the trade hits target or stop, a short "won because / failed because," compared to the pattern's historical win-rate ("this pattern wins ~X%; this was in the Y%").
- **"Why not" for skips**: when a candidate is suppressed (counter-trend, low volume, regime), say so ("near VWAP but volume only 0.6× — not a valid reclaim").
- **Beginner glossary / tooltips**: contextual definitions for every technical term, in-app and on the landing.
- **Guided replay narration**: bar-by-bar narration of how a setup formed ("dip → volume spike → confirmation").

## Acceptance criteria
- **C-1:** Every delivered alert carries a plain-English reason, a grade breakdown, and a one-tap learn link.
- **C-2:** Every resolved alert produces an autopsy referencing the pattern's historical performance.
- **C-3:** At least one class of suppressed setup produces a visible "why not."
- **C-4:** Comprehension test: ≥80% of first-session users can state, in their own words, why a sample alert fired.
- **C-5:** Every technical term in an alert has a one-tap definition.

## Out of scope
- The pattern *content* itself (lives in the library; curated in Sub-spec D).
- AI-generated coaching conversations (Sub-spec F) — though autopsies may optionally use AI.

## Notes
This is the single biggest differentiator and the cheapest to over-deliver on, because the pattern library, real-outcome backfill, and grade data **already exist** — they're just not surfaced at the moment of the alert. Closing that gap makes the landing honest and the product sticky.
