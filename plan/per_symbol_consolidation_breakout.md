# Plan: Per-Symbol Hourly Consolidation Breakout + SPY Short on Breakdown

## Problem Statement

Currently, hourly consolidation detection only runs on SPY (used as a gate). This means:
1. Individual stocks breaking out of their own consolidation are missed if SPY gate is YELLOW/RED
2. SPY breaking DOWN out of consolidation sets gate RED but doesn't fire a SHORT entry signal using the consolidation range itself
3. Other stocks breaking DOWN out of consolidation generate no SHORT signal at all

Additionally, the current consolidation detection uses a **fixed 0.5% range threshold**, which is too tight for most real-world consolidations. Looking at the SPY hourly chart (Mar 21), consolidation zones like $660-$655 are ~0.8% wide — missed by the current threshold.

**Why it matters:** A stock that consolidates for 2-3+ hours then breaks out with volume is one of the highest-conviction setups. Missing these because of a fixed threshold or because SPY hasn't broken out yet leaves money on the table.

## Solution Architecture

```
Per-Symbol Flow:
┌──────────────────────────────────────────────────────┐
│ evaluate_rules() for each symbol                      │
├──────────────────────────────────────────────────────┤
│ 1. Compute hourly ATR from resampled 1h bars         │
│ 2. detect_hourly_consolidation_break()               │
│    range threshold = 1.2x hourly ATR (adaptive)      │
│    min_bars = 2 (catch faster setups)                │
│                                                       │
│    → "consolidating"  → NOTICE (existing, unchanged) │
│    → "breakout UP"    → NEW: consol_breakout_long    │
│    → "breakout DOWN"  → NEW: consol_breakout_short   │
└──────────────────┬───────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────┐
│ Gate Interaction                                      │
│ • BUY:   blocked by RED, overrides YELLOW            │
│ • SHORT: fires on RED + YELLOW, blocked on GREEN     │
└──────────────────────────────────────────────────────┘
```

## Key Design Change: ATR-Based Consolidation Detection

### Why fixed % doesn't work

| Scenario | Price | 0.5% range | Hourly ATR | Actual consolidation |
|----------|-------|-----------|------------|---------------------|
| SPY calm day | $650 | $3.25 | $2.00 | $2.50 (detected) |
| SPY volatile day | $650 | $3.25 | $5.00 | $4.80 (MISSED — too wide for 0.5%) |
| TSLA normal | $370 | $1.85 | $4.50 | $4.00 (MISSED) |
| AAPL calm | $248 | $1.24 | $1.00 | $1.10 (detected) |

### ATR-based approach

```
hourly_atr = average of (High - Low) over last 10 hourly bars
consolidation if: 3-bar range < 1.2x hourly_atr

SPY volatile: ATR=$5.00, threshold=$6.00 → $4.80 range detected!
TSLA normal:  ATR=$4.50, threshold=$5.40 → $4.00 range detected!
```

The ATR adapts to each symbol's volatility AND to the current market regime.

### Min bars: 3 → 2

On fast-moving days (like the SPY chart), some consolidations are only 2 bars before the next leg. Requiring 3 bars means missing breakdowns in a staircase pattern:

```
SPY staircase down:
$684 ─── sell off
$675 ── 2 bars pause ── breakdown ← MISSED with min_bars=3
$669 ── 2 bars pause ── breakdown ← MISSED
$655 ── 3 bars pause ── breakdown ← caught
$648
```

With min_bars=2, we catch each step.

## What Changes

### 1. Update `detect_hourly_consolidation_break()` (intraday_rules.py)

**Before:**
```python
def detect_hourly_consolidation_break(bars_5m):
    range_pct = (range_high - range_low) / range_low
    if range_pct > HOURLY_CONSOL_RANGE_PCT:  # fixed 0.5%
        return None
```

**After:**
```python
def detect_hourly_consolidation_break(bars_5m):
    # Compute hourly ATR
    hourly["TR"] = hourly["High"] - hourly["Low"]
    hourly_atr = hourly["TR"].rolling(HOURLY_CONSOL_ATR_LOOKBACK).mean().iloc[-1]

    range_width = range_high - range_low
    atr_threshold = hourly_atr * HOURLY_CONSOL_ATR_MULT

    if range_width > atr_threshold:
        return None  # range too wide relative to ATR

    # Also enforce a max absolute % cap to prevent absurd ranges
    range_pct = range_width / range_low
    if range_pct > HOURLY_CONSOL_MAX_RANGE_PCT:
        return None
```

Returns dict now also includes `hourly_atr` for logging/debugging.

### 2. New AlertType enums (intraday_rules.py)

```python
CONSOL_BREAKOUT_LONG = "consol_breakout_long"
CONSOL_BREAKOUT_SHORT = "consol_breakout_short"
```

### 3. New Rule Function (intraday_rules.py)

```python
def check_consolidation_breakout(
    symbol, bars_5m, bar_volume, avg_volume
) -> AlertSignal | None
```

Logic:
- Call `detect_hourly_consolidation_break(bars_5m)`
- If status != "breakout", return None
- Volume confirmation: bar_volume >= CONSOL_BREAKOUT_MIN_VOL_RATIO x avg
- Direction UP → BUY signal:
  - Entry = range_high (breakout level)
  - Stop = range_low - buffer (bottom of consolidation)
  - T1 = entry + 1R, T2 = entry + 2R
  - Confidence = "high"
- Direction DOWN → SHORT signal:
  - Entry = range_low (breakdown level)
  - Stop = range_high + buffer (top of consolidation)
  - T1 = entry - 1R, T2 = entry - 2R

### 4. Gate Interaction Rules (intraday_rules.py)

In the SPY gate filter section:
- `consol_breakout_long`: **exempt from YELLOW suppression** (override YELLOW, still blocked by RED)
- `consol_breakout_short`: **allowed on RED and YELLOW** (blocked on GREEN — don't short into bull tape)

### 5. Config (alert_config.py)

```python
# Hourly Consolidation Breakout (updated)
HOURLY_CONSOL_ATR_LOOKBACK = 10       # 10 hourly bars for ATR calculation
HOURLY_CONSOL_ATR_MULT = 1.2          # range must be < 1.2x hourly ATR
HOURLY_CONSOL_MAX_RANGE_PCT = 0.015   # 1.5% absolute cap (safety net)
HOURLY_CONSOL_MIN_BARS = 2            # 2 hourly bars minimum (was 3)
HOURLY_CONSOL_ENABLED = True          # feature flag (unchanged)

# Per-symbol consolidation breakout signals
CONSOL_BREAKOUT_ENABLED = True
CONSOL_BREAKOUT_STOP_OFFSET_PCT = 0.001  # 0.1% buffer beyond range for stop
CONSOL_BREAKOUT_MIN_VOL_RATIO = 0.8      # minimum volume ratio for confirmation
```

Remove `HOURLY_CONSOL_RANGE_PCT` (replaced by ATR-based).

Add to ENABLED_RULES:
```python
"consol_breakout_long",
"consol_breakout_short",
```

## Files to Modify

| File | Change | Risk |
|------|--------|------|
| `analytics/intraday_rules.py` | Update `detect_hourly_consolidation_break()` to ATR-based, add AlertType enums, new `check_consolidation_breakout()`, wire into `evaluate_rules()`, gate exemptions | HIGH — protected business logic |
| `alert_config.py` | Update consolidation config (ATR params, min_bars=2), add breakout config, add to ENABLED_RULES | MEDIUM — config only |

## Impact Analysis

### What behavior changes?
- `detect_hourly_consolidation_break()` now uses ATR-based threshold instead of fixed 0.5%
  - Will detect MORE consolidations on volatile days/stocks
  - Will detect FEWER false consolidations on calm days (ATR tightens threshold)
- Min bars reduced 3 → 2: catches faster staircase patterns
- NEW signals fire: `consol_breakout_long` (BUY) and `consol_breakout_short` (SHORT)
- BUY breakouts override YELLOW gate (but NOT RED)
- SHORT breakouts fire on RED + YELLOW gate
- Existing `hourly_consolidation` NOTICE still fires when consolidating (uses same updated detection)
- SPY gate computation also benefits from improved detection (hourly_break override more accurate)

### What could break?
- More consolidation NOTICEs fire (wider detection) — manageable, they're informational
- Alert volume increases from new breakout signals — dedup handles it
- Existing SPY gate hourly_break override changes behavior (ATR-based detection may flip gate at different times) — this is an improvement, not a regression
- No DB schema changes needed

### Risk mitigation
- `HOURLY_CONSOL_MAX_RANGE_PCT = 1.5%` absolute cap prevents absurd wide ranges from qualifying
- Volume confirmation prevents false breakouts
- ENABLED_RULES + feature flags allow disabling without code change
- RED gate still blocks all BUY (including breakouts)
- Existing tests for `detect_hourly_consolidation_break` updated to use ATR-based thresholds

## Test Plan

Tests to add/update in `tests/test_intraday_rules.py`:

**Updated existing tests:**
1. `test_hourly_consolidation_detection_atr_based` — verify ATR threshold replaces fixed %
2. `test_hourly_consolidation_min_bars_2` — verify 2-bar consolidation detected

**New breakout signal tests:**
3. `test_consol_breakout_long_fires_on_up_break` — tight range then close above range_high
4. `test_consol_breakout_short_fires_on_down_break` — tight range then close below range_low
5. `test_consol_breakout_no_fire_when_consolidating` — still in range, no signal
6. `test_consol_breakout_long_blocked_by_red_gate` — UP break but gate RED, BUY suppressed
7. `test_consol_breakout_long_overrides_yellow_gate` — UP break + YELLOW gate, BUY still fires
8. `test_consol_breakout_short_fires_on_red_gate` — DOWN break + RED gate, SHORT fires
9. `test_consol_breakout_short_blocked_on_green_gate` — DOWN break + GREEN gate, SHORT suppressed
10. `test_consol_breakout_requires_volume` — breakout but vol < threshold, no signal
11. `test_consol_breakout_dedup` — same symbol+type in fired_today, skipped
12. `test_consol_breakout_works_for_crypto` — uses self-gate, not SPY gate
13. `test_consol_breakout_staircase_pattern` — 2-bar consolidation → break → 2-bar → break (catches both)
14. `test_consol_atr_adapts_to_volatility` — high-vol stock gets wider threshold than low-vol

## Implementation Order

1. Update config: ATR params, min_bars=2, breakout config, ENABLED_RULES
2. Update `detect_hourly_consolidation_break()` — ATR-based threshold
3. Add AlertType enums
4. Write `check_consolidation_breakout()` function
5. Wire into `evaluate_rules()`
6. Add gate exemption for consol_breakout_long (YELLOW override)
7. Add gate filter for consol_breakout_short (block on GREEN)
8. Update existing tests + write new tests
9. Run full test suite
