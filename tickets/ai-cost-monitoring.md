# AI Cost Monitoring — Admin Dashboard Widget + Spend Alerts

**Priority**: High — pre-ads launch blocker (blind spending is how platforms die)
**Created**: 2026-04-12
**Owner**: TBD

## Why

Claude API usage is the biggest variable cost. Without visibility:
- We find out we're out of credits only when scans start 400'ing (already happened — see logs 2026-04-12)
- Runaway cost from a loop or misconfig goes unnoticed until the monthly bill
- Can't correlate user growth to cost per user → can't price tiers correctly

We need a dashboard that answers three questions at a glance:
1. How much am I spending today / this month?
2. Which AI features are the cost drivers?
3. Am I on track to hit my monthly budget?

## Scope

### In
- Lightweight cost tracking table
- Instrument every Anthropic API call to log cost
- Admin dashboard widget showing MTD spend + daily burn rate
- Alert when projected month exceeds configured budget
- Per-feature breakdown (AI Scan vs Coach vs Exit vs CoPilot)
- Per-user attribution for Coach / Commands (where it matters for abuse detection)

### Out (separate tickets)
- Anthropic API cost export / reconciliation (we estimate from tokens, not pull from Anthropic)
- Per-user cost limit enforcement (already have quota limits by day)
- Billing customer cost-per-revenue analysis
- Grafana / external dashboard

## Design

### Data model

New table `ai_cost_events` — one row per Anthropic API call:

```sql
CREATE TABLE IF NOT EXISTS ai_cost_events (
    id SERIAL PRIMARY KEY,
    ts TIMESTAMP DEFAULT NOW(),
    session_date VARCHAR(10) NOT NULL,  -- 'YYYY-MM-DD' for fast group-by
    feature VARCHAR(50) NOT NULL,        -- 'ai_day_scan' | 'ai_exit_scan' | 'ai_coach' | 'chart_analysis' | 'telegram_cmd' | ...
    model VARCHAR(50) NOT NULL,          -- 'claude-haiku-4-5' | 'claude-sonnet-4-6' etc
    user_id INTEGER,                     -- NULL for system-wide calls (AI scan)
    symbol VARCHAR(20),                  -- optional, when applicable
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,              -- computed from model pricing
    cached_tokens INTEGER DEFAULT 0      -- prompt caching savings
);

CREATE INDEX idx_ai_cost_events_session ON ai_cost_events(session_date);
CREATE INDEX idx_ai_cost_events_feature ON ai_cost_events(feature);
CREATE INDEX idx_ai_cost_events_user ON ai_cost_events(user_id) WHERE user_id IS NOT NULL;
```

### Pricing constants

```python
# analytics/ai_costs.py
MODEL_PRICING = {
    "claude-haiku-4-5": {"input_per_m": 0.80, "output_per_m": 4.00, "cache_read_per_m": 0.08},
    "claude-haiku-3-5": {"input_per_m": 0.80, "output_per_m": 4.00, "cache_read_per_m": 0.08},
    "claude-sonnet-4-6": {"input_per_m": 3.00, "output_per_m": 15.00, "cache_read_per_m": 0.30},
    "claude-opus-4-6": {"input_per_m": 15.00, "output_per_m": 75.00, "cache_read_per_m": 1.50},
    # Fallback
    "default": {"input_per_m": 0.80, "output_per_m": 4.00, "cache_read_per_m": 0.08},
}

def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    m = MODEL_PRICING.get(model, MODEL_PRICING["default"])
    # Cached tokens are a fraction of regular input cost
    in_cost = ((input_tokens - cached_tokens) * m["input_per_m"] + cached_tokens * m["cache_read_per_m"]) / 1_000_000
    out_cost = output_tokens * m["output_per_m"] / 1_000_000
    return round(in_cost + out_cost, 6)


def log_ai_call(db, feature: str, model: str, response, user_id=None, symbol=None) -> None:
    """Call after every successful Anthropic API response."""
    usage = response.usage
    input_t = usage.input_tokens
    output_t = usage.output_tokens
    cached_t = getattr(usage, "cache_read_input_tokens", 0) or 0
    cost = estimate_cost_usd(model, input_t, output_t, cached_t)
    db.execute(text("""
        INSERT INTO ai_cost_events
        (session_date, feature, model, user_id, symbol, input_tokens, output_tokens, cost_usd, cached_tokens)
        VALUES (:sd, :f, :m, :u, :s, :it, :ot, :c, :ct)
    """), {
        "sd": date.today().isoformat(),
        "f": feature, "m": model, "u": user_id, "s": symbol,
        "it": input_t, "ot": output_t, "c": cost, "ct": cached_t,
    })
    db.commit()
```

### Call sites to instrument

Every place we call `client.messages.create(...)`:

- `analytics/ai_day_scanner.py::scan_day_trade` — feature=`ai_day_scan`, symbol set
- `analytics/ai_day_scanner.py::scan_open_position` — feature=`ai_exit_scan`, symbol set
- `analytics/trade_coach.py::ask_coach` — feature=`ai_coach`, user_id set
- `analytics/chart_analyzer.py` — feature=`chart_analysis`, user_id set
- `scripts/telegram_bot.py` — `/spy`, `/eth` etc — feature=`telegram_cmd`, user_id set
- `analytics/game_plan.py` — feature=`game_plan`
- `analytics/premarket_brief.py` — feature=`premarket`
- `analytics/weekly_review.py` — feature=`weekly_review` / `eod_review`

**Important:** only log on successful responses (skip 400/429/5xx — they didn't consume tokens but also didn't deliver value).

### Admin API

```
GET /api/v1/admin/ai-costs/today
  → {date: "2026-04-12", total_usd: 2.34, calls: 128, by_feature: [...]}

GET /api/v1/admin/ai-costs/month
  → {month: "2026-04", total_usd: 34.17, by_day: [...], by_feature: [...]}

GET /api/v1/admin/ai-costs/top-users?days=7
  → [{user_id, email, total_usd, calls}, ...] sorted desc

GET /api/v1/admin/ai-costs/budget
  → {monthly_budget: 100, mtd_spend: 34.17, projected_eom: 73.50,
     days_elapsed: 12, days_in_month: 30, on_pace: true}
```

### Admin dashboard widget

New section on `/admin` (below Signup Attribution):

```
┌─────────────────────────────────────────────────────────────────┐
│ 🧠 AI API Spend — April 2026                           Budget $100│
│                                                                   │
│  MTD:  $34.17      Today:  $2.34      Projected EoM:  $73.50  ✓  │
│  [══════════════░░░░░░░░░░░░░░░░░░░]  34% of budget              │
│                                                                   │
│  By feature (MTD):           By day (last 14):                   │
│   AI Scan      $21.40 (63%)  [tiny sparkline of daily spend]    │
│   AI Coach     $8.12  (24%)                                      │
│   Chart CoPilot $3.05 (9%)                                       │
│   Exit Scan    $1.20  (4%)                                       │
│   Other        $0.40  (1%)                                       │
│                                                                   │
│  Top 5 users by Coach usage (last 7 days):                       │
│   user@example.com    23 calls  $0.34                            │
│   ...                                                             │
└─────────────────────────────────────────────────────────────────┘
```

### Budget alerts

Simple daily cron job (noon UTC) that checks projected MTD:

```python
def check_budget_and_alert():
    # If projected_eom > budget × 0.75 → send warning to admin email + Telegram
    # If mtd_spend > budget × 0.90 → urgent alert
    # If mtd_spend > budget → hard alert + optional throttle flag
```

Admin email + Telegram chat_id loaded from env / settings.

## Functional Requirements

### FR-1: Cost event logging
- [ ] `ai_cost_events` table created via migration
- [ ] `analytics/ai_costs.py` module with `MODEL_PRICING`, `estimate_cost_usd`, `log_ai_call`
- [ ] Every `client.messages.create()` call site calls `log_ai_call` on success
- [ ] Failures (400/429/5xx) do NOT log a cost event
- [ ] Prompt caching savings recorded via `cached_tokens` field
- Acceptance: run a scan cycle, confirm 2+ rows in `ai_cost_events` with non-zero costs

### FR-2: Admin API
- [ ] `/admin/ai-costs/today` endpoint
- [ ] `/admin/ai-costs/month` endpoint
- [ ] `/admin/ai-costs/top-users` endpoint
- [ ] `/admin/ai-costs/budget` endpoint with projection math
- Acceptance: curl each endpoint as admin, get JSON matching shape above

### FR-3: Admin dashboard widget
- [ ] New section on `/admin` page under Attribution
- [ ] Shows MTD spend, today, projected EoM, % of budget
- [ ] By-feature breakdown with percentages
- [ ] Sparkline of last 14 days (inline SVG, no chart lib)
- [ ] Top 5 users by Coach + Telegram command spend (7-day window)
- Acceptance: admin sees widget populated after 1-2 days of data

### FR-4: Budget alerts
- [ ] `MONTHLY_AI_BUDGET` env var (default $100)
- [ ] Daily cron job checks projected EoM
- [ ] 75% warning — Telegram to admin chat
- [ ] 90% urgent alert
- [ ] 100% + 10% breach — separate "budget exceeded" alert
- [ ] Alerts fire once per threshold per month (track in `usage_limits` with feature='budget_alert_75' etc)
- Acceptance: manually set low budget, force a spend, confirm Telegram alert lands

### FR-5: Pricing refresh
- [ ] Constants in `analytics/ai_costs.py`, documented
- [ ] Easy to update when Anthropic changes prices
- [ ] Bias costs slightly high (5-10% buffer) so we don't undercount
- Acceptance: when Haiku pricing changes, one file edit updates projections

## Testing

- Unit tests for `estimate_cost_usd` with known token counts
- Unit tests for `log_ai_call` happy path + error swallow
- Unit tests for budget projection math (with 0, 15, 29, 30 days elapsed)
- Integration test: trigger a scan with mocked Anthropic response, assert DB row created
- Manual: watch admin dashboard after one live market hour

## Rollout

**Phase 1 — Logging only (day 1):**
- Add table, module, instrument 2-3 highest-volume call sites (ai_day_scan, ai_exit_scan)
- Data starts accumulating, no UI yet
- Safe to deploy mid-session

**Phase 2 — Admin UI (day 2-3):**
- API endpoints
- Dashboard widget
- Sparkline

**Phase 3 — Budget alerts (day 4):**
- Cron job + Telegram alerts
- Env var configuration

**Phase 4 — Extended coverage (ongoing):**
- Instrument remaining call sites (coach, commands, briefs)
- Per-user breakdown refinement
- Weekly email summary

## Open Questions

- **Budget default:** $100/mo reasonable for launch? Bump to $200 if heavy ad traffic expected
- **Attribution granularity:** log per-user for Coach (easy). For AI scan (symbol-level, not user-level), we already know it's shared — but do we want to distribute cost across users for per-user profitability analysis? Probably yes, proportional to users watching that symbol
- **Throttle on budget breach:** soft (alert only) or hard (disable scanner until next month)? Recommend soft for v1

## Risks

| Risk | Mitigation |
|---|---|
| Logging overhead slows scans | Use fire-and-forget write; batch inserts every N calls |
| Cost estimation drift vs actual Anthropic bill | Reconcile weekly — if off by >10%, adjust pricing constants |
| Budget alert spam | One-shot flags per threshold per month |
| User-level cost attribution leaks privacy | Only admin sees — not in any public endpoint |

## Related

- `tickets/pre-ad-launch-smoke-tests.md` — include cost widget in launch checklist
- `tickets/ai-scan-rate-limit-persistence.md` — complements this (rate limit = user-level, cost = dollar-level)
- `specs/30-telegram-ai-commands/` — telegram command usage is a cost factor
- Spec 35 — auto-trade monitor adds minute-cadence AI calls, moderate cost increase

## Success Criteria

- [ ] Admin can see today's AI spend without leaving the app
- [ ] We never get surprised by a credit-exhausted scanner again
- [ ] Cost per user correlates cleanly with tier (free tier < Pro per-user cost)
- [ ] Projected EoM spending visible daily — course correct before end of month
- [ ] Within 30 days, we have clean data to set Pro pricing based on cost-of-goods
