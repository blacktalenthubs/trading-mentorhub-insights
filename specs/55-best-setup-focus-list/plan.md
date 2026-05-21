# Implementation Plan: Persisted Daily Focus List from AI Best Setups

**Branch**: `55-best-setup-focus-list` | **Date**: 2026-05-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `trade-analytics/specs/55-best-setup-focus-list/spec.md`

## Summary

Today the AI "Best Setups" scan (`GET /api/v1/ai/best-setups`) generates ranked day-trade and swing candidates but never persists them — the output vanishes on refresh. This feature wraps the existing scan with persistence: every completed scan is saved as a **Focus List** snapshot (one DB row, recommendations stored inline), retrievable without re-invoking the AI. A new dedicated **Focus List page** becomes the primary surface for reviewing saved recommendations, with default emphasis (day-trade vs swing) set by the run's market window. The existing AI engine (`analytics/ai_best_setups.py`) is reused unchanged for generation and classification; this feature adds the persistence table, four read/run endpoints, and the page.

## Technical Context

**Language/Version**: Python 3.11 (FastAPI API in `trade-analytics/api/`), TypeScript + React 18 (web client in `trade-analytics/web/`)
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x (async), asyncpg / aiosqlite, Anthropic SDK; React Router v6, TanStack React Query, Vite
**Storage**: PostgreSQL on Railway (prod) / SQLite via aiosqlite (local) — accessed through async SQLAlchemy `Base` models; tables auto-created on startup (no Alembic)
**Testing**: pytest for the API (`trade-analytics/tests/`); frontend verified manually in-browser (no formal web test harness)
**Target Platform**: Linux server (Railway) + modern web browser
**Project Type**: Web application — FastAPI backend + React frontend
**Performance Goals**: Saved focus list locatable and rendered in < 10s (SC-004); persisted reads consume zero AI calls and no quota
**Constraints**: Reuse the existing AI Best Setups engine unchanged; no new infrastructure or scheduler (runs stay manual); per-user data isolation; ≥30-day history retention
**Scale/Scope**: Single-digit to low-hundreds of users; ~10–30 symbols per scan; ≤2 scans/user/day expected

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution (`.specify/memory/constitution.md`) is an unpopulated template with no project-specific principles defined — there are no formal gates to evaluate. The following baseline engineering principles are applied instead and are satisfied by this design:

- **Reuse over rebuild**: Generation and day/swing classification stay in the existing `ai_best_setups.py` engine; this feature only adds persistence + UI. PASS.
- **No new infrastructure**: Uses the existing async SQLAlchemy stack, the existing `usage_limits` quota table, and the existing auth dependency. One new table, auto-created like all others. PASS.
- **Test coverage for new surface area**: New endpoints and persistence logic get pytest coverage alongside the existing `trade-analytics/tests/` suite. PASS.
- **Business-logic protection** (`trade-analytics/CLAUDE.md`): No protected alert/signal files are modified. The AI engine is consumed, not changed. PASS.

Post-Phase 1 re-check: no violations introduced — design adds one model, one router, four endpoints, one page. PASS.

## Project Structure

### Documentation (this feature)

```text
trade-analytics/specs/55-best-setup-focus-list/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── focus-list-api.md
├── checklists/
│   └── requirements.md  # Existing (from /speckit-specify)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
trade-analytics/
├── api/
│   └── app/
│       ├── models/
│       │   ├── focus_list.py         # NEW — FocusList SQLAlchemy model
│       │   └── __init__.py           # MODIFIED — import FocusList
│       ├── routers/
│       │   ├── focus_list.py         # NEW — run + read endpoints
│       │   └── ai_coach.py           # MODIFIED — existing best-setups route deprecated/kept
│       ├── services/
│       │   └── focus_list_service.py # NEW — persist, window classification, prune, quota
│       └── main.py                   # MODIFIED — register focus_list router
├── analytics/
│   └── ai_best_setups.py             # REUSED unchanged (generation engine)
├── web/
│   └── src/
│       ├── pages/
│       │   └── FocusListPage.tsx      # NEW — dedicated page
│       ├── components/
│       │   ├── FocusListView.tsx      # NEW — list layout + emphasis tabs
│       │   ├── RecommendationCard.tsx # NEW — expandable recommendation detail
│       │   └── BestSetupsCard.tsx     # MODIFIED — sources persisted list, links to page
│       ├── api/
│       │   └── hooks.ts               # MODIFIED — new React Query hooks
│       ├── App.tsx                    # MODIFIED — add /focus-list route
│       └── (AppLayout sidebar)        # MODIFIED — add Focus List nav item
└── tests/
    └── test_focus_list.py             # NEW — endpoint + persistence tests
```

**Structure decision**: Web application. The backend follows the existing `api/app/{models,routers,services}` layout; the frontend follows the existing `web/src/{pages,components,api}` layout and PascalCase `*Page.tsx` naming convention.

## Phase 0: Outline & Research

See [research.md](./research.md). All Technical Context items are resolved — there are no open `NEEDS CLARIFICATION` markers (the two spec ambiguities were closed by the 2026-05-20 clarification session and documented Assumptions). Phase 0 records the key design decisions: single-table inline-JSON persistence, the run-then-persist endpoint split, window classification, failure isolation, quota/cadence handling, criteria surfacing, and 30-day prune-on-write.

## Phase 1: Design & Contracts

- **Data model**: [data-model.md](./data-model.md) — one new `focus_lists` table; `Setup Recommendation` is the inline JSON sub-structure of the `recommendations` column.
- **Contracts**: [contracts/focus-list-api.md](./contracts/focus-list-api.md) — four endpoints: `POST /ai/focus-lists/run`, `GET /ai/focus-lists/latest`, `GET /ai/focus-lists`, `GET /ai/focus-lists/{id}`.
- **Quickstart**: [quickstart.md](./quickstart.md) — local setup + end-to-end manual verification mapped to acceptance scenarios.
- **Agent context**: The plan reference in `CLAUDE.md` is updated to point at this plan.

## Phase 2: Planning Approach

`/speckit-tasks` will decompose this into ordered tasks. Expected task groupings:

1. **Backend persistence**: `FocusList` model + `__init__.py` import + table auto-create verification.
2. **Backend service**: `focus_list_service` — window classification, persist-on-run, failure isolation, 30-day prune, quota integration with `usage_limits`.
3. **Backend endpoints**: the four routes in `routers/focus_list.py`, registered in `main.py`; map `EntryCandidate` → recommendation JSON incl. `trade_horizon` and `qualifying_criteria`.
4. **Backend tests**: `test_focus_list.py` covering persistence, refresh-survival, failure isolation, empty/zero-setups states, window labelling, quota/cadence.
5. **Frontend hooks**: `useRunFocusList`, `useLatestFocusList`, `useFocusListHistory`, `useFocusListDetail`.
6. **Frontend page**: `FocusListPage` + `FocusListView` + `RecommendationCard`; route + sidebar entry; window-based emphasis; history selector.
7. **Frontend integration**: repoint `BestSetupsCard` to the persisted latest list; manual in-browser verification.

## Complexity Tracking

No constitution violations and no unjustified complexity. The design deliberately avoids: a second `recommendations` table (inline JSON is sufficient — recommendations are an immutable snapshot always read as a set), a background scheduler (runs stay manual per Assumptions), and Alembic (the project auto-creates tables on startup).
