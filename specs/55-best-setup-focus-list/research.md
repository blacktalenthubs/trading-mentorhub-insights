# Phase 0 Research: Persisted Daily Focus List

This feature has no unresolved `NEEDS CLARIFICATION` markers — the spec's two genuine ambiguities were closed in the 2026-05-20 clarification session and the remaining defaults are documented Assumptions. Phase 0 therefore records the design decisions that shape Phase 1, each grounded in the existing codebase.

## Existing system facts (verified)

- **Generation endpoint**: `GET /api/v1/ai/best-setups` — `api/app/routers/ai_coach.py:56-115`. Tier-gated, daily-limited, returns `{generated_at, watchlist_size, day_trade_picks[], swing_trade_picks[], skipped[], error}`. Not persisted.
- **Engine**: `analytics/ai_best_setups.py` — `generate_best_setups()` (`:416-523`). Calls Claude Sonnet (`_call_sonnet()` `:316-335`, max 2500 tokens, ~$0.0003–$0.002/call). Already returns day-trade and swing picks as **separate arrays** — classification exists.
- **`EntryCandidate`** (`ai_best_setups.py:39-52`): `symbol, timeframe, direction, setup_type, entry, stop, t1, t2, conviction, confluence[], why_now, current_price, distance_to_entry_pct`.
- **Persistence**: async SQLAlchemy; `Base` + `async_session_factory` + `get_db()` in `api/app/database.py:41-49`. No Alembic — tables auto-create on startup; new models are registered by importing them in `api/app/models/__init__.py`.
- **Auth**: `get_current_user()` — `api/app/dependencies.py:30-54`. JWT Bearer; `User.id` is `int`.
- **Quota**: per-tier `best_setups_per_day` in `api/app/tier.py:28-110` (Free 1, Comp 1, Pro 20, Premium unlimited). Tracked in `UsageLimit` (`api/app/models/usage.py:11-21`, table `usage_limits`, unique `(user_id, feature, usage_date)`). Incremented after a run in `ai_coach.py`.
- **Frontend**: React Router v6; pages are `web/src/pages/*Page.tsx`; protected routes under `AppLayout` with sidebar nav. Current best-setups UI is `web/src/components/BestSetupsCard.tsx` (side panel in `AICoachPage` + Dashboard). API client `web/src/api/client.ts`; React Query hooks `web/src/api/hooks.ts` (`useBestSetups`, `usePinBestSetupAlert`).

## Decision 1: Persistence shape — single table with inline JSON

- **Decision**: One new `focus_lists` table. Each row is a complete scan snapshot; the ranked recommendations live in a JSON column on that row, not a child table.
- **Rationale**: A focus list is an immutable snapshot (Assumption: snapshot at generation time, no live re-evaluation). Recommendations are always read as a set with their parent list — no requirement queries individual recommendations across lists (alert-filtering integration is explicitly out of scope). Inline JSON mirrors the engine's existing JSON output exactly, makes the snapshot atomic, and makes 30-day pruning a single `DELETE`. No join, no second migration.
- **Alternatives considered**: A child `focus_list_recommendations` table — rejected as premature normalization (YAGNI); it buys cross-list querying the spec does not ask for and adds a join + ordering column to every read. Revisit only if a future feature needs per-recommendation queries.

## Decision 2: Endpoint split — run-and-persist vs read

- **Decision**: Introduce a dedicated router `routers/focus_list.py` with four endpoints. `POST /ai/focus-lists/run` performs the scan, persists a `FocusList`, and consumes quota. `GET /ai/focus-lists/latest`, `GET /ai/focus-lists`, and `GET /ai/focus-lists/{id}` are pure reads — no AI, no quota.
- **Rationale**: The current `GET /ai/best-setups` both mutates (quota) and has a 15-min cache, which makes "persist every scan" ambiguous (a cache hit is not a new scan). A `POST` for the side-effecting run cleanly separates "spend an AI run" from "read a saved list" and satisfies FR-002/FR-007/FR-013 (reads never trigger AI). The existing `generate_best_setups()` engine is called by the new run endpoint.
- **Alternatives considered**: Making the existing GET persist on cache-miss — rejected; conflates caching with persistence and keeps a side-effecting GET. A manual "Save" button — rejected; FR-001 requires *every* completed scan saved automatically.

## Decision 3: Market-window classification

- **Decision**: At run time the service computes `market_window` from the server clock converted to US/Eastern: `pre_open` before 09:30 ET, `pre_close` within 15:00–16:00 ET, `other` otherwise. Stored on the row (FR-003). `session_date` is the target trading session (today's ET date pre-close/intraday; next trading day for a pre-open run is also today's session — store the ET calendar date of the run, the page derives "current vs stale").
- **Rationale**: Deterministic, no scheduler, no user input. The window only sets the page's default emphasis (FR-015) — exact boundaries are a documented tuning detail.
- **Alternatives considered**: Asking the user which window — rejected as friction; the clock is authoritative. Auto-scheduling runs — out of scope (Assumption: runs are manual).

## Decision 4: Failure isolation and explicit non-happy states

- **Decision**: Three persisted statuses — `has_setups`, `no_setups`, `failed`. A scan that completes with zero qualifying setups or an empty watchlist is saved as `no_setups` with an explanatory message (FR-012). A scan that errors/times out is saved as a `failed` row **and does not consume quota**. The "current focus list" (`/latest`) returns the most recent row with status `has_setups` or `no_setups` — a `failed` row never becomes the active list, so a failed run never destroys the prior good list (FR-011, SC-006). `failed` rows still appear in history with a failure badge.
- **Rationale**: Satisfies FR-011/FR-012/SC-006 and the edge cases without special-casing reads. Not charging quota for failures is fair and matches the spirit of the cadence cap.
- **Alternatives considered**: Not recording failures at all — rejected; the edge case calls for a visible failure state. Overwriting a single "current" row — rejected; it cannot preserve the prior list on failure.

## Decision 5: Quota + twice-daily cadence

- **Decision**: Reuse `usage_limits` with feature key `best_setups` as the **hard cap** (existing per-tier limit, unchanged). Add a **soft cadence nudge**: the run response includes `runs_today` and `cadence_exceeded` (true when `runs_today >= 2`). The frontend shows a confirmation dialog before a 3rd+ run, explaining prior lists are saved (US3 scenario 3, FR-010). Reads are never quota-gated, so all saved lists stay viewable when the cap is hit (FR-010 second clause).
- **Rationale**: No new table or concept — extends the existing quota mechanism. Hard cap and soft nudge are independent, so Free tier (cap 1) and Premium (unlimited) both behave sensibly.
- **Alternatives considered**: A new dedicated cadence counter — rejected; `usage_limits` already tracks per-user/feature/day counts.

## Decision 6: Surfacing qualifying criteria (FR-014)

- **Decision**: No new LLM work. Each persisted recommendation maps from the existing `EntryCandidate`: `qualifying_criteria` is assembled from fields the engine already returns — entry trigger = `setup_type`, conviction drivers = `confluence[]`, plus `conviction` and the day/swing horizon. `trade_horizon` is set from which engine array the pick came from (`day_trade_picks` → `day_trade`, `swing_trade_picks` → `swing`).
- **Rationale**: Matches clarification Q1 — scoring stays in the engine; this feature only makes the criteria *visible* per recommendation. Zero added AI cost.
- **Alternatives considered**: A second AI call to explain each pick — rejected; redundant and adds cost. Redefining the criteria here — rejected; explicitly out of scope per Q1.

## Decision 7: History retention — prune on write

- **Decision**: When a new `FocusList` is inserted, delete that user's focus lists older than 30 days in the same transaction.
- **Rationale**: Satisfies SC-005 (≥30 days retrievable) and the Assumption that older lists may be pruned, with no scheduler or cron.
- **Alternatives considered**: A scheduled cleanup job — rejected; unnecessary infrastructure for a low-volume per-user table.

## Decision 8: Frontend integration

- **Decision**: New `/focus-list` route + sidebar entry + `FocusListPage`. New hooks `useRunFocusList`, `useLatestFocusList`, `useFocusListHistory`, `useFocusListDetail`. `BestSetupsCard` is repointed to `useLatestFocusList` (persisted data, no AI on view) and gains an "Open focus list" link; the page becomes the primary planning surface.
- **Rationale**: Follows the existing page/route/hook conventions; keeps the dashboard card useful as a glanceable preview while moving deep review to the dedicated page (US2).
- **Alternatives considered**: Deleting `BestSetupsCard` — rejected; the dashboard glance is still valuable and the spec only asks to *add* a dedicated page.
