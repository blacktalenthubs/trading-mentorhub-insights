# MLV — Directional Monthly-Level Reclaim (full 6-month map)

**Status:** proposed · **Type:** day-trade alert · **Owner:** vbolofinde · **Date:** 2026-07-11

## Overview
Make **MLV** the single alert for *every* completed monthly level, fired only as a **support reclaim** (price opened above the level, dipped through it, reclaimed it). One uniform, directional, 1h-confirmed rule over the full 6-month body+rail map.

## Problem
Today's MLV fires on **H/L of months 2–4 only**, on the **5m** bar, with **no directional gate**. That means it:
1. **Misses the edge** — the validated winners were **body (O/C)** and **recent-month** reclaims (AAPL Jun O, META Apr O, NVDA ~200 O/C cluster). None are in the current level set.
2. **Fires into resistance** — any wick+reclaim triggers a long even when price rallied *up into* the level from below (MU/ACMR failures — closes right back under).
3. **Is noisy** — a 5m close "reclaims" a *monthly* level on a brief poke.

Backtest of the correct rule: **169 trades, 63% win, +0.90R/trade, +152R** (18mo, 5 names, no lookahead). The current alert does not implement that rule.

## The rule (one, uniform, all 24 levels)
A monthly level `L` fires **BUY** when:
```
day_open > L        (support — price opened above it)
AND 1h_low  ≤ L     (wicked below on the 1h bar)
AND 1h_close > L    (reclaimed — 1h close back above)
```
- **Entry** = `L` · **Stop** = the 1h reclaim-bar low · **Once per level per day.**
- Same gate on H, L, O, C alike: a low defended, a broken high retested, a body edge held — all just "opened above, reclaimed."

## Scope
- **Levels:** `H, L, O, C` of the **last 6 completed months** = **24 levels**. No exceptions.
- **CML** (current-month low): **removed, stays removed** (was noisy / handled wrong).
- **monthly_rc** (prior-month H/L reclaim): **RETIRED** — month [1] is now inside MLV's 6-month span, so it's fully covered. **No alerts lost.**
- **MoBO** (monthly box breakout): unchanged — a breakout pattern, not a level reclaim.

## Changes

### 1. Pine — `pine_scripts/active/rc.pine`
- Replace the MLV block (~L559–573): **6 monthly `request.security` calls** (one per month, each returning `[high, low, open, close, time]`) → build a **24-level** array with `{Mon} {H/L/O/C}` labels.
- Add **`day_open`** = `request.security(tid,"D",open)` gate (TF-independent → works on the 5m-bound alert).
- Add **1h confirmation** = `request.security(tid,"60",…)`, fire on the **completed** 1h bar that reclaims (non-repaint form).
- **Delete** the `monthly_rc` alert block (`enM_long`/`enM_hrec` fires) and its input toggles.
- Payload rule name stays **`monthly_lvl_reclaim`**; label carries `{Mon}{O/H/L/C}` + entry/stop.
- **Deploy:** re-paste rc.pine + **delete & recreate** the 5m-bound alert (TV snapshots the Pine).

### 2. Backend
- `alert_type_config.py`: `monthly_lvl_reclaim` stays (style = **day_trade**). Add `monthly_rc` (and `weekly_rc`? no — weekly stays) to **OBSOLETE_ALERT_TYPES** so retired fires record as obsolete, not `unknown_type`.
- `tv_webhook.py`: **no routing change** — MLV routes as a normal BUY; the directional gate lives in the Pine. Entry/stop already structural from the payload.

### 3. UI — Settings
- Keep the **"MLV reclaim"** type toggle (Day Trade group).
- **Remove the "Monthly RC" toggle(s)** (folded into MLV).
- No new user setting — the 6-month depth is a Pine input, not per-user.

## Acceptance
1. On AAPL/META/NVDA over 2026-07-01→10, MLV fires **exactly** the inspected ▲ longs — AAPL Jun O (×2), META May L + Apr O, NVDA May L (×2) + the ~200 O/C cluster — and **nothing** on rally-into-resistance days (e.g. MU 07-10 → no fire; META 07-10 air-pocket → no fire).
2. **Zero** duplicate prior-month alerts (monthly_rc gone).
3. No fire on a bare 5m poke — reclaim confirmed on the **1h** close.

## Out of scope
- Targets (still exploring — keep the structural reclaim-low stop; no target change).
- Extending the `open>level` gate to **PDH/PDL/weekly** — next, after MLV is proven.
- MoBO, CML.

## Risks / notes
- **Cross-TF 1h repaint** — the exact gotcha that broke the rc_4h markers. **Validate on-chart on both 5m and 1h** before trusting. Fallback: 5m reclaim + ~1h hold-confirm (same neatness, no cross-TF repaint).
- **`request.security` budget** — 6 new monthly calls added to rc.pine; verify under the per-script limit.
- **rc.pine is cornerstone** — Pine not compile-verified here; user must TV compile-test + recreate the alert. Concurrent-agent edit risk on the file.

## Rollout
1. Write rebuilt MLV block as a **standalone snippet** → paste on a chart, eyeball vs AAPL/META/NVDA (esp. the 1h confirmation).
2. On pass → merge into rc.pine + retire monthly_rc; backend obsolete-type + Settings toggle removal.
3. User re-pastes rc.pine + recreates the 5m alert.
4. Watch live for a few sessions; then extend the gate to PDH/PDL/weekly.
