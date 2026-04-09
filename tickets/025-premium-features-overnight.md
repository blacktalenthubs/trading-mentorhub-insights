# Ticket 025: Premium Features — Overnight Build

**Created**: 2026-04-08
**Priority**: High — differentiation features for paid tier conversion
**Status**: In Progress
**Branch**: main (local only — DO NOT push to production until morning review)

## Goal

Build 5 features that make TradeCoPilot worth $49-99/mo. These create defensible value no competitor offers: data-driven confidence, automatic journaling, smart entry timing, strategy analytics, and curated daily game plans.

## Feature 1: Multi-Timeframe Confluence Meter

**What**: When daily, 4H, and intraday timeframes all agree on direction, flag the alert with a confluence score (1/3, 2/3, 3/3). Higher confluence = higher win probability.

**Implementation**:
- In `signal_engine.py` or `intraday_rules.py`, for each alert:
  - Check daily trend (price vs 20/50 EMA on daily)
  - Check 4H trend (price vs 20 EMA on 4H)
  - Check intraday signal direction
  - Score: 3/3 = "Strong Confluence", 2/3 = "Moderate", 1/3 = "Weak"
- Add `confluence_score` (int 1-3) and `confluence_label` to AlertResult
- Store in alerts table
- Display in Signal Feed as a visual meter (e.g., 3 dots or bars)
- Display in Telegram alerts

**Files to modify**:
- `analytics/signal_engine.py` — add confluence check
- `analytics/intraday_rules.py` — pass confluence to AlertResult
- `api/app/models/alert.py` — add confluence columns
- `api/app/schemas/alert.py` — expose confluence
- `web/src/types/index.ts` — add to Alert type
- `web/src/pages/TradingPage.tsx` — show confluence meter in Signal Feed
- `alerting/notifier.py` — include in Telegram message

## Feature 2: AI Trade Replay + Auto-Journal

**What**: After market close (4:35 PM ET), AI reviews every alert that fired today. For each: what happened after entry? Did it hit T1/T2? Did the stop get hit? Generates a journal entry per trade.

**Implementation**:
- New file: `analytics/trade_replay.py`
  - Query today's alerts with user_action = "took"
  - For each, fetch post-entry price action from yfinance
  - Use Anthropic API to generate 2-3 sentence replay
  - Store in new `trade_journal` table
- API endpoint: `GET /api/v1/trades/journal?date=YYYY-MM-DD`
- UI: Journal tab on Trades page showing daily entries
- Schedule: runs at 4:35 PM ET (after EOD cleanup, with daily review)

**Files to add**:
- `analytics/trade_replay.py` — replay logic + AI generation
- `api/app/models/journal.py` — TradeJournal model
- `api/app/schemas/journal.py` — response schema

**Files to modify**:
- `api/app/main.py` — add scheduler job
- `api/app/routers/trades.py` — add journal endpoint
- `web/src/pages/RealTradesPage.tsx` — journal section

## Feature 3: Smart Entry Refinement

**What**: Instead of "BUY SPY at $673", enhance alert messages with actionable entry timing: "Wait for pullback to $671.50 for better R:R" or "Enter now — volume 2.1x confirming breakout."

**Implementation**:
- In `intraday_rules.py`, enhance alert message generation:
  - If price is above entry and volume is high → "Enter now — momentum confirmed"
  - If price is above entry but volume is low → "Caution: low volume — wait for confirmation"
  - If price pulled back toward support → "Pullback entry available near $X"
  - Add volume context to every alert message (vol ratio)
- Add `entry_guidance` field to AlertResult

**Files to modify**:
- `analytics/intraday_rules.py` — enhance message generation
- `api/app/models/alert.py` — add entry_guidance column
- `alerting/notifier.py` — include guidance in Telegram

## Feature 4: Win Rate by Strategy Dashboard

**What**: Show historical performance per alert_type: win rate, avg R multiple, total alerts, best/worst performing. Let users filter to only high-win-rate strategies.

**Implementation**:
- API endpoint: `GET /api/v1/alerts/performance`
  - Query alerts joined with outcomes (T1 hit, T2 hit, stopped out)
  - Group by alert_type
  - Calculate: win_rate, avg_rr, total_count, wins, losses
- UI: Performance section on Trades page (or dedicated tab)
  - Table/cards showing each strategy's stats
  - Color-coded win rates (green >60%, amber 40-60%, red <40%)
  - Filter toggle: "Show only strategies with >X% win rate"

**Files to add**:
- `api/app/routers/performance.py` — performance endpoints
- `api/app/schemas/performance.py` — response schemas
- `web/src/components/PerformanceDashboard.tsx` — UI component

**Files to modify**:
- `api/app/main.py` — register router
- `web/src/api/hooks.ts` — add usePerformance hook
- `web/src/pages/RealTradesPage.tsx` — integrate dashboard

## Feature 5: Alert Sniper — Premarket Game Plan

**What**: At 9:00 AM ET, deliver personalized "Today's Top 3 Setups" with exact levels, ordered by confluence score. Not 20 alerts — just the 3 best opportunities for the day.

**Implementation**:
- New file: `analytics/game_plan.py`
  - Run full scan on user's watchlist
  - Score each by: confluence (Feature 1), distance to support, R:R ratio
  - Pick top 3
  - Generate brief with AI (or structured template)
- Telegram delivery: concise card per setup
- API endpoint: `GET /api/v1/intel/game-plan`
- UI: Game Plan card at top of Trading page (dismissible)

**Files to add**:
- `analytics/game_plan.py` — game plan generation
- `web/src/components/GamePlanCard.tsx` — UI card

**Files to modify**:
- `api/app/main.py` — scheduler job at 9:00 AM ET
- `api/app/routers/intel.py` — game-plan endpoint
- `web/src/pages/TradingPage.tsx` — show game plan card
- `alerting/notifier.py` — Telegram delivery

## Testing Plan

- All features testable locally with test user (test@test.com / test1234)
- Features 1, 3 work with live yfinance data (market hours or crypto 24/7)
- Feature 2 needs historical alerts (seed some test data if needed)
- Feature 4 needs alert history (use existing DB data)
- Feature 5 testable with manual trigger

## Review Checklist (Morning)

- [ ] Feature 1: Confluence meter shows on Signal Feed alerts
- [ ] Feature 2: Journal entries generated for test trades
- [ ] Feature 3: Alert messages include entry timing guidance
- [ ] Feature 4: Performance dashboard shows win rates by strategy
- [ ] Feature 5: Game plan endpoint returns top 3 setups
- [ ] All type checks pass (tsc --noEmit)
- [ ] Build succeeds (vite build)
- [ ] No changes pushed to production
