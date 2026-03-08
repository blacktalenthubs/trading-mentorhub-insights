# Plan: Fix Crypto Daily Candle Timezone Bug + Add Prior Day Low Bounce Rule

## Problem Statement

**What:** BTC-USD doesn't fire alerts when the prior day low is held at the start of a new daily candle. Two root causes: (1) no rule exists for "price approaching prior day low and bouncing/holding above it" — only `prior_day_low_reclaim` which requires a dip *below* first; (2) `fetch_prior_day()` and `fetch_intraday()` have a timezone mismatch for crypto symbols where yfinance uses UTC midnight boundaries but the code compares against local Eastern time.

**Why it matters:** Prior day low bounces are high-conviction setups. Crypto trades 24/7 and daily candle boundaries at UTC midnight (7-8 PM ET) create a data gap where the system has near-empty intraday bars but correct prior day levels — making it impossible for any rule to fire during the transition window.

**What success looks like:** BTC-USD fires a BUY alert when price approaches and holds the prior day low without breaking it. Timezone handling correctly identifies "prior day" for crypto regardless of when the poll runs relative to UTC midnight.

## Solution Architecture

```
┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────┐
│ Fix 1: fetch_prior   │     │ Fix 2: fetch_intraday│     │ Fix 3: New rule  │
│ _day() timezone      │     │ crypto period        │     │ PDL Bounce       │
│                      │     │                      │     │                  │
│ Convert yfinance UTC │     │ Use period="5d" for  │     │ check_prior_day  │
│ timestamps to ET     │     │ crypto, filter to    │     │ _low_bounce()    │
│ before comparing     │     │ current UTC day      │     │                  │
│ against local date   │     │ with fallback to     │     │ Fires when price │
│                      │     │ last 24h             │     │ approaches PDL   │
│                      │     │                      │     │ and holds above  │
└──────────────────────┘     └──────────────────────┘     └──────────────────┘
         │                            │                           │
         └────────────────────────────┴───────────────────────────┘
                                      │
                              ┌───────▼────────┐
                              │ evaluate_rules │
                              │ wires new rule │
                              │ + fixed data   │
                              └────────────────┘
```

**Why this architecture:**
- Fix 1 (timezone) is the root data bug — must be fixed first or all crypto rules are unreliable around UTC midnight
- Fix 2 (intraday period) ensures crypto always has enough bars for pattern detection at day boundaries
- Fix 3 (new rule) fills the gap — "approaching level and holding" is a distinct setup from "broke through and reclaimed"

**Scope boundaries:**
- IN: timezone fix for `fetch_prior_day`, intraday data continuity for crypto, new PDL bounce rule
- OUT: refactoring `fetch_intraday` to be timezone-aware globally, crypto-specific session phases, any changes to existing PDL reclaim rule

## Codebase Analysis

### Existing patterns to follow
- `check_prior_day_low_reclaim()` (intraday_rules.py:434) — proximity check + bounce confirmation pattern
- `check_intraday_support_bounce()` — "price approaches level and bounces" pattern (closest match to what we need)
- `is_crypto_alert_symbol()` (config.py:54) — crypto detection
- `_compute_crypto_opening_range()` (intraday_rules.py:2825) — crypto-specific handling in evaluate_rules

### Data pipeline gap
- `fetch_prior_day()` line 170: `pd.Timestamp.now().normalize()` is local time, but `hist.index[-1].normalize()` is UTC (after tz_localize(None) on line 153). For crypto at UTC midnight, these are different dates.
- `fetch_intraday(period="1d")` for crypto returns only the current UTC day's bars. At UTC midnight, this is 0-2 bars.

### Code to reuse
- `MA_BOUNCE_PROXIMITY_PCT` pattern for proximity check
- `PDL_RECLAIM_MAX_DISTANCE_PCT` for "skip if price ran too far"
- `MA_BOUNCE_SESSION_STOP_PCT` for stop placement

## Files to Modify

| File | Change | Impact |
|------|--------|--------|
| `analytics/intraday_data.py` | Fix timezone in `fetch_prior_day()`: convert UTC timestamps to ET before date comparison. Add crypto-aware `fetch_intraday` that uses wider period. | Lines 42, 153, 170-182 |
| `alert_config.py` | Add `PDL_BOUNCE_PROXIMITY_PCT`, `PDL_BOUNCE_MIN_BARS`, `PDL_BOUNCE_HOLD_BARS` constants | New constants |
| `analytics/intraday_rules.py` | Add `AlertType.PRIOR_DAY_LOW_BOUNCE`, add `check_prior_day_low_bounce()`, wire into `evaluate_rules()` | New enum, new function, ~line 3051 |
| `tests/test_intraday_rules.py` | Add `TestPriorDayLowBounce` test class | New tests |
| `tests/test_crypto_timezone.py` | Test timezone fix: verify `fetch_prior_day` returns correct day for crypto at various UTC hours | New file |

## Implementation Steps

### Step 1: Fix timezone in `fetch_prior_day()` (`analytics/intraday_data.py`)

The core fix: convert yfinance timestamps to ET before comparing against local time.

```python
# BEFORE (line 153):
hist.index = hist.index.tz_localize(None)

# AFTER:
# For crypto, yfinance returns UTC timestamps.
# Convert to ET before stripping timezone so date comparisons are consistent.
if hist.index.tz is not None:
    hist.index = hist.index.tz_convert(ET).tz_localize(None)
else:
    hist.index = hist.index.tz_localize("UTC").tz_convert(ET).tz_localize(None)
```

Same fix for `fetch_intraday()` line 42:
```python
# BEFORE:
hist.index = hist.index.tz_localize(None)

# AFTER:
if hist.index.tz is not None:
    hist.index = hist.index.tz_convert(ET).tz_localize(None)
else:
    hist.index = hist.index.tz_localize("UTC").tz_convert(ET).tz_localize(None)
```

**Important:** This must NOT break equities. yfinance returns equity bars with US/Eastern timestamps already, so `tz_convert(ET)` is a no-op for stocks. Need to verify this in tests.

### Step 2: Fix crypto intraday data continuity (`analytics/intraday_data.py`)

Add a crypto-aware wrapper that ensures enough bars exist at UTC day boundaries:

```python
def fetch_intraday_crypto(symbol: str, interval: str = "5m") -> pd.DataFrame:
    """Fetch intraday bars for crypto with UTC day boundary handling.

    Uses period="5d" and filters to current ET day to avoid the near-empty
    bar problem at UTC midnight.
    """
    bars = fetch_intraday(symbol, period="5d", interval=interval)
    if bars.empty:
        return bars
    # After timezone fix, index is ET-based. Filter to today (ET).
    today = pd.Timestamp.now().normalize()
    today_bars = bars[bars.index.normalize() == today]
    if len(today_bars) >= 6:
        return today_bars
    # Fallback: return last 24h of bars (covers UTC midnight transition)
    cutoff = pd.Timestamp.now() - pd.Timedelta(hours=24)
    return bars[bars.index >= cutoff]
```

Update `monitor.py` line 138 to use this for crypto:
```python
if _is_crypto:
    intraday = fetch_intraday_crypto(symbol)
else:
    intraday = fetch_intraday(symbol)
```

### Step 3: Add config constants (`alert_config.py`)

```python
# Prior Day Low Bounce: price approaches PDL and holds above it
PDL_BOUNCE_PROXIMITY_PCT = 0.005   # 0.5% — bar low must be within this of PDL
PDL_BOUNCE_HOLD_BARS = 2           # 2 consecutive bars closing above PDL after touch
PDL_BOUNCE_MAX_DISTANCE_PCT = 0.010  # 1.0% — skip if price ran too far above PDL
PDL_BOUNCE_STOP_OFFSET_PCT = 0.003   # 0.3% below PDL for stop
```

### Step 4: Add `check_prior_day_low_bounce()` rule (`analytics/intraday_rules.py`)

```python
def check_prior_day_low_bounce(
    symbol: str,
    bars: pd.DataFrame,
    prior_day_low: float,
) -> AlertSignal | None:
    """Price approaches prior day low and bounces/holds above it.

    Unlike prior_day_low_reclaim (which requires a dip below), this fires
    when price gets close to PDL but doesn't break it — a "level hold" signal.

    Conditions:
    - Some bar's low was within PDL_BOUNCE_PROXIMITY_PCT of prior day low
    - No bar broke below prior day low (if it did, PDL reclaim handles it)
    - Last N bars all closed above prior day low (hold confirmed)
    - Price hasn't already run too far above
    """
    if bars.empty or prior_day_low <= 0 or len(bars) < PDL_BOUNCE_HOLD_BARS + 1:
        return None

    # If any bar broke below PDL, this is a reclaim scenario — let PDL reclaim handle it
    if bars["Low"].min() < prior_day_low * (1 - PDL_DIP_MIN_PCT):
        return None

    # Check if any bar's low touched within proximity of PDL
    proximity_level = prior_day_low * (1 + PDL_BOUNCE_PROXIMITY_PCT)
    touched = (bars["Low"] <= proximity_level).any()
    if not touched:
        return None

    # Confirm hold: last N bars all closed above PDL
    recent = bars.iloc[-PDL_BOUNCE_HOLD_BARS:]
    if not (recent["Close"] > prior_day_low).all():
        return None

    last_bar = bars.iloc[-1]

    # Skip if price already ran too far
    distance_pct = (last_bar["Close"] - prior_day_low) / prior_day_low
    if distance_pct > PDL_BOUNCE_MAX_DISTANCE_PCT:
        return None

    entry = last_bar["Close"]
    stop = prior_day_low * (1 - PDL_BOUNCE_STOP_OFFSET_PCT)
    risk = entry - stop
    if risk <= 0:
        return None

    return AlertSignal(
        symbol=symbol,
        alert_type=AlertType.PRIOR_DAY_LOW_BOUNCE,
        direction="BUY",
        price=last_bar["Close"],
        entry=round(entry, 2),
        stop=round(stop, 2),
        target_1=round(entry + risk, 2),
        target_2=round(entry + 2 * risk, 2),
        confidence="high",
        message=(
            f"Prior day low bounce — held above ${prior_day_low:.2f}, "
            f"low ${bars['Low'].min():.2f}"
        ),
    )
```

Add to AlertType enum:
```python
PRIOR_DAY_LOW_BOUNCE = "prior_day_low_bounce"
```

Wire into `evaluate_rules()` after the PDL reclaim check (~line 3052):
```python
if AlertType.PRIOR_DAY_LOW_BOUNCE.value in ENABLED_RULES:
    sig = check_prior_day_low_bounce(symbol, intraday_bars, prior_low)
    if sig:
        sig.message += f" ({phase})"
        signals.append(sig)
```

Add to `ENABLED_RULES` and `BOUNCE_ALERT_TYPES` in `alert_config.py`:
```python
ENABLED_RULES: add "prior_day_low_bounce"
BOUNCE_ALERT_TYPES: add "prior_day_low_bounce"
```

### Step 5: Tests (TDD — write first)

**`tests/test_crypto_timezone.py`** — new file:
- `test_fetch_prior_day_crypto_utc_midnight_returns_correct_day` — mock yfinance with UTC-anchored bars, verify prior day is correct at 7 PM ET (midnight UTC)
- `test_fetch_prior_day_crypto_during_us_hours_returns_correct_day` — verify during normal hours
- `test_fetch_prior_day_equities_unchanged` — regression: stocks still work
- `test_fetch_intraday_crypto_has_bars_at_utc_midnight` — verify bars are not near-empty

**`tests/test_intraday_rules.py`** — add `TestPriorDayLowBounce`:
- `test_fires_when_bar_low_near_pdl_and_holds` — happy path
- `test_no_fire_when_bar_broke_below_pdl` — defer to reclaim rule
- `test_no_fire_when_too_far_from_pdl` — no proximity touch
- `test_no_fire_when_close_below_pdl` — hold not confirmed
- `test_no_fire_when_price_ran_too_far` — stale signal
- `test_targets_are_1r_and_2r` — verify entry/stop/targets
- `test_no_fire_when_insufficient_bars` — edge case

## Test Plan

### Unit Tests (write first — TDD)
- PDL Bounce: fire conditions, no-fire conditions, targets, interaction with PDL reclaim
- Timezone fix: correct prior day for crypto at UTC midnight vs US hours
- Regression: equity fetch_prior_day unchanged

### Integration
- `evaluate_rules()` with crypto flag and PDL bounce conditions → BUY signal fires
- `evaluate_rules()` with PDL broken below → PDL reclaim fires, PDL bounce does NOT
- Existing rules still pass (no regression)

### E2E Validation

```
┌──────────┐     ┌──────────────┐     ┌────────────┐     ┌──────────┐
│ 1. Setup │────▶│ 2. Dry Run   │────▶│ 3. Verify  │────▶│ 4. Check │
│ mocked   │     │ monitor.py   │     │ BTC alerts │     │ no regr. │
│ BTC data │     │ --dry-run    │     │ fire       │     │          │
└──────────┘     └──────────────┘     └────────────┘     └──────────┘
```

1. `python -m pytest tests/test_intraday_rules.py::TestPriorDayLowBounce -v` — new tests pass
2. `python -m pytest tests/test_crypto_timezone.py -v` — timezone tests pass
3. `python -m pytest tests/ -v` — full suite passes (no regressions)
4. `python monitor.py --dry-run` — verify BTC-USD PDL bounce signals appear with correct entry/stop/targets

## Out of Scope
- Refactoring all of `fetch_intraday` to be fully timezone-aware globally — separate effort, risk of regression
- Prior day HIGH bounce rule — same concept for resistance, can follow as separate ticket
- Crypto session-based opening range adjustments — `_compute_crypto_opening_range` works, not broken
- Changes to existing `prior_day_low_reclaim` rule — it's correct for its intended behavior (dip-and-reclaim)
