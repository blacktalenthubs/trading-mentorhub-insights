# Tasks: User Alert Preferences (Admin-Only)

**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)
**Created**: 2026-04-03

## Phase 1: Setup & Tests

- [ ] T001 Write unit tests for category mapping and `_should_notify()` logic (path: tests/test_alert_preferences.py)
- [ ] T002 [P] Write DB CRUD tests for category prefs and min_score (path: tests/test_alert_preferences.py)

## Phase 2: Data Layer

- [ ] T003 Define `ALERT_CATEGORIES` dict, `ALERT_TYPE_TO_CATEGORY` reverse lookup, and `EXIT_ALERT_TYPES` set (path: alert_config.py)
- [ ] T004 [P] Add `user_alert_category_prefs` table to `init_db()` (path: db.py)
- [ ] T005 [P] Add `min_alert_score` column to `user_notification_prefs` via `_safe_add_column()` (path: db.py)
- [ ] T006 Add CRUD functions: `get_alert_category_prefs()`, `upsert_alert_category_prefs()`, `get_min_alert_score()`, `set_min_alert_score()` (path: db.py)
- [ ] T007 Run tests — verify T001 and T002 pass

## Phase 3: Notification Gate

- [ ] T008 Add `_should_notify()` helper function to monitor.py (path: monitor.py)
- [ ] T009 Load admin category prefs + min_score once at start of `poll_cycle()` (path: monitor.py)
- [ ] T010 Wire `_should_notify()` gate before `notify()` call — skip Telegram if filtered, log reason (path: monitor.py)
- [ ] T011 Run tests — verify no regressions (648+ baseline)

## Phase 4: Settings UI

- [ ] T012 Add "Alert Preferences" section to Settings page with category toggles (path: pages/settings.py)
- [ ] T013 [P] Add min_score slider to Settings page (path: pages/settings.py)
- [ ] T014 Add save handler that persists all category prefs + min_score to DB (path: pages/settings.py)

## Phase 5: Verify & Deploy

- [ ] T015 Run full test suite — all tests pass
- [ ] T016 Test locally: toggle categories, verify filtered alerts in dashboard but not Telegram
- [ ] T017 Push to main and restart Railway worker

---

**Legend**:
- `T###` — Task ID (sequential)
- `[P]` — Parallelizable (can run alongside other [P] tasks in same phase)
- `path:` — Primary file for the task
