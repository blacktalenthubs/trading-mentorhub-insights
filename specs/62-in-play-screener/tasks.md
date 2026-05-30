# Tasks: In-Play Volume Screener

**Spec**: [spec.md](./spec.md)
**Plan**: [plan.md](./plan.md)
**Created**: 2026-05-30

> TDD is mandatory (Constitution §2): write the failing test before the implementation it covers.
> `signal_engine.py` and other protected files are **reused read-only — never modified**.

## Phase 1: Setup
- [X] T001 [P] Add screener default thresholds (market_cap_floor=2e9, price_floor=5, dollar_vol_floor=2e7, top_n=30, refresh_minutes=10) to `api/app/config.py`
- [X] T002 [P] Create test module with fixtures (sample universe DataFrame, mock intraday volume, fake quotes) in `tests/test_screener.py`

## Phase 2: Foundational (blocking — complete before any user story)
- [X] T003 [P] Create SQLAlchemy models `ScreenerUniverse` + `ScreenerSnapshot` (JSON `entries` column) in `api/app/models/screener.py`
- [X] T004 [P] Create Pydantic schemas `Snapshot`, `Entry`, `Settings`, `SettingsUpdate` (match `contracts/openapi.yaml`) in `api/app/schemas/screener.py`
- [X] T005 Register `screener_universe` + `screener_snapshot` in `create_all` and add idempotent `ALTER ... IF NOT EXISTS` migration block in `api/app/main.py` lifespan
- [X] T006 [P] Create `analytics/screener.py` skeleton — signatures + docstrings for `build_universe`, `rank_in_play`, `scan_setups`, `apply_refine_filters`, and `PRESETS`
- [X] T007 Create `api/app/services/screener_service.py` skeleton — orchestration stubs + `is_market_open()` helper (regular US hours)

## Phase 3: User Story 1 — "Where do I look today" in-play list (P1) 🎯 MVP
**Goal**: A Pro+ trader opens Trade Ideas → In Play during market hours and sees ~30 RVOL-ranked, setup-aware names.
**Independent test**: `GET /api/v1/screener/in-play` returns ≤ top_n entries ordered by RVOL with `setup` populated or null; the In-Play view renders them and a row opens the chart.

- [X] T008 [P] [US1] Write failing tests for `build_universe` floor filtering (excludes below cap/price/$-vol; cap change resizes) in `tests/test_screener.py`
- [X] T009 [P] [US1] Write failing tests for `rank_in_play` ordering (RVOL desc, $-vol tiebreaker; high-absolute/normal-RVOL ranks below low-absolute/high-RVOL) in `tests/test_screener.py`
- [X] T010 [P] [US1] Write failing test for market-hours gate (`refresh_in_play` no-ops when closed; snapshot `market_open=false`) in `tests/test_screener.py`
- [X] T011 [US1] Implement `build_universe()` via yfinance `EquityQuery` (cap/price/$-vol) behind a thin field adapter (pin to installed yfinance) in `analytics/screener.py`
- [X] T012 [US1] Implement `rank_in_play()` — Alpaca most-actives ∩ universe + quotes → reuse `analytics/intraday_data.compute_rvol` → sort RVOL desc, $-vol tiebreaker, top-N — in `analytics/screener.py`
- [X] T013 [US1] Implement `scan_setups()` calling `analytics/signal_engine` (read-only) on the shortlist and attaching pattern/entry per symbol in `analytics/screener.py`
- [X] T014 [US1] Implement `refresh_in_play()` (market-hours gate → rank → scan → compose snapshot → persist) and `rebuild_universe()` in `api/app/services/screener_service.py`
- [X] T015 [US1] Register APScheduler ~10-min market-hours refresh job in `api/app/main.py` lifespan
- [X] T016 [US1] Implement `GET /api/v1/screener/in-play` (serve latest snapshot, Pro+ tier gate → 402 for free) in `api/app/routers/screener.py` and mount the router in `api/app/main.py`
- [X] T017 [P] [US1] Add `useInPlay()` TanStack Query hook in `web/src/api/hooks.ts` and `Snapshot`/`Entry` types in `web/src/pages/InPlay.types.ts`
- [X] T018 [P] [US1] Build `InPlayView.tsx` rows (symbol · last price · signed %chg · RVOL chip · $-vol · market cap · setup badge; row → chart) in `web/src/components/InPlayView.tsx`
- [X] T019 [US1] Add `My Ideas | In Play` segmented control to `web/src/pages/FocusListPage.tsx`, wrapping In-Play in `TierGate` (Pro+ with free teaser)
- [X] T020 [US1] Verify US1 E2E per `quickstart.md` (≤30 ranked rows, RVOL chips, setup badges, row→chart, market-hours timestamp advances)

**Checkpoint**: US1 is a shippable MVP on its own.

## Phase 4: User Story 2 — Refine filters & presets (P2)
**Goal**: Trader narrows the shortlist by style preset (default Momentum Long), direction-aware.
**Independent test**: selecting a preset narrows/sorts the list; Short preset surfaces below-50-EMA setups; clearing returns the full energy-ranked shortlist.

- [X] T021 [P] [US2] Write failing tests for `apply_refine_filters` presets + direction-awareness (long preset does not delete short setups) in `tests/test_screener.py`
- [X] T022 [US2] Implement `apply_refine_filters()` + `PRESETS` (Momentum Long / Pullback / Breakout / Short / Any) in `analytics/screener.py`
- [X] T023 [US2] Attach refine inputs (`above_ema50`, `above_vwap`, `rsi`, `rs_vs_spy`, `atr_pct`) + `direction` to each `Entry` in `api/app/services/screener_service.py`
- [X] T024 [US2] Add `preset` / `direction` / `has_setup` query params (server-side filter over ≤N rows) to `GET /api/v1/screener/in-play` in `api/app/routers/screener.py`
- [X] T025 [P] [US2] Add preset selector + "Has setup" toggle to `web/src/components/InPlayView.tsx`
- [X] T026 [US2] Verify US2: preset narrows; Short surfaces short setups; clearing returns full list

## Phase 5: User Story 3 — Thresholds, operations & resilience (P3)
**Goal**: Configurable cap/top-N, on-demand + weekly universe rebuild, and clean market-closed / stale-data states.
**Independent test**: raising the cap floor shrinks the next snapshot; admin rebuild updates `rebuilt_at`; forcing a data failure shows the last snapshot with a stale indicator (no error).

- [X] T027 [P] [US3] Write failing tests for settings bounds + degraded-data fallback (prior snapshot served, `stale=true`) in `tests/test_screener.py`
- [X] T028 [US3] Implement `GET`/`PUT /api/v1/screener/settings` (global defaults + per-user `market_cap_floor`/`top_n` override with bounds) in `api/app/routers/screener.py`
- [X] T029 [US3] Implement `POST /api/v1/screener/universe/rebuild` (admin) + register weekly APScheduler rebuild job in `api/app/services/screener_service.py` and `api/app/main.py`
- [X] T030 [US3] Add degraded-data handling (keep prior snapshot, set `stale=true` on partial failure) in `api/app/services/screener_service.py`
- [X] T031 [P] [US3] Add market-closed + stale indicators and short/empty-list state to `web/src/components/InPlayView.tsx`
- [X] T032 [US3] Add single-instance scheduler guard (DB "last refresh" / advisory lock so multiple replicas don't double-refresh) in `api/app/services/screener_service.py`
- [ ] T033 [US3] Verify US3: cap/top-N change reflects next refresh; admin rebuild updates `rebuilt_at`; closed + stale states render

## Phase 6: Polish & Cross-Cutting
- [X] T034 [P] Add in-memory cache front for the latest snapshot (fast reads) in `api/app/services/screener_service.py`
- [X] T035 [P] Update `specs/62-in-play-screener/quickstart.md` with any field-name/entitlement findings discovered during impl
- [X] T036 Run full suite `python3 -m pytest tests/ -v` and fix any regression (maintain 648+ baseline)
- [X] T037 Local verification on `localhost:5173` + `localhost:8000` per quickstart; kill local processes before any production check

---

## Dependencies (story completion order)

```
Setup (T001–T002)
   └─► Foundational (T003–T007)   ← blocks all stories
          ├─► US1 (T008–T020)  🎯 MVP — independently shippable
          │       └─► US2 (T021–T026)  (filters layer on US1's list)
          │       └─► US3 (T027–T033)  (ops/resilience on US1's pipeline)
          └─► Polish (T034–T037)  ← after the stories you ship
```
- US2 and US3 both depend only on US1 (not on each other) — they can be built in either order or in parallel by two people.

## Parallel execution examples
- **Foundational**: T003, T004, T006 in parallel (different files); T005 after T003/T004; T007 after T006.
- **US1 tests**: T008, T009, T010 in parallel (same test file, distinct functions — coordinate or split).
- **US1 frontend vs backend**: T017 + T018 (frontend) run parallel to T011–T016 (backend); T019 joins them.

## Implementation strategy
- **MVP = US1 only** (T001–T020): the full funnel works end-to-end, Pro-gated, during market hours. Ship it, gather feedback.
- **Increment 2 = US2** (presets) — the "trade it my way" narrowing.
- **Increment 3 = US3** (settings, rebuild, resilience) — operational hardening.
- Polish (T034–T037) before each production push; always run the full suite and verify locally first.

---

**Legend**: `T###` task ID · `[P]` parallelizable · `[US#]` user-story label · file paths are exact.
