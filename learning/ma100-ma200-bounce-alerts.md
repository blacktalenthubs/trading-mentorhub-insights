# Learning: MA100/MA200 Bounce Alerts

## Codebase Analysis

### Existing MA Bounce Pattern
Both `check_ma_bounce_20` and `check_ma_bounce_50` follow the same structure:
1. Validate MA is available and > 0
2. Check uptrend condition (MA20 > MA50 for bounce_20; prior_close > MA50 for bounce_50)
3. Check proximity: `abs(bar["Low"] - MA) / MA <= MA_BOUNCE_PROXIMITY_PCT`
4. Check bounce: `bar["Close"] > MA`
5. Compute entry/stop/targets using R-multiples

### Key Differences Between MA Levels

| Aspect | MA20/50 | MA100/200 |
|--------|---------|-----------|
| Timeframe | Short/medium trend | Intermediate/long-term |
| Uptrend check | MA20 > MA50 | Price above MA (simpler) |
| Bounce frequency | Often | Rare but high-conviction |
| Stop offset | 0.5% below MA | Should be wider (~0.7-1%) |
| Proximity | 0.3% | Could use same or slightly wider |

### Data Pipeline Gap
- `fetch_prior_day()` uses `period="3mo"` (~63 trading days)
- MA100 needs >= 100 bars → need `period="6mo"` minimum
- MA200 needs >= 200 bars → need `period="1y"`
- **Solution**: Change to `period="1y"` (covers both + margin)

### Uptrend Validation for MA100/200
- MA20 bounce requires MA20 > MA50 (short uptrend)
- MA50 bounce requires prior_close > MA50 (pullback not breakdown)
- MA100 bounce: prior_close > MA100 confirms pullback (same as MA50 pattern)
- MA200 bounce: prior_close > MA200 confirms pullback (same pattern)
- No cross-MA uptrend check needed — these are standalone institutional levels

### Stop Placement
- MA20/50: `stop = max(bar["Low"], MA * (1 - 0.005))` — 0.5% below MA
- MA100/200 operate on larger timeframes → price can wick further through before bouncing
- Recommend `MA100_STOP_OFFSET_PCT = 0.007` (0.7%) and `MA200_STOP_OFFSET_PCT = 0.010` (1.0%)

### Sell-Side Flow (Already Handled)
```
BUY fires → monitor.py calls create_active_entry(signal) → DB stores entry/stop/T1/T2
Next poll → get_active_entries() returns it → SELL rules evaluate against it:
  - check_target_1_hit: bar["High"] >= T1
  - check_target_2_hit: bar["High"] >= T2
  - check_stop_loss_hit: bar["Low"] <= stop
  - check_resistance_prior_high: bar["High"] near prior_high (needs has_active=True)
```
No changes needed on sell-side — it's generic over all active entries regardless of alert_type.

### Files to Modify
1. `analytics/intraday_data.py` — extend history period, compute MA100/MA200
2. `alert_config.py` — add MA100/MA200 stop offset constants
3. `analytics/intraday_rules.py` — new AlertType enum values, new check functions, wire into evaluate_rules
4. `tests/test_intraday_rules.py` — new test classes for MA100/200 bounce
