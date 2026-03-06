# TradeSignal — Project Instructions

## Critical Rule: Protect Business Logic

**NEVER modify alert/signal business logic without explicit approval.** These files control real money decisions:

### Protected Files (require impact analysis before ANY change)
| File | What it does |
|------|-------------|
| `analytics/intraday_rules.py` | Alert rules: MA bounce, support bounce, gap fill, target/stop hits |
| `analytics/signal_engine.py` | Scanner: score calculation, daily plan generation, S/R levels |
| `alerting/alert_store.py` | Alert persistence, dedup, cooldowns |
| `alerting/notifier.py` | Telegram + email delivery |
| `alerting/real_trade_store.py` | Real trade P&L tracking |
| `alerting/options_trade_store.py` | Options trade tracking |
| `monitor.py` | Live polling loop — fires alerts during market hours |
| `worker.py` | Railway background worker — same as monitor but headless |

### Before Modifying Any Protected File
1. **Read the file completely** — understand what it does
2. **Write an impact analysis** — what behavior changes? what could break?
3. **Run the full test suite** — `python3 -m pytest tests/ -v`
4. **Get explicit user approval** before making the change
5. **Verify after** — run tests again, check alert flow end-to-end

### What Counts as Business Logic
- Alert trigger conditions (price vs MA, support levels, confidence)
- Score calculation (what makes a signal high/medium/low)
- Dedup rules (what prevents duplicate alerts)
- Cooldown logic (post-stop-out suppression)
- Target/stop hit detection
- Trade sizing (position size calculations)
- Notification routing (who gets which alert)

---

## Architecture

### Database: Dual-mode (SQLite + Postgres)
```
Production:  DATABASE_URL set → Railway Postgres (shared by worker + Streamlit)
Local dev:   No DATABASE_URL  → SQLite at data/trades.db
```

Key file: `db.py` — contains `PostgresConnectionWrapper` that translates SQLite conventions (`?` params, `.lastrowid`, `executescript`) to psycopg2. All 26+ consumer files use `get_db()` unchanged.

**Rules for db.py changes:**
- `INSERT OR IGNORE` → use `ON CONFLICT(...) DO NOTHING` (works in both SQLite 3.24+ and Postgres)
- `INSERT OR REPLACE` → use `ON CONFLICT(...) DO UPDATE SET ...`
- Never use `sqlite3.OperationalError` directly → use `_DB_OPERATIONAL_ERRORS` tuple
- Never use `sqlite3.IntegrityError` directly → use `IntegrityError` from db.py
- All `pd.read_sql_query` in db.py must use `_pd_read_sql()` helper
- SQL `LIKE` patterns with `%` work correctly (wrapper escapes them)
- numpy values in params work correctly (wrapper coerces to native Python)

### Services
```
┌──────────────┐         ┌──────────────────┐
│ Railway       │         │ Streamlit Cloud   │
│ worker.py     │         │ app.py + pages/   │
└──────┬───────┘         └────────┬──────────┘
       │     DATABASE_URL          │
       └──────────┬────────────────┘
            ┌─────▼──────────┐
            │ Railway Postgres│
            └────────────────┘
```

### Alert Flow
```
worker.py poll loop
  → fetch intraday data (yfinance)
  → evaluate_rules() per symbol
  → dedup check (was_alert_fired)
  → cooldown check (is_symbol_cooled_down)
  → record_alert() → DB
  → notify() → Telegram + Email
```

---

## Testing

### Run Tests Before Any Push
```bash
# SQLite tests (always run)
python3 -m pytest tests/test_turso_migration.py tests/test_alert_dedup.py tests/test_intraday_rules.py -v

# Postgres tests (requires Docker Desktop running)
python3 -m pytest tests/test_postgres_wrapper.py -v

# All tests
python3 -m pytest tests/ -v
```

### Test Coverage Requirements
- `test_intraday_rules.py` — 283 tests covering all alert rules
- `test_alert_dedup.py` — cooldown, dedup, SPY regime demotion
- `test_turso_migration.py` — schema, CRUD, auth, pandas compat
- `test_postgres_wrapper.py` — Postgres wrapper, init_db, ON CONFLICT

---

## Tech Stack
- **Python 3.9+** (Streamlit Cloud uses 3.13)
- **Streamlit** — dashboard UI
- **psycopg2-binary** — Postgres driver
- **yfinance** — market data
- **APScheduler** — worker polling
- **Anthropic API** — AI narratives for alerts
- **Twilio** — SMS (unused currently)
- **Telegram Bot API** — primary notification channel

---

## Common Patterns

### Adding a New Page
Pages go in `pages/` with numeric prefix for ordering. Every page calls `ui_theme.setup_page("page_name")` which handles auth + init_db.

### Adding a New Table
1. Add `CREATE TABLE IF NOT EXISTS` to `init_db()` DDL block in `db.py`
2. Use `INTEGER PRIMARY KEY AUTOINCREMENT` — auto-converted to `SERIAL PRIMARY KEY` on Postgres
3. Add CRUD functions in `db.py` using `get_db()` context manager
4. Use `?` for params — wrapper translates to `%s` on Postgres

### Environment Variables
| Variable | Where | Purpose |
|----------|-------|---------|
| `DATABASE_URL` | Railway + Streamlit | Postgres connection string |
| `TELEGRAM_BOT_TOKEN` | Railway + Streamlit | Telegram notifications |
| `TELEGRAM_CHAT_ID` | Railway | Default chat ID |
| `ANTHROPIC_API_KEY` | Railway | AI narratives |
| `ADMIN_EMAIL` | Both | Default admin account |
| `ADMIN_PASSWORD` | Both | Default admin password |
