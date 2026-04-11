# Implementation Plan: AI Entry Detection Engine

**Spec**: [spec.md](spec.md)
**Branch**: 27-ai-trading-intelligence
**Created**: 2026-04-11

## Technical Context

| Item | Value |
|------|-------|
| Language | Python 3.9+ |
| Framework | FastAPI (API), APScheduler (worker) |
| Database | SQLite (local) / Postgres (production) |
| Notifications | Telegram Bot API |
| Market Data | Alpaca (equities), Coinbase (crypto), yfinance (fallback) |
| AI | Anthropic API (Haiku for day trades, Sonnet for swing trades) |
| Deployment | Railway (worker) |

### Dependencies
- No new dependencies — uses existing anthropic, alpaca-py, yfinance

### Integration Points
- `analytics/ai_scanner.py` — existing AI scanner to enhance
- `api/app/background/monitor.py` — existing poll cycle to integrate with
- `alerting/notifier.py` — existing Telegram notification
- `alert_config.py` — configuration constants

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| Protect Business Logic | PASS | Enhancing ai_scanner.py (not modifying rule engine). Impact: AI becomes primary, rules remain as fallback. |
| Test-Driven Development | PASS | Tests for prompt builders, output parsing, dedup logic |
| Local First | PASS | Test locally before any production push |
| Database Compatibility | PASS | Uses existing Alert model (same SQLite/Postgres compat) |
| Alert Quality | PASS | Spec requires entry within 0.5% of key level, structural stops |
| Single Notification Channel | PASS | Uses existing Telegram notification path |

## Solution Architecture

```
┌──────────────────────────────────────────────────────┐
│ APScheduler (every 3-5 min)                          │
│                                                       │
│  ┌─────────────────────┐  ┌────────────────────────┐ │
│  │ Day Trade Scanner    │  │ Swing Trade Scanner    │ │
│  │ (Haiku, every 3 min) │  │ (Sonnet, 2x/day)      │ │
│  │                      │  │                         │ │
│  │ Specialized prompt:  │  │ Specialized prompt:     │ │
│  │ - PDL hold/reclaim   │  │ - Daily EMA close above │ │
│  │ - PDH breakout+vol   │  │ - Weekly level hold     │ │
│  │ - VWAP hold          │  │ - Trend pullback to EMA │ │
│  │ - Double bottom hold │  │                         │ │
│  │ - MA/EMA holds       │  │                         │ │
│  └──────┬───────────────┘  └──────────┬─────────────┘ │
│         │                              │               │
│         ▼                              ▼               │
│  ┌─────────────────────────────────────────────────┐  │
│  │ Signal Output (standardized)                     │  │
│  │ Direction · Entry · Stop · T1 · T2 · Conviction │  │
│  └──────────┬──────────────────────────────────────┘  │
│             │                                          │
│             ▼                                          │
│  ┌──────────────────┐  ┌───────────────────────────┐  │
│  │ Dedup Engine      │  │ Regime Filter             │  │
│  │ (symbol, setup,   │  │ (suppress MEDIUM in       │  │
│  │  level, session)  │  │  CHOPPY regime)           │  │
│  └──────┬───────────┘  └──────────┬────────────────┘  │
│         │                          │                   │
│         ▼                          ▼                   │
│  ┌─────────────────────────────────────────────────┐  │
│  │ Alert DB + Telegram                              │  │
│  └─────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### Data Flow
1. Scheduler triggers day trade scan every 3 min (market hours)
2. For each symbol: fetch intraday bars, prior day levels, compute VWAP
3. Build specialized day trade prompt with specific entry rules
4. Claude Haiku evaluates → returns structured signal
5. Parse response, check dedup, check regime filter
6. If passes: create Alert, send Telegram
7. Swing trade scan runs 2x/day (9:05 AM pre-market, 3:30 PM pre-close)

### Files to Modify

| File | Change | Risk |
|------|--------|------|
| `analytics/ai_scanner.py` | Rewrite with specialized day/swing prompts, better parsing | Med |
| `api/app/main.py` | Update scheduler jobs for day/swing cadence | Low |
| `alert_config.py` | Add AI scanner config constants | Low |

### Files to Add

| File | Purpose |
|------|---------|
| `analytics/ai_day_scanner.py` | Day trade specialized scanner (PDL, PDH, VWAP, MA holds) |
| `analytics/ai_swing_scanner.py` | Swing trade scanner (daily EMA, weekly levels) |
| `tests/test_ai_scanner_v2.py` | Tests for new scanner prompts and parsing |

## Implementation Approach

### Phase 1: Day Trade Scanner
1. Create `analytics/ai_day_scanner.py` with specialized prompt for day trade entry rules
2. Build prompt that includes specific confirmation criteria (2-3 bar hold, volume thresholds)
3. Parser extracts: direction, setup_type, entry, stop, T1, T2, conviction
4. Dedup: (symbol, setup_type, level_bucket) per session
5. Regime filter: suppress MEDIUM in CHOPPY
6. Wire into scheduler (replace current ai_scanner interval job)

### Phase 2: Swing Trade Scanner
1. Create `analytics/ai_swing_scanner.py` with Sonnet prompt for daily chart analysis
2. Fetch daily bars (not intraday) + weekly levels
3. Focus on: EMA close above, weekly hold, trend pullback
4. Run 2x/day (pre-market 9:05 AM, pre-close 3:30 PM)
5. Label output as "SWING TRADE" in Telegram

### Phase 3: WATCH Alerts + Resistance Warnings
1. Add WATCH detection: price within 0.5-1.0% of key level
2. Send anticipatory alerts (no Took/Skip buttons)
3. Resistance warnings when approaching overhead levels
4. Dedup: one per level per session

## Test Plan

### Unit Tests
- [ ] Day trade prompt builder includes all required levels (PDL, PDH, VWAP, MAs)
- [ ] Day trade prompt includes specific confirmation rules
- [ ] Swing prompt includes daily EMAs and weekly levels
- [ ] Parser extracts all fields from well-formed response
- [ ] Parser handles missing fields gracefully
- [ ] Parser handles malformed prices (commas, no $, etc.)
- [ ] Dedup correctly blocks same setup at same level
- [ ] Dedup allows same setup at different levels
- [ ] Regime filter suppresses MEDIUM in CHOPPY
- [ ] Regime filter passes HIGH in CHOPPY

### Integration Tests
- [ ] Day scan cycle fetches data and calls Claude successfully
- [ ] Swing scan cycle uses Sonnet model
- [ ] Alert records created in DB with correct fields
- [ ] Telegram notification sent with correct format

### E2E Validation
1. **Setup**: Start local API server, ensure ANTHROPIC_API_KEY set
2. **Action**: Add ETH-USD to watchlist, trigger manual scan
3. **Verify**: Check Telegram for properly formatted signal with entry/stop/T1/T2
4. **Cleanup**: Remove test alerts from DB

## Out of Scope

- Removing the rule engine (stays as fallback)
- Portfolio risk management
- Behavioral coaching
- Trade journaling
- News sentiment integration
- Performance dashboard changes

## Research Notes

_See research from AI scanner exploration above — existing implementation provides the foundation._
