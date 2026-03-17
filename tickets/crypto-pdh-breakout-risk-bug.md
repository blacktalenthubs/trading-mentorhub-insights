# Crypto PDH Breakout — risk <= 0 kills alert when price opens above PDH

## Problem

`check_prior_day_high_breakout()` never fires for crypto symbols (BTC-USD, ETH-USD) when the asset opens above the prior day high. This is the common case for crypto because:

1. Daily bars use UTC midnight boundaries (yfinance)
2. Crypto trades 24/7 — price often moves above PDH during off-hours
3. By the time the worker polls, every 5-min bar already has `Low > PDH`

The function sets `entry = PDH` and `stop = last_bar["Low"]`. When `stop > entry`, `risk = entry - stop` is negative, and the function returns `None` (line 753).

## Evidence

- **March 15, 2026**: BTC PDH = $71,291 (from March 14 UTC daily bar). BTC opened March 15 at $71,411 — already above PDH. Every single 5-min bar had `Low > PDH`. The breakout alert never fired despite BTC closing at $72,789 (+2.1% above PDH) with strong volume.
- **March 15, 2026**: ETH PDH = $2,105. ETH crossed above at 01:15 ET with volume ratio 2.29x. Risk calculation also negative.
- **March 10, 2026**: ETH PDH breakout DID fire — because ETH approached PDH from below during that session (normal equity-like behavior).

## Root Cause

`intraday_rules.py` line 749-754:
```python
entry = round(prior_day_high, 2)
stop = round(last_bar["Low"], 2)
stop = _cap_risk(entry, stop, symbol=symbol)
risk = entry - stop
if risk <= 0:
    return None  # <-- always hits this for crypto gap-up above PDH
```

## Fix

When `stop >= entry` (price entirely above PDH), use the lookback low or PDH as the stop reference. The breakout is confirmed — the stop should protect against a failed breakout (drop back below PDH).

## Impact

BTC and ETH PDH breakout alerts are silently dropped on most days. This is a high-value alert type for crypto — prior day high breakout with volume is one of the strongest momentum signals.

## Observed on

2026-03-15 — BTC-USD +3%, ETH-USD +5.8%, zero PDH breakout alerts fired.
