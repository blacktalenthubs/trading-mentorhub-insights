# Sub-spec I — EOD Trade Self-Reporting & Pattern Validation (P1)

**Parent:** #64 Launch Value Master · **Pillar:** Ground truth + discipline · **Priority:** P1 (it's how every other "keep what works" decision gets made)

## Overview
A frictionless **end-of-day review** where the user reports which alerts they actually took — *did you take it? entry? exit?* (the alert type is already known). This produces the **self-reported outcome dataset we completely lack today**, which tells us — and the user — **which patterns actually work**. It is simultaneously the backtesting seed, the pattern-pruning evidence, and a discipline loop that pushes the user toward the setups that pay.

## Problem (current state)
We have ~31 alert types and **almost no truth about whether they profit.** Does **RC 4h** work? **Weekly RC**? **Daily RC**? **Level holds**? We don't know — `mfe_r / mae_r / real_outcome` are largely null, and the Performance tab collects some exit prices but there's **no structured EOD prompt** that captures "took / entry / exit" per alert. Without this:
- We can't honor the master principle **"keep only the patterns that work"** — we're guessing.
- We can't backtest or tune — there's no labeled outcome data.
- The user has no mirror showing **which of their patterns actually pay**, so discipline doesn't compound.

## Target state
A daily, two-minute EOD review that captures **took / entry / exit** per engaged alert in ≤2 taps, aggregates into **real win-rate + average outcome per pattern** (per user and platform-wide), surfaces it back to the user ("RC 4h is your best setup — 7/9"), and feeds the pattern-pruning + discovery + triage layers. Self-reported, real — never synthetic.

## Scope

**The EOD review:**
- At market close (or first app-open after close), present the day's alerts the user could have taken → for each: **"Took it?" (Yes / No).**
- If **Yes** → capture **entry** (pre-filled from the alert; one-tap "took at alert entry") and **exit** (price or "still holding"). **Alert type is already known** — no typing.
- If **No** → optional one-tap reason (missed / didn't trust it / no time) — also teaches us.

**Frictionless capture:**
- Pre-fill entry from the alert; defaults make the common case ("took at entry, exited at X") a couple of taps.
- Works from the EOD report and from any past alert card.

**Per-pattern aggregation:**
- Real **win-rate + average R / avg %** per alert type (RC 4h, weekly RC, daily RC, level holds, gap-and-go, swing momentum…), **per user** and **platform-wide**.
- Sliced by symbol, time-of-day, market regime where useful.

**Discipline loop:**
- Show the user their own mirror: "You took 3 of 5 RC 4h signals — 2 won. You skipped the 2 best." / "Your edge is RC-H; your worst is MA bounce."
- Reinforces sticking to the patterns that work and cutting the ones that don't.

**Pattern validation → pruning (closes the loop with Sub-spec A):**
- Platform-wide pattern win-rates become the **evidence** for "keep only what works" — low-win patterns get demoted/cut; high-win patterns get promoted/default-on.
- Becomes the **backtesting ground truth** seed.

## Acceptance criteria
- **I-1:** A daily EOD review prompts the user on the day's engaged alerts.
- **I-2:** Capturing took / entry / exit for an alert takes ≤2 taps (alert type pre-known, entry pre-filled).
- **I-3:** Per-pattern real win-rate + average outcome is computed and shown (per user + platform).
- **I-4:** The dataset is queryable to answer "does pattern X work?" for any alert type.
- **I-5:** Every number is real self-reported outcome — no synthetic win-rates.

## Out of scope
- Broker auto-import of fills (manual self-report first; auto-import is a later enhancement).
- The full backtesting engine (this provides its ground-truth data; the engine is separate).

## Notes
Extends the existing real-trade exit collection in the Performance tab into a proper EOD workflow. Pairs naturally with the **triage agent (H)** — it can run the EOD review conversationally and write the autopsy (Sub-spec C) — and it's the data that makes the master's central promise ("keep only the best, profitable strategies") true rather than asserted. Ties to [[project_outcomes_not_computed]].
