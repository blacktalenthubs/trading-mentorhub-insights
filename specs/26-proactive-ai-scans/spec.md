# Feature Specification: AI-Powered Alert Engine (Parallel to Rule-Based)

**Status**: Draft
**Created**: 2026-04-10
**Author**: Claude (via /speckit.specify)
**Priority**: High — AI services are the biggest product value
**Depends on**: Spec 25 (AI actionable services), Spec 23 (alert engine redesign)

## Overview

The AI Coach produces better entry/exit analysis than 78 hand-coded rules — but only when users manually ask. This feature makes the AI proactive: it scans watchlist symbols automatically on a schedule, identifies setups at key levels, and delivers actionable alerts alongside the existing rule-based engine. Both systems run in parallel, recording to the same database. After 1-2 weeks of data, we evaluate which produces more accurate entries and iterate.

## Problem Statement

Two problems converge:

1. **Rule engine is fragile**: 78 rules with proximity thresholds, gates, cooldowns, and filters that keep breaking. Every "fix" introduces side effects. 5 days of fixes (April 5-10) destabilized the system.

2. **AI Coach is on-demand only**: Users must open the Coach tab, select a symbol, and type a question. By then the setup may be gone. The AI reads charts better than the rules — it understands context, structure, and gives cleaner entries — but it's passive.

**Solution**: Make the AI proactive. Run the same Coach analysis automatically for every watchlist symbol on a schedule. Record results as alerts. Users get AI-powered entries without asking.

## Functional Requirements

### FR-1: Scheduled AI Scan Job
- A new background job `ai_scan_cycle()` runs on a configurable schedule during market hours
- Default schedule: every 15 min during opening range (9:30-10:00) and power hour (3:00-4:00), every 30 min during core session (10:00-3:00)
- For crypto symbols: every 30 min, 24/7
- Job runs inside the existing worker process (Railway), using the APScheduler already in place
- Acceptance: Scans execute on schedule without impacting rule-based poll cycle performance

### FR-2: Per-Symbol AI Analysis
- For each unique symbol across all users' watchlists, fetch:
  - Last 20 OHLCV bars on 5-min timeframe (intraday context)
  - Last 20 OHLCV bars on 1-hour timeframe (structure context)
  - Key levels: PDH, PDL, prior day close, MAs (20/50/100/200), VWAP, weekly high/low
  - RSI14
- Build a context prompt identical to the Coach system prompt (same prompt, same format)
- Call Claude API (Haiku for free tier, Sonnet for Pro/Premium)
- Parse structured output: CHART READ + ACTION (Direction, Entry, Stop, T1, T2)
- Acceptance: AI analysis produces the same quality output as the interactive Coach

### FR-3: AI Scan Alert Recording
- If AI identifies an actionable entry (Direction = LONG or SHORT, not WAIT):
  - Create an alert record with `alert_type = 'ai_scan_long'` or `alert_type = 'ai_scan_short'`
  - Store in the same `alerts` table used by rule-based engine
  - Include: symbol, direction, price, entry, stop, target_1, target_2, score, message
  - Message format: `"AI: {setup name} — {chart read summary}"`
  - Score: derived from AI's conviction (HIGH=85, MEDIUM=65, LOW=45)
- If AI says WAIT or NO_TRADE:
  - Record with `alert_type = 'ai_scan_wait'` for analysis (no notification)
- Acceptance: Every scan produces a DB record — actionable entries AND wait decisions

### FR-4: Deduplication
- Same AI setup for the same symbol should not fire repeatedly every cycle
- Dedup key: `(symbol, ai_scan_direction, entry_price_bucket)` per session
- If the AI identifies the same setup at the same level on consecutive scans, skip
- If price moves to a new level and AI identifies a new setup, fire
- Acceptance: Users receive 1-3 AI scan alerts per symbol per day, not 16

### FR-5: Signal Feed Integration
- AI scan alerts appear in the same Signal Feed as rule-based alerts
- Visual distinction: purple "AI SCAN" badge (vs green "BUY" / orange "RESISTANCE")
- Same interaction: "Took It" / "Skip" / "Exit" buttons
- Sortable/filterable by source (rule-based vs AI scan)
- Acceptance: Users see both sources side-by-side in the Signal Feed

### FR-6: Telegram Delivery
- AI scan alerts sent to Telegram with clean format:
  ```
  AI SCAN — SPY $673.50
  Entry: $673.50 — 50MA support
  Stop: $671.80 | T1: $677.08 | T2: $681.00
  Conviction: HIGH
  ```
- Opt-in per user (default: ON for Pro/Premium, OFF for free tier)
- Respect existing notification preferences (quiet hours, email toggle)
- Acceptance: AI scan alerts delivered via same channels as rule-based alerts

### FR-7: Comparison Analytics
- New dashboard section: "AI vs Rules" comparison
- For each symbol, show side-by-side:
  - Rule-based alerts fired vs AI scan alerts fired
  - Entry accuracy (was entry at a real key level?)
  - Win rate (of alerts user "Took")
  - False signal rate
  - Missed setups (one system caught it, the other didn't)
- Queryable by date range, symbol, alert source
- Acceptance: After 1 week, data clearly shows which source is more accurate

## User Scenarios

### Scenario 1: AI Scan Identifies Support Bounce
**Actor**: Trader with SPY on watchlist
**Trigger**: 10:30 AM scan cycle runs
**Steps**:
1. AI fetches SPY 5m bars — price pulling back from $681 toward 50MA at $673
2. AI analysis: "CHART READ: SPY pullback to 50MA support. ACTION: LONG at $673.50, Stop $671.80, T1 $677"
3. Alert created: `ai_scan_long` for SPY at $673.50
4. User sees "AI SCAN — SPY LONG $673.50" in Signal Feed and Telegram
5. User also sees rule-based "MA bounce 50" alert at $673.54 from the same cycle
6. Both alerts are actionable — user picks the one they trust
**Expected Outcome**: AI and rules agree on the same setup — high confidence for the user

### Scenario 2: AI Says Wait, Rules Fire
**Actor**: Trader with AAPL on watchlist
**Trigger**: 11:00 AM scan cycle
**Steps**:
1. AI fetches AAPL — price at $260, between 50MA ($258) and PDH ($261)
2. AI analysis: "CHART READ: AAPL mid-range, no clear setup. ACTION: WAIT. Watch $258 (50MA) for bounce or $261 (PDH) for breakout."
3. Alert recorded as `ai_scan_wait` (no notification)
4. Meanwhile, rule-based engine fires "ema_bounce_20" at $260 (20MA touch)
5. User only sees the rule-based alert — AI filtered it as not actionable
**Expected Outcome**: AI is more selective than rules. Comparison data shows which was right.

### Scenario 3: AI Catches What Rules Miss
**Actor**: Trader with TSLA on watchlist
**Trigger**: 2:30 PM scan cycle
**Steps**:
1. TSLA approaching VWAP from below after morning selloff
2. Rule-based VWAP reclaim hasn't fired (too strict max distance, or dedup blocked it)
3. AI analysis: "CHART READ: TSLA reclaiming VWAP at $345. ACTION: LONG at $345, Stop $342, T1 $350"
4. AI scan alert fires — user gets the entry the rules missed
**Expected Outcome**: AI fills gaps in rule coverage

## Key Entities

| Entity | Description | Key Fields |
|--------|-------------|------------|
| AIScanResult | Parsed AI analysis for one symbol | symbol, direction, entry, stop, t1, t2, conviction, chart_read, raw_response |
| AIScanAlert | Alert record from AI scan | Same as Alert, alert_type starts with `ai_scan_` |
| AIScanLog | Audit trail of all scans | scan_time, symbols_scanned, alerts_created, cost_tokens, duration_ms |

## Technical Architecture

```
┌─────────────────────────────────────────────────┐
│               Worker Process (Railway)           │
│                                                  │
│  ┌──────────────┐     ┌──────────────────────┐  │
│  │ Rule Engine   │     │ AI Scan Engine        │  │
│  │ (poll cycle)  │     │ (scheduled job)       │  │
│  │ Every 5 min   │     │ Every 15-30 min       │  │
│  │ evaluate_rules│     │ ai_scan_cycle()       │  │
│  └──────┬───────┘     └──────────┬───────────┘  │
│         │                        │               │
│         │    ┌───────────┐       │               │
│         └───>│ alerts DB │<──────┘               │
│              │ (unified) │                       │
│              └─────┬─────┘                       │
│                    │                             │
│         ┌──────────┼──────────┐                  │
│         │          │          │                  │
│    ┌────▼───┐ ┌───▼────┐ ┌──▼──────┐           │
│    │Telegram│ │Signal  │ │Compare  │           │
│    │Notify  │ │Feed API│ │Analytics│           │
│    └────────┘ └────────┘ └─────────┘           │
└─────────────────────────────────────────────────┘
```

### Shared Resources
- **OHLCV data**: Both engines fetch from yfinance (equities) / Coinbase (crypto). AI scan caches bars to avoid duplicate fetches within the same cycle.
- **Key levels**: `fetch_prior_day()` output shared between both engines.
- **Alerts table**: Unified storage. `alert_type` prefix distinguishes source (`ai_scan_long` vs `ma_bounce_50`).
- **Notification pipeline**: Same Telegram/email delivery. Same user preferences.

### AI Scan Prompt
Identical to the Coach prompt (`trade_coach.py:format_system_prompt`), but:
- No user position data (scans are market-level, not user-specific)
- No paper trading context
- No session history
- Just: OHLCV bars + key levels + MAs + RSI → CHART READ + ACTION

### Cost Optimization
- **Symbol dedup**: If 3 users watch SPY, scan once, create alert per user
- **Haiku by default**: $0.001 per scan. 10 symbols x 16 scans/day = $0.16/day
- **Prompt caching**: System prompt cached (Anthropic ephemeral cache) — ~90% savings
- **Skip if no change**: If price hasn't moved >0.3% since last scan, skip AI call
- **Batch context**: Fetch all symbols' bars once, then run AI serially

## Scan Schedule

| Market Phase | ET Time | Interval | Scans/Symbol |
|-------------|---------|----------|-------------|
| Pre-market | 9:00 AM | Once | 1 |
| Opening range | 9:30-10:00 | 15 min | 2 |
| Morning | 10:00-12:00 | 30 min | 4 |
| Lunch | 12:00-2:00 | 30 min | 4 |
| Afternoon | 2:00-3:00 | 30 min | 2 |
| Power hour | 3:00-4:00 | 15 min | 4 |
| **Total** | | | **~17 scans/symbol/day** |

## Cost Model

| Tier | Model | Symbols | Scans/Day | Cost/Day | Cost/Month |
|------|-------|---------|-----------|----------|------------|
| Free | Haiku | 5 | 85 | $0.08 | $2.50 |
| Pro | Haiku | 10 | 170 | $0.16 | $5.00 |
| Premium | Sonnet | 15 | 255 | $2.50 | $75.00 |

At $49/mo (Pro) and $99/mo (Premium), AI scan cost is 5-10% of subscription revenue. Acceptable.

## Success Criteria

After 1 week of parallel operation:
- [ ] AI scan runs on schedule for all watchlist symbols
- [ ] Entries are at key levels (not current price) — verified manually
- [ ] AI scan win rate comparable or better than rule-based (when users "Took")
- [ ] AI scan catches setups that rules missed (at least 3 per week)
- [ ] Cost stays within budget ($0.50/day for Haiku tier)
- [ ] Users can distinguish AI scan alerts from rule-based in Signal Feed
- [ ] No performance degradation to the 5-min rule-based poll cycle

## Scope

### In Scope
- Scheduled AI scan job in worker
- Per-symbol AI analysis with structured output parsing
- Alert recording with `ai_scan_*` alert types
- Signal Feed integration with purple "AI SCAN" badge
- Telegram delivery (opt-in)
- Comparison analytics (AI vs rules side-by-side)
- Cost tracking per scan

### Out of Scope
- Replacing the rule-based engine (parallel only — data decides)
- Real-time streaming AI (every bar) — too expensive
- Per-user customized scans (same market analysis for all users)
- AI-powered exit management (separate spec)
- Mobile push notifications (use existing Telegram)

## Edge Cases

- **Market holiday**: Skip scan if market is closed (use existing `is_market_hours()`)
- **API rate limit**: If Claude API returns 429, retry with exponential backoff (max 3 retries)
- **yfinance outage**: If OHLCV fetch fails, skip symbol for this cycle (log warning)
- **AI returns invalid format**: If parsing fails, record raw response as `ai_scan_error` for debugging
- **Symbol removed from watchlist mid-scan**: Skip — next cycle picks up updated watchlist
- **All users on free tier**: Use Haiku only. Sonnet upgrade requires Pro/Premium subscription.

## Assumptions

- The existing APScheduler in the worker can handle an additional scheduled job
- Claude Haiku response time is <3 seconds per symbol (fast enough for 10 symbols in <30 seconds)
- The Coach prompt works without user-specific context (position, history)
- Users want both AI and rule-based alerts in the same feed (not separate tabs)
- 1 week of parallel data is sufficient to evaluate accuracy differences

## Constraints

- **Protected files**: `api/app/background/monitor.py` requires impact analysis before modification
- AI scan job must NOT delay or interfere with the 5-min rule-based poll cycle
- AI scan must respect existing Telegram rate limits and notification preferences
- Cost per user must stay under 10% of subscription revenue
- Prompt must be identical to Coach (single source of truth for AI trading logic)

## Clarifications

_To be added during /speckit.clarify sessions._
