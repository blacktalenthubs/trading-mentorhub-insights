# Outside/Inside Day Detection — Pre-Market Alert Enrichment

## Problem
Alerts fire without knowing whether the prior session was an inside day (consolidation) or outside day (range expansion). This context changes how traders interpret support/resistance levels — inside day breakouts are high-conviction setups, while outside day down means support levels are more critical.

## Proposed Solution
Add a pre-market enrichment step that tags each symbol with its prior-day candle pattern:
- **Inside day**: prior day's high/low contained within the day before's range
- **Outside day**: prior day's range exceeds the day before's range (up or down)
- **Normal day**: neither

### Implementation
- Add `classify_day_pattern(symbol) -> str` to `analytics/intraday_data.py`
- Call it during daily plan generation in `signal_engine.py`
- Store as `day_pattern` column on `daily_plans` table
- Append pattern tag to alert messages: e.g. "MA Bounce 20 [INSIDE DAY BREAKOUT]"
- Inside day breakout → score boost (+5); outside day down → support alerts get confidence note

### Files to Modify
| File | Change |
|------|--------|
| `analytics/intraday_data.py` | Add `classify_day_pattern()` |
| `analytics/signal_engine.py` | Call pattern detection during plan generation |
| `db.py` | Add `day_pattern` column to `daily_plans` |
| `alerting/notifier.py` | Append pattern tag to alert message |

## Acceptance Criteria
- [ ] Inside/outside/normal day correctly classified for all watchlist symbols
- [ ] Pattern tag visible in Telegram alerts
- [ ] Inside day breakout alerts get +5 score boost
- [ ] Existing tests still pass
