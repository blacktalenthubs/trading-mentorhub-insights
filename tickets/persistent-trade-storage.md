# Persistent Trade Storage — Survive Streamlit Cloud Restarts

## Problem

Real trade data (`real_trades`, `real_options_trades`) is stored in a local SQLite file (`data/trades.db`). On Streamlit Cloud, the filesystem is ephemeral — every reboot or deploy wipes the DB. This loses all trade history, P&L tracking, and performance metrics.

## Impact

- Cannot evaluate short-term trading performance reliably
- Lose all open position tracking on deploy
- Options trade history gone after every push
- Win rate, expectancy, equity curve — all reset to zero

## Tables Affected

| Table | Records | Priority |
|-------|---------|----------|
| `real_trades` | Active + closed equity trades | HIGH |
| `real_options_trades` | Active + closed options trades | HIGH |
| `alerts` | Signal history (used for dedup + reports) | MEDIUM |
| `daily_plans` | Scanner plans (regenerated daily) | LOW |
| `swing_trades` | Swing scanner state (regenerated on scan) | LOW |

## Options to Evaluate

### 1. Turso (SQLite over HTTP) — Recommended
- Drop-in SQLite replacement, minimal code changes
- Free tier: 500 DBs, 9 GB storage, 25M reads/mo
- Python SDK: `libsql-experimental`
- Change: swap `sqlite3.connect(DB_PATH)` → `libsql.connect(TURSO_URL, auth_token=TOKEN)`
- Pros: closest to current architecture, near-zero refactor
- Cons: slight latency vs local file

### 2. Supabase (PostgreSQL)
- Free tier: 500 MB, 2 projects
- Requires SQL dialect changes (e.g., `AUTOINCREMENT` → `SERIAL`)
- Change: replace `sqlite3` with `psycopg2` or `sqlalchemy`
- Pros: full Postgres features, dashboard UI
- Cons: bigger refactor, SQL differences

### 3. JSON backup to GitHub (quick hack)
- Export trades to JSON, commit to repo on each write
- On startup, import from JSON if DB is empty
- Pros: zero external dependencies
- Cons: not real-time, merge conflicts, ugly

### 4. Streamlit Cloud persistent storage (st.experimental_connection)
- Limited support, still evolving
- Not reliable for structured data

## Suggested Approach

**Turso** — minimal code change, stays SQLite-compatible:

1. Create Turso DB (free tier)
2. Add `TURSO_DB_URL` and `TURSO_AUTH_TOKEN` to Streamlit secrets
3. Modify `db.py` `get_connection()` to use `libsql` when env vars present, fall back to local SQLite for dev
4. All SQL stays the same — no migration needed
5. Add `libsql-experimental` to `requirements.txt`

## Scope

- Only migrate trade-critical tables: `real_trades`, `real_options_trades`
- Keep regeneratable tables (alerts, daily_plans, swing_trades) in local SQLite
- Dual-mode: local SQLite for dev, Turso for cloud

## Weekend Plan

- [ ] Set up Turso account + DB
- [ ] Modify `db.py` for dual-mode connection
- [ ] Test locally with Turso remote
- [ ] Add secrets to Streamlit Cloud
- [ ] Verify trades persist across reboot
