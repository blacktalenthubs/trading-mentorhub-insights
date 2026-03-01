# TradeSignal — Production Platform Spec

> Living document. No implementation yet — spec only.
> Current phase: Streamlit prototype with 3-5 beta users.

---

## 1. Product Vision

Turn a personal day-trading alert system into a subscription platform where users
receive real-time mechanical trading signals, track performance, and build custom
alert rules — backed by a verifiable paper trade track record.

---

## 2. Current State (Streamlit Prototype)

| What works | Limitation |
|------------|------------|
| 8+ signal rules scanning 10 symbols every 3 min | Single-threaded, no concurrency |
| Email + SMS/WhatsApp alerts | No per-user alert preferences |
| Paper trading via Alpaca | Tied to one Alpaca account |
| Real trade tracking ("Took It" flow) | No multi-user isolation |
| SQLite persistence | Won't handle concurrent writes |
| Bcrypt auth + session tokens | No subscription/billing |
| 119 passing tests | No API layer — UI calls DB directly |

**What to do now:** Keep accumulating paper trade data. Fix UI rough edges.
Expose to 3-5 friends for feedback. Don't build the production stack yet.

---

## 3. Subscription Tiers

### Free

- View delayed signal feed (15-min delay)
- Daily end-of-day summary email
- Paper trade track record (read-only)
- 3 symbols on watchlist

### Pro — $29/mo

- Real-time signal feed (live during market hours)
- Email + SMS/WhatsApp alerts
- Full paper trade history + stats
- Real trade tracking ("Took It" journal)
- 15 symbols on watchlist
- All 8+ built-in signal rules
- Performance dashboard (equity curve, win rate, expectancy)

### Premium — $79/mo

- Everything in Pro
- Custom alert rules (user-defined entry/stop/target logic)
- Unlimited watchlist symbols
- API access (webhook delivery for signals)
- Priority signal delivery (< 30s latency)
- Backtest custom rules against historical data
- Export trade history (CSV/PDF)

### Pricing Notes

- Annual discount: 2 months free (Pro $290/yr, Premium $790/yr)
- Beta users (current 3-5 friends): lifetime Pro access free
- Revisit pricing after 50+ paying users

---

## 4. User Roles

| Role | Access |
|------|--------|
| **Admin** | Full platform access, user management, system config |
| **Subscriber** | Tier-gated features per subscription level |
| **Beta Tester** | Pro-tier access, feedback channel, no billing |

---

## 5. API Contract

The Next.js frontend will consume these endpoints. FastAPI wraps the existing
Python analytics engine — no logic rewrite.

### 5.1 Auth (handled by Clerk in production)

Clerk handles signup, login, session tokens, and subscription status.
The API validates Clerk JWTs and reads subscription tier from claims.

### 5.2 Signals

```
GET  /api/signals/live
     → SSE stream of AlertSignal objects during market hours
     → Fields: symbol, direction, alert_type, price, entry, stop,
               target_1, target_2, confidence, score, message, fired_at
     → Free tier: 15-min delay applied server-side
     → Auth: Pro+ required for real-time

GET  /api/signals/today
     → All signals fired in current session
     → Response: { signals: [...], summary: { total, buy_count, sell_count,
                   short_count, t1_hits, stopped_out, win_rate } }

GET  /api/signals/history?days=30&symbol=AAPL
     → Historical alerts with optional filters
     → Pagination: cursor-based
```

### 5.3 Watchlist

```
GET    /api/watchlist
       → User's watchlist with current prices + change %
       → Response: { symbols: [{ symbol, price, change_pct, has_signal }] }

PUT    /api/watchlist
       → Replace watchlist (enforces tier symbol limit)
       → Body: { symbols: ["AAPL", "NVDA", ...] }
```

### 5.4 Real Trades

```
POST   /api/trades/real
       → Open a real trade ("Took It")
       → Body: { symbol, direction, entry_price, stop_price,
                 target_price, target_2_price, alert_type, alert_id }
       → Auto-calculates shares from position sizing caps

PATCH  /api/trades/real/{id}/close
       → Close at exit price
       → Body: { exit_price, notes }

PATCH  /api/trades/real/{id}/stop
       → Mark as stopped out
       → Body: { exit_price, notes }

PATCH  /api/trades/real/{id}/notes
       → Update journal entry
       → Body: { notes }

GET    /api/trades/real?status=open
       → List trades, filterable by status (open, closed, stopped)

GET    /api/trades/real/stats
       → Aggregate: total_pnl, win_rate, total_trades, expectancy,
                    avg_win, avg_loss
```

### 5.5 Paper Trades (Track Record)

```
GET    /api/trades/paper/stats
       → Platform-wide paper trade performance (public, used for marketing)
       → Response: { total_pnl, win_rate, total_trades, expectancy,
                     avg_win, avg_loss, risk_reward, track_record_days }

GET    /api/trades/paper/history?limit=200
       → Closed paper trades (read-only for subscribers)

GET    /api/trades/paper/equity-curve
       → Time-series of cumulative P&L for charting
```

### 5.6 Market Data

```
GET    /api/market/{symbol}/intraday
       → 5-min OHLCV bars for chart rendering
       → Includes VWAP overlay data

GET    /api/market/{symbol}/prior-day
       → Prior day OHLCV + MA20/MA50 + day pattern

GET    /api/market/spy/context
       → SPY trend, support/resistance levels, regime
```

### 5.7 Custom Rules (Premium)

```
GET    /api/rules
       → User's custom alert rules

POST   /api/rules
       → Create custom rule
       → Body: { name, symbol_filter, conditions: [...], entry_logic,
                 stop_logic, target_logic, enabled }

PATCH  /api/rules/{id}
       → Update rule definition or toggle enabled

DELETE /api/rules/{id}

POST   /api/rules/{id}/backtest
       → Run rule against historical data
       → Body: { start_date, end_date, symbols }
       → Response: { trades: [...], stats: { win_rate, pnl, ... } }
```

### 5.8 User Preferences

```
GET    /api/preferences
       → Notification settings, position sizing, display preferences

PATCH  /api/preferences
       → Body: { email_alerts, sms_alerts, position_size,
                 spy_position_size, timezone }
```

---

## 6. Data Model Changes (SQLite → PostgreSQL)

### New Tables

```sql
-- User subscription tracking (Clerk is source of truth,
-- this caches tier for fast API checks)
CREATE TABLE subscriptions (
    user_id TEXT PRIMARY KEY,           -- Clerk user ID
    tier TEXT NOT NULL DEFAULT 'free',  -- free, pro, premium
    stripe_customer_id TEXT,
    current_period_end TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Per-user watchlists
CREATE TABLE user_watchlists (
    user_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, symbol)
);

-- Custom alert rules (premium)
CREATE TABLE custom_rules (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    symbol_filter TEXT[],               -- empty = all symbols
    conditions JSONB NOT NULL,          -- rule definition
    entry_logic JSONB,
    stop_logic JSONB,
    target_logic JSONB,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User notification preferences
CREATE TABLE user_preferences (
    user_id TEXT PRIMARY KEY,
    email_alerts BOOLEAN DEFAULT true,
    sms_alerts BOOLEAN DEFAULT false,
    position_size INTEGER DEFAULT 50000,
    spy_position_size INTEGER DEFAULT 100000,
    timezone TEXT DEFAULT 'America/New_York'
);
```

### Existing Tables — Scope Changes

| Table | Change |
|-------|--------|
| `users` | Replaced by Clerk — drop table |
| `session_tokens` | Replaced by Clerk JWTs — drop table |
| `alerts` | Add `user_id TEXT` for per-user signal delivery |
| `real_trades` | Add `user_id TEXT`, index on `(user_id, status)` |
| `paper_trades` | Keep as platform-wide (not user-scoped) — this is your track record |

---

## 7. Target Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Vercel (Frontend)                     │
│                                                         │
│  Next.js 15 + shadcn/ui + TradingView Lightweight Charts│
│  Clerk auth + billing components                        │
│  TanStack Query for API state                           │
└────────────────────┬────────────────────────────────────┘
                     │ HTTPS
                     ▼
┌─────────────────────────────────────────────────────────┐
│               Fly.io / Cloud Run (API)                  │
│                                                         │
│  FastAPI                                                │
│  ├── /api/signals/live  → SSE stream                    │
│  ├── /api/trades/*      → CRUD                          │
│  ├── /api/market/*      → yfinance + cache              │
│  └── /api/rules/*       → custom rules (premium)        │
│                                                         │
│  Analytics engine (unchanged Python modules):           │
│  ├── intraday_rules.py  → signal evaluation             │
│  ├── intraday_data.py   → market data fetch             │
│  ├── signal_engine.py   → scoring + trade plans         │
│  └── market_hours.py    → session timing                │
│                                                         │
│  Background worker (APScheduler or Celery):             │
│  └── monitor.py → poll cycle every 3 min                │
└────────┬──────────────────────────┬─────────────────────┘
         │                          │
         ▼                          ▼
┌─────────────────┐     ┌─────────────────────┐
│   PostgreSQL    │     │       Redis          │
│                 │     │                      │
│ alerts          │     │ live prices (TTL 60s)│
│ real_trades     │     │ signal cache         │
│ paper_trades    │     │ SSE pub/sub          │
│ subscriptions   │     │ rate limiting        │
│ custom_rules    │     │                      │
└─────────────────┘     └─────────────────────┘
```

---

## 8. Migration Phases

### Phase 1 — API Extraction (2-3 weeks)

**Goal:** FastAPI layer wrapping existing analytics. Streamlit still works.

- [ ] Create `api/` directory with FastAPI app
- [ ] Wrap signal evaluation as `/api/signals/today` endpoint
- [ ] Wrap real trade CRUD as `/api/trades/real/*` endpoints
- [ ] Wrap market data as `/api/market/*` endpoints
- [ ] Migrate SQLite → PostgreSQL (use Alembic for migrations)
- [ ] Add Redis for live price caching (replace yfinance TTL cache)
- [ ] Streamlit pages call API instead of importing DB directly
- [ ] Deploy API on Fly.io (or Docker Compose for local dev)

### Phase 2 — Next.js MVP (3-4 weeks)

**Goal:** 3 core pages live. Clerk auth + Pro tier billing active.

- [ ] Scaffold Next.js 15 with shadcn/ui
- [ ] Clerk integration (sign-up, login, subscription management)
- [ ] Signal Feed page (real-time via SSE, TradingView charts)
- [ ] Real Trades page (open positions, close/stop, P&L dashboard)
- [ ] Paper Trade Track Record page (public — marketing proof)
- [ ] Deploy on Vercel

### Phase 3 — Full Platform (4-6 weeks)

**Goal:** All features migrated. Streamlit retired.

- [ ] Scanner page with interactive trade plans
- [ ] Backtest page for built-in + custom rules
- [ ] Custom rule builder UI (Premium tier)
- [ ] Webhook delivery for Premium API access
- [ ] Trade history export (CSV/PDF)
- [ ] Admin dashboard (user management, system health)
- [ ] Sunset Streamlit

---

## 9. Beta Program (Current Phase)

### What to Do Now

1. **Keep running the system.** Accumulate paper trade data daily.
   Every week of track record makes the product more credible.

2. **Invite 3-5 friends.** They use the Streamlit app as-is.
   Give them accounts via the existing auth system.

3. **Collect feedback on:**
   - Which signals they actually trade on
   - What's confusing in the UI
   - What's missing that would make them pay
   - Mobile experience (Streamlit on phone)

4. **UI improvements for beta users (Streamlit):**
   - Fix any rough edges reported by testers
   - Ensure "Took It" / "Skip" flow is smooth
   - Make Real Trades dashboard clear and useful
   - Add better error messages and empty states

5. **Track these metrics:**
   - Paper trade win rate + total P&L (your proof)
   - Signals fired per day (volume)
   - How many signals beta users "Took It" on (engagement)
   - Time from signal → user action (latency matters)

### Beta User Onboarding

- Create accounts for each user
- Share the Streamlit URL (local network or Streamlit Cloud)
- Brief 5-min walkthrough: "Here's the signal feed, here's how Took It
  works, here's the Real Trades page"
- Set up a group chat for feedback (Signal/WhatsApp/Discord)

### Success Criteria Before Phase 1

- [ ] 60+ days of paper trade data
- [ ] Win rate > 55% sustained over 30+ days
- [ ] 3+ beta users actively using "Took It" flow
- [ ] Clear feedback on what to build / what to fix
- [ ] At least 2 users say "I'd pay for this"

---

## 10. Competitive Positioning

| Competitor | Price | What they offer | Our edge |
|-----------|-------|-----------------|----------|
| Trade Ideas | $118/mo | AI-powered stock scanner | Our rules are transparent + verifiable track record |
| TrendSpider | $49/mo | Automated chart analysis | We focus on actionable BUY/SHORT signals, not just analysis |
| Benzinga Pro | $117/mo | News + signals | We're mechanical (no news bias), cheaper, open rules |
| Stock Alarm | $9/mo | Price alerts only | We provide full trade plans (entry/stop/T1/T2) |

**Our moat:** Transparent, mechanical rules with a public paper trade track record.
Users can verify signal accuracy before subscribing. No black-box AI.

---

## 11. Open Questions

- [ ] Should custom rules be code-based (Python snippets) or visual (drag-and-drop conditions)?
- [ ] Do we want a mobile app eventually, or is responsive web enough?
- [ ] Should the paper trade track record be fully public (marketing) or gated (free tier signup)?
- [ ] What's the right data provider for production? (yfinance has rate limits — consider Polygon.io or Alpaca data API)
- [ ] Do we need a community/social feature (shared watchlists, signal discussion)?
