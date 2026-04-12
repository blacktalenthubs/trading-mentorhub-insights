# Implementation Plan: Swing Scanner Price Refresh

**Spec**: [spec.md](spec.md)
**Branch**: 23-swing-price-refresh
**Created**: 2026-04-08

## Technical Context

| Item | Value |
|------|-------|
| Language | Python 3.9+ (backend), TypeScript (frontend) |
| Framework | FastAPI (API), React + Tailwind (frontend) |
| Database | SQLite (local) / Postgres (production) |
| Scheduler | APScheduler (BackgroundScheduler in main.py lifespan) |
| Market Data | yfinance (equities premarket), Coinbase (crypto) |
| Notifications | Telegram Bot API (per-user DMs) |
| Deployment | Railway (auto-deploy on push to main) |

### Dependencies
- No new dependencies needed
- Uses existing yfinance, APScheduler, and Telegram notification infrastructure

### Integration Points
- `analytics/swing_rules.py` (PROTECTED) — add setup_level + setup_condition to AlertSignal returns
- `alerting/swing_scanner.py` (PROTECTED) — store setup_level in alert record
- `alerting/notifier.py` (PROTECTED) — format condition-based messages
- `api/app/main.py` — add 9:00 AM scheduler job
- `db.py` — add columns to alerts/swing_trades tables

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| Protect Business Logic | CAUTION | Modifies swing_rules.py (adds fields to returns, doesn't change logic) and swing_scanner.py (stores new field). Impact analysis required. Alert evaluation logic UNCHANGED. |
| Test-Driven Development | PASS | Tests for: refresh logic, gap detection, condition formatting, invalidation |
| Local First | PASS | All testable locally with SQLite |
| Database Compatibility | PASS | New columns use standard types (REAL, TEXT, INTEGER). ALTER TABLE with try/except for both SQLite and Postgres. |
| Alert Quality | PASS | Improves alert quality — stale prices replaced with current levels. Invalidation prevents users acting on bad data. |
| Single Notification Channel | PASS | Premarket update goes to per-user Telegram (same as swing alerts). Consolidated single message, not per-alert. |

## Solution Architecture

```
┌─────────────────────────────────────────────────────────┐
│ 3:30 PM ET — EOD Swing Scan (existing)                  │
│ swing_scanner.py → evaluate_swing_rules()               │
│ Records alerts with: price, entry, stop, setup_level,   │
│ setup_condition                                          │
└───────────────────────────┬─────────────────────────────┘
                            │ (overnight)
┌───────────────────────────▼─────────────────────────────┐
│ 9:00 AM ET — Premarket Refresh (NEW)                    │
│ swing_refresher.py → refresh_pending_swing_alerts()     │
│                                                          │
│ For each pending swing alert:                            │
│   1. Fetch current premarket price                       │
│   2. Recalculate EMA/MA levels                          │
│   3. Compute gap_pct from setup_level                    │
│   4. If gap > 5%: mark invalidated                       │
│   5. Else: update refreshed_entry/stop                   │
│   6. Update DB record                                    │
│                                                          │
│ Send consolidated Telegram summary                       │
└─────────────────────────────────────────────────────────┘
```

### Files to Modify

| File | Change | Risk |
|------|--------|------|
| `analytics/swing_rules.py` | Add `setup_level` and `setup_condition` to AlertSignal returns in each check_ function | Low — adds fields, doesn't change trigger logic |
| `alerting/swing_scanner.py` | Store `setup_level` and `setup_condition` when recording alerts | Low — passes through new fields |
| `alerting/notifier.py` | Format condition-based swing messages | Low — only swing message formatting |
| `db.py` | Add columns to alerts and swing_trades tables | Low — ALTER TABLE with try/except |
| `api/app/main.py` | Add 9:00 AM scheduler job | Low — follows existing job pattern |

### Files to Add

| File | Purpose |
|------|---------|
| `alerting/swing_refresher.py` | Core refresh logic — fetch prices, recalculate, detect gaps, update DB, send summary |
| `tests/test_swing_refresher.py` | Tests for refresh, gap detection, invalidation, message formatting |

## Implementation Approach

### Phase 1: Data Layer
1. Add `setup_level`, `setup_condition`, `refreshed_entry`, `refreshed_stop`, `refreshed_at`, `gap_invalidated`, `gap_pct` columns to alerts table in `db.py`
2. Add `setup_level`, `setup_condition`, `refreshed_entry` columns to swing_trades table in `db.py`
3. Add ALTER TABLE migrations in `api/app/main.py` lifespan

### Phase 2: Swing Rules — Add Setup Level (PROTECTED — needs approval)
1. **Impact Analysis**: Each check_ function in `swing_rules.py` currently returns `AlertSignal(price=close, entry=close, ...)`. We ADD two fields to the return: `setup_level` (the MA/support value) and `setup_condition` (human-readable string). No existing logic changes.
2. Modify each check_ function to include setup_level:
   - `check_swing_pullback_20ema`: setup_level = ema20 value, condition = "Pullback to rising 20 EMA"
   - `check_swing_200ma_reclaim`: setup_level = ma200, condition = "Close reclaims 200 MA"
   - `check_swing_ema_crossover_5_20`: setup_level = ema20, condition = "EMA5/20 bullish crossover"
   - `check_swing_200ma_hold`: setup_level = ma200, condition = "Holding above 200 MA"
   - `check_swing_50ma_hold`: setup_level = ma50, condition = "Holding above 50 MA"
   - `check_swing_weekly_support`: setup_level = prior_week_low, condition = "Holding weekly support"
   - `check_swing_rsi_30_bounce`: setup_level = low, condition = "RSI bouncing from oversold"
   - `check_swing_candle_patterns`: setup_level = support, condition = "Hammer/engulfing at support"
3. Modify `swing_scanner.py` to pass setup_level/condition to `record_alert()` 

### Phase 3: Swing Refresher (NEW module)
1. Create `alerting/swing_refresher.py` with:
   - `fetch_premarket_price(symbol) -> float | None` — uses yfinance premarket or Coinbase for crypto
   - `refresh_pending_swing_alerts(session_factory) -> dict` — main refresh function:
     - Query today's swing alerts (alert_type starts with "swing_")
     - For each: fetch premarket price, compute gap from setup_level
     - If gap > 5%: mark `gap_invalidated = 1`
     - Else: recalculate entry/stop based on current price and setup structure
     - Update DB records
     - Return summary dict {refreshed: N, invalidated: N, details: [...]}
   - `format_refresh_summary(summary) -> str` — Telegram message formatter
2. Write tests in `tests/test_swing_refresher.py`

### Phase 4: Scheduler Job + Notification
1. Add `_premarket_swing_refresh` job at 9:00 AM ET in `api/app/main.py`
2. Job calls `refresh_pending_swing_alerts()`, then sends summary via `_send_telegram_to()`
3. Only sends message if material changes exist (>1% price diff or invalidations)

### Phase 5: Notifier Format Change (PROTECTED)
1. Modify swing alert message format in `notifier.py`:
   - Include `setup_condition` in the message: "Setup: Pullback to rising 20 EMA ($657.81)"
   - Show entry as level-based: "Entry: near 20 EMA ($657.81)"
   - Show stop as condition: "Stop: daily close below 20 EMA"

### Phase 6: Frontend — Signal Feed Updates
1. Update alert card rendering in Signal Feed to show:
   - If `refreshed_entry`: show refreshed price with "(was $659)" and "Updated 9:00 AM" badge
   - If `gap_invalidated`: show dimmed with "Invalidated — {gap_pct}% gap" warning
   - Show `setup_condition` as subtitle under the alert type

## Test Plan

### Unit Tests
- [ ] `test_swing_refresher.py::test_fetch_premarket_price` — returns float for valid symbol
- [ ] `test_swing_refresher.py::test_gap_detection_above_threshold` — 5%+ gap = invalidated
- [ ] `test_swing_refresher.py::test_gap_detection_below_threshold` — <5% gap = valid
- [ ] `test_swing_refresher.py::test_refresh_updates_entry` — refreshed_entry set correctly
- [ ] `test_swing_refresher.py::test_invalidated_no_refreshed_entry` — invalidated alerts have null refreshed_entry
- [ ] `test_swing_refresher.py::test_format_refresh_summary` — Telegram message contains counts and symbols
- [ ] `test_swing_refresher.py::test_crypto_uses_coinbase` — crypto symbols use Coinbase for price

### Integration Tests
- [ ] `test_swing_refresher.py::test_refresh_end_to_end` — insert mock swing alert, run refresh, verify DB updated
- [ ] `test_swing_rules.py::test_setup_level_present` — all swing rules return setup_level and setup_condition

### E2E Validation
1. **Setup**: Create swing alerts manually in DB with yesterday's prices
2. **Action**: Run `refresh_pending_swing_alerts()` 
3. **Verify**: Alerts have refreshed_entry, gap_pct calculated, invalidations flagged
4. **Cleanup**: Remove test alerts

## Out of Scope
- Changing the EOD scan timing (stays at 3:30 PM)
- Adding new swing setups
- Real-time continuous refresh during market hours
- Modifying intraday alert rules (only swing scanner)

## Research Notes
See [research.md](research.md) for decisions on timing, price source, entry format, gap threshold, and protected file approach.
