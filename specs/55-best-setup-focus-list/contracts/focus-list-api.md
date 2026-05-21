# API Contract: Focus List

All endpoints are mounted under `/api/v1` and require a JWT Bearer token (`get_current_user`). All responses are scoped to the authenticated user. Router: `api/app/routers/focus_list.py`.

Shared JSON shapes:

```jsonc
// Recommendation — one ranked candidate
{
  "symbol": "AAPL",
  "setup_type": "VWAP bounce",
  "direction": "LONG",            // LONG | SHORT
  "trade_horizon": "day_trade",   // day_trade | swing
  "conviction": "HIGH",           // HIGH | MEDIUM | LOW
  "entry": 196.40, "stop": 194.80, "t1": 199.10, "t2": 201.50,
  "current_price": 196.85,
  "distance_to_entry_pct": -0.23,
  "confluence": ["PDL 196.20", "rising 20MA"],
  "why_now": "Holding above prior-day low with VWAP reclaim.",
  "qualifying_criteria": {
    "entry_trigger": "VWAP bounce",
    "conviction_drivers": ["PDL 196.20", "rising 20MA"],
    "horizon_fit": "day_trade"
  }
}

// FocusList — one saved scan snapshot
{
  "id": 412,
  "generated_at": "2026-05-20T13:18:04Z",
  "session_date": "2026-05-20",
  "market_window": "pre_open",    // pre_open | pre_close | other
  "status": "has_setups",         // has_setups | no_setups | failed
  "watchlist_size": 14,
  "recommendations": [ /* Recommendation[] — empty unless status=has_setups */ ],
  "skipped": [ { "symbol": "TSLA", "reason": "no clean level within 2%" } ],
  "message": null                 // string when status=no_setups|failed
}
```

---

## 1. `POST /ai/focus-lists/run`

Runs the AI Best Setups scan, persists the result as a FocusList, returns it. Consumes one AI run + one `usage_limits` (`best_setups`) increment **on success or no-setups only** — a `failed` run consumes neither.

**Request body**: none (the watchlist is the user's saved watchlist).
Optional query: `force=true` to proceed past the soft cadence check.

**Responses**:

- `200 OK` — scan completed (status `has_setups` or `no_setups`). Body: FocusList, plus:
  ```jsonc
  { "...FocusList fields...": "...",
    "cadence_check": false,
    "runs_today": 2,
    "cadence_exceeded": true }   // true when runs_today >= 2
  ```
- `200 OK` with `cadence_check: true` — the user has already run ≥2 scans today and `force` was not set. **No scan runs, no quota consumed, no row saved.** Body: `{ "cadence_check": true, "runs_today": 2, "cadence_exceeded": true, "message": "..." }`. The client shows a confirmation and, if accepted, re-calls with `?force=true`. This pre-check ensures the cadence is never discovered by *spending* an AI run (FR-010, US3 scenario 3).
- `200 OK` with `status: "failed"` — scan errored/timed out. A `failed` FocusList row is saved; quota NOT consumed; the prior good list remains the current list. `message` carries the error.
- `429 Too Many Requests` — tier hard cap (`best_setups_per_day`) reached. Body: `{ "detail": {...limit explanation...} }`. No row saved. All saved lists remain readable via the GET endpoints.
- `401 Unauthorized` — missing/invalid token.

**Notes**: Empty watchlist → `200` with `status: "no_setups"`, `message: "Add symbols to your watchlist..."` (FR-012).

---

## 2. `GET /ai/focus-lists/latest`

Returns the current focus list — the most recent row with status `has_setups` or `no_setups`. No AI run, no quota.

**Responses**:

- `200 OK` — Body: FocusList, plus `is_stale` (boolean — true when `session_date` is before today's ET session, FR-009).
- `204 No Content` — the user has never run a successful scan (FR — page shows first-run guidance, US2 scenario 3).
- `401 Unauthorized`.

---

## 3. `GET /ai/focus-lists`

Returns the browsable history of the user's focus lists (metadata only, newest first). No AI run.

**Query params**: `limit` (default 30, max 60), `offset` (default 0).

**Responses**:

- `200 OK` — Body:
  ```jsonc
  { "items": [
      { "id": 412, "generated_at": "...", "session_date": "2026-05-20",
        "market_window": "pre_open", "status": "has_setups",
        "recommendation_count": 6 }
    ],
    "total": 18 }
  ```
  `failed` rows are included with `recommendation_count: 0` so the history shows the failure (edge case).
- `401 Unauthorized`.

---

## 4. `GET /ai/focus-lists/{id}`

Returns one full focus list by id, including all recommendations. No AI run, no quota (FR-007, FR-013).

**Responses**:

- `200 OK` — Body: FocusList (full, with `recommendations[]`).
- `404 Not Found` — no such id, or the row belongs to another user (do not leak existence).
- `401 Unauthorized`.

---

## Contract test checklist

- `POST /run` on a populated watchlist → `200`, `status=has_setups`, row persisted, quota incremented, `runs_today` reflects the count.
- `POST /run` on an empty watchlist → `200`, `status=no_setups`, explanatory `message`.
- `POST /run` when the engine raises → `200`, `status=failed`, quota NOT incremented, `/latest` still returns the prior good list.
- `POST /run` at tier hard cap → `429`, no row saved, GET endpoints still serve saved lists.
- `POST /run` as the 3rd run of the day → `cadence_check=true`, no row saved, no quota consumed; `POST /run?force=true` then proceeds.
- `GET /latest` after a run → identical recommendations, no quota consumed (refresh-survival, SC-001/SC-002).
- `GET /latest` with only a stale list → `is_stale=true`.
- `GET /latest` for a brand-new user → `204`.
- `GET /focus-lists` → newest-first, includes `failed` rows.
- `GET /focus-lists/{id}` for another user's row → `404`.
