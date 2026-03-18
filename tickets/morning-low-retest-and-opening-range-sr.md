# Morning Low Retest + Opening Range as Dynamic S/R

## Problem

Day trading is about capturing swings from low to high. The morning low (first 15-30 min) becomes the key reference level for the rest of the day, but the alert engine doesn't track it after initial formation.

### Current gaps:
1. **No morning low retest alert** — when price rallies away from the first-hour low, then pulls back to test it later, no alert fires. GOOGL on 2026-03-17 is the perfect example: morning low ~$303, rallied to $311, pulled back to $306-307, bounced back to $311.

2. **No first-hour high breakout** — `opening_range_breakout` exists but is disabled. When price breaks above the first-hour high later in the session, this is a strong continuation signal.

3. **Opening range not used as dynamic S/R** — the first 30-min range (high/low) should serve as support and resistance for the entire session, not just a one-time ORB check.

## Observed on

2026-03-17:
- **GOOGL**: Morning low ~$303-304, rallied to $311, pulled back to retest morning low ~$306-307, bounced to $311. NO ALERT fired for the retest. The existing `opening_low_base` only fires once when the base forms.
- **AAPL**: PDH breakout fired locally at 10 AM but never appeared in production alert report — needs investigation (possible dedup issue).
- **NVDA**: PDL bounce fired at 2:16 PM but the actual low was at open ($181.68). Best entry was the open-drive bounce.

## Proposed New Rules

### 1. `morning_low_retest` (BUY)
```
Trigger: Price retests first-hour low after rallying away
Conditions:
  - First-hour low established (min 6 bars / 30 min after open)
  - Price rallied at least 0.5% above first-hour low (the move away)
  - Price pulls back to within 0.3% of first-hour low
  - Bar closes above first-hour low (bounce confirmed)
  - Time: after 10:30 AM ET (retest, not initial formation)
  - Entry = first-hour low
  - Stop = first-hour low - 0.3% (or session low, whichever is lower)
  - T1 = VWAP or first-hour high
  - T2 = prior day high
```

### 2. `first_hour_high_breakout` (BUY)
```
Trigger: Price breaks above first-hour high after 10:30 AM
Conditions:
  - First-hour high established
  - Bar closes above first-hour high
  - Volume confirmation (>= 0.8x avg)
  - Entry = first-hour high
  - Stop = VWAP or first-hour low
  - T1 = prior day high
  - T2 = 2R
```

### 3. Re-enable `opening_range_breakout` with tuned thresholds
Already implemented but disabled. Review thresholds and enable for mega-cap watchlist.

## Impact

These rules capture the classic day trade setup: morning range establishes, price tests edges of range through the day. This is the highest-probability pattern for the user's trading style (catching swings from low to high).

## Related existing rules
- `opening_low_base` — fires on initial formation only
- `opening_range_breakout` — disabled
- `intraday_support_bounce` — generic, doesn't specifically track morning low
- `session_low_double_bottom` — requires two touches, may be too late
