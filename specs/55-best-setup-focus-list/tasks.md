---
description: "Task list for Persisted Daily Focus List from AI Best Setups"
---

# Tasks: Persisted Daily Focus List from AI Best Setups

**Input**: Design documents from `trade-analytics/specs/55-best-setup-focus-list/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/focus-list-api.md, quickstart.md

**Tests**: Test tasks ARE included — the `trade-analytics` project mandates `pytest` coverage before any push (`trade-analytics/CLAUDE.md`) and the plan calls for `tests/test_focus_list.py`.

**Organization**: Tasks are grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 / US2 / US3 — maps to the user stories in spec.md
- All paths are relative to repo root (`master-domain-hub/`)

## Path Conventions

Web application. Backend: `trade-analytics/api/app/`. Frontend: `trade-analytics/web/src/`. Tests: `trade-analytics/tests/`. AI engine (reused, not modified): `trade-analytics/analytics/ai_best_setups.py`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Test scaffolding and dependency confirmation. No new packages are required.

- [x] T001 [P] Create test file scaffold `trade-analytics/tests/test_focus_list.py` — imports plus the async test client and authenticated-user fixtures reused from the existing `trade-analytics/tests/` suite
- [x] T002 [P] Confirm no new dependencies are needed — FastAPI, async SQLAlchemy + asyncpg/aiosqlite, Anthropic SDK in `trade-analytics/api/requirements.txt`; React Router v6 + TanStack React Query in `trade-analytics/web/package.json`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The persistence table, the shared service helpers, and the router skeleton that every user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T003 [P] Create the `FocusList` SQLAlchemy model in `trade-analytics/api/app/models/focus_list.py` — table `focus_lists` with columns `id, user_id, generated_at, session_date, market_window, status, watchlist_size, recommendations (JSON), skipped (JSON), message, created_at` and indexes `(user_id, generated_at desc)` and `session_date`, per data-model.md
- [x] T004 Register `FocusList` in `trade-analytics/api/app/models/__init__.py` so the table auto-creates on startup (depends on T003)
- [x] T005 [P] Create `trade-analytics/api/app/services/focus_list_service.py` with two pure helpers: `classify_market_window(dt)` returning `pre_open` / `pre_close` / `other` from a US/Eastern time, and `entry_candidate_to_recommendation(candidate, horizon)` mapping an `EntryCandidate` to a recommendation dict including `trade_horizon` and the assembled `qualifying_criteria` object, per data-model.md
- [x] T006 [P] Create the `focus_list` `APIRouter` in `trade-analytics/api/app/routers/focus_list.py` (prefix `/ai/focus-lists`, `get_current_user` dependency) and register it under `/api/v1` in `trade-analytics/api/app/main.py`

**Checkpoint**: Table exists on startup; service helpers and an empty router are importable.

---

## Phase 3: User Story 1 — Focus list persists and survives refresh (Priority: P1) 🎯 MVP

**Goal**: Every completed scan is saved; the saved list survives refresh, navigation, and a new session, with zero extra AI runs to view it.

**Independent Test**: Run the Best Setups scan, note the recommendations, refresh the page → the identical list is still displayed with a "generated at" timestamp and no AI run was consumed. Reopen the app later → the prior list is still retrievable.

- [x] T007 [US1] Implement `save_focus_list(...)` in `trade-analytics/api/app/services/focus_list_service.py` — persist a `FocusList` row with status `has_setups` or `no_setups`, and prune the owning user's rows older than 30 days in the same transaction (depends on T003, T005)
- [x] T008 [US1] Implement `POST /ai/focus-lists/run` in `trade-analytics/api/app/routers/focus_list.py` — call `generate_best_setups()`, map day/swing picks via `entry_candidate_to_recommendation`, compute `market_window`, persist via `save_focus_list`, increment `usage_limits` (feature `best_setups`) on success/no-setups only; on engine error save a `status=failed` row WITHOUT consuming quota and WITHOUT overwriting the prior list; return `429` when the tier hard cap (`best_setups_per_day`) is reached (depends on T006, T007)
- [x] T009 [US1] Implement `GET /ai/focus-lists/latest` in `trade-analytics/api/app/routers/focus_list.py` — return the user's most recent row with status `has_setups`/`no_setups` plus an `is_stale` flag (true when `session_date` precedes today's ET session); return `204` when none exists (depends on T008)
- [x] T010 [P] [US1] Add `useRunFocusList` (POST `/ai/focus-lists/run`) and `useLatestFocusList` (GET `/ai/focus-lists/latest`) React Query hooks in `trade-analytics/web/src/api/hooks.ts`
- [x] T011 [US1] Repoint `trade-analytics/web/src/components/BestSetupsCard.tsx` to read persisted data via `useLatestFocusList` (no AI run on view) and trigger scans via `useRunFocusList`, so the dashboard card survives refresh (depends on T010)
- [x] T012 [P] [US1] Add tests to `trade-analytics/tests/test_focus_list.py` — persist-on-run, refresh-survival (`/latest` returns the identical recommendations with no quota consumed), failure isolation (a `failed` run preserves the prior good list and consumes no quota), empty-watchlist and zero-setups saved as explicit `no_setups` states, tier hard cap returns `429` with saved lists still readable (depends on T008, T009)

**Checkpoint**: A scan result persists and survives refresh — this is an independently shippable MVP.

---

## Phase 4: User Story 2 — Dedicated focus-list page for review and analysis (Priority: P1)

**Goal**: A dedicated page where the saved focus list is the primary content — each recommendation laid out in full, with history and chart drill-in, and no AI run on view.

**Independent Test**: Navigate to the focus-list page → the most recent saved focus list renders as the main content, each recommendation expandable to full detail, with no AI run triggered by viewing.

- [x] T013 [US2] Implement `GET /ai/focus-lists` in `trade-analytics/api/app/routers/focus_list.py` — paginated history (`limit` default 30 / max 60, `offset`), newest-first, returning metadata + `recommendation_count`, including `failed` rows (depends on T009)
- [x] T014 [US2] Implement `GET /ai/focus-lists/{id}` in `trade-analytics/api/app/routers/focus_list.py` — return one full focus list with all recommendations; `404` when the id does not exist or belongs to another user (depends on T013)
- [x] T015 [P] [US2] Add `useFocusListHistory` (GET `/ai/focus-lists`) and `useFocusListDetail` (GET `/ai/focus-lists/{id}`) React Query hooks in `trade-analytics/web/src/api/hooks.ts`
- [x] T016 [P] [US2] Create `trade-analytics/web/src/components/RecommendationCard.tsx` — an expandable card showing symbol, setup type, direction, conviction tier, entry/stop/T1/T2, distance-to-entry, `confluence`, AI reasoning (`why_now`), and the `qualifying_criteria` block, with a link to open the symbol's chart (FR-006, FR-007, FR-014)
- [x] T017 [US2] Create `trade-analytics/web/src/components/FocusListView.tsx` — renders one `FocusList`: header with generated-at timestamp, market-window label, and current-vs-stale badge; recommendations grouped by `trade_horizon` (day-trade / swing) using `RecommendationCard` (depends on T016)
- [x] T018 [US2] Create `trade-analytics/web/src/pages/FocusListPage.tsx` — main content is the latest list via `FocusListView`; a history selector backed by `useFocusListHistory`/`useFocusListDetail`; first-run guidance when `/latest` returns `204` (depends on T015, T017)
- [x] T019 [US2] Add the `/focus-list` route in `trade-analytics/web/src/App.tsx` and a "Focus List" sidebar nav item in the `AppLayout` component (depends on T018)
- [x] T020 [P] [US2] Add tests to `trade-analytics/tests/test_focus_list.py` — history endpoint newest-first ordering and inclusion of `failed` rows; detail endpoint returns `404` for another user's row; `/latest` returns `204` for a brand-new user (depends on T013, T014)

**Checkpoint**: The dedicated page renders the saved list, history, and per-recommendation detail with no AI runs on view.

---

## Phase 5: User Story 3 — Twice-daily cadence with window-based emphasis (Priority: P2)

**Goal**: Pre-open and pre-close runs are saved and labelled by window; the page emphasizes day-trade vs swing accordingly; a soft nudge discourages unnecessary extra runs.

**Independent Test**: Run a scan in the morning → saved and labelled pre-open, page emphasizes day-trade-tagged setups. Run again near close → saved separately as pre-close, page emphasizes swing-tagged setups. A third run the same day is clearly flagged as beyond the recommended cadence.

- [x] T021 [US3] Extend `POST /ai/focus-lists/run` in `trade-analytics/api/app/routers/focus_list.py` — include `runs_today` and `cadence_exceeded` (true when `runs_today >= 2`) in the response, and honor a `force=true` query param so a run proceeds past the soft nudge (depends on T014)
- [x] T022 [US3] Add window-based emphasis to `trade-analytics/web/src/components/FocusListView.tsx` — default-select the day-trade group for a `pre_open` list and the swing group for a `pre_close` list, with both groups always visible (depends on T017)
- [x] T023 [US3] Add a cadence confirmation dialog before a 3rd+ run in `trade-analytics/web/src/pages/FocusListPage.tsx` and `trade-analytics/web/src/components/BestSetupsCard.tsx`, triggered by `cadence_exceeded`, explaining prior lists are still saved (depends on T021, T018)
- [x] T024 [P] [US3] Add tests to `trade-analytics/tests/test_focus_list.py` — `market_window` labelling for pre-open / pre-close / other run times; `cadence_exceeded` becomes true on the 3rd run; read endpoints are never quota-gated (depends on T021)

**Checkpoint**: Twice-daily cadence labelling, window emphasis, and the soft nudge all work.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T025 Run the full backend test suite from `trade-analytics/` (`python3 -m pytest tests/ -v`) and confirm no regressions against the pre-existing baseline
- [ ] T026 Execute the 14 manual in-browser checks in `trade-analytics/specs/55-best-setup-focus-list/quickstart.md` (US1, US2, US3, and edge cases) and confirm SC-001 / SC-006 hold
- [x] T027 [P] Remove the now-unused `useBestSetups` live-scan hook usage in `trade-analytics/web/src/api/hooks.ts` and deprecate the superseded `GET /api/v1/ai/best-setups` route in `trade-analytics/api/app/routers/ai_coach.py`

---

## Dependencies & Story Completion Order

```
Phase 1 Setup (T001–T002)
        ↓
Phase 2 Foundational (T003–T006)  ← BLOCKS all stories
        ↓
Phase 3 US1 (T007–T012)  ← MVP, independently shippable
        ↓
Phase 4 US2 (T013–T020)  ← depends on US1 run + latest endpoints
        ↓
Phase 5 US3 (T021–T024)  ← depends on US1 run endpoint + US2 FocusListView
        ↓
Phase 6 Polish (T025–T027)
```

- **US1** is the MVP — it delivers the headline value (persistence + refresh-survival) on its own surface (the existing dashboard card).
- **US2** builds on US1's `/run` and `/latest` endpoints and shares the `routers/focus_list.py` file.
- **US3** extends US1's run endpoint and US2's `FocusListView`.

## Parallel Execution Examples

- **Phase 2**: T003, T005, T006 touch three different new files → run in parallel; T004 follows T003.
- **US1**: T010 (frontend hooks) runs in parallel with backend T007–T009; T012 (tests) parallels T011 (frontend).
- **US2**: T015 (hooks) and T016 (`RecommendationCard`) are parallel; T020 (tests) parallels the frontend chain once T013/T014 land.
- **Note**: Endpoint tasks in the same file (`routers/focus_list.py`: T008→T009→T013→T014→T021) are sequential — no `[P]`.

## Implementation Strategy

1. **MVP**: Complete Phase 1 → Phase 2 → Phase 3 (US1). Ship — the output now persists, which is the headline pain.
2. **Increment 2**: Phase 4 (US2) — the dedicated planning page.
3. **Increment 3**: Phase 5 (US3) — cadence labelling and window emphasis.
4. **Close out**: Phase 6 — full test run, manual verification, cleanup.
