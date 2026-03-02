# Plan: Add MA100/MA200 Bounce Alerts

## Problem Statement
The system only detects bounces off MA20 and MA50. MA100 and MA200 — the most important institutional support levels — are missing entirely. Today NVDA bounced off 100MA, TSLA sat at 200MA, SPY at 100MA, and zero alerts fired.

**Why it matters:** MA100/200 bounces are the highest-conviction setups because institutional buyers accumulate at these levels. Missing these defeats the purpose of the alert system.

## Solution Architecture

```
┌───────────────┐     ┌──────────────────┐     ┌──────────────────────┐
│ Data Pipeline │────▶│ Rule Engine      │────▶│ Monitor Loop         │
│ fetch_prior   │     │ check_ma_bounce  │     │ create_active_entry  │
│ _day()        │     │ _100 / _200      │     │ → SELL rules fire    │
│               │     │                  │     │   next cycle         │
│ +MA100, MA200 │     │ +entry/stop/T1/T2│     │ (already handled)    │
└───────────────┘     └──────────────────┘     └──────────────────────┘
```

**Sell-side is already wired** — no changes needed to monitor.py or SELL rules. When a BUY fires, `create_active_entry()` persists entry/stop/T1/T2, and subsequent poll cycles evaluate T1 hit, T2 hit, stop loss, and resistance at prior high against those entries.

## Codebase Analysis

### Existing pattern to follow
`check_ma_bounce_20` (line 130) and `check_ma_bounce_50` (line 184) — identical structure:
1. Validate MA available
2. Check uptrend/pullback condition
3. Proximity check: `abs(bar["Low"] - MA) / MA`
4. Bounce confirmation: `bar["Close"] > MA`
5. R-based targets: entry = close, stop = max(bar low, MA - offset), T1 = 1R, T2 = 2R

### Data pipeline gap
`fetch_prior_day()` uses `period="3mo"` (~63 bars). MA200 requires 200 bars → change to `period="1y"`.

## Files to Modify

| File | Change | Lines Affected |
|------|--------|----------------|
| `analytics/intraday_data.py` | Extend period to `"1y"`, compute MA100/MA200, add to return dict | ~48, 54-56, 91-92, 101-117 |
| `alert_config.py` | Add `MA100_STOP_OFFSET_PCT`, `MA200_STOP_OFFSET_PCT` | New constants |
| `analytics/intraday_rules.py` | Add `AlertType.MA_BOUNCE_100/200`, import new configs, add `check_ma_bounce_100/200` functions, wire into `evaluate_rules()` | Enum, imports, new functions, ~1117-1120, ~1188-1206 |
| `tests/test_intraday_rules.py` | Add `TestMABounce100`, `TestMABounce200` test classes | New tests |

## Implementation Steps

### Step 1: `alert_config.py` — add constants
```python
# MA100 Bounce: wider stop for intermediate timeframe
MA100_STOP_OFFSET_PCT = 0.007  # 0.7%

# MA200 Bounce: widest stop for long-term institutional level
MA200_STOP_OFFSET_PCT = 0.010  # 1.0%
```

### Step 2: `analytics/intraday_data.py` — extend data pipeline
- Change `period="3mo"` → `period="1y"`
- Add MA100/MA200 rolling calculations
- Add `ma100`, `ma200` to return dict

### Step 3: `analytics/intraday_rules.py` — new rules

**AlertType enum** — add:
```python
MA_BOUNCE_100 = "ma_bounce_100"
MA_BOUNCE_200 = "ma_bounce_200"
```

**Import** new configs: `MA100_STOP_OFFSET_PCT`, `MA200_STOP_OFFSET_PCT`

**`check_ma_bounce_100()`** — follows MA50 pattern:
- Conditions: ma100 available, prior_close > ma100, proximity check, close > ma100
- Stop: `max(bar["Low"], ma100 * (1 - MA100_STOP_OFFSET_PCT))`
- Targets: 1R/2R
- Confidence: high (institutional level)

**`check_ma_bounce_200()`** — same pattern, strongest signal:
- Conditions: ma200 available, prior_close > ma200, proximity check, close > ma200
- Stop: `max(bar["Low"], ma200 * (1 - MA200_STOP_OFFSET_PCT))`
- Targets: 1R/2R
- Confidence: always high (major institutional level)

**Wire into `evaluate_rules()`:**
- Read `ma100`, `ma200` from `prior_day`
- Add both checks inside the `if not is_cooled_down:` BUY block

### Step 4: `tests/test_intraday_rules.py` — new tests

**TestMABounce100:**
- `test_fires_when_bar_low_touches_ma100_and_closes_above`
- `test_no_fire_when_close_below_ma100`
- `test_no_fire_when_prior_close_below_ma100` (breakdown, not pullback)
- `test_no_fire_when_too_far_from_ma100`
- `test_targets_are_1r_and_2r`

**TestMABounce200:** (same structure)
- `test_fires_when_bar_low_touches_ma200_and_closes_above`
- `test_no_fire_when_close_below_ma200`
- `test_no_fire_when_prior_close_below_ma200`
- `test_always_high_confidence` (institutional level)
- `test_targets_are_1r_and_2r`

## Test Plan

### Unit Tests (write first — TDD)
- MA100/200 bounce: fire conditions, no-fire conditions, targets, confidence
- Data pipeline: ma100/ma200 present in return dict

### Integration
- `evaluate_rules()` with ma100/ma200 in prior_day → BUY signals fire
- Existing MA20/50 tests still pass (no regression)

### E2E Validation
```
┌──────────┐     ┌──────────────┐     ┌────────────┐     ┌──────────┐
│ 1. Setup │────▶│ 2. Dry Run   │────▶│ 3. Verify  │────▶│ 4. Check │
│ prior_day│     │ monitor.py   │     │ BUY + SELL │     │ no regr. │
│ with MAs │     │ --dry-run    │     │ alerts     │     │          │
└──────────┘     └──────────────┘     └────────────┘     └──────────┘
```

1. `python -m pytest tests/test_intraday_rules.py -v` — new + existing tests pass
2. `python -m pytest tests/ -v` — full suite passes (153+ tests)
3. `python monitor.py --dry-run` — verify MA100/200 bounce signals appear with proper targets

## Out of Scope
- MA100/200 as **resistance** levels (for SHORT signals) — separate ticket
- Intraday moving averages (computed on 5m bars) — these are daily MAs only
- Swing high/low resistance alerts — separate feature
