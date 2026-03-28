# Hourly Resistance Rejection SHORT

## Problem Statement
Price tests a horizontal hourly resistance level multiple times and gets rejected, but no SHORT alert fires. The system only detects EMA/MA rejections (diagonal levels) — it misses horizontal supply zones where sellers repeatedly step in.

**Example**: ETH-USD tested $2076 resistance 3-4 times on the hourly chart, got rejected each time, then broke down. The consolidation breakdown alert fired at $2061 — too late. The ideal short was at the rejection off $2076.

**Why it matters**: Horizontal resistance rejections are high-probability shorts, especially when the level has been tested multiple times. For a busy professional who can't watch charts, getting alerted at the rejection (not after the breakdown) is the difference between a 2:1 and a 5:1 risk/reward.

## Solution Architecture

```
┌──────────────┐     ┌───────────────────┐     ┌──────────────────┐
│ Hourly bars  │────▶│ detect_hourly_    │────▶│ hourly_resistance│
│ (1h OHLCV)   │     │ resistance()      │     │ [2076, 2197, ...]│
└──────────────┘     └───────────────────┘     └────────┬─────────┘
                                                        │
┌──────────────┐                                        ▼
│ 5-min bars   │────▶ check_hourly_resistance_rejection_short()
│ (intraday)   │        │
└──────────────┘        ├─ Bar high near resistance? (within 0.3%)
                        ├─ Close in lower 40% of range? (rejection)
                        ├─ Price below resistance? (approaching from below)
                        ├─ Not already too far below? (max distance)
                        │
                        ▼
                   AlertSignal(SHORT) → Telegram + Email
```

**Data flow**: `hourly_resistance` list is already computed in `evaluate_rules()` via `detect_hourly_resistance()`. We just need to pass it to the new rule function.

## Codebase Analysis

### Existing patterns to follow
- `check_ema_rejection_short` (line 3482) — rejection confirmation via close in lower 40% of bar range
- `check_hourly_resistance_approach` (line 5122) — already uses hourly_resistance list, proximity check, direction guard
- `detect_hourly_resistance` in `intraday_data.py` (line 301) — already clusters swing highs, filters broken levels

### Code to reuse
- `hourly_resistance` list already computed in `evaluate_rules()` (line 6418)
- Proximity check pattern from `check_hourly_resistance_approach`
- Rejection confirmation pattern from `check_ema_rejection_short`
- Stop/target calculation pattern from all SHORT rules

### Gaps
- No existing rule combines horizontal level + rejection candle pattern
- Need new AlertType enum value
- Need new config constants

## Implementation Approach

### Files to modify

| File | Change |
|------|--------|
| `alert_config.py` | Add config constants + enable rule |
| `analytics/intraday_rules.py` | Add AlertType, rule function, wire into evaluate_rules |
| `tests/test_intraday_rules.py` | Add test cases |

### Config constants (alert_config.py)

```python
# Hourly Resistance Rejection SHORT
HOURLY_RES_REJECTION_PROXIMITY_PCT = 0.003  # 0.3% — bar high must reach within this of level
HOURLY_RES_REJECTION_CLOSE_PCT = 0.40       # close must be in lower 40% of bar range
HOURLY_RES_REJECTION_MIN_BARS = 12          # 60 min into session minimum
HOURLY_RES_REJECTION_STOP_OFFSET_PCT = 0.003  # 0.3% above resistance for stop
```

### AlertType enum

```python
HOURLY_RESISTANCE_REJECTION_SHORT = "hourly_resistance_rejection_short"
```

### Rule function signature

```python
def check_hourly_resistance_rejection_short(
    symbol: str,
    bars: pd.DataFrame,
    hourly_resistance: list[float],
    prior_close: float | None = None,
) -> AlertSignal | None:
```

### Conditions
1. At least 12 bars (60 min into session)
2. Bar high reaches within 0.3% of an hourly resistance level
3. Bar closes in lower 40% of range (rejection candle confirmed)
4. Price must be BELOW the resistance (approaching from below)
5. If prior close was above the level, skip (it's support, not resistance)

### Stop/Target calculation
- **Stop**: resistance level * 1.003 (0.3% above)
- **Target 1**: entry - 1R
- **Target 2**: entry - 2R

### Wire into evaluate_rules
Add after the existing `check_hourly_resistance_approach` call (~line 7024), using same `hourly_resistance` data.

## Test Plan

### Unit tests
1. **Fires on valid rejection**: Bar high near resistance, close in lower 40%, price below level
2. **No fire when close too high**: Bar touches resistance but closes in upper 60% (no rejection)
3. **No fire when price above level**: Prior close above resistance (it's support, not resistance)
4. **No fire with too few bars**: Less than 12 bars
5. **No fire when no resistance levels**: Empty hourly_resistance list
6. **Picks nearest resistance**: Multiple levels, selects closest above price
7. **Crypto max distance**: Verify crypto-specific filtering if needed

### E2E validation
1. Deploy to Railway
2. Wait for crypto resistance test (ETH/BTC test levels frequently)
3. Verify alert fires near resistance with correct entry/stop/targets
4. Verify Telegram + email delivery

## Out of Scope
- Multi-touch count in the alert message (would require passing touch history from detect_hourly_resistance) — future enhancement
- Intraday horizontal resistance detection (building levels from 5-min bars within the session) — different pattern
- Volume confirmation at rejection — can add later based on evaluation data
