---

description: "Implementation task list for Spec 58 — Day-Trade Entry Rules Redesign"
---

# Tasks: Day-Trade Entry Rules Redesign

**Input**: Design documents from `trade-analytics/specs/58-entry-rules-redesign/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/tv-webhook-payload.md](./contracts/tv-webhook-payload.md), [quickstart.md](./quickstart.md)

**Tests**: Limited targeted unit tests for the pure deterministic confluence helpers (`find_confluences`, `format_confluence_annotation`) — high-ROI coverage of math that's hard to validate visually. Smoke tests are manual chart verification per `quickstart.md`. No full TDD.

**Organization**: Tasks grouped by user story for independent implementability. Phase 2 (Foundational) MUST complete before any user-story phase begins — the payload schema is the shared contract.

## Format: `[ID] [P?] [Story] Description`

- **[P]** — can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]** — `[US1]` / `[US2]` / `[US3]` for user-story tasks; absent for setup/foundational/polish
- Exact file paths included for every code task

## Path Conventions

This is an existing monorepo. All paths relative to repo root:

- `trade-analytics/pine_scripts/active/*.pine` — TradingView scripts (deployed via Pine Editor save + chart re-add)
- `trade-analytics/api/app/...` — FastAPI backend (deployed via Railway push)
- `trade-analytics/tests/...` — pytest tests

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish baseline and test scaffolding before any edits.

- [X] T001 Verify baseline FastAPI tests pass green: `cd trade-analytics && python3 -m pytest tests/ -v` — record the pass count so regressions are caught **(baseline: 1571 passed, 55 pre-existing failures unrelated to spec 58)**
- [X] T002 [P] Create empty test file scaffold at `trade-analytics/tests/test_tv_webhook_confluence.py` with one passing placeholder test so the file is importable

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Define the payload contract (Pine → webhook) and the pure-function helpers everything depends on.

**⚠️ CRITICAL**: No user-story work can begin until this phase is complete — every user story uses the new payload fields and the confluence helpers.

- [X] T003 Added `find_confluences()` to `trade-analytics/api/app/routers/tv_webhook.py` with the 1.0% band and `CONFLUENCE_BAND_PCT` constant.
- [X] T004 Added `format_confluence_annotation()` to `trade-analytics/api/app/routers/tv_webhook.py` — empty string when no confluences, else `"Confluence: <label> ($value), ..."`.
- [X] T005 [P] 8 `find_confluences()` unit tests in `trade-analytics/tests/test_tv_webhook_confluence.py` (AVGO/NVDA/multi/edge cases) — all green.
- [X] T006 [P] 8 `format_confluence_annotation()` unit tests in `trade-analytics/tests/test_tv_webhook_confluence.py` — all green. **Total 16/16 passing.**
- [X] T007 Extended the Pine payload parser in `trade-analytics/analytics/tv_signal_adapter.py` to attach `_tv_uptrend_pass`, `_tv_overhead_mas`, `_tv_nearby_levels`, `_tv_mtd_avwap` on the signal object. Backward-compat preserved (all default None/[]). 106 webhook tests still pass.

**Checkpoint**: Payload contract defined, helpers tested. User-story work can begin.

---

## Phase 3: User Story 1 — Uptrend gate + MA bounce with confluence annotation (Priority: P1) 🎯 MVP

**Goal**: Stop the 6/8 MA-bounce noise. A stock with overhead MAs (META, PLTR, MSFT, V, MSTR etc.) produces no entry. A clean-uptrend bounce (AAOI, AVGO etc.) produces one alert with confluence annotation inline.

**Independent Test**: On the next live session, META and similar overhead-MA stocks produce zero Buy alerts; AAOI-style triple-confluence bounces produce one alert per setup with a `Confluence:` line listing the other clustered levels. See `quickstart.md` smoke tests #1 + #2.

### Implementation for User Story 1

- [X] T008 [US1] Ported MTD AVWAP accumulator into `trade-analytics/pine_scripts/active/ma_ema_daily.pine` — `var float mtd_pv/mtd_vv`, monthly reset, `mtd_avwap = mtd_vv > 0 ? mtd_pv / mtd_vv : na`.
- [X] T009 [US1] Added `uptrend_pass` (close above every key MA via `nz()`-guarded comparison) and `overhead_mas_str` (CSV of overhead MA names) in `ma_ema_daily.pine`.
- [X] T010 [US1] Built `nearby_levels_csv` using `array.new<string>` + push + `array.join(",")` — 11 potential levels (8 MAs + PDH + PDL + MTD AVWAP), each as `kind|value|label`. Pipe avoids the JSON-in-string escaping problem.
- [X] T011 [US1] Extended `build_v3_payload()` in `ma_ema_daily.pine` — appended `uptrend_pass`, `overhead_mas`, `nearby_levels`, `mtd_avwap` as string fields (function reads outer-scope vars, no signature change needed).
- [X] T012 [US1] Gated `any_long`, `any_prox_long`, `fire_pullback` fires on `uptrend_pass` in `ma_ema_daily.pine`. SHORT fires NOT gated (out of spec-58 scope; shorts require MAs overhead by definition).
- [X] T013 [US1] Backend uptrend-gate enforcement added to `trade-analytics/api/app/routers/tv_webhook.py` after the `_is_allowed_alert_type` check — rejects with `suppressed_reason='uptrend_gate_failed'` via `_persist_unrouted()` (extended with new optional `suppressed_reason` arg). Backward-compat: legacy Pine sending no `uptrend_pass` is treated as None → let through.
- [X] T014 [US1] Confluence annotation invocation added in `tv_webhook.py` right after the gap-context formatting block — calls `find_confluences(sig.entry, sig.nearby_levels)` → `format_confluence_annotation()` → appends `"\nConfluence: ..."` to `sig.message`. Single alert preserved.
- [X] T015 [P] [US1] 10 adapter-payload unit tests in `tests/test_tv_webhook_confluence.py` cover: uptrend_pass true/false/missing, overhead_mas CSV parsing, nearby_levels pipe-CSV parsing (incl. malformed-entry skipping + native-list compat), mtd_avwap parsing. **Total 26 spec-58 tests + 90 existing webhook tests = 116/116 passing, zero regressions.**
- [ ] T016 [US1] Smoke test #1 from `quickstart.md` — open TradingView SPY/META daily chart, wait for an MA bounce on META, verify NO Telegram alert and a DB row with `suppressed_reason='uptrend_gate_failed'`. Query: `SELECT created_at,symbol,suppressed_reason FROM alerts WHERE symbol='META' AND created_at >= now() - interval '1 day';` **DEFERRED — requires market hours and a live MA bounce on a META-like (overhead-MA) stock.**
- [ ] T017 [US1] Smoke test #2 from `quickstart.md` — on a clean-uptrend stock (AAOI/AVGO equivalent) with a confluent bounce, verify exactly one Telegram alert fires and its message body contains a `Confluence:` line listing the other clustered levels by label and price. **DEFERRED — requires market hours and a live confluent bounce.**

**Checkpoint**: US1 is fully functional and independently testable. **This alone is the MVP** — ship it, validate for a few days, decide whether to proceed to US2.

---

## Phase 4: User Story 2 — Buy 2 prior-high held + chop gate (Priority: P2)

**Goal**: Catch the entries Buy 1 structurally misses — a stock above all MAs (no MA to pull back to) pulls back to a *reclaimed prior high* (PDH/PWH/PMH it is above) and holds it. The higher-high chop gate suppresses these once the trend stalls.

**Independent Test**: A clean-uptrend stock making new session highs pulls back to a PDH it's above → one `tv_staged_pdh_held` alert fires. Same stock 30+ min after the last new high → no further Buy-2 alerts. See `quickstart.md` smoke tests #4 + #5.

### Implementation for User Story 2

- [X] T018 [US2] Added `tv_staged_pdh_held`, `tv_staged_pwh_held`, `tv_staged_pmh_held` to `_BASE_CATALOG` in `trade-analytics/api/app/models/alert_type_config.py` (default_enabled=False). Also added `SPEC_58_RETIRED_ENTRY_TYPES` tuple referenced by the startup migration.
- [X] T019 [US2] Added `s58_pdh_held` / `s58_pwh_held` / `s58_pmh_held` detection in `levels_day_vwap.pine` — `close[1] > level and low <= level and close >= level`. Named with `s58_` prefix to avoid collision with the existing `pwh_held_fired` HTF logic.
- [X] T020 [US2] Added `session_high_58` + `last_new_high_time_58` chop-gate state in `levels_day_vwap.pine` after the session-open block — `chop_gate_pass_58 = (time - last_new_high_time_58) <= 30 * 60 * 1000`.
- [X] T021 [US2] Added three new `alert()` blocks for `staged_pdh_held` / `staged_pwh_held` / `staged_pmh_held` in `levels_day_vwap.pine`, each gated on `(held and uptrend_pass_58 and chop_gate_pass_58)`. Entry = the held level, stop = day low − ATR buffer, targets stack to next higher level.
- [X] T022 [US2] Disabled LONG `pdh_break` alert in `levels_day_vwap.pine` via `if false and pdh_break` neutralization (kept block for easy revert). SHORT-side `pdh_rejection` block unchanged (out of spec-58 scope). Same retirement happens at the DB level for `tv_staged_pwh_break` / `tv_staged_pmh_break` via the migration.
- [ ] T023 [US2] Smoke test #4 from `quickstart.md` — find a stock where intraday price climbs into PDH from below, verify NO long alert fires. Verify that AFTER price closes above PDH, retraces, and bounces from above, the new `tv_staged_pdh_held` DOES fire (the correct Buy 2 pattern). **DEFERRED — requires market hours.**
- [ ] T024 [US2] Smoke test #5 from `quickstart.md` — find a stock that runs strong in the morning then chops sideways 30+ min, verify NO further Buy-2 alerts fire during the chop. Verify Buy-2 resumes if a new session high prints. **DEFERRED — requires market hours.**

**Checkpoint**: US1 + US2 deliver the full Buy framework (MA bounce + prior-high held + chop filter). Validate before US3.

---

## Phase 5: User Story 3 — Catalog cleanup + open-line retirement (Priority: P3)

**Goal**: Cut the routed entry-rule count to ≤ 6 by retiring open-line and breakout entries. The open-line plot stays as a visual reference; just the `alertcondition()` triggers are removed.

**Independent Test**: Settings UI shows ≤ 6 enabled entry types. On a chop day no open-line alerts fire. See `quickstart.md` smoke test #3.

### Implementation for User Story 3

- [X] T025 [US3] Set Pine input defaults for `fire_open_held` / `fire_open_wick_reclaim` / `fire_open_reclaimed` / `fire_open_lost` to **false** in `levels_day_vwap.pine` (was true). Labels updated to "(retired — spec 58)". Open-line `plot()` calls untouched — visual reference preserved.
- [X] T026 [US3] Updated `_BASE_CATALOG` defaults to `False` for all retired types AND labels appended with "(retired — spec 58 [FR-N])". Affected: open_reclaimed/held/wick_reclaim/lost, staged_pdh/pwh/pmh_break, pullback_long.
- [X] T027 [US3] Added idempotent `UPDATE alert_type_config SET enabled = false WHERE alert_type = ANY(:types)` migration to `api/app/main.py` startup, sourcing types from `SPEC_58_RETIRED_ENTRY_TYPES` (open-line × 4 + breakout × 3 + pullback_long + proximity × 6 + htf_support_held = 15 total).
- [ ] T028 [US3] Smoke test #3 from `quickstart.md` — on a chop day, watch price cross the open line multiple times. Verify zero `tv_open_*` alerts fire and the open line is still drawn on the chart. DB check: `SELECT count(*) FROM alerts WHERE alert_type LIKE 'tv_open_%' AND created_at >= now() - interval '1 day';` should be zero. **DEFERRED — requires market hours.**
- [ ] T029 [US3] Verify entry-rule count is ≤ 6 — open the web Settings page → Alert Types section, count enabled entry families. Expected: 4 (MA bounce / Prior-high held / Prior-low reclaim / HTF support held — wait, htf_support_held also retired in spec 58, so it's 3: MA bounce + 3 new staged_*_held + pdl/pwl/pml_reclaim families = ≤ 6 ✓). **DEFERRED — requires deploy + Settings UI access.**

**Checkpoint**: All three user stories complete. Spec 58 is functionally done — validation week begins.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Quality gates, deployment, validation period.

- [X] T030 Full pytest run: **1612 passed (+41 from 1571 baseline; 26 confluence/adapter + 15 gate-refinement), 55 failed (all pre-existing, unrelated to spec 58), 4 errors (premarket pre-existing), 7 skipped.** Zero regressions from spec-58 changes.

### Post-implementation refinement (2026-05-23)

User observation (SWMR / PLTR charts): original FR-003 was too broad — it blocked **all** entries on downtrend stocks, filtering out valid level plays. Refined to:

- **FR-003**: scope uptrend gate to MA-based entries only. Level-based entries (PDH/PDL/PWH/PWL/PMH/PML reclaim or hold) fire regardless of MA stack — overhead MAs become targets / resistance, not entry blockers.
- **FR-004**: drop the "strong uptrend" precondition from Buy-2 — the held-from-above pattern itself is the precondition.
- **FR-006**: chop gate applies only in uptrend context — in downtrend regimes, Buy-2 are reversal plays, not continuation.

Implementation: extracted `is_uptrend_gate_rejected()` predicate to `tv_webhook.py` (testable). Pine `levels_day_vwap.pine` `staged_*_held` blocks changed from `(uptrend_pass_58 and chop_gate_pass_58)` to `(not uptrend_pass_58 or chop_gate_pass_58)`. spec.md FR-003/004/006 + spec.html updated. 15 new gate-refinement unit tests cover MA-gated/level-passes/legacy-compat/direction-edge cases.
- [ ] T031 [P] (Optional) Surface `overhead_mas` in the web scorecard — `trade-analytics/web/src/pages/TradingPageV2.tsx` badge. **DEFERRED — UX nice-to-have, not blocking.**
- [ ] T032 Deploy to Railway — push the branch, monitor deploy logs for the migration message ("Spec 58 — retired N entry alert type(s)"), restart the worker. Update the Pine scripts in TradingView Pine Editor and re-add to chart. **PENDING USER — operational step.**
- [ ] T033 One-week validation per `quickstart.md` — daily ✓/✗ marks + EOD SC checks (SC-001 through SC-006). **PENDING — runs across the next 5 trading days starting Monday.**

---

## Phase 7 (Deferred): Python swing-scanner retirement

Not part of spec 58 — explicitly deferred until after Phase 6 validation passes (see `quickstart.md` "When to declare victory"). When ready, the cleanup is:

- Delete `trade-analytics/analytics/swing_scanner.py` + `trade-analytics/analytics/swing_quality.py`
- Remove `_swing_scan` job and its `add_job` from `trade-analytics/api/app/main.py`
- Delete the 9 `swing_*` types from `_SWING_CATALOG` in `trade-analytics/api/app/models/alert_type_config.py`
- Delete `trade-analytics/api/app/routers/swing.py` + `trade-analytics/api/app/schemas/swing.py`
- Delete or repurpose `trade-analytics/web/src/pages/SwingTradesPage.tsx`
- Add a header note to `trade-analytics/specs/56-swing-trade-criteria/spec.md`: **"Superseded by spec 58 — swing entries handled by the unified Pine-based MA-bounce framework. Original Python implementation retired YYYY-MM-DD."**

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** — no dependencies; can run first
- **Foundational (Phase 2)** — depends on Phase 1; **BLOCKS** all user stories (defines the payload schema + helpers everyone uses)
- **US1 (Phase 3)** — depends on Phase 2 complete
- **US2 (Phase 4)** — depends on Phase 2 complete; recommended to ship US1 first and validate before starting US2, but technically independent
- **US3 (Phase 5)** — depends on Phase 2 complete; technically independent of US1/US2 but logically follows them (cleanup after replacements exist)
- **Polish (Phase 6)** — depends on all desired user stories being complete

### User-Story Dependencies (logical)

- **US1 (P1)** — independent, MVP
- **US2 (P2)** — independent of US1 but logically extends it (Buy 2 complements Buy 1)
- **US3 (P3)** — should NOT ship until US1 + US2 are live, because retiring the old types without their replacement leaves the user temporarily with fewer alerts

### Within Each User Story

- Pine changes (model the data) before backend changes (consume the data) — except where the file is the same
- Pine file edits are sequential within the same file (single-file = sequential per `[P]` rules)
- Unit tests `[P]` can run alongside the implementation tasks they cover

---

## Parallel Opportunities

```text
Phase 2 (Foundational) — these are parallelizable:
  T005 [P]  find_confluences unit test
  T006 [P]  format_confluence_annotation unit test
  (both touch tests/test_tv_webhook_confluence.py — actually sequential at file level;
   the [P] reflects logical independence — coordinate file edits)

Phase 3 (US1):
  T015 [P]  unit test for uptrend-gate enforcement (different test in the same file)
  T016, T017  smoke tests can run concurrently (different symbols, different bars)

Phase 6 (Polish):
  T030 + T031 — different files, parallelizable
```

**Note**: All Pine edits within a single `.pine` file are sequential (Pine Editor's single-source-file model). Backend `tv_webhook.py` edits are sequential too. The `[P]` markers reflect "no semantic dependency" — coordinate file-level conflicts manually.

---

## Implementation Strategy

### MVP First (US1 only)

1. Complete Phase 1 (Setup)
2. Complete Phase 2 (Foundational — contract + helpers)
3. Complete Phase 3 (US1 — uptrend gate + confluence annotation)
4. **STOP and VALIDATE** — run smoke tests #1 and #2 from `quickstart.md`
5. Ship to Railway, watch live alerts for 2-3 days
6. If green: proceed to US2; if issues: iterate on confluence band % / overhead-MA logic before going further

### Incremental Delivery (recommended)

```
Phase 1 + 2          → Foundation ready             (1 work session)
+ Phase 3 (US1)      → MVP shipped                  (1 work session)
+ Phase 4 (US2)      → Buy 2 framework complete     (1 work session)
+ Phase 5 (US3)      → Catalog cleanup, ≤ 6 rules   (½ work session)
+ Phase 6            → Validation week + scorecard   (1 calendar week, passive)
```

Each phase ends in a working, shippable state. Roll back any phase independently via Railway redeploy + Pine version history.

### Estimated effort

| Phase | Type | Estimate |
|-------|------|----------|
| 1 Setup | Boilerplate | 15 min |
| 2 Foundational | Backend + tests | 1-2 hr |
| 3 US1 | Pine + backend + smoke | 2-3 hr |
| 4 US2 | Pine + backend + smoke | 2-3 hr |
| 5 US3 | Pine + DB migration | 1 hr |
| 6 Polish + validation | Active code + 1 week passive | 30 min + week |

**Total active work**: ~7-10 hours across 3-4 sessions. **Calendar time to validated victory**: ~10-12 days (active work + validation week).

---

## Notes

- **No new dependencies** — all changes in existing files. No new pip packages, no new Pine libraries.
- **No Anthropic spend** — entire spec is deterministic logic.
- **Single-user scope preserved** — `SCAN_USER_EMAIL=vbolofinde@gmail.com` continues to gate all routing.
- **Backward-compatible payload** — Phase A (Pine) can ship first; Phase B (backend) ignores new fields harmlessly until deployed. Two-phase rollout = minimal blast radius.
- **Rollback** — per `quickstart.md`, Pine Editor version history + Railway previous-deploy revert. Both halves restore baseline within one bar cycle.
- **Commit cadence**: commit after each completed task or each phase, your call. Group commits per phase keeps history readable.
- **Stop and validate** at any checkpoint — every phase ends in a working state.
