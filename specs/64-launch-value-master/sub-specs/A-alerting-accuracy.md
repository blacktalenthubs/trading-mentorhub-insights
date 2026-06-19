# Sub-spec A — Alerting Accuracy Hardening (P1)

**Parent:** #64 Launch Value Master · **Pillar:** Trust · **Priority:** P1 (launch-critical)

## Overview
Make every alert one a busy professional can act on without second-guessing. Keep only the proven entries, **fix the dual-role resistance defect**, grade by real confluence (volume, VWAP slope, the symbol's own trend), and demote the noise to confluence-only. We grade and surface — we never silently drop.

## Problem (current state)
~31 alert types, all off by default. The trust killers found in audit:
1. **Dual-role levels not enforced.** Long "reclaim" alerts fire on a level *approached from below* — i.e. into resistance. Confirmed live on **SPCX**: a long fired at the PDL as price was *rejected* there. `_held` has the `day_open > level` support guard; `_reclaim` does not.
2. **No volume confluence** on level bounces — fires on any volume; real support shows buyers stepping in (≥1.5×).
3. **VWAP slope ignored** on holds/reclaims — a panic free-fall bounce is graded the same as an accumulation bounce.
4. **No per-symbol trend confirmation** — a PDH-held can fire while the *stock itself* is below its daily EMA50; only market-level SPY regime is gated, and that gate is off.
5. **Gap context incomplete** — applied to reclaim only, not the rest of the gap-affected family.
6. **Noise still on the board:** standalone MA bounce/rejection (EMA tangle, backward-looking support test), pullback continuation (5 gates to fire), multi-period S/R on individual names.

## Target state
- Default-on set = **trusted core only.**
- No alert can fire a long into a level being approached from below.
- Every fired alert carries a **grade with a visible breakdown** (volume × slope × own-trend × confluence) — informative, not suppressive.
- Noise demoted to a **confluence flag** on level alerts, not standalone signals.

## Scope

**KEEP (default ON — the trusted core):**
- Structural level **holds + reclaims**: PDH/PDL/PWH/PWL/PMH/PML
- **4h RC + RC-H** (the cornerstone undercut-reclaim and breakout-retest)
- **Daily swing momentum**: RSI-70 ignition, 5/20 EMA cross, RSI-30–35 oversold reclaim
- **Gap-and-go** (opened above PDH, held)
- **Weekly RC** (prior-week low reclaim on a green weekly close)

**FIX — enforce dual-role on every level entry:**
- A level is **support** only when price is above it (opened above / trading above). A level **approached from below is resistance** → no long; optionally a short/"watch for break+retest" notice.
- Apply the `day_open > level` + recent-position guard to **reclaim** (not just held). Track whether a level has been *closed below this session* (breakdown) → it flips to resistance until a break-above-and-hold.

**ADD — confluence as soft grades (never silent drops):**
- **Volume**: ≥1.5× avg → upgrades grade; below → downgrades + says so.
- **VWAP slope**: floor per family (reversal holds tolerate mild negative; breaks require positive).
- **Own-symbol trend**: price vs its daily EMA50 — above = with-trend (A), below = counter-trend (downgrade + flag).
- **Confluence**: nearby level / recent 4h-1h swing extreme within ~1% annotated inline.

**RETIRE / DEMOTE:**
- Standalone **MA bounce / rejection** → confluence flag on level alerts only (your "EMA = confluence, not signal" stance).
- **Pullback continuation** → keep only if it clears all gates and maps to a level; otherwise cut.
- **Multi-period S/R** → indexes only (already), or cut on equities.

## Realistic targets — anchored to the level + EMA stack (added per feedback 2026-06-19)

Today T1/T2 are **arbitrary R-multiples** (4R/6R, 2R/3R). Price doesn't move in R — it moves **level to level.** Targets must be the **actual neighbor levels and EMAs above the entry**, all of which the chart already plots.

**The target engine:**
- **Candidate targets** = every structural level above the entry: PDH/PDL/PWH/PWL/PMH/PML **+** the daily EMAs/SMAs (8/21/50/100/200 EMA, 50/100/200 SMA) **+** recent 4h/1h swing highs.
- **Cluster** levels within ~1% of each other into a single **"wall"** (e.g. TSLA PDH 405.94 + EMA50 406.06 + EMA100 405.17 = one strong target). A wall is a stronger, stickier target than a lone level.
- **Skip** any level closer than ~0.3% to the entry (noise, not a target).
- **T1 = nearest meaningful overhead level/wall · T2 = the next · T3 = stretch** (the major level — PDH/PWH/SMA200).
- **Stop = below the entry structure**: the RC undercut low, the reclaimed level, or the nearest support below — never a fixed R.
- **Dual-role aware (ties to the fix above):** when price is *below* a level, that level is overhead **resistance → it is T1.** When it reclaims and holds, the level flips to **support** and the next level up becomes the new T1.

**The cascade (the "tricky" part):** targets are not static. As each level clears and flips to support, the next level becomes the key resistance/target — and a **next-leg buy** can fire ("PDL reclaimed & holding → next target EMA200"). The triage agent / lifecycle watcher updates the active target as levels are taken, so the user always sees "next key level," not a stale far number.

**Worked examples (for the build):**
- *TSLA below PDL 393.76, RC reclaim ~390:* T1 = PDL 393.76; on hold → T2 = EMA200 396.85 → T3 = SMA100/SMA50 400–401.
- *TSLA long off SMA100 ~400:* stop < EMA200 396.85; T1 = EMA8 403.41; T2 = the 405–406 wall; T3 = EMA21 408.44.
- *SPCX RC 4h @ 175.94:* ladder T1 = weekly high 176.52 → T2 = PDL 187.06 → T3 = PDH 213.73 (not a single skip-to-213.80).

**Grade interaction:** more clean overhead room to the first wall = better reward; a target wall right above the entry caps the trade and should downgrade it (no room to run).

## Acceptance criteria
- **A-1:** 2-week audit shows **zero** long-into-resistance fires.
- **A-6:** Every alert's T1/T2/T3 are **real chart levels/EMAs** above the entry (clustered, >0.3% away), not R-multiples; the stop is a structural level, not a fixed R.
- **A-7:** When price is below a level and reclaims it, the alert's first target is that level; after it holds, targets advance to the next level up (the cascade is visible to the user).
- **A-2:** Every fired alert exposes its grade breakdown (the factors that set the grade).
- **A-3:** Fresh-account default-on set = exactly the trusted core; nothing else fires until the user opts in.
- **A-4:** A level that has closed below this session does not fire a long reclaim until it is reclaimed-and-held.
- **A-5:** No alert is silently suppressed for low quality — it is graded down with a reason and still shown.

## Out of scope
- New pattern *types* (this hardens what exists). New patterns go through Sub-spec D.
- The discovery/ranking board (Sub-spec B).

## Notes
Aligns with the validated philosophy: levels primary, support-in-uptrend, dual-role, grade-don't-drop, EMA-as-confluence. The dual-role fix is the single highest-trust change before launch.
