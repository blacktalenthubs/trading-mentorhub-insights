# Confluence Score Upgrade — Rolling Correlation Window

## Problem

When multiple signals fire in the same direction for the same symbol within a short window (30-75 min), each one is scored independently. Today's SPY example: 5 SHORT alerts over 75 min, all scored B (55-70). Individually they're medium conviction, but together they're screaming "SHORT this." The system doesn't recognize that pattern stacking = higher conviction.

## Current State

- `_consolidate_signals()` in `intraday_rules.py` merges signals that fire in the **same 3-min poll cycle** with a score boost
- `_check_ma_confluence()` detects when an entry aligns with another MA level
- Neither looks back at **recently fired alerts** from prior poll cycles

## Proposed Solution: Rolling Lookback Window

When a new BUY/SHORT signal fires, query the DB for recent alerts on the same symbol + same direction within the last 60 minutes. Boost score based on corroborating signal count.

### Score Boost Logic

```
0 prior signals  → no change (standalone)
1 prior signal   → +10 pts (early confirmation)
2 prior signals  → +15 pts (strong confirmation)
3+ prior signals → +20 pts (full confluence, cap)
```

### Message Enhancement

Append confluence context to the alert message:
```
"[CONFLUENCE: 3 SHORT signals in 52min — Hourly Rejection, VWAP Loss, MA Resistance]"
```

### Implementation

**Where:** `monitor.py`, after `record_alert()` but before `notify()`. Or alternatively inside `evaluate_rules()` by passing `fired_today` timestamps.

**New function in `alert_store.py`:**
```python
def get_recent_same_direction(symbol, direction, user_id, session_date, lookback_minutes=60):
    """Return recent alerts for same symbol+direction within lookback window."""
    # Query alerts table for same symbol, direction, session
    # WHERE created_at >= now - lookback_minutes
    # Returns list of (alert_type, created_at, score)
```

**In `monitor.py` poll loop:**
```python
recent = get_recent_same_direction(symbol, signal.direction, uid, session)
if recent:
    boost = min(len(recent) * 10, 20)  # cap at +20
    signal.score = min(100, signal.score + boost)
    types = [r["alert_type"] for r in recent]
    signal.message += f" [CONFLUENCE: {len(recent)} {signal.direction} signals in {window}min — {', '.join(types)}]"
```

### Example: How Today's SPY Would Have Looked

```
1:39 PM  MA Resistance SHORT        C (30)  → C (30)   standalone
2:27 PM  Hourly Rejection SHORT     B (55)  → B (65)   +10 (1 prior)
2:35 PM  VWAP Loss SHORT            B (70)  → A (85)   +15 (2 prior)
2:51 PM  EMA20 Rejection SHORT      B (55)  → B (75)   +20 (3 prior)  ← MUTED (ACK suppression)
2:55 PM  Double Top SHORT           B (65)  → A (85)   +20 (4 prior)  ← MUTED (ACK suppression)
```

With ACK suppression active, the user would see the first 1-2 alerts. By the time VWAP Loss fires at B→A (85), it has real conviction behind it.

### Interaction with ACK Suppression

These two features complement each other:
- **ACK suppression** reduces Telegram noise (fewer messages)
- **Confluence boost** increases conviction on the messages that DO get through

If user skips the first SHORT, the second one arrives with a higher score and confluence context — more convincing.

### Considerations

- Only boost BUY/SHORT entry signals, not SELL/NOTICE
- Lookback window: 60 min default (configurable)
- Don't double-count signals already consolidated in same poll cycle
- Score cap remains 100
- Confluence context should flow through to AI narrative generation

## Status

**PLANNED** — implement after validating ACK suppression in production (1-2 days).

## Dependencies

- ACK-based directional suppression (deployed 2026-04-01)
- Existing `_consolidate_signals()` pattern in intraday_rules.py
