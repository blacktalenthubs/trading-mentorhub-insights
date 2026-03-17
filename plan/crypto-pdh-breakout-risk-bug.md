# Plan: Fix Crypto PDH Breakout risk <= 0 Bug

## Problem Statement
`check_prior_day_high_breakout()` silently drops alerts for crypto when price opens above PDH, because `stop = last_bar["Low"]` > `entry = PDH`, making risk negative. Same bug in `check_weekly_high_breakout()`.

## Solution Architecture

```
Current (broken):
  entry = PDH
  stop  = last_bar["Low"]    ← ABOVE entry for crypto gap-ups
  risk  = entry - stop        ← NEGATIVE → return None

Fixed:
  entry = PDH
  stop  = last_bar["Low"]
  IF stop >= entry:           ← Gap-up detected
    lookback_low = min(lookback bars Low)
    stop = min(lookback_low, PDH - buffer)
    IF stop still >= entry:   ← Even lookback is above PDH
      stop = PDH * (1 - fallback_pct)  ← percentage-based stop
  risk  = entry - stop         ← POSITIVE → alert fires
```

## Files to Modify

| File | Change |
|------|--------|
| `analytics/intraday_rules.py` | Fix `check_prior_day_high_breakout()` stop logic (lines 749-754) |
| `analytics/intraday_rules.py` | Fix `check_weekly_high_breakout()` stop logic (lines 1427-1432) |
| `tests/test_intraday_rules.py` | Add test cases for crypto gap-up above PDH |

## Implementation Details

### Fix for `check_prior_day_high_breakout()` (line 749-754)

When `stop >= entry`, use lookback low. If lookback low is also above PDH (crypto gap-up), use PDH with a small buffer as stop:

```python
entry = round(prior_day_high, 2)
stop = round(last_bar["Low"], 2)
stop = _cap_risk(entry, stop, symbol=symbol)
risk = entry - stop
if risk <= 0:
    # Gap-up above breakout level — use lookback low or PDH buffer
    lookback_low = round(bars.tail(MA_BOUNCE_LOOKBACK_BARS)["Low"].min(), 2)
    if lookback_low < entry:
        stop = lookback_low
    else:
        # Even lookback is above PDH — use PDH with 0.5% buffer
        stop = round(entry * 0.995, 2)
    stop = _cap_risk(entry, stop, symbol=symbol)
    risk = entry - stop
    if risk <= 0:
        return None
```

### Same fix for `check_weekly_high_breakout()` (line 1427-1432)

Identical pattern — apply same logic.

## Test Plan

1. **Existing test**: Verify all 283 existing tests still pass
2. **New test — crypto gap-up above PDH**: BTC opens above PDH, all bars have Low > PDH → alert should fire with PDH buffer stop
3. **New test — crypto lookback low below PDH**: Some bars have Low < PDH in lookback → uses lookback low as stop
4. **New test — weekly high same pattern**: Weekly high breakout with gap-up
5. **New test — equity behavior unchanged**: Equity PDH breakout with normal approach from below still works

## Out of Scope
- Changing how `fetch_prior_day` determines PDH for crypto (UTC boundaries are correct)
- Volume ratio adjustments for crypto (separate concern)
- Worker uptime monitoring (separate infra issue)
