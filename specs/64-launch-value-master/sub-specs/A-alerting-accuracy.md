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

## Targets — two methodologies, chosen by trade type (rewritten 2026-06-19)

Targets are **never R-multiples.** Price moves to the next *level*, or until *momentum exhausts*, or it simply *runs for the session*. Each entry gets **one** target so accuracy is a single binary: *did the trade reach its target before the stop — yes or no?* — but the **target can be one of three TYPES**, picked by what's actually above the entry:

- **A price level** — when there's a real overhead level/wall to aim at (the common day-trade case).
- **An RSI level** — RSI 70 (or **80** for strong-momentum names — SNDK has run to 83), used when there's **no overhead level** (blue sky / gap-and-go) and for all swing entries.
- **A time exit (EOD)** — a pure day-trade with no overhead level can simply target the **close** (exit end-of-day), stop = morning low.

A "no overhead level" entry is **NOT** a no-trade and **NOT** an automatic downgrade — it's a momentum trade that targets RSI/EOD instead of a price. The two models below assign the type; the trade type (day vs swing) it belongs to is classified separately (see Out of scope).

### Model 1 — DAY-TRADE entries → nearest overhead level/wall

**Applies to:** every level entry (`staged_*` holds / reclaims / breaks, `gap_up_continuation`, `orl_held`, the `*_proximity` bounces), the **MA bounce / rejection** family, and **4h RC / RC-H**.

**Case A — there IS an overhead level (the common case):**
- **One target = the nearest meaningful level above the entry** (below, for shorts) — the first real resistance the trade can reach.
- **Candidate set** (the full chart stack, unified across both Pines):
  PDH / PDL / PWH / PWL / **PMH / PML** · daily **EMA 8/21/50/100/200** · **SMA 50/100/200** · recent **4h/1h swing highs/lows**.
- **Cluster** candidates within **~1%** of each other into one **"wall"** (e.g. PDH 405.94 + EMA50 406.06 + EMA100 405.17 = one strong target). A wall is stickier than a lone level.
- **Skip** anything closer than **~0.3%** to the entry (that's the level you're trading *at*, not a target).
- **No T1/T2/T3** — one target only.
- **Stop = structure below the entry**: the RC undercut low, the reclaimed level, or the nearest support below — never a fixed R.
- **Dual-role aware:** price *below* a level → that level is overhead resistance → it is the target. On reclaim-and-hold the level flips to **support** and the **next level up** becomes the target.
- **Cascade (single-target legs):** the ladder is NOT priced into one alert. When a target is taken and **holds**, a **new alert** fires with the next level as its one target ("PDL reclaimed & holding → target EMA200"). The lifecycle watcher drives the legs, so every alert is one clean measurable bet.

**Case B — NO overhead level (blue sky / gap-and-go / new highs):** this is a **valid momentum day-trade, not a no-trade and not a downgrade.** `gap_up_continuation_long` is the textbook case (opens above PDH and runs). When the level picker finds nothing above the entry:
- **Target = RSI 70**, or **RSI 80 for strong-momentum names** (parabolic runners — SNDK has hit RSI 83). Alternatively a **pure EOD exit** (sell the close) when there's no level and no clean RSI room.
- **Stop = the morning low** (opening / first-15m low) — already how `gap_up_continuation_long` sets it.
- This is a **riskier** trade (chasing strength) and should be **labeled as such in the grade breakdown**, but it remains a real A/B setup — momentum names make new highs, and that's where the money is on a gap-and-go.
- Emit the target as `target_rsi` (70/80) or a `target_eod=true` flag, not a fabricated price.

*Worked examples:*
- *TSLA below PDL 393.76, RC reclaim ~390 (Case A):* target = PDL 393.76 → on hold, new alert targets EMA200 396.85 → then the SMA100/SMA50 shelf.
- *SPCX RC 4h @ 175.94 (Case A):* target = weekly high 176.52 (not a leap to 213.80); each reclaim advances the leg → PDL 187.06 → PDH 213.73.
- *SNDK gap-and-go @ 2184, RSI 71 (Case B):* no level above → it's a momentum day-trade: target = **RSI 80** (it's already past 70 and these run) or **EOD exit**, stop = **morning low**. A valid, riskier setup — labeled as a chase, not blocked.

### Model 2 — SWING entries → RSI 70 (momentum exhaustion)

**Applies to:** the swing book — `rsi_oversold` (daily RSI 30–40 reclaim), `ema_5_20_cross`, the 20/50-EMA pullback hold, **and `weekly_rc`** (the weekly prior-week-low reclaim). These don't aim at a price level; they ride momentum and **exit into strength** — the institutional "buy weakness / pullback, sell into strength" model.

- **Target = RSI 70 on the entry's own timeframe.** The trade is "done" when RSI reaches 70, regardless of price. Daily entries → **daily** RSI 70; `weekly_rc` → **weekly** RSI 70.
- **Entry → target map:**
  - *Oversold reclaim* — buy daily RSI **30–40** reclaim/hold → target daily **RSI 70** (interim checkpoint RSI 50).
  - *5/20 EMA bullish cross* (Steve Burns) → target daily **RSI 70**.
  - *20/50-EMA pullback hold* → target daily **RSI 70**.
  - *Weekly RC* (undercut + reclaim prior-week low, green week) → target **weekly RSI 70.** This is a weeks-long position trade; weekly RSI 70 can take many weeks (or not print) — that's expected, the trail-stop below carries it.
- **Stop = structural, not R:** oversold → daily **close back under RSI 30**; EMA-cross / pullback → daily **close back under the 20 EMA**; `weekly_rc` → **weekly close below the prior-week low / 30w MA** (the existing weekly-stage trail).
- **`rsi_70` ignition is a NOTICE, not an entry** — it fires *at* the target zone (momentum already extended), so it carries no upside target; it's a heads-up / trail-the-stop signal.
- **Must be machine-readable:** emit a `target_rsi` field (= 70) **with its timeframe** (daily vs weekly), not prose in the note, so the lifecycle watcher can mark the hit and accuracy is the real RSI-70 hit-rate.

### Accuracy = one binary per leg
- Day trade: **did price reach the target level before the structural stop?**
- Swing: **did daily RSI reach 70 before the structural stop (RSI 30 / 20-EMA close-under)?**
Both reduce to a clean hit-rate — which is what makes the engine *measurable* and the grade trustworthy.

**Grade interaction:** more clean overhead room to the first wall (day) or more RSI distance to 70 (swing) = better reward → upgrade. A target wall right above the entry, or an entry already near RSI 70, caps the trade → downgrade (no room to run).

## Current implementation audit (2026-06-19 — what exists vs. the above)

The target logic is **partially built and fragmented across three code paths.** This is what the implementation pass must reconcile:

**Day-trade targets:**
- `levels_day_vwap.pine` **holds** still use the *old per-rule hierarchy* (`PWH→PMH→%`, `PDH→PWH→%`) inline — **defective**: `pwh_held` ignores PDH (the obvious overhead level); `pdl_held`/`pwl_held` leap to PDH skipping the nearer PWH/PMH/EMA walls.
- Only `pdl_reclaim` / `pwl_reclaim` use the `nearest_stack_above` picker (#307). Holds, breaks, and gap-and-go were never converted.
- `ma_ema_daily.pine` uses a *separate* engine `ma_targets_above/below` — nearest 2 of {8 MAs + PDH/PDL/PWH/PWL}, **missing PMH/PML**, with R-multiple fallback (`r_t1=4`, `r_t2=6`).
- **Still emits T1 AND T2 everywhere** (46 `t2_*` calcs in the levels Pine; `t1_long`/`t2_long` in `ma_ema_daily`). Spec requires **one** target.
- **No clustering** anywhere. **No 4h/1h swing highs** in any candidate set. Skip band is a flat ~1% (no 0.3%-noise / cluster distinction).

**4h RC (`rc_4h.pine` — day-trade, Model 1):**
- Fires 3 patterns (RC = reclaim prior-4h low; RC-H = breakout-retest of prior-4h high; rejection short). Entry = 4h close, stop = the 4h bar extreme (structural — correct). ✅
- **Emits NO target at all** (payload is entry + stop + note). Must be wired into the unified day-trade picker.
- **No confluence gating** — fires on every 4h reclaim, no volume/VWAP/own-trend check. Needs the grade pass.

**Swing targets:**
- RSI-70 target lives **only as note text** (`rsi_oversold`: "T1 RSI 50, T2 RSI 70"; `ema_5_20_cross`: "Target = RSI 70"). **No machine-readable target field** → not measurable.
- `rsi_70` fires with **no stop and no target** → risk can't be computed.
- `weekly_rc` (`levels_day_vwap`, 2 variants: below/above the 30w MA, green-week required) fires entry = weekly close, stop = weekly low, but **no target**. Decision 2026-06-19: target = **weekly RSI 70** (folds into Model 2). Needs `target_rsi=70` + timeframe=W in the payload.

Note `gap_up_continuation_long` currently emits a fabricated price target (`PWH` or `+2%`); under the new model it has **no overhead level** → its target must become **RSI 70/80 or EOD**, stop already = the open low (correct).

**The reconciliation work (for the implementation HLD):**
1. **Unify** the day-trade target engine into ONE clustered nearest-wall picker over the full candidate set (incl. PMH/PML + 4h/1h swings), used by *every* day-trade entry in *both* Pines.
2. **Fallback to RSI/EOD when no level is found** (Case B): the picker returns "no overhead level" → emit `target_rsi` (70, or 80 for strong momentum) or `target_eod=true`, not a fabricated price. Fix `gap_up_continuation_long` here.
3. **Remove T2** end-to-end (Pine payloads, `notifier`, `monitor` `target_2_hit`, UI / PDF) — one target only.
4. **Add `target_rsi`** (+ timeframe) to the swing payloads + a structural stop on every swing entry; demote `rsi_70` to NOTICE.
5. **Add clustering + the 0.3%-skip / ~1%-cluster bands** to the picker.

## Acceptance criteria
- **A-1:** 2-week audit shows **zero** long-into-resistance fires.
- **A-6:** Every **day-trade** alert has **exactly one** target, not an R-multiple and not T1+T2, with a structural stop (not a fixed R). One unified picker serves both Pines and all day-trade entry types (holds, reclaims, breaks, gap-and-go, MA bounce/rejection, 4h RC). The target is one of: **(a)** the nearest clustered level/EMA/swing above the entry (>0.3% away, walls merged within ~1%) when one exists, or **(b)** when none exists (blue sky / gap-and-go) → **RSI 70/80 or EOD exit**, stop = morning low. Case (b) is a valid setup labeled as a momentum chase in the grade — never silently dropped.
- **A-7:** The day-trade ladder plays out as single-target legs — when a target level is taken and holds, a new alert fires with the next level as its one target. Accuracy is the hit-rate of "reached target before stop."
- **A-8 (swing):** Every **swing** alert (`rsi_oversold`, `ema_5_20_cross`, 20/50-EMA pullback hold, **`weekly_rc`**) carries a **machine-readable `target_rsi=70` with its timeframe** (daily for the daily entries, **weekly** for `weekly_rc`) and a structural stop (RSI-30 close-under for oversold; 20-EMA close-under for cross/pullback; weekly close below prior-week low / 30w MA for `weekly_rc`). `rsi_70` ignition is demoted to NOTICE (no target). Accuracy is the hit-rate of "RSI reached 70 (on the entry's timeframe) before the stop."
- **A-9 (visibility):** the single target is drawn on the chart as a **labeled line** ("T · PDH 405.94") alongside entry + stop, so target realism is visible at a glance. *(The chart component already draws E / S / T lines — it just needs the alert's `entry/stop/target` wired into the Trading-page chart, which is currently not passed. Small, frontend-only.)*
- **A-2:** Every fired alert exposes its grade breakdown (the factors that set the grade).
- **A-3:** Fresh-account default-on set = exactly the trusted core; nothing else fires until the user opts in.
- **A-4:** A level that has closed below this session does not fire a long reclaim until it is reclaimed-and-held.
- **A-5:** No alert is silently suppressed for low quality — it is graded down with a reason and still shown.

## Out of scope
- New pattern *types* (this hardens what exists). New patterns go through Sub-spec D.
- The discovery/ranking board (Sub-spec B).
- **Day-trade vs swing classification (its own sub-spec).** *How* an alert is tagged day vs swing — and the RSI-at-fire-time signal that drives it — is a separate spec. The intent captured here for that follow-up: **read RSI at the moment the alert fires** and tag accordingly — e.g. an entry firing with **RSI already > 70** is a classic **day-trade** (extended; momentum chase, EOD/morning-low frame), while the same setup at lower RSI may be **swing**-eligible; the user can always choose to swing a strong-momentum day-trade. This spec only defines the *targets per type*; the classifier that assigns the type comes next.

## Notes
Aligns with the validated philosophy: levels primary, support-in-uptrend, dual-role, grade-don't-drop, EMA-as-confluence. The dual-role fix is the single highest-trust change before launch.
