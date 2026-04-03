# Constitution [v 1.0.0]

**Project**: TradeSignal / TradeCoPilot
**Ratification Date**: 2026-04-02
**Last Amended**: 2026-04-02

## Principles

### 1. Protect Business Logic
All alert/signal business logic changes require impact analysis and explicit approval before implementation. Files controlling real money decisions (intraday_rules.py, signal_engine.py, alert_store.py, notifier.py, monitor.py, worker.py) are protected.

- **MUST** read the file completely before modifying
- **MUST** write an impact analysis (what behavior changes, what could break)
- **MUST** run the full test suite before and after changes
- **MUST** get explicit user approval before making the change

### 2. Test-Driven Development
Tests come first, implementation follows.

- **MUST** write failing tests before implementation
- **MUST** ensure all tests pass before merging
- **SHOULD** cover happy path, edge cases, and error conditions
- **MUST** maintain 648+ test baseline (no regressions)

### 3. Local First, Then Production
All changes are tested locally before pushing to production.

- **MUST** run tests locally: `python3 -m pytest tests/ -v`
- **MUST** verify on localhost before pushing
- **MUST** restart Railway worker after alert logic changes
- **MUST** kill local processes before evaluating production

### 4. Database Compatibility
Code must work on both SQLite (local) and Postgres (production).

- **MUST** use `?` for params (wrapper translates to `%s`)
- **MUST** use `ON CONFLICT(...) DO NOTHING` instead of `INSERT OR IGNORE`
- **MUST** use `_DB_OPERATIONAL_ERRORS` tuple, never `sqlite3.OperationalError`
- **SHOULD** use `_pd_read_sql()` helper for pandas queries

### 5. Alert Quality Over Quantity
Better to miss a marginal trade than send a bad signal.

- **MUST** validate alerts against chart context (support vs resistance)
- **MUST** require confirmation for breakouts (hold, volume, close above level)
- **SHOULD** use structural S/R levels for targets, not fixed R multiples
- **MUST NOT** filter by score alone (structural alerts work at any score)

### 6. Single Notification Channel
All alerts go to the Telegram group only.

- **MUST** send alerts to TELEGRAM_CHAT_ID (group: -5016298458)
- **MUST NOT** send to individual user telegram_chat_ids
- **SHOULD** use `notify()` (group) not `notify_user()` (individual) from worker

## Governance

- **Amendment**: Any principle can be updated via `/speckit.constitution` with version bump
- **Versioning**: MAJOR (principle added/removed), MINOR (principle modified), PATCH (wording)
- **Review**: Constitution checked during `/speckit.plan` and `/speckit.analyze`
