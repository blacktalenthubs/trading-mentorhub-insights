# Spec 14 — Swing Trade Entry/Exit System

## Problem Statement

**What:** The current alert system focuses on intraday entries (5-min bars, same-session exits). Swing traders who hold overnight need a separate system that operates on daily bars, enters at structural levels (RSI 30, 200MA, 50MA), and exits on daily closes — not intraday noise.

**Why:** Swing traders are a key user segment. They need different signals (daily timeframe), different entries (critical support levels), different exits (daily close-based, not intraday stops), and different Telegram formatting (labeled "SWING" to distinguish from day trades).

**What success looks like:**
- Swing alerts fire via Telegram labeled "SWING LONG" / "SWING EXIT"
- Entries only at high-conviction daily levels (RSI 30, 200MA, 50MA bounce)
- Exits based on daily closes (not intraday wicks)
- Completely isolated from intraday alert rules
- Trades tracked separately with swing-specific P&L

---

## Current State

### What Exists (strong foundation)
- `analytics/swing_rules.py` — 3 setup rules + 5 professional rules
- `alerting/swing_scanner.py` — EOD orchestrator, DB helpers, runs at 4:15 PM
- `swing_trades` table — tracks active/closed swing trades with RSI
- `fetch_prior_day()` — returns all daily MAs, EMAs, RSI14
- SPY regime gate — market filter
- API endpoints: `/swing/regime`, `/swing/categories`, `/swing/trades/active`
- Symbol categorization (buy_zone, strongest, building_base, etc.)

### What's Missing
- Swing alerts don't reach Telegram (no "SWING" label format)
- No RSI 30 bounce entry rule (only RSI zone crossover notice)
- No 50MA hold/bounce entry rule
- No daily-close-based exit system (current exits are intraday)
- No RSI target exits (e.g., bought at RSI 30 → exit at RSI 45-50)
- No close-below-PDL exit
- No close-below-key-MA invalidation exit
- MACD and divergence data not populated in `prior_day`

---

## Swing Entry Rules

### Rule 1: RSI 30 Bounce (Oversold Reversal)
```
Trigger: Daily RSI14 crosses above 30 (was below, now above)
Confirm: Close in upper 50% of daily range (buying pressure)
Entry:   Daily close
Stop:    Close below the low of the RSI < 30 day (daily close basis)
T1:      RSI reaches 45 (first momentum target)
T2:      RSI reaches 50-55 (mean reversion complete)
Score:   +20 if near 200MA, +10 if volume > avg, +10 if SPY bullish
```

### Rule 2: 200MA Hold/Bounce
```
Trigger: Daily low wicks to within 1% of 200MA AND closes above it
Confirm: Prior trend was above 200MA (pullback, not breakdown)
         At least 20 days above 200MA in last 30 days
Entry:   Daily close
Stop:    Daily close below 200MA (thesis invalidated)
T1:      50MA (first overhead MA)
T2:      20MA (trend resume target)
Score:   +20 if RSI < 40, +10 if hammer candle, +10 if SPY bullish
```

### Rule 3: 50MA Hold/Bounce
```
Trigger: Daily low wicks to within 0.5% of 50MA AND closes above it
Confirm: 50MA is rising (today > 10 days ago)
         Price was above 50MA prior (pullback to support)
Entry:   Daily close
Stop:    Daily close below 50MA
T1:      20MA or prior swing high
T2:      Prior day high or new highs
Score:   +20 if RSI 35-45, +10 if green candle, +10 if SPY bullish
```

### Rule 4: 20MA Pullback (Trend Continuation)
```
Trigger: Daily close within 0.5% of rising 20MA
Confirm: 20MA > 50MA (uptrend confirmed)
         RSI between 40-55 (not overbought)
Entry:   Daily close
Stop:    Daily close below 20MA
T1:      Prior swing high
T2:      1.5x risk above entry
Score:   +10 if green candle, +10 if volume increasing
```
*Already exists as `check_swing_pullback_20ema` — enhance with better stop/target*

### Rule 5: RSI Divergence (Advanced)
```
Trigger: Price makes lower low, RSI14 makes higher low
Confirm: At support level (near MA or prior swing low)
Entry:   Daily close
Stop:    Below the lower low (daily close basis)
T1:      RSI 45
T2:      RSI 55
Score:   +20 if at 200MA, +10 if volume spike on reversal bar
```
*Exists as `check_swing_rsi_divergence` — needs daily_closes/daily_rsi data*

---

## Swing Exit Rules (Daily Close Basis ONLY)

### Exit 1: RSI Target Reached
```
Condition: RSI14 reaches target zone
  - If entered from RSI < 30 → exit at RSI 45-50
  - If entered from MA bounce → exit at RSI 65-70
Action:  Send "SWING EXIT" notification with P&L
         Do NOT auto-close — user decides
```

### Exit 2: Close Below Prior Day Low
```
Condition: Daily close < prior day low
Action:  Send "SWING EXIT" notification
         "Daily close below PDL — swing thesis weakening"
```

### Exit 3: Close Below Key MA (Invalidation)
```
Condition: Daily close below the MA that was the entry thesis
  - Entered at 200MA → close below 200MA = invalidated
  - Entered at 50MA → close below 50MA = invalidated
  - Entered at 20MA → close below 20MA = invalidated
Action:  Send "SWING EXIT — INVALIDATED" notification
         Strongest exit signal — thesis is broken
```

### Exit 4: Close Below Stop Level
```
Condition: Daily close below the stop price set at entry
Action:  Send "SWING STOP REACHED" notification
         Same as current stop tracking but DAILY close, not intraday wick
```

---

## Telegram Format

### Swing Entry
```
SWING LONG AAPL $185.50
Entry $185.50 · Stop $182.00 (close below 200MA)
T1: RSI 45 (~$192) · T2: RSI 55 (~$198)
Setup: 200MA Bounce — RSI 32 recovering
Conviction: HIGH

[Took It] [Skip]
```

### Swing Exit (Target)
```
SWING TARGET — AAPL $195.20
RSI reached 48 (target zone 45-50)
Your swing from $185.50: +$9.70 (+5.2%)
Consider taking profits or trailing stop

[Exit Trade]
```

### Swing Exit (Invalidation)
```
SWING INVALIDATED — AAPL $181.50
Daily close below 200MA ($183.20) — thesis broken
Your swing from $185.50: -$4.00 (-2.2%)
Exit recommended

[Exit Trade]
```

---

## Architecture

```
┌──────────────────┐     ┌──────────────────┐
│ swing_scanner.py │────▶│ swing_rules.py   │
│ (EOD 4:15 PM)    │     │ (entry rules)    │
└────────┬─────────┘     └──────────────────┘
         │
         ▼
┌──────────────────┐     ┌──────────────────┐
│ swing_trades DB  │────▶│ notifier.py      │
│ (track positions)│     │ (SWING label)    │
└────────┬─────────┘     └──────────────────┘
         │
         ▼
┌──────────────────┐
│ Daily exit check │ ← runs AFTER market close (4:15 PM)
│ (RSI target,     │   checks daily closes, not intraday
│  MA invalidation,│
│  PDL break)      │
└──────────────────┘
```

### Key Isolation from Day Trades
| Aspect | Day Trades | Swing Trades |
|--------|-----------|--------------|
| **Timeframe** | 5-min bars | Daily bars |
| **Entry trigger** | Intraday patterns | Daily close levels |
| **Stop basis** | Intraday price | Daily close only |
| **Exit timing** | During session | After market close |
| **Hold period** | Minutes to hours | Days to weeks |
| **Telegram label** | "LONG" / "SHORT" | "SWING LONG" / "SWING EXIT" |
| **Alert type prefix** | Various | `swing_*` |
| **Database** | `alerts` + `real_trades` | `swing_trades` |
| **Scanner** | 3-min poll cycle | Once at 4:15 PM ET |

---

## Implementation Plan

### Phase 1: Enhanced Entry Rules
| File | Change |
|------|--------|
| `analytics/swing_rules.py` | Add RSI 30 bounce, 200MA bounce, 50MA bounce rules |
| `analytics/intraday_data.py` | Populate `daily_closes`, `daily_rsi` series in `prior_day` |
| `alert_config.py` | Add swing entry thresholds |

### Phase 2: Daily Exit System
| File | Change |
|------|--------|
| `alerting/swing_scanner.py` | Add exit checks: RSI target, PDL close, MA invalidation |
| `alerting/swing_scanner.py` | Send exit notifications via Telegram |

### Phase 3: Telegram Integration
| File | Change |
|------|--------|
| `alerting/notifier.py` | Add `_format_swing_body()` with "SWING LONG/EXIT" labels |
| `alerting/notifier.py` | Add `_build_swing_buttons()` for Took/Skip/Exit |
| `alerting/swing_scanner.py` | Call notifier for swing alerts |

### Phase 4: Frontend
| File | Change |
|------|--------|
| `web/src/pages/SwingTradesPage.tsx` | Show active swings with daily P&L |
| Signal Feed | Show swing alerts with "SWING" badge |

---

## Acceptance Criteria

- [ ] RSI 30 bounce fires when RSI crosses above 30 on daily close
- [ ] 200MA bounce fires when price wicks to 200MA and closes above
- [ ] 50MA bounce fires similarly
- [ ] All swing entries labeled "SWING LONG" in Telegram with Took/Skip
- [ ] Exit notifications fire on daily close (not intraday wick)
- [ ] RSI target exit fires when RSI reaches target zone
- [ ] MA invalidation exit fires when daily close breaks below entry MA
- [ ] Swing trades tracked separately from day trades
- [ ] No swing alert fires during market hours (EOD only)
- [ ] SPY regime gate respected (no swings when SPY < 20MA)

---

## Test Plan

### Unit Tests
- RSI 30 bounce: test with RSI series [28, 29, 31] → should fire
- RSI 30 bounce: test with RSI series [28, 29, 29] → should NOT fire
- 200MA bounce: test with close above 200MA, low within 1% → should fire
- 200MA bounce: test with close below 200MA → should NOT fire
- Exit RSI target: entered at RSI 30, current RSI 46 → exit notification
- Exit MA invalidation: entered at 200MA, close below 200MA → exit notification

### E2E Tests
- Run swing_scan_eod() with test data
- Verify Telegram messages have "SWING" prefix
- Verify swing_trades DB rows created correctly
- Verify exit checks only use daily close (not intraday low)
