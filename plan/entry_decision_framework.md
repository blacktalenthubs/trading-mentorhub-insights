# Entry Decision Framework — Design Document

## Problem

We have 15+ BUY signal types, a SPY gate, consolidation detection, daily trend, support fatigue, and various filters — all making interconnected decisions. Adding point fixes (falling knife filter, etc.) creates conflicts because one filter blocks a setup that another rule says is valid.

We need a unified framework for how entries are evaluated, not more ad-hoc filters.

## Current Signal Types (BUY)

### Breakout (trend continuation)
- `consol_breakout_long` — hourly consolidation breaks UP
- `first_hour_high_breakout` — morning range breaks UP
- `inside_day_breakout` — prior day range breaks UP
- `prior_day_high_breakout` — breaks above PDH

### Bounce / Mean Reversion (counter-trend)
- `session_low_bounce_vwap` — low at hourly support, bounce to VWAP
- `vwap_reclaim` — price reclaims VWAP from below
- `vwap_bounce` — pullback to VWAP holds
- `ma_bounce_20/50/100/200` — pullback to MA holds
- `prior_day_low_reclaim` — reclaims PDL after dipping below
- `opening_low_base` — first-hour low holds, base forms
- `morning_low_retest` — retests first-hour low and bounces

### Level Touch (informational → entry)
- `planned_level_touch` — hits a pre-identified level
- `weekly/monthly_level_touch` — hits weekly/monthly S/R

## The Core Question

When should a BUY signal fire vs. be suppressed?

The answer depends on TWO dimensions:
1. **Signal type** — is this a breakout or a bounce?
2. **Market context** — what's the broader environment?

## Proposed Framework: Signal Type x Context Matrix

```
                    TRENDING UP      RANGING        TRENDING DOWN
                    (gate GREEN)   (gate YELLOW)    (gate RED)
                  ┌──────────────┬──────────────┬──────────────┐
  BREAKOUT        │ FIRE (high)  │ FIRE (high)  │ SUPPRESS     │
  (continuation)  │              │ overrides    │              │
                  │              │ yellow       │              │
                  ├──────────────┼──────────────┼──────────────┤
  BOUNCE          │ FIRE (high)  │ FIRE (med)   │ context-     │
  (mean revert)   │              │              │ dependent*   │
                  ├──────────────┼──────────────┼──────────────┤
  LEVEL TOUCH     │ FIRE (med)   │ FIRE (low)   │ NOTICE only  │
  (informational) │              │              │              │
                  └──────────────┴──────────────┴──────────────┘
```

*context-dependent for bounces on RED gate:
- Crypto/SPY: FIRE if key level reclaim + volume (liquidity grab pattern)
- Other equities: SUPPRESS (don't fight the tape)

## What Makes a Bounce Valid After a Drop?

Not all drops are the same. The key differentiator is **how the drop happened**:

### Liquidity Grab (VALID bounce)
```
Price drops fast (wick), sweeps below key level, immediately reclaims.
- Sharp wick below support (not sustained closes below)
- Volume spike on the bounce (buyers stepping in)
- Reclaims a key level (PDL, VWAP, hourly support)
- Example: ETH $2,155 → $2,055 wick → reclaim $2,100 with 2.3x vol
```

### Distribution Breakdown (INVALID bounce — trap)
```
Price grinds down through support with multiple closes below.
- Sustained closes below the level (not just a wick)
- Volume on the breakdown (sellers in control)
- Bounce is weak, low volume, fails to reclaim the level
- Example: BTC $70,200 tested 6x → finally breaks → bounces to $69,500
  but can't reclaim $70,200
```

### How to differentiate programmatically:
1. **Wick vs Close**: Did price CLOSE below the level or just wick below?
   - Wick below + close above = liquidity grab (valid bounce)
   - Close below = real breakdown (invalid bounce)
2. **Volume on bounce**: Is bounce volume > breakdown volume?
   - Yes = buyers overwhelming sellers (valid)
   - No = weak relief rally (invalid)
3. **Level reclaim**: Did price reclaim the broken level within 2-3 bars?
   - Yes = fast reclaim (valid)
   - No = level is now resistance (invalid)

## What Needs to Change

### Phase 1: Classify signals by type (breakout vs bounce)
Already partially done with `BOUNCE_ALERT_TYPES`. Formalize the classification.

### Phase 2: Context-aware gating
Instead of one gate behavior for all BUY signals:
- Breakouts: suppress on RED, override YELLOW (already done)
- Bounces: allow on RED for crypto/SPY if level reclaim + volume confirmed
- Level touches: NOTICE only on RED, don't generate BUY

### Phase 3: Bounce quality scoring
Add to bounce signals:
- Was the drop a wick or sustained close below?
- Volume on bounce vs volume on drop
- Did price reclaim the broken level?
- Time to reclaim (fast = high conviction, slow = low conviction)

### Phase 4: Daily context integration
Already started with `daily_trend` in consolidation breakout.
Extend to all signal types:
- Bullish daily + bounce at support = high conviction
- Bearish daily + bounce at support = lower conviction (add CAUTION)
- Bearish daily + breakdown short = high conviction

## Next Steps

1. Review this framework with user
2. Decide which phases to implement first
3. Collect more weekend crypto data to validate the framework
4. Implement before Monday equity open
