# BUG-12: Crypto VWAP calculation inconsistent across timeframes

## Problems

### 1. VWAP differs across timeframes
The VWAP line shows different values on 1H vs 4H charts. The chart VWAP
indicator computes from visible bars, not session-anchored. For crypto,
there's no clear "session open" so VWAP anchor varies by timeframe.

### 2. VWAP LOSS alert fires on $3 difference ($69,130 vs $69,127)
On a $69K asset, a $3 cross below VWAP is noise (0.004%). The threshold
should require at least 0.1% below VWAP to be meaningful.

### 3. Crypto VWAP anchor point
For equities: VWAP anchors at 9:30 AM open (clear).
For crypto: VWAP should anchor at midnight UTC (24h session reset).
Currently unclear if the bars passed to compute_vwap() start from midnight UTC.

## Fix Needed
1. Chart VWAP: ensure consistent session-anchored computation across timeframes
2. Alert VWAP loss: add minimum distance threshold (0.1% below VWAP)
3. Crypto: verify bars passed to compute_vwap() start from midnight UTC

## Priority
MEDIUM — VWAP loss is already a NOTICE (not entry), so impact is limited
