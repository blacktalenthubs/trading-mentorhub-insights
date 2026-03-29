# Monthly EMA Alerts + Multi-Month Support Zones

## Problem
The system only tracks prior month's high/low for monthly levels. It misses:
1. **Monthly EMA levels** (EMA8, EMA20) — institutional reference levels on the monthly timeframe. SPY at monthly EMA20 ($614) is a massive buy zone.
2. **Multi-month support zones** — areas where monthly bars found support/resistance 2-3+ times over the last 3-6 months. These are the highest-conviction levels on any chart.

## Part 1: Monthly EMA Alerts

### What
Compute monthly EMA8 and EMA20 for each watchlist symbol. Alert when intraday price touches these levels.

### How
1. In `fetch_prior_day()` (intraday_data.py), add monthly EMA computation:
   - Resample daily bars to monthly (or fetch monthly bars from yfinance)
   - Compute EMA8 and EMA20 on monthly closes
   - Store as `monthly_ema8` and `monthly_ema20` in the prior_day dict

2. Add alert rule `check_monthly_ema_touch()`:
   - Fire when intraday price comes within 0.5% of monthly EMA8 or EMA20
   - Direction: BUY if approaching from above (support), alert if approaching from below (resistance)
   - High confidence — monthly EMAs are major institutional levels

3. Add AlertType: `MONTHLY_EMA_TOUCH`

### Example
SPY monthly EMA20 = $614. If SPY intraday drops to $616 (within 0.3% of $614), fire:
```
LONG SPY $616.00
Entry $616.00 · Stop $610.00 · T1 $625.00 · T2 $634.00
Reason: Monthly EMA20 support at $614.02
```

## Part 2: Multi-Month Support Zones

### What
Detect horizontal zones where monthly bar lows/highs cluster across 3-6 months — areas where price repeatedly found buyers or sellers.

### How
1. Compute from last 6-12 monthly bars:
   - Find monthly swing lows (bar low < both neighbors' lows)
   - Cluster nearby lows within 2% into zones
   - Count how many months tested each zone
   - Zones with 2+ touches = multi-month support

2. Same for resistance (monthly swing highs)

3. Alert when intraday price enters a multi-month support/resistance zone

4. Similar to existing `detect_hourly_resistance()` but on monthly bars

### Example
SPY monthly lows: $610 (Jan), $615 (Mar) → zone $610-615 tested 2x = multi-month support.
If SPY drops to $612 intraday → alert with high conviction.

## Priority
Part 1 first (monthly EMAs) — simpler, immediate value, uses existing patterns.
Part 2 after (multi-month zones) — more complex, needs zone detection algorithm.

## Acceptance Criteria
- [ ] Monthly EMA8 and EMA20 computed per symbol
- [ ] Alerts fire when intraday price touches monthly EMA levels
- [ ] Multi-month support zones detected from 6-12 monthly bars
- [ ] Alerts fire when price enters a multi-month zone
- [ ] Tests cover both features
