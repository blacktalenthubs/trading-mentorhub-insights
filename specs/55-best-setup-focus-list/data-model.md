# Phase 1 Data Model: Persisted Daily Focus List

One new table, `focus_lists`. The spec's two entities map as: **Focus List** = one table row; **Setup Recommendation** = one object in that row's inline `recommendations` JSON array. `Watchlist` and `Scan Run Quota` are existing entities — referenced, not redefined.

## Entity: FocusList → table `focus_lists`

A saved snapshot of one AI Best Setups scan, owned by one user.

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK, autoincrement | |
| `user_id` | int, FK → `users.id`, NOT NULL, indexed | Per-user isolation (Assumption: per-user persistence). |
| `generated_at` | datetime (UTC), NOT NULL | When the scan completed. Drives the "generated at" timestamp (US1). |
| `session_date` | date, NOT NULL, indexed | ET calendar date of the run; the page derives current-vs-stale by comparing to today's ET session date (FR-009). |
| `market_window` | string, NOT NULL | One of `pre_open`, `pre_close`, `other` (FR-003). Sets page default emphasis (FR-015). |
| `status` | string, NOT NULL | One of `has_setups`, `no_setups`, `failed` (FR-012, FR-011). |
| `watchlist_size` | int, NOT NULL, default 0 | Symbols analyzed; 0 for empty-watchlist case. |
| `recommendations` | JSON, NOT NULL, default `[]` | Ordered array of Setup Recommendation objects (below). Empty when status ≠ `has_setups`. |
| `skipped` | JSON, NOT NULL, default `[]` | Array of `{symbol, reason}` from the engine. |
| `message` | string, nullable | Human-readable explanation for `no_setups` (e.g. "no setups found", "add symbols to your watchlist") or `failed`. |
| `created_at` | datetime (UTC), NOT NULL, default now | Row insert time. |

**Indexes**: `(user_id, generated_at desc)` for `/latest` and history reads; `user_id` FK index.

**Ownership / access**: every query is filtered by `user_id` from `get_current_user()`. A user can only read their own focus lists.

### Lifecycle / state

`focus_lists` rows are **immutable** once written — a focus list is a snapshot at generation time (Assumption: no live re-evaluation). There are no updates. `status` is set at insert and never changes.

- `has_setups` — scan completed, ≥1 qualifying recommendation.
- `no_setups` — scan completed, zero qualifying recommendations, OR watchlist empty. `recommendations` is `[]`, `message` explains.
- `failed` — scan errored or timed out. `recommendations` is `[]`, `message` carries the error. **Does not consume quota.**

The "current focus list" (`/latest`) is the most recent row with status in (`has_setups`, `no_setups`). A `failed` row is visible in history but is never the current list — so a failed run never destroys the prior good list (FR-011, SC-006).

### Retention

On each insert, the service deletes the owning user's `focus_lists` rows with `generated_at` older than 30 days (prune-on-write). Guarantees ≥30 days retrievable (SC-005).

## Sub-structure: Setup Recommendation (inline JSON object in `recommendations[]`)

A single ranked candidate. Derived from the engine's `EntryCandidate` (`analytics/ai_best_setups.py:39-52`) — no new AI work; new fields are mapped/assembled from existing engine output.

| Field | Type | Source / Notes |
|---|---|---|
| `symbol` | string | `EntryCandidate.symbol` |
| `setup_type` | string | `EntryCandidate.setup_type` — e.g. "VWAP bounce", "PDL bounce" |
| `direction` | string | `EntryCandidate.direction` — `LONG` / `SHORT` |
| `trade_horizon` | string | `day_trade` / `swing` — set from which engine array the pick came (FR-008) |
| `conviction` | string | `EntryCandidate.conviction` — `HIGH` / `MEDIUM` / `LOW` |
| `entry` | number | `EntryCandidate.entry` |
| `stop` | number | `EntryCandidate.stop` |
| `t1` | number | `EntryCandidate.t1` |
| `t2` | number | `EntryCandidate.t2` |
| `current_price` | number | `EntryCandidate.current_price` |
| `distance_to_entry_pct` | number | `EntryCandidate.distance_to_entry_pct` |
| `confluence` | string[] | `EntryCandidate.confluence` — supporting levels |
| `why_now` | string | `EntryCandidate.why_now` — the AI's plain-language reasoning (FR-006) |
| `qualifying_criteria` | object | Assembled (FR-014): `{ entry_trigger: setup_type, conviction_drivers: confluence[], horizon_fit: trade_horizon }` — surfaces why the engine ranked it a "best setup" |

**Ordering**: the array preserves the engine's rank order (conviction HIGH → MEDIUM → LOW). The page renders day-trade-tagged and swing-tagged recommendations grouped by `trade_horizon`.

**Validation**: `trade_horizon ∈ {day_trade, swing}`; `direction ∈ {LONG, SHORT}`; `conviction ∈ {HIGH, MEDIUM, LOW}`. These hold by construction from the engine output; the mapping layer asserts them.

## Referenced existing entities (not modified)

- **Watchlist** — `watchlist_groups` / `watchlist_items` (`api/app/models/watchlist.py`). The scan's input symbol set. Read-only here.
- **Scan Run Quota** — `usage_limits` (`api/app/models/usage.py`), feature key `best_setups`, unique `(user_id, feature, usage_date)`. The hard per-tier cap. A successful or `no_setups` run increments it; a `failed` run does not. The soft twice-daily cadence nudge reads the same row's `usage_count` as `runs_today`.
