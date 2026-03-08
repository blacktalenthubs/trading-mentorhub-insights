# Prior Session Pattern Context on Alerts

## Problem
Today's alerts lack context about what happened yesterday. An alert saying "SPY MA Bounce at 679.62" is more actionable if the trader knows "yesterday was an outside day down — this support level is being tested after a range expansion." Currently only the AI coach can synthesize this; it should be baked into the alert itself.

## Proposed Solution
Attach a 1-line prior session summary to each alert message:
- "Prior session: OUTSIDE DAY DOWN, low 675.90 → support 679.62 tested"
- "Prior session: INSIDE DAY, consolidation → breakout pending"
- "Prior session: 3 BUY alerts fired, 1 T1 hit, 0 stops"

### Implementation
- Add `get_prior_session_context(symbol) -> str` to `alerting/alert_store.py`
  - Combines day pattern (from outside/inside day ticket) + prior session alert summary
- Call in `notifier.py` before sending and append to message body
- Include in narrator prompt for richer AI narratives

### Dependencies
- Depends on: `outside-inside-day-detection.md` (for day pattern classification)

### Files to Modify
| File | Change |
|------|--------|
| `alerting/alert_store.py` | Add `get_prior_session_context()` |
| `alerting/notifier.py` | Append prior session line to alert message |
| `alerting/narrator.py` | Include in narrative prompt context |

## Acceptance Criteria
- [ ] Prior session context line appears in Telegram alerts
- [ ] Context is concise (1 line max)
- [ ] Gracefully handles missing data (first day, no prior alerts)
- [ ] Existing tests still pass
