# Quickstart: Persisted Daily Focus List

Local setup and end-to-end manual verification for the Focus List feature. Steps map to the spec's acceptance scenarios and Success Criteria.

## Prerequisites

- `trade-analytics/` repo checked out on branch `55-best-setup-focus-list`.
- Python 3.11 env for the API; Node for the web client.
- `ANTHROPIC_API_KEY` set (the scan calls Claude Sonnet).
- A test user account with ≥1 symbol in their watchlist.

## Run locally

```bash
# Backend (FastAPI) — from trade-analytics/api/
uvicorn app.main:app --reload --port 8000

# Frontend (Vite) — from trade-analytics/web/
npm install && npm run dev   # serves on :5173
```

No `DATABASE_URL` locally → SQLite at the project default; the new `focus_lists` table auto-creates on startup (it is imported in `api/app/models/__init__.py`). With `DATABASE_URL` set, it auto-creates in Postgres the same way.

> Per `trade-analytics/CLAUDE.md`: kill any stray local API/worker processes before testing against production Telegram. This feature sends no Telegram messages, but keep the rule in mind.

## Verify the table exists

After API startup, confirm `focus_lists` is present (SQLite: `.tables`; Postgres: `\dt`). Expect columns: `id, user_id, generated_at, session_date, market_window, status, watchlist_size, recommendations, skipped, message, created_at`.

## End-to-end checks

Run these in a browser at `http://localhost:5173`, logged in as the test user.

### US1 — Persistence survives refresh

1. Open **Focus List** in the sidebar → run a scan (`POST /ai/focus-lists/run`).
2. Note the recommendations and the "generated at" timestamp.
3. **Refresh the page.** → The identical list renders from `GET /ai/focus-lists/latest`; no AI run consumed (SC-001, SC-002). *(US1 scenario 1)*
4. Close the tab, reopen the app → the same list is still there, marked with its window/date. *(US1 scenario 2)*

### US2 — Dedicated page

5. The Focus List page shows recommendations as the primary content — each with symbol, setup type, direction, conviction, entry/stop/T1/T2, reasoning, and `qualifying_criteria`. *(US2 scenario 1, FR-006, FR-014)*
6. Expand a recommendation and open its chart → no AI run triggered. *(US2 scenario 2, FR-007)*
7. As a brand-new user (no scans), open the page → first-run guidance shown (`/latest` returns `204`). *(US2 scenario 3)*

### US3 — Twice-daily cadence + emphasis

8. Run a scan before 09:30 ET → saved as `market_window: pre_open`; page emphasizes day-trade-tagged recommendations (swing still visible). *(US3 scenario 1, FR-015)*
9. Run a scan within 15:00–16:00 ET → saved as `pre_close`; page emphasizes swing-tagged recommendations. *(US3 scenario 2)*
10. Attempt a 3rd run the same day → response has `cadence_exceeded: true`; the UI shows a confirmation explaining prior lists are saved. *(US3 scenario 3, FR-010)*
11. Open history → both the pre-open and pre-close runs are listed and distinguishable by window. *(US3 scenario 4, SC-007)*

### Edge cases

12. Empty the watchlist, run a scan → `status: no_setups`, message "Add symbols to your watchlist" — not a blank panel. *(FR-012)*
13. Simulate an engine failure (e.g. unset `ANTHROPIC_API_KEY` and run) → `status: failed`; `GET /latest` still returns the last good list; quota not consumed. *(FR-011, SC-006)*
14. View yesterday's list today → shown with a clear "previous session" marker (`is_stale: true`). *(FR-009)*

## Automated tests

```bash
# from trade-analytics/
python3 -m pytest tests/test_focus_list.py -v
```

Covers the contract-test checklist in `contracts/focus-list-api.md`: persistence, refresh-survival, failure isolation, empty/zero-setups states, window labelling, quota hard cap, and the cadence nudge.

## Done when

- All 14 manual checks pass and `test_focus_list.py` is green.
- A focus list survives refresh 100% of the time (SC-001).
- A failed/empty scan never replaces a prior good list (SC-006).
