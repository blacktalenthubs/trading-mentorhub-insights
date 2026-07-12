# WLV — Directional Weekly-Level Reclaim (4-week map)

**Status:** proposed · **Type:** day-trade alert · **Owner:** vbolofinde · **Date:** 2026-07-11
**Sibling of:** spec 68 (MLV) — same rule, applied to weeks.

## Overview
Make **WLV** the single alert for *every* completed weekly level, fired only as a **support reclaim**. One uniform, directional rule over the last **4 weeks'** H/L/O/C — the weekly twin of MLV. Retires the prior-week-only weekly alerts.

## Problem
Weekly coverage today is thin and scattered: `weekly_rc` sees only the **prior week's** H/L (undercut & reclaim), `staged_pwl_held` only the prior-week LOW. There's no body (O/C) coverage, no multi-week map, and no directional gate — so a rally *up into* a weekly level fires the same as a genuine reclaim from above. The new `weekly_levels.pine` visual already tracks **4 weeks of H/L/O/C** (16 levels) with the directional marks; the alert should match it.

## The rule (one, uniform — identical to MLV)
A weekly level `L` fires **BUY** when:
```
day_open > L        (support — price opened above it)
AND low  ≤ L        (wicked below)
AND close > L       (reclaimed — closed back above)     + min-penetration floor
```
- **Optional (`enWLVbelow`):** also fire **reclaim-from-below** (`day_open < L`, `close > L`, prior close ≤ L).
- **Entry** = `L` · **Stop** = the reclaim-bar low · **Once per level per day** · **long only** · fires on the chart/5m bar like rc_daily (tight stop; the TF sets the stop width, not a 1h wait).
- Same gate on H, L, O, C alike.

## Scope
- **Levels:** `H, L, O, C` of the **last 4 completed weeks** = **16 levels**, no exceptions.
- **Emit type:** new **`weekly_lvl_reclaim`** (mirrors `monthly_lvl_reclaim`), **day-trade** style.
- **Retire (fold into WLV):**
  - **`weekly_rc`** — prior-week H/L reclaim (week[1] is now inside WLV).
  - **`staged_pwl_held`** — PWL held (the prior-week low is a WLV level).
- **Decision needed — the weekly *MA* alerts:** `weekly_10w_held` / `weekly_30w_held` are the 10/30-**week moving averages** (a Weinstein-style *trend* tool), **not** weekly candle levels. WLV does **not** compute them. **Recommend: keep them separate** (exactly as MLV kept `monthly_ma_reclaim`). If "retire all weekly alerts" means these too, say so and they're added to the retire list.

## Changes
### Pine — `rc.pine`
- Add a 16-level WLV engine: **4 weekly `request.security` calls** (H/L/O/C/time), `day_open` (D) gate, `enWLV` (default ON) fires DEFEND, `enWLVbelow` (default ON, off if noisy) fires from-below, `wlvMinPen` floor.
- **Delete** the `weekly_rc` block (`enW_long`/`enW_hrec` + fires) and the `staged_pwl_held` path (if in rc.pine; else its source pine).
- Payload rule = `weekly_lvl_reclaim`; label `wk {date} {H/L/O/C} ... entry/stop`.
- **Default ON** (per [[feedback_pine_defaults_on]] — re-paste resets toggles).
- Deploy: re-paste + delete/recreate the bound alert.

### Backend — `alert_type_config.py`
- Add `weekly_lvl_reclaim` (category "Weekly", day_trade style via a `("weekly_lvl","day_trade")` prefix).
- `weekly_rc` + `staged_pwl_held` → **OBSOLETE_ALERT_TYPES**.

### Settings
- Auto-updates (catalog-driven) → **WLV becomes the single weekly toggle**; old weekly-level toggles drop.

## Acceptance
1. WLV fires the same ▲ reclaims the `weekly_levels.pine` visual marks (defend + from-below), on the validation names.
2. No `weekly_rc` / `staged_pwl_held` duplicates.
3. Micro-stop pokes filtered by `wlvMinPen`.
4. Weekly 10w/30w MA alerts unaffected (unless explicitly folded in).

## Out of scope
- Targets (structural reclaim-low stop only).
- The weekly *MA* (10w/30w) tool — separate, pending the decision above.
- Extending the `open>level` gate to PDH/PDL (that's the daily track, later).

## Risks
- **`request.security` budget** — 4 weekly calls added on top of MLV's 6 monthly; verify rc.pine stays under the per-script limit (may need to collapse tuples).
- rc.pine cornerstone — not compile-verified; TV compile-test + recreate the alert.
- **Validate the visual first** (this spec's prerequisite) — the `weekly_levels.pine` marks must read right on 1h/4h before wiring the alert.

## Rollout (mirrors MLV)
1. ✅ Visual shipped — `weekly_levels.pine` (#750).
2. **USER eyeballs** the ▲/△ marks on 1h/4h across names.
3. On pass → build the WLV alert in rc.pine + retire `weekly_rc`/`staged_pwl_held`; backend obsolete + Settings.
4. User re-paste + recreate; watch live.
5. Decide the weekly-MA question.
