# Ticket: Filter session_low_bounce after large gaps

**Priority**: Low
**Status**: Backlog
**File**: `analytics/intraday_rules.py`

## Problem

After a large gap up (>3%), the `session_low_bounce` rule fires on the opening range low, which is just where the stock happened to open — not a real support level that was tested and defended.

Example: LRCX gapped from $220 → $244 (11%). The "session low" was $244 (the open). Price consolidated $244-$246 for a few bars. The alert fired as "session low bounce" but there was no real test — just opening range consolidation.

Compare to AAPL: dropped to $256.53 intraday, recovered, came back to $256.53 and held (tested 2x). That's a real session low bounce.

## Proposed Fix

Add a gap filter to `session_low_bounce`:
- If stock gapped >3% from prior close, require at least one of:
  - Session low tested 2+ times (already partially exists in `session_low_double_bottom`)
  - Price moved at least 0.5% above session low before returning (real pullback, not just consolidation)
  - At least 6 bars (30 min) elapsed since session low was set (let opening range establish)

## Impact

- Reduces false positives on gap-up opening consolidation
- Does NOT affect normal session low bounces (no gap or small gap)
- Protected file: requires impact analysis + approval before implementation
