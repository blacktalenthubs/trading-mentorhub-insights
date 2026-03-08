# Persistent Trade Storage v2

## Status: Backlog (Weekend)

## Context

Turso embedded replica (libsql-experimental) was too unstable for production:
- Rust panics (`pyo3_runtime.PanicException`)
- Stale Hrana stream errors on every connection
- No `row_factory` support, no `cursor()` for pandas
- Required extensive wrapper code that still broke

The only data lost on Streamlit Cloud restart is `real_trades` and `real_options_trades`.
Current workaround: limit restarts to once/day outside market hours.

## Weekend Goals

1. **System architecture redesign** — proper infra planning for robustness
2. **Persistent storage solution** — evaluate alternatives:
   - **Supabase (Postgres)** — free tier, mature Python client, no Rust issues
   - **Turso HTTP API** — stateless REST calls (not embedded replica)
   - **S3/GCS SQLite backup** — dump on write, restore on startup
   - **Neon (serverless Postgres)** — free tier, standard psycopg2
3. **Real trade export/import** — CSV download button + upload restore as interim safety net

## Scope

- Only `real_trades` and `real_options_trades` need cloud persistence
- All other data (alerts, paper trades, imports) is transient or re-importable
- Solution must not slow down page loads
- Must work on Streamlit Cloud (no persistent disk)

## Lessons from Turso Attempt

- Embedded replica mode is not production-ready (v0.0.55)
- Any solution must use standard Python DB drivers (no Rust/native extensions)
- Wrapper complexity is a red flag — if the DB client needs heavy wrapping, pick a different DB
- Test on Streamlit Cloud early, not just locally
