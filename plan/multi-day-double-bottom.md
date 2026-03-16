# Plan: Multi-Day Double Bottom Alert

## Problem Statement

**What:** The current `session_low_double_bottom` only detects intraday micro-patterns (two touches of session low within a single day on 5-min bars). It misses the structural multi-day double bottoms visible on daily/4H charts — the setups that give real conviction.

**Example:** BTC-USD had a clear double bottom at **$70,413** (4H chart) / **$70,450** area (daily chart), tested on two separate days with recovery between. Our system fired a session_low_double_bottom at $71,343 — $900 above the real level, a noise-level intraday retest.

**Why it matters:** Multi-day double bottoms are among the highest-conviction reversal patterns. The user explicitly trusts these for entries. Missing them means missing the best trades.

**Success criteria:** When BTC tests $70,413 twice across different days and bounces, the system fires a `multi_day_double_bottom` alert at the structural level, not a micro-intraday one.

---

## Solution Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│ fetch_prior_ │     │ detect_daily_    │     │ check_multi_day_    │
│ day()        │────▶│ double_bottoms() │────▶│ double_bottom()     │
│ (1y daily    │     │ (find swing low  │     │ (intraday bar near  │
│  bars exist) │     │  zones w/ 2+     │     │  a DB zone? bounce  │
│              │     │  touches)        │     │  confirmed? → BUY)  │
└──────────────┘     └──────────────────┘     └─────────────────────┘
        │                                              │
        │ hist DataFrame                               │ AlertSignal
        │ already fetched                              │
        ▼                                              ▼
  No new API call                              evaluate_rules() appends
  (piggyback on existing)                      to signals list
```

### Data Flow

1. `fetch_prior_day()` already calls `yf.Ticker(symbol).history(period="1y")` — returns 1 year of daily OHLCV bars
2. **New:** Extract last 20 completed daily bars from `hist`, detect swing low zones with 2+ touches → return as `daily_double_bottoms` list in the `prior_day` dict
3. **New:** In `evaluate_rules()`, call `check_multi_day_double_bottom()` which checks if current intraday bar is bouncing off a multi-day double bottom zone
4. Fire BUY signal with structural entry/stop/targets

### Why this approach
- **No additional API calls** — `fetch_prior_day()` already has 1 year of daily history
- **Follows existing patterns** — mirrors `detect_hourly_support()` for swing detection and `check_session_low_retest()` for the bounce check
- **Works for stocks and crypto** — `fetch_prior_day()` already handles both with timezone normalization

---

## Codebase Analysis

### Existing patterns to reuse:
| Pattern | File | What we reuse |
|---|---|---|
| `detect_hourly_support()` | `intraday_data.py:281-309` | Swing low detection + clustering algorithm |
| `check_session_low_retest()` | `intraday_rules.py:2630-2729` | Double bottom check structure, AlertSignal creation |
| `check_intraday_support_bounce()` | `intraday_rules.py` | "Intraday price approaching a known support level" pattern |
| `fetch_prior_day()` return dict | `intraday_data.py:424-454` | Where to add `daily_double_bottoms` field |

### Files to modify:
| File | Change |
|---|---|
| `analytics/intraday_data.py` | Add `detect_daily_double_bottoms()` function |
| `analytics/intraday_data.py` | Extend `fetch_prior_day()` to include `daily_double_bottoms` in return dict |
| `analytics/intraday_rules.py` | Add `MULTI_DAY_DOUBLE_BOTTOM` to `AlertType` enum |
| `analytics/intraday_rules.py` | Add `check_multi_day_double_bottom()` rule function |
| `analytics/intraday_rules.py` | Hook into `evaluate_rules()` after session_low_double_bottom |
| `alert_config.py` | Add constants + add to `ENABLED_RULES` and `BOUNCE_ALERT_TYPES` |
| `tests/test_intraday_rules.py` | Add `TestMultiDayDoubleBottom` test class |

### Files NOT modified:
- `monitor.py` / `worker.py` — no changes needed, data flows through `evaluate_rules()`
- `alerting/` — no changes, existing alert pipeline handles new AlertType automatically
- `db.py` — no schema changes needed

---

## Implementation Approach

### Step 1: Constants in `alert_config.py`

```python
# Multi-Day Double Bottom
DAILY_DB_LOOKBACK_DAYS = 20           # Scan last 20 completed daily bars
DAILY_DB_SWING_LOW_CLUSTER_PCT = 0.005  # 0.5% — cluster daily lows within this range
DAILY_DB_MIN_TOUCHES = 2              # Minimum touches to qualify as double bottom
DAILY_DB_MIN_DAYS_BETWEEN = 1         # At least 1 day between touches (not same day)
DAILY_DB_MIN_RECOVERY_PCT = 0.005     # 0.5% recovery between touches
DAILY_DB_INTRADAY_PROXIMITY_PCT = 0.005  # 0.5% — how close intraday bar must be to trigger
DAILY_DB_STOP_OFFSET_PCT = 0.005      # 0.5% below zone low for stop
DAILY_DB_MAX_DISTANCE_PCT = 0.02      # 2% — skip if price already ran past zone
```

### Step 2: `detect_daily_double_bottoms()` in `intraday_data.py`

Algorithm:
1. Take last 20 completed daily bars
2. Find swing lows (bar whose Low < both neighbors' Low)
3. Also include the absolute low of the period (may not be a swing low but is a structural level)
4. Cluster swing lows within 0.5% (wider than intraday 0.3% because daily bars have more range)
5. For each cluster with 2+ touches: record as double bottom zone
6. Return list: `[{"level": float, "touch_count": int, "first_touch_days_ago": int, "last_touch_days_ago": int}]`

### Step 3: Extend `fetch_prior_day()` return dict

Add the daily_double_bottoms detection at the end of `fetch_prior_day()`, using the `hist` DataFrame that's already in scope. Add `"daily_double_bottoms": [...]` to the return dict.

### Step 4: `check_multi_day_double_bottom()` rule in `intraday_rules.py`

Trigger conditions:
1. `daily_double_bottoms` list is non-empty
2. Last intraday bar's low is within `DAILY_DB_INTRADAY_PROXIMITY_PCT` (0.5%) of a double bottom zone
3. Last bar closes above the zone level (bounce confirmed)
4. Price hasn't already run >2% above the zone (stale signal guard)
5. Not a descending low (current low not significantly below zone — reject if making lower lows)

Entry/Stop/Targets:
- Entry = zone level (structural support)
- Stop = zone low - 0.5% (below both touches)
- T1 = entry + 1x risk (minimum target)
- T2 = entry + 2x risk (measured move)
- Confidence: "high" if 3+ touches or volume exhaustion on retest; "medium" for 2 touches

### Step 5: Hook into `evaluate_rules()`

After the session_low_double_bottom block (line ~4406), add:

```python
# --- Multi-Day Double Bottom ---
if AlertType.MULTI_DAY_DOUBLE_BOTTOM.value in ENABLED_RULES:
    daily_dbs = prior_day.get("daily_double_bottoms", [])
    if daily_dbs and not is_cooled_down:
        sig = check_multi_day_double_bottom(
            symbol, intraday_bars, daily_dbs, bar_vol, avg_vol,
        )
        if sig:
            sig.message += f" ({phase})"
            sig.message += caution_suffix
            signals.append(sig)
```

---

## Test Plan (TDD)

### Unit Tests: `TestMultiDayDoubleBottom`

1. **test_detect_daily_double_bottoms_two_touches** — Two daily bars with lows at same zone → detected
2. **test_detect_daily_double_bottoms_no_retest** — Only one low → not detected
3. **test_detect_daily_double_bottoms_three_touches** — Three touches → detected with touch_count=3
4. **test_detect_daily_double_bottoms_descending_lows** — Lows getting lower each time → not a double bottom, reject
5. **test_fires_when_intraday_bounces_at_zone** — Intraday bar touches zone and closes above → fires BUY
6. **test_no_fire_when_too_far_above_zone** — Price already 3% above zone → stale, skip
7. **test_no_fire_when_close_below_zone** — Intraday close below zone → no bounce confirmation
8. **test_confidence_high_on_three_touches** — 3+ touches → high confidence
9. **test_confidence_medium_on_two_touches** — 2 touches → medium confidence
10. **test_works_for_crypto_btc** — BTC-level prices ($70K) with appropriate % thresholds
11. **test_works_for_stocks** — Stock-level prices ($150) with same logic

### Test fixtures:
- Build synthetic daily DataFrame (20 bars) with controlled lows
- Build synthetic intraday DataFrame (5-min bars) approaching the zone
- Follow `TestSessionLowDoubleBottom` fixture pattern

---

## E2E Validation

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ 1. Setup     │────▶│ 2. Simulate      │────▶│ 3. Verify        │────▶│ 4. Cleanup       │
│ Add constants│     │ BTC touches      │     │ Alert fires with │     │ None needed      │
│ + rule code  │     │ $70,413 twice    │     │ correct levels   │     │ (no DB changes)  │
└──────────────┘     └──────────────────┘     └──────────────────┘     └──────────────────┘
```

1. **Run unit tests:** `python3 -m pytest tests/test_intraday_rules.py -v -k "multi_day_double_bottom"`
2. **Run full test suite:** `python3 -m pytest tests/ -v`
3. **Manual validation:** Create a test script that feeds real BTC data through `detect_daily_double_bottoms()` and verifies the $70,413 zone is detected

---

## Out of Scope
- Multi-day double TOP (bearish pattern) — future work
- Measured move targets (height of W pattern) — can add later, start with 1R/2R
- Volume profile confirmation — future enhancement
- Triple bottom detection — covered implicitly (3+ touches = higher confidence)
