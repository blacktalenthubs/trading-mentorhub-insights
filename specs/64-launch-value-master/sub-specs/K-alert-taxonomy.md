# Sub-spec K — Alert Taxonomy & Consistency: one canonical registry across Pines, Learn & Strategy (P1)

**Parent:** #64 Launch Value Master · **Pillars:** A (alerting) + C (education) + I (analysis) · **Priority:** P1

## Overview
There is **no single source of truth for "what alert types exist."** The Pines emit one set of `rule` codes, `Strategy Analysis` shows the *entire historical archive* (including retired rules), `Learn` has its own pattern list, and the card label (`formatSetup`) is a third mapping. Result: a user opens Strategy Analysis and sees 23 patterns — many of which **no current Pine fires** (`Ma Rejection Short V3`, `Session Low Double Bottom`, `Vwap Reclaim Long`, `Morning Low Retest`, `Staged Sweep Long`…) — with no way to learn most of them. This spec makes **every live alert type a first-class, consistent entity** across emission → label → education → analysis, and retires the legacy ones.

## Problem
1. **Legacy pollution.** Strategy Analysis / the data hold alert types from old Python rules + retired Pine alerts. They dilute the "what works" view with dead setups.
2. **No 1:1 Learn coverage.** Not every live alert type has a lesson; some lessons describe patterns we no longer fire.
3. **Three inconsistent mappings.** Pine `rule` code, `formatSetup` label, and Learn slug are maintained separately and drift.
4. **No classification.** Day vs swing vs trend, and trusted-core vs noise, isn't encoded — so we can't filter or prioritize.

## The live taxonomy (audited from the four firing Pines, 2026-06-19)
| Pine | Live alert types |
|------|------------------|
| **levels_day_vwap** | `*_held` (pdh/pdl/pwh/pwl/pmh/pml), `pdl_reclaim`, `pdh_reclaim`, `*_break` (pdh/pwh/pmh), `pdh_rejection`, `orl_held`, `mtd_avwap_held`, `pm_avwap_held`, `*_proximity` (info), `lost_support_reject`, `gap_fill`, `gap_reject`, `gap_support` |
| **rc_4h** (cornerstone) | `rc_4h` (reclaim prior 4h low), `rc_h` (reclaim prior 4h high) |
| **momentum_rsi_ma** | `ema_5_20_cross`, `rsi_oversold`, `rsi_70` |
| **weekly / trend** | `weekly_rc` (+ `WkStage` if it alerts) |
| **ma_ema_daily** | *MA flat-level bounces — verify which (if any) fire vs are legacy* |

Everything else in the data (≈10 names) is **legacy → retire**.

## The fix — one registry, three consumers
**A single canonical registry** (one file/table) is the source of truth. Each live alert type has:
- `code` (the Pine `rule`, e.g. `staged_pdl_reclaim`)
- `label` (human, e.g. "PDL reclaim")
- `classification` (`day` | `swing` | `trend`) + `tier` (`core` | `context` | `retired`)
- `pine` (which Pine emits it)
- `learn_slug` (the Learn lesson it links to) + a one-line "why it works"
- `tradeable` (true) vs `info` (proximity/notice — excluded from win-rate)

Then:
1. **Strategy Analysis** shows only registry types (`tier != retired`); legacy rows are hidden (or grouped under a collapsed "Retired/legacy" footer). Info types (proximity) are excluded from win-rate.
2. **Learn** has a lesson for **every** `tier: core` type (`learn_slug` resolves); the card's "Learn" deep-links to it (closes the alert_type→lesson gap noted in #64-I).
3. **`formatSetup`** reads the registry `label` — no separate drift.
4. **Cards / EOD / MyStrategy** all show the registry label + link.

## Acceptance criteria
- **K-1:** A canonical registry lists every LIVE alert type with code · label · classification · tier · pine · learn_slug.
- **K-2:** Strategy Analysis + MyStrategy show only non-retired registry types; legacy is hidden or clearly grouped as retired.
- **K-3:** Every `core` alert type has a Learn lesson; the card's Learn deep-links to it (not just `/learn`).
- **K-4:** `formatSetup`, the cards, EOD, and Strategy Analysis all render the same registry label for a given code.
- **K-5:** `info`/proximity types are excluded from win-rate math.
- **K-6:** Adding a new alert type = one registry entry (label + lesson + class), automatically reflected everywhere.

## Out of scope
- Changing *which* alerts fire (that's Sub-spec A's trusted-core decisions) — K only makes the taxonomy consistent + educated.
- The lesson *content* (Sub-spec C / D own the pedagogy); K guarantees the 1:1 link exists.
- The **dynamic, at-fire-time** day/swing tag (read from RSI + EMA-location per fired alert) and the swing target/stop mechanics — **Sub-spec L** owns that. K provides only the **static per-type baseline** `classification` field that L refines.

## Notes
This is the connective tissue under A (the setups), C/D (the education), and I (the analysis). Without it, every surface drifts. Build the registry once; Strategy Analysis stops lying about retired setups, and every live pattern becomes learnable in one tap. Ties to [[feedback_what_value_data_chain]], [[project_launch_value_master_spec]], [[project_rc_pine_cornerstone]].
