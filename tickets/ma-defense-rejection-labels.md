# MA Defense/Rejection Labels — Alert Context Enrichment

## Problem
Alerts don't communicate which moving average a symbol is defending (support) or being rejected by (resistance). The AI coach identified patterns like "SPY defending 100MA, rejected at 50EMA" — this context should be embedded directly in alert messages so traders don't need to ask the coach.

## Proposed Solution
For each BUY/SELL alert, scan nearby MAs and label:
- **Defending**: price is within 0.5% above a key MA (20/50/100/200 EMA/SMA) and bouncing
- **Rejected**: price approached within 0.5% below a key MA and reversed down

### Implementation
- Add `detect_ma_context(symbol, price, hist) -> dict` to `analytics/intraday_data.py`
  - Returns `{"defending": "100MA", "rejected_by": "50EMA"}` or empty
- Call during `evaluate_rules()` and attach to `AlertSignal`
- Add `ma_defending` and `ma_rejected_by` fields to `AlertSignal` dataclass
- Include in alert message: "MA Bounce 20 | Defending 100MA | Rejected at 50EMA"
- Include in narrator context for richer AI narratives

### Files to Modify
| File | Change |
|------|--------|
| `analytics/intraday_data.py` | Add `detect_ma_context()` |
| `analytics/intraday_rules.py` | Add fields to `AlertSignal`, call detection |
| `alerting/notifier.py` | Append MA context to message |
| `alerting/narrator.py` | Include in narrative prompt |

## Acceptance Criteria
- [ ] MA defense/rejection detected for all enabled alert types
- [ ] Labels visible in Telegram alert messages
- [ ] Narrator references MA context in trade thesis
- [ ] No impact on alert scoring (informational only)
- [ ] Existing 283 intraday_rules tests still pass
