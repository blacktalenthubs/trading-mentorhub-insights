# Alert Quality & Noise Reduction Plan

## Problem Statement

On March 27, the system fired **85 alerts** — far too many for a busy professional. Key issues:

1. **Counter-trend LONG alerts fail fast** — NVDA BUY at 2:19 PM stopped out in 8 min, AAPL BUY at 3:03 PM stopped out in 10 min. Both stocks below all daily EMAs.
2. **Entry/stop bug on gap-downs** — SPY Short Entry used broken level ($644.82) as entry when actual price was $634.96
3. **No market-regime-aware filtering** — once SPY breaks its morning low on volume, most equity longs are dead. The system keeps firing them.
4. **Low-score alerts create noise** — C(30) alerts are nearly always skipped.

**Goal**: Reduce alerts to ~10-15/day of high-conviction, trend-aligned setups without losing legitimate opportunities.

## Solution Architecture

```
                    ┌─────────────────────────┐
                    │   SPY Morning Range      │
                    │   (first 30 min H/L)     │
                    └────────┬────────────────┘
                             │
                    ┌────────▼────────────────┐
                    │  SPY breaks morning low? │
                    │  (volume >= 1.2x avg)    │
                    └────┬──────────┬─────────┘
                    NO   │          │  YES
                    ┌────▼───┐  ┌───▼──────────────────┐
                    │ Normal │  │ BEARISH REGIME         │
                    │ mode   │  │ • Suppress equity LONG │
                    │        │  │   unless score >= A(75)│
                    │        │  │ • Boost SHORT +15 pts  │
                    └────────┘  └──────────────────────┘
                             │
                    ┌────────▼────────────────┐
                    │  Minimum Score Gate      │
                    │  Telegram: B(55)+        │
                    │  Email: C(40)+           │
                    └────────────────────────┘
```

## Three Changes (Priority Order)

---

### Change 1: Fix Gap-Down Entry Bug (Quick Fix)

**File**: `analytics/intraday_rules.py` — `check_spy_short_entry()` (line 3929)

**Bug**: When SPY gaps below PDL, `entry = level_price` sets entry to the broken level ($644.82), not current price ($634.96). The stop is also based on the level, creating an impossible trade.

**Fix**:
```python
# BEFORE (buggy)
entry = round(level_price, 2)
stop = round(level_price * (1 + SPY_SHORT_STOP_OFFSET_PCT), 2)

# AFTER (fixed)
entry = round(last_bar["Close"], 2)
# Stop: use a reasonable overhead level (VWAP, recent swing high, or fixed %)
stop = round(entry * (1 + SPY_SHORT_STOP_OFFSET_PCT), 2)
```

**Impact**: Prevents confusing alerts where entry/stop are $10 above current price.

---

### Change 2: SPY Morning Low Break → Suppress Equity Longs (High Impact)

**Concept**: The first-hour low (first 6 bars = 30 min, already computed via `compute_opening_range()`) is an institutional reference level. When SPY breaks below it on volume, sellers are in control. Most equity longs will fail.

**How it works now**: The SPY gate checks VWAP dominance + EMA trend but doesn't specifically track whether the morning low broke. The morning low breakdown rule fires alerts but doesn't feed back into the gate logic.

**Proposed change**: Add a `spy_morning_low_broken` flag to the gate state. When True:
- **Equity BUY alerts**: Require score >= A(75) to fire. Below that → suppressed.
- **Equity SHORT alerts**: Boost score by +15 points (trend-aligned).
- **Crypto**: Unaffected (has its own gate).
- **SPY itself**: SHORT alerts still fire normally. BUY alerts suppressed unless A(75)+.

**Why this is better than "mute all longs when SPY < VWAP"**:
- VWAP cross happens multiple times per day — too sensitive
- Morning low break is a **one-time event** — once it breaks, the regime changes for the rest of the day
- SPY can be below VWAP briefly and recover, but morning low breaks rarely recover (especially on volume)
- This preserves opportunity: before the break, longs are still valid. After, only the highest-conviction survive.

**How morning low is detected today**:
- `compute_opening_range()` in `intraday_data.py` (line 1430) — first 6 bars (30 min), returns `or_low`
- `check_morning_low_breakdown()` in `intraday_rules.py` (line 4207) — fires alert when bar low breaks below `or_low` on 1.2x volume
- The opening range dict is already available inside `evaluate_rules()`

**Implementation**:
1. In `evaluate_rules()`, after computing SPY's opening range, track whether SPY broke its morning low
2. Pass this flag alongside the existing gate state
3. In the signal filtering section (end of evaluate_rules), suppress low-score BUY alerts when flag is True

**Edge cases**:
- SPY gaps below morning low on open → flag is True from the start (correct — it's a gap-down day, longs are risky)
- Morning low breaks then price reclaims → keep flag True for the session (breaks rarely fully recover, and reclaim can be a bull trap)
- Pre-market/after-hours: morning low only applies 9:30-4:00

---

### Change 3: Minimum Score Gate for Notifications (Noise Reduction)

**Current**: Every fired alert goes to Telegram + email regardless of score.

**Proposed**:
- **Telegram**: Only send alerts with score >= B(55) — these are actionable
- **Email**: Send alerts with score >= C(40) — for review/tracking
- **Below C(40)**: Record in DB only, no notification

This alone would have cut March 27 alerts from 85 to ~25-30.

**Implementation**: Add score check in `notify()` and `send_sms()` before sending.

**Config**:
```python
TELEGRAM_MIN_SCORE = 55   # B grade minimum for Telegram
EMAIL_MIN_SCORE = 40      # C grade minimum for email
```

**Exception**: Exit alerts (T1 hit, stop loss, auto stop out) always send regardless of score — these are time-critical.

---

## Files to Modify

| File | Change |
|------|--------|
| `analytics/intraday_rules.py` | Fix entry bug in `check_spy_short_entry()`, add morning-low-broken gate logic in `evaluate_rules()` |
| `alert_config.py` | Add `TELEGRAM_MIN_SCORE`, `EMAIL_MIN_SCORE`, `SPY_MORNING_LOW_BROKEN_MIN_SCORE` |
| `alerting/notifier.py` | Add score filtering in `notify()` |
| `monitor.py` | Pass SPY morning low state across poll cycles |
| `tests/test_intraday_rules.py` | Test entry bug fix, morning low gate, score filtering |

## What This Preserves

- **High-conviction longs still fire** in bear markets (A 75+ score = strong technical setup that can work even against trend)
- **All shorts fire** regardless of market regime (they're trend-aligned on down days)
- **Crypto unaffected** — has its own gate system
- **All data still recorded** in DB for analysis — just fewer notifications

## Expected Impact on March 27 Data

| Metric | Before | After |
|--------|--------|-------|
| Total alerts fired | 85 | 85 (unchanged — still recorded) |
| Telegram notifications | 85 | ~15-20 |
| Counter-trend longs to Telegram | ~8 | 0-1 (only A 75+) |
| Stopped-out longs | 4+ | ~0-1 |
| Profitable shorts still delivered | All | All |

## Implementation Order

1. **Fix entry bug** (15 min, immediate value)
2. **Minimum score gate** (30 min, cuts noise by 50%+)
3. **SPY morning low break filter** (1 hour, highest impact on quality)

## Out of Scope (Future)

- Per-symbol daily trend filter (EMA20/EMA50 check) — more complex, requires daily bar data per symbol
- Dynamic score thresholds based on historical hit rates
- ML-based signal quality prediction
