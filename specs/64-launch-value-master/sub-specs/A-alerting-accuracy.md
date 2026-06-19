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
- **One target only** = the **nearest meaningful overhead level/wall** — the first real resistance the trade can reach. **No T1/T2/T3.** One target keeps accuracy unambiguous: *did price reach the level before the stop — yes or no?* That single binary is what makes win-rate measurable.
- **Stop = below the entry structure**: the RC undercut low, the reclaimed level, or the nearest support below — never a fixed R.
- **Dual-role aware (ties to the fix above):** when price is *below* a level, that level is overhead **resistance → it is the target.** When it reclaims and holds, the level flips to **support** and the next level up becomes the new target.

**The cascade (single-target legs):** the level ladder is NOT priced into one alert — it plays out as a **series of discrete single-target trades.** When a target level is taken and holds, a **new alert** fires with the next level as its one target ("PDL reclaimed & holding → target EMA200"). The triage agent / lifecycle watcher drives the legs, so every alert is one clean, measurable bet — and accuracy is the simple hit-rate of "reached the target before the stop."

**Worked examples (for the build):**
- *TSLA below PDL 393.76, RC reclaim ~390:* target = PDL 393.76. On hold → new alert, target = EMA200 396.85. Then the SMA100/SMA50 shelf.
- *TSLA long off SMA100 ~400:* stop < EMA200 396.85; target = EMA8 403.41. If taken → next alert, target = the 405–406 wall.
- *SPCX RC 4h @ 175.94:* target = weekly high 176.52 (not a skip to 213.80); each reclaim advances the next leg → PDL 187.06 → PDH 213.73.

**Swing targets — separate methodology (to detail in a follow-up):** swing entries don't aim at a price level, they aim at **momentum exhaustion = RSI 70.** Buy oversold (RSI 30–40 reclaim) → target **RSI 70**. Buy a 20/50-EMA pullback hold → target **RSI 70**. This is the institutional "buy weakness / pullback, sell into strength" model — a dynamic momentum target, not a fixed price. Day-trade level-targets ship first; swing RSI-targets come in their own pass.

**Grade interaction:** more clean overhead room to the first wall = better reward; a target wall right above the entry caps the trade and should downgrade it (no room to run).

## Acceptance criteria
- **A-1:** 2-week audit shows **zero** long-into-resistance fires.
- **A-6:** Every day-trade alert has **exactly one** target = a real chart level/EMA above the entry (clustered, >0.3% away), not an R-multiple; the stop is a structural level, not a fixed R.
- **A-7:** The ladder plays out as single-target legs — when a target level is taken and holds, a new alert fires with the next level as its one target. Accuracy is measured as the hit-rate of "reached target before stop."
- **A-8 (swing, later):** swing-entry alerts (oversold reclaim, 20/50-EMA hold) target **RSI 70**, not a price level — specced in a follow-up.
- **A-9 (visibility):** the single target is drawn on the chart as a **labeled line** ("T · PDH 405.94") alongside entry + stop, so target realism is visible at a glance. *(The chart component already draws E / S / T lines — it just needs the alert's `entry/stop/target` wired into the Trading-page chart, which is currently not passed. Small, frontend-only.)*
- **A-2:** Every fired alert exposes its grade breakdown (the factors that set the grade).
- **A-3:** Fresh-account default-on set = exactly the trusted core; nothing else fires until the user opts in.
- **A-4:** A level that has closed below this session does not fire a long reclaim until it is reclaimed-and-held.
- **A-5:** No alert is silently suppressed for low quality — it is graded down with a reason and still shown.

## Out of scope
- New pattern *types* (this hardens what exists). New patterns go through Sub-spec D.
- The discovery/ranking board (Sub-spec B).

## Notes
Aligns with the validated philosophy: levels primary, support-in-uptrend, dual-role, grade-don't-drop, EMA-as-confluence. The dual-role fix is the single highest-trust change before launch.
