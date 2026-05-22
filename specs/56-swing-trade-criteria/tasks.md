---
description: "Task list for Swing Trade Qualification Criteria for the AI Scan"
---

# Tasks: Swing Trade Qualification Criteria for the AI Scan

**Input**: Design documents from `trade-analytics/specs/56-swing-trade-criteria/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/swing-quality.md, quickstart.md

**Tests**: Test tasks ARE included — `trade-analytics/CLAUDE.md` mandates pytest coverage for alert-trigger logic, the plan calls for `tests/test_swing_quality.py`, and deterministic rules make the spec's success criteria directly testable.

**Organization**: Tasks are grouped by user story. User Stories 1–3 build and unit-test the deterministic qualification function (each story independently testable via `test_swing_quality.py`); the Integration phase wires it into the live scanner.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 / US2 / US3 — maps to the user stories in spec.md
- All paths are relative to repo root (`master-domain-hub/`)

## Path Conventions

Backend analytics change. New logic: `trade-analytics/analytics/swing_quality.py`. Wiring: `trade-analytics/analytics/ai_swing_scanner.py`. Indicators reused from `trade-analytics/analytics/intraday_data.py`. Tests: `trade-analytics/tests/test_swing_quality.py`.

---

## Phase 1: Setup

**Purpose**: Module scaffolding and dependency confirmation. No new packages required.

- [x] T001 [P] Create the module skeleton `trade-analytics/analytics/swing_quality.py` (module docstring + imports) and the test scaffold `trade-analytics/tests/test_swing_quality.py` (imports + fixture helpers for building daily OHLC series)
- [x] T002 [P] Confirm `trade-analytics/analytics/intraday_data.py` `fetch_prior_day()` exposes `ema21, ema50, ema100, ema200, ma50, ma100, ma200, rsi14` and an RSI history (`compute_rsi_series`) — the seven key MAs + RSI inputs the rules need; no new indicator code if all present

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared data structures, config, helpers, and the dispatch entrypoint that all three rule families plug into.

**⚠️ CRITICAL**: No user story rule work can begin until this phase is complete.

- [x] T003 Define the `SwingRuleHit` and `SwingQualification` data structures in `trade-analytics/analytics/swing_quality.py` per data-model.md (`rule`, `level`, `detail`; `symbol`, `direction`, `rules`, `entry`, `stop`, `target_1`, `target_2`, `close`, `session_date`, `summary`)
- [x] T004 Define the `SwingQualityConfig` tuning struct + defaults in `trade-analytics/analytics/swing_quality.py` — MA proximity tolerance (~1%), recent-high lookback (~20 bars), oversold lookback (~5–10 bars), downtrend filter
- [x] T005 Implement the uptrend-gate helper `_in_uptrend(daily, indicators, config)` in `trade-analytics/analytics/swing_quality.py` — true when a higher high was made within the recent-high lookback and the symbol is not in a sustained downtrend (FR-011)
- [x] T006 Implement the level-derivation helper `_derive_levels(daily, hits, config)` in `trade-analytics/analytics/swing_quality.py` — entry = qualifying close; structural stop (below the defended/reclaimed MA or candle low; RSI rule → below recent swing low); T1/T2 via R-multiple projection
- [x] T007 Implement the `evaluate_swing_quality(symbol, daily, indicators, config)` entrypoint in `trade-analytics/analytics/swing_quality.py` — calls the three rule-check functions (stubs returning `[]` for now), OR-combines their hits, merges into ONE `SwingQualification` (or `None`), attaches derived levels; pure/deterministic, no I/O

**Checkpoint**: The function exists and returns `None` for everything; the test file imports it cleanly.

---

## Phase 3: User Story 1 — Key-MA defense & reclaim (Priority: P1) 🎯 MVP

**Goal**: A pullback that holds, or a close that reclaims, one of the seven key MAs (21 EMA; 50/100/200 EMA & SMA) qualifies the symbol as a swing candidate.

**Independent Test**: Run `tests/test_swing_quality.py` against fixture daily series — a bar that holds the 50 EMA and a bar that reclaims the 100 SMA each return a `SwingQualification` citing that MA; a downtrend close-above-MA returns none.

- [x] T008 [US1] Implement the EMA/SMA **hold** rule `_ema_hold_hits(daily, indicators, config)` in `trade-analytics/analytics/swing_quality.py` — for each of the seven key MAs: bar was above the MA going in, low came within `config` tolerance of it, close finished above it; gated by `_in_uptrend`; returns `SwingRuleHit(rule="ema_hold", ...)` per MA met (FR-002)
- [x] T009 [US1] Implement the EMA/SMA **reclaim** rule `_ema_reclaim_hits(daily, indicators, config)` in `trade-analytics/analytics/swing_quality.py` — for each key MA: prior daily close below the MA, current daily close above it; gated by `_in_uptrend`; returns `SwingRuleHit(rule="ema_reclaim", ...)` per MA met (FR-003); wire both into `evaluate_swing_quality`
- [x] T010 [US1] Add tests to `trade-analytics/tests/test_swing_quality.py` — EMA hold, SMA hold, reclaim from below, the TSLA-style close back above 21 EMA + 100 EMA (one qualification, two hits), the uptrend gate (downtrend close-above-MA → no MA hit), and a bar that closes below the tested MA → no hit

**Checkpoint**: All seven key MAs are evaluated for hold + reclaim; US1 tests pass.

---

## Phase 4: User Story 2 — Oversold-RSI recovery (Priority: P1)

**Goal**: A stock whose daily RSI(14) closes back above 30 after being oversold qualifies as a swing candidate.

**Independent Test**: Run `tests/test_swing_quality.py` — a fixture with RSI ≤ 30 within the oversold window then a close with RSI > 30 returns a `SwingQualification` citing the RSI recovery; a mid-range-RSI fixture does not.

- [x] T011 [US2] Implement the RSI-recovery rule `_rsi_recovery_hit(indicators, config)` in `trade-analytics/analytics/swing_quality.py` — RSI(14) now above 30 and at/below 30 within `config.oversold_lookback` bars; NOT gated by the uptrend check; returns a `SwingRuleHit(rule="rsi_recovery", level="RSI 30", ...)`; wire into `evaluate_swing_quality` (FR-004)
- [x] T012 [US2] Add tests to `trade-analytics/tests/test_swing_quality.py` — the NFLX-style RSI-up-through-30 case qualifies; a never-oversold mid-range RSI does not; an RSI still ≤ 30 (not yet recovered) does not

**Checkpoint**: The RSI recovery rule fires independently of the MA rules; US2 tests pass.

---

## Phase 5: User Story 3 — Each swing candidate shows why it qualified (Priority: P2)

**Goal**: Every `SwingQualification` carries a plain-language reason naming the rule(s) and level(s) behind it.

**Independent Test**: Run `tests/test_swing_quality.py` — a candidate that qualified on the 50 EMA states "held the 50 EMA"; a multi-rule candidate lists every reason; an RSI candidate states the RSI recovery.

- [x] T013 [US3] Implement the `summary` composition in `trade-analytics/analytics/swing_quality.py` — build a plain-language sentence from `SwingQualification.rules` (each `SwingRuleHit`'s `rule` + `level` + `detail`), e.g. "Held the 50 EMA after a pullback; reclaimed the 100 SMA." (FR-007); confirm multi-hit merge yields one candidate with all rules (FR-008)
- [x] T014 [US3] Add tests to `trade-analytics/tests/test_swing_quality.py` — `summary` names rule + level for each rule type; a bar satisfying an MA rule and the RSI rule the same day → one `SwingQualification`, both reasons in `summary`; a no-setup series → `None`; identical inputs called twice → identical output (determinism)

**Checkpoint**: Qualification results are self-describing; the function is fully covered.

---

## Phase 6: Integration — wire into the AI swing scan

**Purpose**: Make the deterministic qualification live — replace the LLM path in the scheduled scanner.

- [x] T015 Wire `swing_scan_cycle` in `trade-analytics/analytics/ai_swing_scanner.py` to call `evaluate_swing_quality(...)` per symbol instead of `scan_swing(...)` (the Claude path); map a non-`None` `SwingQualification` onto the existing `Alert` persist + Telegram path (symbol, direction, entry/stop/T1/T2, `message`=`summary`, `setup_level`/`setup_condition`); keep watchlist loading, the 15-min schedule, market-hours/regime gating, per-day dedup, and the `ai_swing_alerts_per_day` rate limit unchanged
- [x] T016 Retire the now-unused LLM swing-qualification code in `trade-analytics/analytics/ai_swing_scanner.py` — `scan_swing`, the swing prompt builder, and the response parser; remove the Anthropic import/usage from the swing path if nothing else needs it

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T017 Run the full backend test suite from `trade-analytics/` (`python3 -m pytest tests/ -v --continue-on-collection-errors`) and confirm no new failures versus the pre-change baseline — alert and swing suites still green
- [x] T018 Execute the `quickstart.md` verification — `test_swing_quality.py` green and covering every rule + the TSLA/NFLX cases + the no-setup control; optional live spot-check that a scan produces self-describing swing candidates and makes no Anthropic call from the swing path

---

## Dependencies & Story Completion Order

```
Phase 1 Setup (T001–T002)
        ↓
Phase 2 Foundational (T003–T007)   ← BLOCKS all rule work
        ↓
Phase 3 US1 (T008–T010)  ← MVP — the key-MA defense/reclaim rules
Phase 4 US2 (T011–T012)  ← independent of US1 (RSI rule)
Phase 5 US3 (T013–T014)  ← depends on US1 + US2 (summarises their hits)
        ↓
Phase 6 Integration (T015–T016)  ← needs the function complete
        ↓
Phase 7 Polish (T017–T018)
```

- **US1 and US2** are independent rule families — once Foundational is done they can be built in either order.
- **US3** summarises whatever rules fired, so it follows US1 + US2.
- **Integration** wires the finished function into the live scanner — it delivers all three stories at once (the scanner calls one entrypoint).

## Parallel Execution Examples

- **Phase 1**: T001 (module + test scaffolds) and T002 (indicator-input check) are independent → run in parallel.
- **Phases 2–5**: nearly all tasks edit the single file `analytics/swing_quality.py` (rules) or `tests/test_swing_quality.py` (tests) — they are **sequential**; no `[P]`. US1 (T008–T010) and US2 (T011–T012) are independent *stories* but share the file, so interleave at the task level rather than running truly parallel.

## Implementation Strategy

1. **MVP**: Phase 1 → Phase 2 → Phase 3 (US1) → Phase 6 wiring → ship. The key-MA defense/reclaim rules are the headline change and deliver value alone.
2. **Increment 2**: Phase 4 (US2) — the RSI-recovery path.
3. **Increment 3**: Phase 5 (US3) — self-describing reasons.
4. **Close out**: Phase 7 — full regression + quickstart verification. Because this is protected alert-trigger logic (`trade-analytics/CLAUDE.md`), the regression run is mandatory before the change is considered done.
