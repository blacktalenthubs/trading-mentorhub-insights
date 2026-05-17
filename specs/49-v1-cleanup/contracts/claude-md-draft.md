# Contract — Rewritten root `CLAUDE.md` (FR-413)

**Status**: Phase 1 design artifact for Spec 49. Replaces `/Users/mentorhub/Documents/master-domain-hub/trade-analytics/CLAUDE.md` in Phase D T-D1.

**Why this is in a contract file**: outside agents read CLAUDE.md to decide which files they may touch. A wrong list trains every future agent to refuse to touch live V2 files (because they appear "protected" under stale V1 rules). The wording matters; reviewers approve the draft below before the file flip.

---

## Text to write (copy verbatim to `trade-analytics/CLAUDE.md`)

```markdown
# TradeCoPilot — Project Instructions

**Status as of 2026-05-16**: V2 production. The Pine + `tv_webhook` + `triage-agent` pipeline is the live stack. The V1 Streamlit + AI-scanner + rule-engine stack was deleted per [Spec 49 (V1 Cleanup)](specs/49-v1-cleanup/spec.md). Active manifest: [Spec 48 (V3 Revamp)](specs/48-v3-cleanup-and-paid-ai-revamp/spec.md).

## Deployment Rule: Local First, Then Production

**ALWAYS test changes locally before pushing to production.**

### Deployment Workflow (V2)

1. **Make changes** locally.
2. **Run tests**: `python3 -m pytest tests/ -v`
3. **Test locally** — bring up the FastAPI dev server:
   ```bash
   cd api
   uvicorn app.main:app --reload --port 8000
   ```
4. **Trigger a sample alert** by POSTing to `/tv/webhook` with a representative Pine payload (see `tests/test_tv_webhook.py` for canonical samples):
   ```bash
   curl -X POST http://localhost:8000/tv/webhook \
     -H 'Content-Type: application/json' \
     -d @tests/fixtures/sample_pdh_break.json
   ```
5. **Inspect the row** in your local Postgres:
   ```bash
   psql "$DATABASE_URL" -c "SELECT id, symbol, alert_type, fired_at FROM alerts ORDER BY id DESC LIMIT 5;"
   ```
6. **Verify the triage-agent picks it up** — start the agent locally:
   ```bash
   cd triage-agent
   python3 live.py
   ```
   Watch its log for the `LISTEN new_alert` cursor to fire on your test row.
7. **Push to main** — Railway auto-deploys the FastAPI service + triage-agent worker.
8. **Verify production** — check the Telegram conviction channel + `https://tradingwithai.ai` Dashboard + `/public/eod-report` page.

### Critical: Kill Local Processes Before Testing Production

Local FastAPI + triage-agent processes send to the SAME Telegram bot as production.

```bash
lsof -ti:8000 | xargs kill -9 2>/dev/null
pkill -f "uvicorn" 2>/dev/null
pkill -f "triage-agent/live.py" 2>/dev/null
pkill -f "vite" 2>/dev/null         # also kill the React dev server if running
```

### Railway Worker Restart

The triage-agent caches state per process. After ANY change to:

- `analytics/alert_types.py`
- `analytics/regime_gate.py`
- `alert_config.py`
- `alerting/notifier.py`
- `triage-agent/live.py`, `triage.py`, `telegram_post.py`

**Redeploy the triage-agent service on Railway** (Deployments → three dots → Redeploy).

---

## Critical Rule: Protect Business Logic

**NEVER modify alert/triage business logic without explicit approval.** These files control real money decisions and the live V2 alert pipeline.

### Protected Files (require impact analysis before ANY change)

| File | What it does |
|------|--------------|
| `api/app/routers/tv_webhook.py` | TradingView webhook ingest: validation, dedup (60-min identity + 30-min level confluence + symbol-session), DB insert, notifier dispatch |
| `analytics/tv_signal_adapter.py` | Pine JSON → internal `AlertSignal` (uses `analytics.alert_types`) |
| `analytics/alert_types.py` | Canonical `AlertType` enum, `AlertSignal` dataclass, `targets_for_long` / `targets_for_short` helpers |
| `analytics/regime_gate.py` | `compute_spy_gate` SPY-regime gate function (mutes non-index SHORTs in bullish SPY regime) |
| `alerting/notifier.py` | Telegram + email delivery |
| `alerting/alert_store.py` | Alert persistence, dedup helpers |
| `alert_config.py` | Tier config, dedup windows, SPY-short symbol set, webhook IP allowlist |
| `triage-agent/live.py` | `pg_notify('new_alert')` listener + per-alert NOTICE / non-index / MA-cooldown / cost-cap gates |
| `triage-agent/triage.py` | Per-alert Claude Haiku agent + sector/index enrichment + safety net |
| `triage-agent/telegram_post.py` | HIGH / NORMAL / MUTE verdict formatters + inline chart rendering |

### Before Modifying Any Protected File

1. **Read the file completely** — understand its role in the V2 pipeline.
2. **Write an impact analysis** — what behavior changes? what could break? which downstream consumers are affected?
3. **Run the full test suite** — `python3 -m pytest tests/ -v`
4. **Get explicit user approval** before making the change.
5. **Verify after** — run tests again, fire a synthetic alert end-to-end, confirm Telegram receives the expected output.

### What Counts as Business Logic

- Pine payload schema / field semantics
- Dedup rules (identity window, level-confluence window, session dedup)
- Triage gate conditions (NOTICE handling, MA cooldown, daily USD cap)
- HIGH / NORMAL / MUTE verdict criteria
- SPY-regime gate behavior
- Notification routing (firehose channel vs conviction channel)
- Target / stop computation

---

## Architecture

### Database: Postgres on Railway (dev parity via local Postgres)

```
Production:  DATABASE_URL → Railway Postgres (shared by api + triage-agent)
Local dev:   DATABASE_URL → your local Postgres
```

The V1 dual-mode SQLite + Postgres wrapper (`db.py`) is retained because the Postgres dev path still uses its `?` → `%s` translation and `ON CONFLICT` normalization. The SQLite branch is now legacy — local dev should run Postgres for parity.

**Rules for `db.py` changes** (unchanged from V1 — these are the wrapper semantics):

- `INSERT OR IGNORE` → use `ON CONFLICT(...) DO NOTHING`
- `INSERT OR REPLACE` → use `ON CONFLICT(...) DO UPDATE SET ...`
- Never use `sqlite3.OperationalError` directly → use `_DB_OPERATIONAL_ERRORS` tuple
- Never use `sqlite3.IntegrityError` directly → use `IntegrityError` from `db.py`
- All `pd.read_sql_query` in `db.py` must use `_pd_read_sql()` helper

### Services

```
┌──────────────────┐    ┌──────────────────────┐    ┌───────────────────────┐
│ Railway: api      │    │ Railway: triage-agent │    │ Railway: worker        │
│ uvicorn + FastAPI │    │ LISTEN new_alert      │    │ (V1 — being retired)   │
│  - /tv/webhook    │    │  → Claude Haiku       │    │                        │
│  - /api/v1/...    │    │  → Telegram conviction│    │                        │
└────────┬─────────┘    └──────────┬───────────┘    └─────────┬─────────────┘
         │                          │                          │
         └──────────────┬───────────┴──────────────┬──────────┘
                        │  DATABASE_URL            │
                        ▼                          ▼
                  ┌───────────────────────────────────┐
                  │     Railway Postgres               │
                  │ alerts, users, watchlists,         │
                  │ chart_analysis, journal, billing,  │
                  │ usage_limits, …                    │
                  └───────────────────────────────────┘
```

### Alert Flow (V2 — the live pipeline)

```
TradingView Pine indicator fires
  → POST /tv/webhook (FastAPI)
    → tv_webhook.py: validate, dedup (60-min identity, 30-min level confluence, session)
    → INSERT INTO alerts
    → notifier.notify() → Telegram (firehose channel)
  → pg_notify('new_alert', id)
    → triage-agent/live.py: NOTICE/short/cooldown gates
    → triage.py: Claude Haiku rate alert + sector/index enrichment
    → telegram_post.py: HIGH/NORMAL/MUTE → Telegram (conviction channel)
  → EOD cron: triage-agent/eod.py recap → Telegram + PublicEODReportPage
```

### Pine Indicators (live)

| Indicator | File | Alerts? | Backend payload consumer |
|-----------|------|---------|--------------------------|
| `ma-ema-daily` | `pine_scripts/active/ma_ema_daily.pine` | YES — 36+ keys (MA bounces / rejections / proximity across 9 MAs + stacked variants) | tv_webhook |
| `levels-day-vwap` | `pine_scripts/active/levels_day_vwap.pine` | YES — 10 keys + HTF (PDH/PDL break/reclaim/rejection, VWAP, open-line, PWH/PWL/PMH/PML hold/wick) | tv_webhook |
| `levels-week-month` | `pine_scripts/active/levels_week_month.pine` | NO — visual only | N/A |
| `open-line` | `pine_scripts/active/open_line.pine` | NO — visual only (alerts fire from levels-day-vwap) | N/A |

Full inventory: see `pine_scripts/active/ALERTS.md` (regenerated 2026-05-16).

---

## Testing

### Run Tests Before Any Push

```bash
python3 -m pytest tests/ -v
```

Critical tests for the V2 path (must always be green):

- `tests/test_tv_webhook.py` — dedup, payload validation
- `tests/test_notifier.py` — Telegram + email delivery formatting
- `tests/test_chart_analyzer.py` — chart-analysis foundation (Spec 51 prep)
- `tests/test_alert_routing.py`, `test_alert_preferences.py`, `test_per_user_*.py` — per-user notification rules
- `tests/test_postgres_wrapper.py`, `test_turso_migration.py` — DB wrapper semantics
- `tests/test_alert_types.py`, `test_regime_gate.py` — extracted-module contracts (created in Spec 49 Phase C)

### Postgres-backed tests (requires Docker Desktop)

```bash
python3 -m pytest tests/test_postgres_wrapper.py -v
```

---

## Tech Stack

- **Python 3.13** (Railway services + tests)
- **FastAPI + uvicorn** — `api/` service
- **psycopg2-binary** — Postgres driver
- **Pine v5** — TradingView indicators (source of all live alerts)
- **Anthropic API** — Claude Haiku for triage agent, Claude Vision (Spec 51) for chart critique
- **Telegram Bot API** — primary notification channel
- **React 18 + Vite + Tailwind + Capacitor** — `web/` (web + iOS app)

---

## Common Patterns

### Adding a new Pine alert

1. Add the alert key to the appropriate Pine indicator (`pine_scripts/active/`).
2. Add the corresponding `AlertType` enum member in `analytics/alert_types.py`.
3. Update `analytics/tv_signal_adapter.py` to map the Pine payload to the new `AlertSignal`.
4. Update `pine_scripts/active/ALERTS.md` so the alert is documented.
5. Add a unit test in `tests/test_tv_webhook.py` for the new payload shape.
6. Run the full pipeline locally with a synthetic POST.

### Adding a new API endpoint

Endpoints live under `api/app/routers/`. Each router registered in `api/app/main.py`. Pattern:

1. Create the router file.
2. Import + include in `main.py`.
3. Add a tier-gate decorator if the endpoint is paid (`api/app/tier.py`).
4. Add a usage-counter increment if the endpoint counts against a per-tier quota.

### Adding a new table

1. Add `CREATE TABLE IF NOT EXISTS` to the DDL in `db.py` (via Alembic migration in `api/alembic/`).
2. Use `INTEGER PRIMARY KEY AUTOINCREMENT` (auto-converted to `SERIAL` on Postgres).
3. Add a SQLAlchemy/Pydantic model in `api/app/models/`.
4. Add CRUD via `get_db()` context manager.

### Environment Variables

| Variable | Where | Purpose |
|----------|-------|---------|
| `DATABASE_URL` | api + triage-agent + Streamlit (legacy) | Postgres connection |
| `TELEGRAM_BOT_TOKEN` | api + triage-agent | Telegram notifications |
| `TELEGRAM_CHAT_ID` | api | Firehose channel ID |
| `TELEGRAM_CONVICTION_CHAT_ID` | triage-agent | Conviction channel ID |
| `ANTHROPIC_API_KEY` | api + triage-agent | LLM calls |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | api | Default admin account |
| `TV_WEBHOOK_ALLOWED_IPS` | api | IP allowlist for `/tv/webhook` |
| `TRIAGE_DAILY_USD_CAP` | triage-agent | LLM-spend ceiling |
| `RULE_ENGINE_ENABLED` | (V1 — must be `false`) | Kept for back-compat; flipping `true` re-activates the deleted V1 path and is unsupported |
| `AI_SCAN_ENABLED` | (V1 — must be `false`) | Same as above |

---

## What's been retired (do not revive without a new spec)

These were active in V1 and are no longer in the codebase. Re-introducing any of them requires explicit operator approval and a new spec under `specs/`.

- "AI picks the trades" intraday + swing scanners (`ai_day_scanner`, `ai_swing_scanner`, `ai_best_setups`)
- V1 rule-engine (`analytics/intraday_rules.py` body — only its types and SPY-gate live on, in `alert_types.py` + `regime_gate.py`)
- Streamlit dashboard at `tradesignalwithai.com` (legacy domain handling: see `specs/49-v1-cleanup/decision.md`)
- yfinance polling loop (`monitor.py`, `worker.py`)
- Real-money / paper-trading / options-store layers (status per `specs/49-v1-cleanup/decision.md`)
- PDF trade-import tooling (`parsers/`)

If you're an outside agent and a file you want to touch is on this retirement list and not in the Protected Files table above, it is either deleted or out of scope — do not re-add it.

---

## Active spec ladder

- [Spec 48 — V3 Cleanup & Paid AI Revamp (manifest)](specs/48-v3-cleanup-and-paid-ai-revamp/spec.md)
- [Spec 49 — V1 Cleanup (foundation, in progress)](specs/49-v1-cleanup/spec.md)
- [Spec 50 — Landing & Internal Page Revamp](specs/50-landing-revamp/spec.md)
- [Spec 51 — AI Chart Critique (headline paid feature)](specs/51-chart-critique/spec.md)
- [Spec 52 — Pattern Education with Live Examples](specs/52-pattern-education-live/spec.md)
- [Spec 53 — Personalized Replay Coach](specs/53-replay-coach/spec.md)
- [Spec 54 — Daily Conviction Report Email Digest](specs/54-conviction-report-email/spec.md)

For historical V1 context: [Spec 46 (superseded)](specs/46-stable-state-reference/spec.md).
```

---

## Verification after file flip

After replacing `trade-analytics/CLAUDE.md` with the above content:

1. Every file path mentioned in the "Protected Files" table MUST exist in the repo.
2. No file path mentioned in the "Protected Files" table MUST have been deleted by Spec 49.
3. `grep "intraday_rules" /Users/mentorhub/Documents/master-domain-hub/trade-analytics/CLAUDE.md` MUST return zero references EXCEPT the historical / retirement-notice mentions in the "What's been retired" section.
4. Run the SC-105 outside-agent audit (20 prompts) — record results in `decision.md` D-6.
