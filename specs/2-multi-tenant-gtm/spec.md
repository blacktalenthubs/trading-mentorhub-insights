# Feature Specification: Multi-Tenant Go-To-Market

**Status**: Draft
**Created**: 2026-04-03
**Branch**: 2-multi-tenant-gtm

---

## Overview

Transform TradeCoPilot from a single-admin tool into a production-grade multi-tenant SaaS platform. This is a holistic redesign covering user isolation, platform architecture, notification routing, monetization, and go-to-market strategy. The goal: 1,000+ concurrent users, each with their own watchlist, alerts, trades, and Telegram notifications — while maintaining the alert quality that makes the product valuable.

## Problem Statement

TradeCoPilot currently works for one user (admin). The alert engine, trade tracking, and notification system are all single-tenant:
- **Worker polls one watchlist** and records all alerts under one user_id
- **Trading tables** (paper_trades, real_trades, swing_trades) have no user_id — everyone shares the same portfolio
- **Notifications** go to one Telegram group — no per-user routing
- **Streamlit** runs a single background monitor thread — can't scale to concurrent users
- **No onboarding flow** — users register but can't self-serve into a working alert pipeline

Users sign up, see a dashboard, but get no alerts and can't trade independently. The product is a demo, not a SaaS.

---

## Part 1: Platform Architecture Decision

### The Streamlit Question

Streamlit is excellent for prototyping and single-user dashboards. For multi-tenant SaaS:

| Concern | Streamlit | FastAPI + React |
|---------|-----------|-----------------|
| Concurrent users | Single-threaded per session, shared runtime | Async, handles 1000+ concurrent |
| Background jobs | Global thread, no per-user isolation | APScheduler/Celery, per-user job queues |
| Real-time updates | st.rerun polling (slow, janky) | WebSocket/SSE (instant) |
| Mobile/PWA | No native support | Full PWA, Capacitor for iOS/Android |
| Auth/sessions | Cookie hack via JS injection | JWT/OAuth2, proper middleware |
| API-first | No API, tightly coupled UI+logic | API layer already exists (api/) |
| Deployment cost | One dyno per instance | Horizontal scaling, CDN for frontend |

**Recommendation**: Migrate to **FastAPI (API) + React (web)** — the api/ and web/ directories already exist with partial implementations. Streamlit becomes a legacy admin dashboard, not the user-facing product.

### FR-1: Platform Migration Strategy
- Phase 1: FastAPI becomes the primary backend for all user-facing features
- Phase 2: React frontend replaces Streamlit for users (Streamlit kept for admin tools only)
- Phase 3: Streamlit sunset — admin-only or removed entirely
- Acceptance: New users never touch Streamlit. All user flows go through React + FastAPI.

---

## Part 2: User Isolation & Multi-Tenancy

### Current State: What's Broken

| Table | Has user_id? | Status |
|-------|-------------|--------|
| alerts | Yes (migrated) | Needs per-user routing in worker |
| active_entries | Yes (optional) | Needs enforcement |
| cooldowns | Yes (optional) | Needs enforcement |
| watchlist | Yes | Working |
| paper_trades | **No** | **Blocked** — shared portfolio |
| real_trades | **No** | **Blocked** — shared portfolio |
| real_options_trades | **No** | **Blocked** — shared portfolio |
| swing_trades | **No** | **Blocked** — shared signals |
| swing_categories | **No** | **Blocked** |
| daily_plans | **No** | Global — may stay global (market data is shared) |

### FR-2: Complete Data Isolation
- Every trading table gets a `user_id` column with NOT NULL constraint
- All queries filter by authenticated user_id
- No user can see another user's trades, alerts, or portfolio
- Acceptance: User A's paper trades are invisible to User B. DB queries always include `WHERE user_id = ?`.

### FR-3: Per-User Alert Pipeline
- Worker polls **all subscribed users' watchlists** (deduplicated symbol fetches)
- Alert evaluation runs per-symbol (shared), but alert recording + notification routing is per-user
- Each user's alert preferences (categories, score filter) control their own notifications
- Acceptance: User A (watching NVDA, SPY) gets NVDA+SPY alerts to their Telegram. User B (watching META, QQQ) gets META+QQQ alerts to theirs. No cross-contamination.

### FR-4: Per-User Notification Routing
- Each user links their Telegram account via the `/start` bot command (already implemented in telegram_bot.py)
- Alerts route to each user's individual Telegram chat_id (not the group)
- Users who haven't linked Telegram get dashboard-only alerts (no push)
- Email alerts also route per-user via notification_email
- Acceptance: User A gets alerts in their Telegram DM. User B gets alerts in theirs. Group chat is optional broadcast.

---

## Part 3: Onboarding & Self-Service

### FR-5: User Onboarding Flow
- New user registers (email + password)
- Guided setup wizard:
  1. **Choose watchlist** — search and add symbols (max based on tier)
  2. **Link Telegram** — scan QR / click deep link to connect bot
  3. **Set alert preferences** — toggle trading patterns, set score filter
  4. **Choose subscription tier** — free (5 symbols, dashboard only) / pro ($X/mo, full alerts) / elite ($X/mo, AI + paper trading)
- Acceptance: New user goes from registration to receiving first alert in under 5 minutes.

### FR-6: Subscription & Billing
- Stripe integration for recurring billing
- Tier enforcement at API level (not just UI):
  - Free: 5 symbols watchlist, dashboard only, no Telegram alerts
  - Pro: 20 symbols, Telegram + email alerts, alert preferences
  - Elite: Unlimited symbols, AI narratives, paper trading, real trade tracking
- Upgrade/downgrade flows with proration
- Acceptance: Free user hitting symbol limit sees upgrade prompt. Pro user gets alerts. Elite user gets full AI features.

---

## Part 4: Go-To-Market Strategy

### Target Audience

| Segment | Profile | Pain Point | Value Prop |
|---------|---------|-----------|------------|
| **Day Traders** | Active, 2-10 trades/day, watches 5-10 symbols | Missing entries while watching charts, alert fatigue from TradingView | Real-time structural alerts with entry/stop/target — not just "price crossed MA" |
| **Swing Traders** | 1-3 trades/week, holds 2-5 days | No systematic way to track daily levels across portfolio | Daily plan + multi-day double bottom detection + exit management |
| **Learning Traders** | 6-18 months experience, paper trading | Information overload, no structured approach | AI narratives explaining WHY each setup works, score-based filtering |

### FR-7: Marketing & Growth Channels

**Content Marketing (Primary)**
- Daily pre-market brief published to Twitter/X (free, drives awareness)
- Weekly alert performance scorecards (transparency builds trust)
- "Alert of the Week" deep-dive posts showing entry → target → outcome with chart annotations
- YouTube/short-form video: "How TradeCoPilot caught the SPY double bottom" — real alerts, real charts

**Community & Virality**
- Telegram group as free tier (see alerts, discuss with community)
- "Powered by TradeCoPilot" watermark on shared alert screenshots
- Referral program: give 1 month free for each referral who subscribes
- Discord community for education + live market discussion

**Paid Acquisition**
- Twitter/X promoted posts targeting #daytrading, #stockalerts, #swingtrading
- Google Ads: "stock alert app", "day trading alerts", "support resistance alerts"
- Retargeting: visitors who hit landing page but didn't register

**Partnerships**
- Trading educators / YouTubers — white-label or affiliate model
- Prop firms — bulk licenses for funded traders who need systematic alerts
- Trading communities (Discord servers) — group plans

### FR-8: Competitive Positioning

| Competitor | Their Weakness | Our Advantage |
|-----------|---------------|---------------|
| TradingView alerts | Generic "price crossed X" — no context | Structural alerts with entry/stop/T1/T2 + AI narrative |
| TradeIdeas | Expensive ($200/mo), overwhelming scanner | Simple category toggles, mobile-first, $20-50/mo |
| StockTwits/Finviz | Social noise, no actionable alerts | Every alert has a trade plan (entry, stop, targets) |
| Manual charting | Time-consuming, miss setups while away | 24/7 monitoring, alerts while you sleep (crypto) or work |

### FR-9: Pricing Strategy

| Tier | Price | What You Get |
|------|-------|-------------|
| **Free** | $0 | 5 symbols, dashboard only, community Telegram group, delayed alerts |
| **Pro** | $29/mo | 20 symbols, real-time Telegram DM alerts, alert preferences, email alerts |
| **Elite** | $59/mo | Unlimited symbols, AI narratives, paper trading, real trade tracking, priority support |
| **Team** | $149/mo | 5 seats, shared watchlists, team Telegram group, admin dashboard |

Annual discount: 20% off (2 months free)

---

## Part 5: Technical Infrastructure

### FR-10: API-First Architecture
- All user-facing operations go through FastAPI endpoints
- JWT authentication with refresh tokens
- Rate limiting per tier (free: 10 req/min, pro: 60, elite: 120)
- WebSocket endpoint for real-time alert streaming (replaces Streamlit polling)
- Acceptance: React frontend communicates exclusively via API. No direct DB access from frontend.

### FR-11: Worker Architecture
- Single worker process polls all symbols (deduplicated across users)
- Alert evaluation is per-symbol (shared computation)
- Alert recording + notification is per-user (isolated)
- Worker scales horizontally by symbol partition (future: shard by symbol hash)
- Acceptance: 100 users watching 50 unique symbols = 50 data fetches, not 5000.

### FR-12: Database Strategy
- Postgres (Railway) as primary — already in production
- Add connection pooling (PgBouncer or built-in pool)
- All tables enforce user_id with row-level filtering
- Migration path: add user_id columns, backfill existing data to admin user, add NOT NULL constraint
- Acceptance: No query returns data across users without explicit admin override.

### FR-13: Mobile Strategy
- React PWA (installable, push notifications via service worker)
- Capacitor wrapper for iOS App Store / Google Play (web/ already has capacitor.config.ts)
- Push notifications via Firebase Cloud Messaging (supplements Telegram)
- Acceptance: User installs app from App Store, receives push alerts on phone.

---

## Success Criteria

- [ ] New user completes onboarding and receives first alert within 5 minutes
- [ ] 100 concurrent users with independent watchlists and alert routing
- [ ] Zero data leakage between users (audit verified)
- [ ] Alert delivery latency under 30 seconds from signal detection to Telegram
- [ ] Free-to-paid conversion rate above 5%
- [ ] Monthly churn below 8% for paid users
- [ ] App Store rating above 4.0 after 100 reviews

## Edge Cases

- User links Telegram from two devices — last link wins, previous unlinked
- User downgrades from Elite to Free — paper trades preserved but read-only, watchlist trimmed to 5
- Two users watch the same symbol — one data fetch, two alert records
- Worker restart during market hours — recover from last poll timestamp, no duplicate alerts (dedup)
- Stripe webhook failure — grace period of 3 days before downgrade

## Assumptions

- FastAPI + React migration builds on existing api/ and web/ codebases (not greenfield)
- Telegram Bot API supports DM alerts at scale (rate limit: 30 msgs/sec to different users)
- Railway can handle Postgres connection pooling for 1000+ users
- Stripe handles all billing/subscription logic (no custom billing engine)

## Constraints

- Must maintain backward compatibility during migration — existing Streamlit dashboard stays live until React is production-ready
- Alert quality standards from constitution (Principle 5) apply to all users equally
- Database migration must be zero-downtime (add columns, not rebuild tables)
- Budget: bootstrapped — minimize infrastructure costs, maximize organic growth

## Scope

### In Scope
- Platform architecture decision (Streamlit → FastAPI + React)
- Complete user data isolation (all tables)
- Per-user alert pipeline and notification routing
- Onboarding wizard
- Subscription tiers with Stripe billing
- Go-to-market strategy and positioning
- Mobile PWA + Capacitor wrapper
- Marketing channels and pricing

### Out of Scope
- Building the React frontend (separate implementation tickets)
- Stripe webhook implementation (separate ticket)
- iOS/Android App Store submission process
- Content creation (blog posts, videos)
- Hiring / team scaling
- Legal (terms of service, privacy policy, SEC disclaimers)

## Migration Strategy: V1/V2 Coexistence

### Architecture: Monorepo with Shared Core

```
trade-analytics/
├── analytics/               ← SHARED: business logic (both v1 + v2 import)
│   ├── intraday_rules.py    ← 8000+ lines of alert rules — no rewrite
│   ├── signal_engine.py     ← Scanner, scoring, daily plans
│   ├── market_data.py       ← yfinance data fetching
│   ├── intraday_data.py     ← Prior day, daily double bottoms
│   └── market_hours.py      ← Session phase, crypto hours
│
├── alerting/                ← SHARED: alert store, notifier, paper trader
│   ├── alert_store.py
│   ├── notifier.py
│   └── paper_trader.py
│
├── alert_config.py          ← SHARED: config, enabled rules, categories
├── db.py                    ← SHARED: DB layer (SQLite + Postgres)
│
├── ── V1 (Streamlit — stays live) ──
├── app.py                   ← Streamlit entry point
├── pages/                   ← Streamlit pages
├── monitor.py               ← V1 single-user worker
├── worker.py                ← V1 Railway worker entry
│
├── ── V2 (FastAPI + React — new development) ──
├── api/                     ← V2 FastAPI backend
│   ├── app/
│   │   ├── main.py          ← FastAPI app + multi-user scheduler
│   │   ├── background/
│   │   │   └── monitor.py   ← V2 multi-tenant worker (already exists)
│   │   ├── routers/         ← API endpoints
│   │   ├── models/          ← SQLAlchemy ORM
│   │   └── services/        ← Business logic wrappers
│   └── pyproject.toml
│
└── web/                     ← V2 React frontend
    ├── src/
    │   ├── pages/            ← Dashboard, Settings, etc.
    │   ├── components/       ← UI components
    │   └── api/              ← API client hooks
    ├── capacitor.config.ts   ← Mobile wrapper config
    └── package.json
```

### Key Principles

1. **V1 keeps running untouched** — Streamlit + monitor.py + Railway worker. No changes that risk production alerts.

2. **V2 builds on existing api/ and web/** — not a greenfield rewrite. The FastAPI app and React frontend already have partial implementations.

3. **Shared core is the bridge** — `analytics/`, `alerting/`, `alert_config.py`, `db.py` are imported by both V1 and V2. Improvements to alert rules benefit both immediately.

4. **Same database** — V2 connects to the same Railway Postgres. Data isolation is additive (new columns, not new tables). Both V1 and V2 can coexist reading/writing the same DB.

5. **Cutover is a deployment swap** — when V2 is ready:
   - Railway: swap worker.py → api/app/main.py (includes multi-user scheduler)
   - DNS: point tradesignalwithai.com → React frontend (Vercel/Netlify)
   - Streamlit: keep running as admin-only tool or sunset

### What V2 Gets for Free (from shared core)

| Component | Lines of Code | What V2 Inherits |
|-----------|--------------|-------------------|
| `analytics/intraday_rules.py` | 8,500+ | All 60+ alert rules, scoring, targets |
| `analytics/signal_engine.py` | 500+ | Scanner, daily plans, S/R levels |
| `alerting/alert_store.py` | 400+ | Alert dedup, cooldowns, ACK system |
| `alerting/notifier.py` | 420+ | Telegram + email delivery |
| `alert_config.py` | 700+ | Enabled rules, categories, thresholds |
| `db.py` | 1,800+ | All CRUD, Postgres wrapper, migrations |

**V2 does NOT rewrite any of this.** It imports and uses it.

### What V2 Builds New

| Component | What | Why Can't Reuse V1 |
|-----------|------|--------------------|
| Multi-user worker | Per-user watchlist polling + alert routing | V1 monitor is single-user |
| JWT auth | Proper token-based auth for API | V1 uses cookie/session hack |
| WebSocket alerts | Real-time alert stream to frontend | V1 uses st.rerun polling |
| React frontend | All user-facing pages | V1 is Streamlit (can't scale) |
| Stripe billing | Subscription management + webhooks | V1 has stub fields only |
| Onboarding flow | Guided setup wizard | V1 has no onboarding |
| Push notifications | FCM for mobile alerts | V1 has no mobile support |

## Implementation Phases (High-Level)

| Phase | Duration | Deliverable | V1 Impact |
|-------|----------|-------------|-----------|
| **Phase 1: Data Isolation** | 2 weeks | Add user_id to trading tables, backfill to admin | None — additive columns |
| **Phase 2: API Completion** | 3 weeks | All FastAPI endpoints, JWT auth, multi-user worker | None — separate process |
| **Phase 3: React MVP** | 4 weeks | Dashboard, watchlist, settings, alert stream | None — separate frontend |
| **Phase 4: Billing** | 2 weeks | Stripe integration, tier enforcement | None — API-only |
| **Phase 5: Onboarding** | 1 week | Setup wizard, Telegram linking | None — new pages |
| **Phase 6: Mobile** | 2 weeks | PWA, push notifications, Capacitor build | None — web/ only |
| **Phase 7: Cutover** | 2 weeks | DNS swap, worker swap, beta migration | **V1 sunset begins** |

**V1 stays live and untouched through Phases 1-6.** Phase 7 is the only phase that affects production.

## Clarifications

_Added during `/speckit.clarify` sessions_
