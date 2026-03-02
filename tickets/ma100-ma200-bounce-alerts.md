# Ticket: Add MA100/MA200 Bounce Alerts

## Problem

The system only detects bounces off MA20 and MA50. The two most important institutional levels — **100-day MA** and **200-day MA** — are completely absent from both the data pipeline and the rules engine.

**Real-world impact (2026-03-02):**
- NVDA bounced off 100MA → no alert fired
- TSLA at 200MA → no alert fired
- SPY at 100MA → no alert fired

These are the levels where mega-cap stocks find major support and institutions accumulate. Missing these means missing the highest-conviction bounce setups.

## Requirements

### Must Have
1. **Data pipeline**: Compute MA100 and MA200 in `fetch_prior_day()` — requires extending history period from 3mo to 1y
2. **`check_ma_bounce_100`**: BUY rule with entry/stop/target_1/target_2 — follows existing MA bounce pattern
3. **`check_ma_bounce_200`**: BUY rule with entry/stop/target_1/target_2 — follows existing MA bounce pattern
4. **Sell-side alerts work automatically**: When BUY fires → `create_active_entry()` → T1/T2/stop/resistance alerts fire on subsequent cycles

### Nice to Have
- Higher default confidence for MA200 bounces (institutional level)
- Wider stop offset for MA100/200 (larger timeframe = more noise tolerance)

## Acceptance Criteria
- [ ] `fetch_prior_day()` returns `ma100` and `ma200` fields
- [ ] MA bounce 100/200 rules fire when price touches those levels
- [ ] Entry/stop/target_1/target_2 computed correctly (R-based targets)
- [ ] SELL alerts (T1, T2, stop loss, resistance) fire after BUY entry created
- [ ] All existing tests still pass
- [ ] New unit tests cover MA100/200 bounce rules
