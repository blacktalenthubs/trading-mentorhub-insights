# Learning: Crypto PDH Breakout risk <= 0 Bug

## Investigation Summary

### What happened
BTC and ETH broke above their prior day highs on March 15, 2026 but no `prior_day_high_breakout` alert fired. Manual simulation confirmed the root cause.

### Root Cause: Negative Risk Calculation
`check_prior_day_high_breakout()` sets `entry = PDH` and `stop = last_bar["Low"]`. For crypto, daily bars use UTC boundaries. When price opens the ET session already above PDH (gap-up overnight), every 5-min bar has `Low > PDH`, making `risk = entry - stop` negative. The function returns `None`.

### Simulation Results (March 15 BTC-USD)
- PDH (March 14 UTC high): $71,291
- BTC opened March 15 at $71,411 — already above PDH
- 288 5-min bars, ALL closed above PDH
- Volume was sufficient (ratio up to 6.28x on some bars)
- `risk` was negative on every single bar (-48 to -1316)
- Alert never fired

### Same Bug in Other Breakout Rules
- `check_weekly_high_breakout()` — same `risk <= 0` guard at line 1431
- `check_inside_day_breakout()` — uses `inside_low` as stop, so less susceptible

### Why This Only Affects Crypto
- Equities have a defined open; price usually approaches PDH from below during the session
- Crypto trades 24/7; UTC daily boundaries mean the "session" can start with price already above PDH
- The breakout may have happened during Asia/Europe hours, but the alert engine needs to catch it whenever it polls

### ETH March 10 — Why That One Worked
ETH PDH breakout fired on March 10 at 14:59 UTC. On that day, ETH approached PDH from below during the session (normal equity-like behavior), so `bar_low < entry` and risk was positive.

### Fix Approach
When `stop >= entry` (gap-up above breakout level), set stop to `PDH` itself. The thesis: if price drops back below PDH, the breakout failed. This is the natural stop for a gap-up breakout.

- `stop = prior_day_high` (or a small buffer below)
- Risk = `entry - stop` still works, using a percentage-based fallback
- Apply same fix to `check_weekly_high_breakout()`
