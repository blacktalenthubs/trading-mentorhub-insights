# Implementation Plan: User Alert Preferences (Admin-Only)

**Spec**: [spec.md](spec.md)
**Branch**: 1-user-alert-preferences
**Created**: 2026-04-03

## Technical Context

| Item | Value |
|------|-------|
| Language | Python 3.9+ |
| Framework | Streamlit (dashboard), APScheduler (worker) |
| Database | SQLite (local) / Postgres (production) |
| Notifications | Telegram Bot API |
| Deployment | Railway (worker + Streamlit) |

### Dependencies
- No new dependencies needed.

### Integration Points
- `alert_config.py` — category definitions (code-level mapping)
- `db.py` — new table + CRUD functions
- `monitor.py` — preference gate before `notify()` (protected file)
- `pages/settings.py` — UI for toggles + score slider

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| Protect Business Logic | PASS | Adds preference gate before `notify()` in monitor.py. Alert evaluation/scoring unchanged. Alerts always recorded to DB. |
| Test-Driven Development | PASS | Tests first: category mapping, CRUD, filtering logic, defaults |
| Local First | PASS | SQLite-compatible. Settings page testable on localhost:8501 |
| Database Compatibility | PASS | `?` params, `ON CONFLICT` upsert, `_safe_add_column()` for migration |
| Alert Quality | PASS | Does not change which alerts fire. Only filters Telegram delivery. |
| Single Notification Channel | PASS | Still `notify()` → group chat. Preferences gate what reaches `notify()`. |

## Solution Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│ alert_config │     │    db.py     │     │ pages/settings   │
│              │     │              │     │                  │
│ ALERT_CATS   │────▶│ user_alert   │◀────│ Toggle switches  │
│ (code map)   │     │ _category    │     │ Score slider     │
│              │     │ _prefs table │     │ Save button      │
└──────┬───────┘     └──────┬───────┘     └──────────────────┘
       │                    │
       ▼                    ▼
┌──────────────────────────────────────┐
│           monitor.py                  │
│                                       │
│  signal fires → record_alert (always) │
│    ↓                                  │
│  load admin prefs (once per cycle)    │
│    ↓                                  │
│  _should_notify(signal, prefs)?       │
│    ↓                                  │
│  YES → notify() → Telegram group     │
│  NO  → skip Telegram, update DB      │
└───────────────────────────────────────┘
```

### Data Flow

1. **Code**: `ALERT_CATEGORIES` in alert_config.py maps category_id → set of AlertType values
2. **Settings**: Admin toggles categories, sets min_score → persisted to DB
3. **Poll cycle**: Worker loads admin's category prefs + min_score once at cycle start
4. **Per signal**: `_should_notify()` checks category enabled + score threshold before `notify()`
5. **Fail-open**: Lookup failure → send all alerts

### Files to Modify

| File | Change | Risk |
|------|--------|------|
| `alert_config.py` | Add `ALERT_CATEGORIES`, `ALERT_TYPE_TO_CATEGORY`, `EXIT_ALERT_TYPES` | Low |
| `db.py` | Add `user_alert_category_prefs` table, `min_alert_score` column, CRUD functions | Low |
| `monitor.py` | Add `_should_notify()` gate before `notify()` call | Med (protected) |
| `pages/settings.py` | Add Alert Preferences section with toggles + slider | Low |

### Files to Add

| File | Purpose |
|------|---------|
| `tests/test_alert_preferences.py` | Unit + integration tests |

## Implementation Approach

### Phase 1: Data Layer

1. **`alert_config.py`** — Define `ALERT_CATEGORIES` dict mapping category_id → {name, description, alert_types set}. Build `ALERT_TYPE_TO_CATEGORY` reverse lookup. Define `EXIT_ALERT_TYPES` set.

2. **`db.py`** — Add `user_alert_category_prefs` table in `init_db()`. Add `min_alert_score` column to `user_notification_prefs` via `_safe_add_column()`. Add CRUD:
   - `get_alert_category_prefs(user_id) -> dict[str, bool]`
   - `upsert_alert_category_prefs(user_id, category_id, enabled)`
   - `get_min_alert_score(user_id) -> int`
   - `set_min_alert_score(user_id, score)`

### Phase 2: Notification Gate

3. **`monitor.py`** — Add `_should_notify(signal, category_prefs, min_score)` helper. Load admin prefs once at start of `poll_cycle()`. Gate `notify()` call with preference check. Log when alerts are preference-filtered.

### Phase 3: Settings UI

4. **`pages/settings.py`** — Add "Alert Preferences" expander/section. Render category toggles with descriptions. Render min_score slider. Save button persists all prefs.

### Phase 4: Test & Deploy

5. Run full test suite, test locally, push, restart Railway worker.

## Test Plan

### Unit Tests (`tests/test_alert_preferences.py`)

- [ ] `test_all_alert_types_have_category` — every AlertType in ENABLED_RULES maps to one category
- [ ] `test_no_duplicate_alert_type_mapping` — no alert type in multiple categories
- [ ] `test_default_prefs_all_enabled` — missing prefs default to all enabled
- [ ] `test_should_notify_category_disabled` — returns False when category disabled
- [ ] `test_should_notify_category_enabled` — returns True when category enabled
- [ ] `test_should_notify_exit_bypasses_score` — exit alerts always True
- [ ] `test_should_notify_below_min_score` — returns False when score < min
- [ ] `test_should_notify_zero_min_score` — min_score=0 sends everything
- [ ] `test_upsert_and_get_category_prefs` — DB round-trip
- [ ] `test_min_alert_score_crud` — DB round-trip for score

### E2E Validation

1. **Setup**: Start Streamlit locally, log in as admin
2. **Action**: Settings → disable Breakout Signals, set min_score=55, save
3. **Verify**: Breakout alerts in dashboard but not Telegram. Low-score alerts filtered. Exits still come through.
4. **Cleanup**: Re-enable all, set score=0, save. Kill local processes.

## Out of Scope

- Per-user preferences with individual Telegram DMs (multi-tenant ticket)
- Per-user watchlists driving different alert sets
- Per-symbol or per-alert-type granularity
- Telegram bot commands for preferences

## Research Notes

### Existing Patterns
- `user_notification_prefs` table (db.py:587) — same table pattern
- `upsert_notification_prefs()` (db.py:1189) — same ON CONFLICT upsert
- `_safe_add_column()` (db.py) — for adding min_alert_score column
- Settings notification tab (pages/settings.py:310) — same UI pattern
- `_get_admin_uid()` (monitor.py:87) — how worker resolves admin user_id
