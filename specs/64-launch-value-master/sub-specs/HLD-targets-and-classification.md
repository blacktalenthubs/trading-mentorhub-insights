# HLD — Realistic Targets + Day/Swing Classification (Sub-specs A + L)

**Parent:** #64 Launch Value Master · **Implements:** Sub-spec A (targets) + Sub-spec L (day/swing classification) · **Priority:** P1

## Overview
One build that makes every alert carry **one realistic target** (a level, an RSI, or an EOD exit) and a **DAY/SWINGABLE tag**, both decided from the chart state at fire time. A and L are drafted together because they share the same plumbing: the **Pine payload**, the **backend route-and-persist step**, the **notifier**, and the **lifecycle watcher**.

## Problem (today)
- Targets are computed in the **Pine**, fragmented across **three engines** (levels-holds hierarchy, levels-reclaims `nearest_stack_above`, `ma_ema_daily.ma_targets_above`), all emitting **T1 + T2**, none clustering, none including 4h/1h swings. `4h RC` emits **no target**; swing RSI targets are **prose only**; `gap_up_continuation` emits a **fabricated price**.
- Classification is **static by type** (`_is_swing_alert`), used only to bypass a gate — invisible to the user, doesn't drive targets/stops.
- **RSI is not in the day-trade payload** — the one missing classification input.

## The keystone decision
**Move target computation + classification OUT of the Pines and INTO the backend**, extending the existing structural-targets step in `tv_webhook._route_and_persist`. Rationale:
- A single picker can't be shared across two Pines — it has to live in one place. The backend already runs a structural-targets + level-dedup pass and already has prior-day/level data.
- The backend can hold the **full candidate set** (levels + EMAs + later 4h/1h swings) and do **clustering** — things the Pine can't share.
- It makes **T2 removal** trivial (backend emits one target) and kills the 3-engine fragmentation.

**The Pines become the *trigger + context* layer**; they send entry, structural stop, and the raw inputs (levels, EMAs, **RSI**). The backend computes the **one** target + the **trade_type** tag. Pine `target_1/target_2` fields are ignored once Phase 2 ships (kept in payload for one release for rollback).

## Architecture — phased delivery

### Phase 1 — Pine payload enrichment (ships first, backward-compatible)
- Add **`rsi`** (daily, `request.security` "D") to `build_payload_v2` — the missing classification input.
- Swing payloads (`rsi_oversold`, `ema_5_20_cross`, `weekly_rc`): emit machine-readable **`target_rsi`** (70) **+ `target_tf`** (D or W) instead of prose.
- `gap_up_continuation`: stop already = open low; mark it **Case B** (`target_kind=rsi|eod`) rather than a fake price.
- `staged_orl_held` once-per-day guard — **already shipped**.
- Backend treats all new fields as optional → no break if old Pine still live.

### Phase 2 — Backend unified target picker (the core of A)
Extend the structural-targets step in `tv_webhook._route_and_persist`:
- **Candidate set:** PDH/PDL/PWH/PWL/**PMH/PML** + daily EMA 8/21/50/100/200 + SMA 50/100/200. (No 4h/1h swing pivots — unnecessary complexity per founder; the level + EMA stack is the candidate set.)
- **Cluster** within ~1% into one wall; **skip** <0.3% from entry.
- **Case A** (level above) → nearest wall = the one target.
- **Case B** (none above) → `target_rsi` (70, or 80 if RSI already >70) or `target_eod=true`; stop = morning low.
- Emit **one** `target` (+ `target_kind` = `level|rsi|eod`). Replaces all Pine-side target math for day trades.

### Phase 3 — T2 removal (end-to-end)
- Stop populating `target_2`; remove `T2 $X` from `notifier.py`; drop `target_2_hit` from `monitor.py`; remove from card / `alerts_pdf.py`. Keep the DB column (harmless).

### Phase 4 — Day/Swing classifier (the core of L)
- Backend function: `(alert_type, rsi, registry_baseline) → (trade_type, swing_eligible)`. **Extends the existing `_is_swing_alert`** — the type already names the EMA, so no EMA-location math.
  - Slow-EMA bounce (`ma_bounce_*_ema21/50/100/200` + matching SMAs) or K-baseline `swing` → **SWING** (target RSI 70–75 or prior-day-low break). *Adds the 21-EMA to the swing set (was 50/100/200).*
  - Core level / fast **8-EMA** → **DAY** (Sub-spec A targets, morning-low stop).
  - RSI >70 at fire → **DAY** + `swing_eligible=true` (tag only — user decides).
- Surface the tag in the **notifier label** ("DAY" / "SWINGABLE" / "DAY · swing-eligible") + card + EOD.

### Phase 5 — Swing lifecycle
- Swing stop = **prior-day-low trailing** in the lifecycle watcher: **day 1 = the morning low; every day after = the prior day's low**, raised daily. Exit on a break below it **or** RSI 70–75.

### Phase 6 — Measurement
- Per `trade_type`, the binary hit-rate: **reached target (level / RSI / EOD) before the structural stop?** Feeds the grade and the Performance view (closes the "outcomes not computed" gap for these types).

## Functional requirements
- **FR-1:** Pine emits `rsi` (daily) + machine-readable `target_rsi`/`target_kind` on every entry.
- **FR-2:** Backend computes exactly **one** target per alert (level / RSI / EOD), clustered, dual-role aware.
- **FR-3:** No alert carries T2 after Phase 3.
- **FR-4:** Every tradeable alert carries `trade_type` + `swing_eligible`, set at fire time from **alert type + RSI + registry baseline** (no EMA-location math).
- **FR-5:** Swing entries get a **prior-day-low trailing stop** (day 1 = morning low; after = prior-day low, raised daily) and an RSI 70–75 / PDL-break exit.
- **FR-6:** The DAY/SWINGABLE tag and the single target render in Telegram + card + EOD.

## Signal-feed impact
The live Signals feed + EOD report show **delivered** rows only (`suppressed_reason IS NULL`), rendered by `SignalCard.tsx`. Impact:

- **Price targets stay the default.** Most day-trade entries have a neighbor level above → they keep a **price target** (Case A) and render exactly as today. **RSI/EOD targets are the exception** (Case B — blue sky / gap-and-go), not the norm. So the feed's look is mostly unchanged; the new rendering is **additive**.
- **Volume drops (positive, no UI work):** the ORL once-per-day guard + `orl_always_symbols` strip the feed's #1 noise source (ORL ~24k/10d → one per setup). Cleaner feed immediately.
- **Card render — branch on `target_kind`:**
  - `level` (the common day-trade case) → render the **price** + the chart **T-line** + `dollarReward`, **as today**.
  - `rsi` → render **"RSI 70"** (no price line, `dollarReward` hidden — there's no entry-to-target dollar delta).
  - `eod` → render **"Exit EOD"** (same — no price line / dollar reward).
  - **Remove the T2 block** — one target only.
  - Add the **DAY / SWINGABLE** badge.
- **Guard the price-only code:** `dollarReward` (SignalCard:58) and the chart **T1 line** (CandlestickChart:388) assume a price target — they must **no-op for `rsi`/`eod`** kinds, not render `$NaN` / a bogus line. This is the one easy-to-miss break.
- **Mixed legacy/new during rollout:** historical rows keep Pine T1/T2 (price); new rows carry one `target` + `target_kind`. `target_kind == null` ⇒ legacy ⇒ render as a price (today's path). No migration.
- **Stats:** `PerformanceDashboard` "T1 Hits" → "Target hits" (one binary). RSI/EOD hits are marked by the Phase-5/6 lifecycle watcher, not a price cross.
- **New `AlertResponse` + `types/index.ts` fields** (3 spots): `trade_type`, `swing_eligible`, `target_kind`, `rsi` — without them the badge + target-kind can't render.
- **Optional win:** `trade_type` lets the feed **filter/group DAY vs SWING**.

## Non-functional requirements
- **NFR-1:** Phase 1 is backward-compatible (old Pine keeps working; new fields optional).
- **NFR-2:** Target/classification logic is unit-testable in the backend (no Pine round-trip) — fixtures per Case A/B and per trade_type.
- **NFR-3:** Each phase is independently deployable + reversible (env flag on the picker swap).
- **NFR-4:** Protected-file discipline (CLAUDE.md): `tv_webhook`, `notifier`, `monitor` changes get impact analysis + the full test suite before merge.

## Decisions (resolved 2026-06-19)
1. **Picker location:** extend the existing structural-target step in `tv_webhook._route_and_persist` (the LLD factors it into a testable helper as it goes — no greenfield module unless the step proves too tangled).
2. **EMA classification:** ~~tolerance~~ **N/A** — the alert type already names the EMA; no location math. Just re-tag the slow-EMA bounce types as swing.
3. **`swing_eligible`:** **a tag only** — the user decides whether to hold. No behavior change, no button.
4. **4h/1h swing pivots:** **dropped** — candidate set is levels + EMAs only.

## Out of scope
- Static registry/taxonomy (Sub-spec K) — consumed here as the classification baseline, not built here.
- Swing-scanner / discovery board (Sub-spec B).
- New pattern types (Sub-spec D).

## Notes
Ties to [[feedback_level_anchored_targets]], [[project_launch_value_master_spec]], [[project_rc_pine_cornerstone]]. The keystone is moving target+classification to the backend — it unifies both Pines, enables clustering + 4h/1h swings, and makes the whole thing unit-testable and measurable.
