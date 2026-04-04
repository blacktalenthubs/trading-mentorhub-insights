# Feature Specification: V1 → V2 Feature Parity

**Status**: In Progress
**Created**: 2026-04-04
**Priority**: Critical — must close gaps before V1 sunset

---

## Overview

V2 (FastAPI + React) is live in production at `www.tradesignalwithai.com`. Core alert pipeline works. However, several V1 (Streamlit + worker.py) features were not ported. This spec tracks every gap for systematic closure.

---

## Parity Status Summary

| Category | V1 Features | V2 Ported | V2 Missing | Parity |
|----------|------------|-----------|------------|--------|
| Alert Pipeline | 8 | 6 | 2 | 75% |
| Telegram | 5 | 2 | 3 | 40% |
| Scheduled Jobs | 7 | 0 | 7 | 0% |
| Trade Management | 6 | 4 | 2 | 67% |
| Special Features | 5 | 0 | 5 | 0% |
| **Total** | **31** | **12** | **19** | **39%** |

---

## CRITICAL — Fix Before Monday Market

### C1: Telegram Bot Not Running in V2

**V1 behavior**: `worker.py` starts `telegram_bot.start_bot_thread()` which runs the python-telegram-bot polling loop in a background thread. Handles:
- `/start <token>` deep-link for account linking
- Inline button callbacks: Took It, Skip, Exit, Hold
- `/exit SYMBOL` command for manual trade exit

**V2 status**: The V2 FastAPI app (`api/app/main.py` lifespan) does NOT start the Telegram bot. Alerts are sent via `notify_user()` with inline buttons, but no bot is listening for callback responses.

**Impact**: Users receive alerts with Took/Skip/Exit buttons but tapping them does nothing (or returns "Alert not found" if local bot is running).

**Fix**: Add `telegram_bot.start_bot_thread()` to the V2 FastAPI lifespan hook.

**Files**:
- `api/app/main.py` — add bot startup in lifespan
- `scripts/telegram_bot.py` — ensure `_find_alert` and `_ack_v2_alert` use `db.get_db()` (DONE)

**Acceptance**: User receives alert on Telegram → taps "Took It" → alert marked as took, real trade opened → taps "Exit" → trade closed with P&L recorded.

---

### C2: Post-Stop Re-Fire Logic

**V1 behavior** (`monitor.py:207-226`):
```python
# After stop-out + cooldown expiry, allow BUY signals to re-fire
for sym in stopped_symbols:
    if sym not in cooled_symbols:
        fired_today = {(s, at) for s, at in fired_today if s != sym or at in _sell_types}
```

**V2 status**: Missing entirely. Once an alert fires for a symbol, it's blocked for the rest of the session — even after stop-out and cooldown expire.

**Impact**: If SPY hits stop at 10 AM, cools down by 10:15 AM, V1 would re-fire a new BUY signal if conditions are met. V2 will not.

**Fix**: Port the post-stop re-fire logic from V1 `monitor.py:207-226` to V2 `api/app/background/monitor.py` before the evaluate_rules loop.

**Files**: `api/app/background/monitor.py`

---

## HIGH — Fix This Sprint

### H1: SPY Inside Day Detection & Gate

**V1 behavior** (`monitor.py:241-310`):
- Computes `spy_gate` dict with: trend, VWAP position, morning low, below_morning_low, inside_day
- Passes `spy_gate` to `evaluate_rules()` which uses it to suppress/demote alerts
- Sends one-time "SPY INSIDE DAY" Telegram notice when detected

**V2 status**: Uses `get_spy_context()` which returns trend only — no gate, no inside day detection.

**Impact**: V2 fires alerts during choppy inside-day conditions that V1 would suppress.

**Fix**: Add `compute_spy_gate()` to V2 monitor, pass as parameter to `evaluate_rules()`.

**Files**: `api/app/background/monitor.py`

---

### H2: Burst Cooldown (BUY Alert Spam Prevention)

**V1 behavior** (`monitor.py:428-441`):
```python
if signal.direction == "BUY" and BUY_BURST_COOLDOWN_MINUTES > 0:
    if symbol in _last_buy_notify and elapsed < BUY_BURST_COOLDOWN_MINUTES:
        _burst_suppressed = True  # Record to DB but don't send notification
```

**V2 status**: No burst cooldown. Multiple BUY alerts for the same symbol can fire within minutes.

**Impact**: User gets spammed with rapid BUY notifications for the same symbol.

**Fix**: Add in-memory `_last_buy_notify` dict to V2 monitor with configurable cooldown.

**Files**: `api/app/background/monitor.py`

---

### H3: EOD Swing Scan

**V1 behavior** (`monitor.py:650-670`):
- After 4 PM ET, runs `swing_scan_eod()` once per day
- Scans for multi-day swing setups (RSI, MACD, double bottoms)
- Creates swing_trade entries

**V2 status**: No EOD scan. The 3-min poll only runs intraday rules.

**Fix**: Add APScheduler job for EOD swing scan at 4:15 PM ET.

**Files**: `api/app/main.py` (add job), `alerting/swing_scanner.py` (already exists)

---

### H4: Pre-Market Brief

**V1 behavior** (`monitor.py:672-690`):
- Between 9:10-9:29 AM ET, generates and sends pre-market brief via Telegram
- Includes: key levels, overnight moves, daily plan for each watchlist symbol

**V2 status**: No pre-market brief.

**Fix**: Add APScheduler job for pre-market brief at 9:15 AM ET.

**Files**: `api/app/main.py` (add job), `analytics/premarket_brief.py` (already exists)

---

## MEDIUM — Fix Before Launch

### M1: Post-Market Review (EOD AI Summary)

**V1 behavior**: After market close, generates AI summary of the day's alerts, winners/losers, and coaching insights. Sent via Telegram.

**V2 status**: Missing.

**Files**: `analytics/eod_review.py` (exists), `api/app/main.py` (add scheduled job)

---

### M2: Weekly Tuning Report

**V1 behavior**: Friday EOD, generates per-category win rate breakdown and tuning suggestions. Sent via Telegram.

**V2 status**: Missing.

**Files**: `analytics/weekly_tuning.py` (exists if present), `api/app/main.py`

---

### M3: EOD Cleanup (Close Stale Entries)

**V1 behavior**: After market close, closes any remaining `active_entries` with status='active' for that session date.

**V2 status**: Missing. Stale entries persist indefinitely.

**Fix**: Add EOD cleanup job.

---

### M4: Options Trade Tracking

**V1 behavior** (`alerting/options_trade_store.py`):
- Open/close/expire options trades
- Track premium, contracts, strike, expiration
- P&L calculation for options

**V2 status**: API endpoints exist in `real_trades.py` (lines 216-305) but they call V1 `options_trade_store.py` which uses SQLite. Needs migration to SQLAlchemy.

**Fix**: Create `OptionsTradeModel` in SQLAlchemy, port endpoints.

---

### M5: Alpaca Paper Trade Auto-Sync

**V1 behavior** (`alerting/paper_trader.py`):
- `sync_open_trades()` called every poll cycle
- Checks Alpaca API for filled bracket orders
- Updates paper_trades table with fill prices

**V2 status**: Paper trading router exists but no auto-sync in the background monitor.

**Fix**: Add Alpaca sync call to V2 poll cycle (if paper trading enabled).

---

### M6: Crypto Polling Outside Market Hours

**V1 behavior** (`monitor.py:700-720`):
- After equity market close, continues polling crypto-only symbols (BTC-USD, ETH-USD)
- Uses `is_crypto_alert_symbol()` to filter

**V2 status**: V2 monitor already handles this via `is_market_hours_for_symbol()` which returns True for crypto 24/7. **PASS** — but verify this works in production.

---

## LOW — Nice to Have

### L1: Cluster Narrator

**V1**: When multiple confirming signals fire for same symbol, generates consolidated AI narrative explaining confluence.

**V2**: Not ported.

---

### L2: AI Conviction Filter

**V1**: Feature-flagged (disabled by default). Uses Claude to score conviction on BUY signals, suppresses low-conviction, boosts high-conviction.

**V2**: Not ported. Was disabled in V1 anyway.

---

### L3: Regime Narrator

**V1**: Detects SPY regime shifts (bullish→bearish, etc.) and sends one-time AI narrative explaining the shift.

**V2**: Not ported.

---

### L4: Exit Coach / Position Advisor

**V1**: Disabled in production. Would check open positions hourly and suggest exit/hold.

**V2**: Has `position_advisor.py` endpoint but not scheduled.

---

### L5: Group Telegram Fallback

**V1**: Falls back to `TELEGRAM_CHAT_ID` (group chat) if per-user chat_id not set.

**V2**: Only sends to per-user chat_id. Users without linked Telegram get dashboard-only alerts.

---

## V2-Only Features (Not in V1)

| Feature | Description |
|---------|-------------|
| Signal Library | 8 educational pattern categories with live win rates |
| Onboarding Wizard | 4-step guided setup (symbols → Telegram → prefs → done) |
| Square Billing | Subscription management with Square payments |
| Landing Page | Public marketing page with live track record |
| Push Notifications (APNs) | iOS push via DeviceToken + send_push_sync |
| SSE Alert Stream | Real-time browser alert delivery via SSE |
| Multi-User Architecture | Per-user watchlists, alerts, preferences, Telegram routing |
| Toast Notifications | In-app feedback on mutations |
| Optimistic Updates | Instant UI response on watchlist/alert actions |
| Position Close from Dashboard | Hover → Close button with current price |

---

## Implementation Priority Order

```
Week 1 (Monday):
  C1: Start Telegram bot in V2          ← users can interact with alerts
  C2: Post-stop re-fire logic           ← proper re-entry after stop-outs

Week 1 (Midweek):
  H1: SPY inside day gate               ← reduce noise in choppy markets
  H2: Burst cooldown                    ← prevent BUY notification spam

Week 2:
  H3: EOD swing scan                    ← swing traders get setups
  H4: Pre-market brief                  ← daily preparation
  M1: Post-market review                ← daily debrief
  M3: EOD cleanup                       ← data hygiene

Week 3+:
  M2: Weekly tuning report
  M4: Options tracking
  M5: Alpaca auto-sync
  L1-L5: Nice-to-haves
```

---

## Acceptance Criteria

### C1 done when:
- [ ] Telegram bot runs inside V2 FastAPI process
- [ ] User taps "Took It" → alert marked, real trade opened
- [ ] User taps "Skip" → alert marked as skipped
- [ ] User taps "Exit" → trade closed with P&L at current price
- [ ] `/start <token>` links new user's Telegram account
- [ ] `/exit SYMBOL` closes trade from Telegram

### C2 done when:
- [ ] Symbol stops out → cooldown starts → cooldown expires → new BUY signal fires
- [ ] Same behavior as V1 monitor.py lines 207-226

### H1 done when:
- [ ] SPY inside day detected → alerts demoted or suppressed
- [ ] One-time "SPY INSIDE DAY" notice sent to Telegram

### Full parity when:
- [ ] All CRITICAL and HIGH items completed
- [ ] V1 Streamlit can be fully sunset
- [ ] No user-facing feature regression
