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

## Acceptance criteria
- **A-1:** 2-week audit shows **zero** long-into-resistance fires.
- **A-2:** Every fired alert exposes its grade breakdown (the factors that set the grade).
- **A-3:** Fresh-account default-on set = exactly the trusted core; nothing else fires until the user opts in.
- **A-4:** A level that has closed below this session does not fire a long reclaim until it is reclaimed-and-held.
- **A-5:** No alert is silently suppressed for low quality — it is graded down with a reason and still shown.

## Out of scope
- New pattern *types* (this hardens what exists). New patterns go through Sub-spec D.
- The discovery/ranking board (Sub-spec B).

## Notes
Aligns with the validated philosophy: levels primary, support-in-uptrend, dual-role, grade-don't-drop, EMA-as-confluence. The dual-role fix is the single highest-trust change before launch.
