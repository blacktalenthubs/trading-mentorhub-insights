# Implementation Plan: AI Platform Marketing — Landing Page + Evidence Board

**Spec**: [spec.md](spec.md)
**Branch**: 29-ai-platform-marketing
**Created**: 2026-04-11

## Technical Context

| Item | Value |
|------|-------|
| Language | Python 3.9+ (API), TypeScript/React (frontend) |
| Framework | FastAPI (API), React + Vite (web) |
| Database | SQLite (local) / Postgres (production) |
| Notifications | Telegram Bot API |
| Market Data | Alpaca (equities), Coinbase (crypto) |
| AI | Anthropic API (Haiku for replay narration) |
| Deployment | Railway (API + worker) |

### Dependencies
- No new dependencies — uses existing React, FastAPI, Anthropic

### Integration Points
- Existing `GET /api/v1/intel/public-track-record` endpoint (win rates by pattern)
- Existing `GET /api/v1/intel/trade-replay/{alert_id}` endpoint (AI narration)
- Existing `GET /api/v1/intel/trade-journal` endpoint (outcome data)
- Existing chart replay component (`web/src/components/ChartReplay`)
- Landing page: `web/src/pages/LandingPage.tsx`

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| Protect Business Logic | PASS | Not modifying alert/signal logic — read-only data display |
| Test-Driven Development | PASS | Tests for new API endpoint, component rendering |
| Local First | PASS | Test on localhost:5173 before production |
| Database Compatibility | PASS | Read-only queries, existing tables, `?` params |
| Alert Quality | PASS | Not touching alert logic |
| Single Notification Channel | PASS | Not touching notifications |

## Solution Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Landing Page (public, no auth)                          │
│                                                          │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────┐ │
│  │ Hero Section  │  │ Core Values   │  │ Feature List │ │
│  │ (new headline)│  │ (5 pillars)   │  │ (8, not 12)  │ │
│  └──────────────┘  └───────────────┘  └──────────────┘ │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Evidence Board Preview (top 3 recent trades)     │   │
│  │ → Link to /proof for full page                    │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ /proof — AI Evidence Board (public, no auth)             │
│                                                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │ Filters: Symbol | Setup Type | Outcome | Date   │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌─────────────────┐  ┌─────────────────┐               │
│  │ Evidence Card    │  │ Evidence Card    │  ...         │
│  │ ┌─────────────┐ │  │ ┌─────────────┐ │               │
│  │ │ Alert Info   │ │  │ │ Alert Info   │ │               │
│  │ │ Entry/Stop   │ │  │ │ Entry/Stop   │ │               │
│  │ │ T1/T2       │ │  │ │ T1/T2       │ │               │
│  │ ├─────────────┤ │  │ ├─────────────┤ │               │
│  │ │ Chart Replay │ │  │ │ Chart Replay │ │               │
│  │ │ (animated)   │ │  │ │ (animated)   │ │               │
│  │ ├─────────────┤ │  │ ├─────────────┤ │               │
│  │ │ AI Analysis  │ │  │ │ AI Analysis  │ │               │
│  │ │ Outcome/P&L  │ │  │ │ Outcome/P&L  │ │               │
│  │ └─────────────┘ │  │ └─────────────┘ │               │
│  └─────────────────┘  └─────────────────┘               │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│ API: GET /api/v1/intel/evidence-board                    │
│ (public, no auth)                                        │
│                                                          │
│ Returns: alerts with outcome + replay_text + chart bars  │
│ Filters: ?symbol=&setup_type=&outcome=&days=             │
│ Source: alerts table + trade_journal + real_trades        │
└─────────────────────────────────────────────────────────┘
```

### Data Flow
1. User visits `/proof` (public, no login)
2. React page calls `GET /api/v1/intel/evidence-board?days=30`
3. API queries alerts that have resolved outcomes (T1 hit, stopped, etc.)
4. For each alert: joins with trade_journal for AI replay text
5. Returns array of evidence cards with all fields
6. Frontend renders cards with embedded mini chart replay + outcome badge

### Files to Modify

| File | Change | Risk |
|------|--------|------|
| `web/src/pages/LandingPage.tsx` | Update hero, remove 3 unbuilt features, add core values, add evidence preview | Med |
| `web/src/App.tsx` or router | Add `/proof` route (public) | Low |
| `api/app/routers/intel.py` | Add `GET /evidence-board` endpoint (public) | Low |

### Files to Add

| File | Purpose |
|------|---------|
| `web/src/pages/EvidenceBoardPage.tsx` | Public proof page with evidence cards |
| `web/src/components/EvidenceCard.tsx` | Single evidence card component |

## Implementation Approach

### Phase 1: Evidence Board API
1. Add `GET /api/v1/intel/evidence-board` endpoint to `api/app/routers/intel.py`
   - Public (no auth required)
   - Query alerts with `user_action = 'took'` AND outcome resolved (T1 hit, T2 hit, or stopped)
   - Join with trade_journal for replay_text
   - Return: symbol, setup_type, direction, entry, stop, t1, t2, conviction, outcome, pnl_r, replay_text, alert_time, outcome_time
   - Params: `days` (default 30), `symbol`, `setup_type`, `outcome` (win/loss/all)
   - Limit: last 20 resolved trades

### Phase 2: Evidence Board Frontend
1. Create `EvidenceBoardPage.tsx` — public page at `/proof`
   - Filter bar: symbol dropdown, setup type dropdown, outcome toggle (all/wins/losses)
   - Grid of evidence cards
   - Each card shows: alert info, outcome badge (green WIN / red LOSS), P&L, AI analysis
   - Shareable URL per card: `/proof?id={alert_id}`
2. Create `EvidenceCard.tsx` — individual card component
   - Compact: setup name, symbol, direction, entry/stop/T1, outcome, P&L
   - Expandable: full AI replay text
   - Optional: mini chart (static image or simplified replay)

### Phase 3: Landing Page Updates
1. Update hero headline in `LandingPage.tsx`
   - Replace "Your chart analyst that never sleeps" with outcome-focused headline
2. Remove 3 unbuilt features (Options Flow, Sector Rotation, Catalyst Calendar)
3. Add core values section (5 pillars)
4. Add evidence board preview (top 3 recent winning trades with link to /proof)
5. Update SEO meta tags (title, description, keywords → "AI trading")
6. Add "WAIT signals" as a marketed feature

## Test Plan

### Unit Tests
- [ ] Evidence board API returns correct structure with all required fields
- [ ] Evidence board API filters by symbol, setup_type, outcome correctly
- [ ] Evidence board API returns only resolved trades (not open/pending)
- [ ] Evidence board API respects days parameter
- [ ] Evidence board API works without auth (public endpoint)

### Integration Tests
- [ ] Evidence board page loads at /proof without login
- [ ] Evidence cards render with all fields populated
- [ ] Filter controls update displayed cards
- [ ] Landing page loads without errors after feature removal

### E2E Validation
1. **Setup**: Start local API + dev server, ensure DB has resolved trades
2. **Action**: Visit localhost:5173/proof
3. **Verify**: Page shows evidence cards with setup type, entry/stop/T1, outcome, P&L, AI analysis
4. **Verify**: Filter by "wins only" — only green cards shown
5. **Verify**: Landing page no longer mentions Options Flow, Sector Rotation, Catalyst Calendar
6. **Cleanup**: None needed (read-only)

## Out of Scope

- Implementing new AI initiatives (confidence stars, autopilot, education game — separate specs)
- Paid advertising campaigns
- Collecting real testimonials (manual task, not code)
- Blog/content calendar execution
- Pricing changes
- Mobile app

## Research Notes

### Decision 1: Evidence Board Data Source
- **Decision**: Use existing alerts + trade_journal tables
- **Rationale**: Data already flows: alert fires → user clicks Took → T1/T2/Stop detected → trade_journal entry created with replay_text
- **Alternatives**: New dedicated table (unnecessary duplication), external analytics service (overkill)

### Decision 2: Chart Display in Evidence Cards
- **Decision**: Start with AI replay text only (no embedded chart animation)
- **Rationale**: The existing chart replay component requires authenticated chart data fetching. For the public evidence board, AI's written analysis + price data is sufficient proof. Chart replay embed can be added later.
- **Alternatives**: Static chart screenshot (requires headless rendering), full interactive replay (requires auth bypass for chart data)

### Decision 3: Public API Security
- **Decision**: Evidence board endpoint is fully public (no auth), but only returns aggregated/anonymized data — no user IDs, no personal trade data
- **Rationale**: The whole point is public proof. User-specific data is stripped. Only alert metadata + outcomes shown.
- **Alternatives**: Auth-required with public share links (adds friction), rate-limited public (premature optimization)
