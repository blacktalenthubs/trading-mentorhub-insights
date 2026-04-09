# Ticket: Swing Scanner Stale Prices — Entry/Stop/Target Show Yesterday's Close

**Priority**: High
**Status**: Active
**Protected Files**: `alerting/swing_scanner.py`, `analytics/swing_rules.py`

## Problem

The EOD swing scanner runs at 4:15 PM ET and fires alerts using `fetch_prior_day()` data. The entry price in the alert is **yesterday's closing price**. By the time users see these alerts (next morning), the stock may have moved significantly.

Examples from Apr 8, 2026:
- SPY alert: "Entry $659.22" — but SPY opened at $674 (2.2% gap up)
- GOOGL alert: "Entry $305.46" — but GOOGL is at $317 (3.8% higher)
- The EMAs in the alert message are also stale (EMA5 at $297 when price is $317)

## Root Cause

`swing_scan_eod()` in `alerting/swing_scanner.py` line 257:
```python
prior_day = fetch_prior_day(symbol)
```
All signal prices, entries, stops, targets come from this prior_day data. The alerts fire at 4:15 PM with yesterday's close, but users act on them the next trading day.

## Proposed Solution

**Run a premarket price refresh** for swing alerts at 9:00 AM ET (before market open):

1. Query all pending swing alerts from today's session
2. For each, fetch current premarket price
3. Recalculate entry/stop/target based on current price and the original setup structure
4. Update the alert record in DB with refreshed prices
5. Re-send the Telegram notification with updated prices and a "PREMARKET UPDATE" label

### Alternative: Condition-based entries instead of price-based

Instead of "Entry $659.22", the alert should say:
- "Entry: pullback to 20 EMA ($657.81)" — the LEVEL matters, not yesterday's close
- "Stop: daily close below 20 EMA" — condition, not fixed price
- "Target: prior resistance at $665" — structural level

This way the alert is valid regardless of what price the stock opens at.

## Impact Analysis

- `alerting/swing_scanner.py` — add premarket refresh job or change alert format
- `analytics/swing_rules.py` — change how entry/stop/target are calculated (use levels, not close price)
- `api/app/main.py` — add premarket refresh scheduler job at 9:00 AM ET
- `alerting/notifier.py` — format premarket update messages

## Acceptance Criteria

- Swing alert entry prices are within 1% of actual price at time of user viewing
- OR swing alerts use condition-based entries that don't depend on a specific price
- EMAs in the alert reflect current values, not stale prior-day values
