# Alert Engine Review — Critical Issues Found Apr 9

**Priority**: Critical
**Status**: Active — needs comprehensive review

## Issues Found Today

### 1. PDH Breakout Not Firing (SPY)
- SPY broke above PDH $677.08, closed at $677.39 — no breakout alert
- **Root cause**: `breakout_margin = prior_day_high * 0.0015` = $1.02. SPY at $677.39 is below $678.10 threshold
- **Fix needed**: Reduce breakout margin to 0.05% (~$0.34 for SPY) or use a fixed dollar amount
- **File**: `analytics/intraday_rules.py` line 1045

### 2. Double Top SHORT Fired Before Breakout
- System fired SHORT at $676.28 (session high double top at $676.47)
- 30 minutes later, SPY broke above $677 and rallied to $678
- The "double top" was actually a consolidation before breakout, not a reversal
- **Root cause**: Double top rule doesn't check if price is about to break out (no volume/momentum filter)
- **Fix needed**: Double top should require 2+ bars of rejection after the second test, not fire immediately

### 3. PDL Bounce at Wrong Level (FIXED)
- Fired "PDL bounce" at $675.52 when PDL was $671.46 ($4 away)
- **Fixed**: Removed 1% proximity override, now uses configured 0.2%

### 4. Resistance Rejection Without Touch (FIXED)
- Fired "rejected at $677.08" when price high was $675.13
- **Fixed**: Tightened proximity from 0.3% to 0.15%

### 5. T1 Spam — 7 Notifications (FIXED)
- T1 set at entry price, fired on every price fluctuation
- **Fixed**: T1 dedup + minimum 0.3% profit guard

### 6. Stale Swing Prices (FIXED)
- AMD entry $217.78 from yesterday's close
- **Fixed**: Premarket refresh at 9 AM + column fallback

## Systematic Issues

### Proximity Thresholds Too Loose
Many rules have 0.3% proximity which is $2 on SPY. Price "near" a level ≠ price "at" a level.
Tightened resistance/rejection to 0.15%. Other rules may need similar review.

### No Cross-Rule Awareness
Double top SHORT fires at $676, then PDH breakout would fire at $678 — but they don't know about each other. The system can give SHORT and then immediately BUY on the same move.
**Need**: A directional lock — if a SHORT was recently fired, suppress BUY signals for N minutes (or vice versa).

### Missing Breakout Confirmation
PDH breakout requires price to close 0.15% above the level ($1 on SPY). That's too tight for a breakout confirmation. Real breakouts often start with a close just $0.30-0.50 above.

### No Volume Context on Rejections
Double top and resistance rejection fire on price pattern alone. Adding a volume check (rejection should have higher volume = sellers stepping in) would reduce false shorts.

## Recommended Review Order
1. PDH breakout margin (line 1045) — reduce to 0.05%
2. Double top confirmation bars — require 2+ bars below after second test
3. Cross-rule directional lock
4. Volume filter on rejection rules
5. Full proximity audit across all rules
