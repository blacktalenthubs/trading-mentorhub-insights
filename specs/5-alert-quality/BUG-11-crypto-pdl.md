# BUG-11: Crypto PDL uses session low instead of actual prior day low

## Problem
BTC-USD "prior day low reclaim" alert fired at $68,840 claiming it's the PDL.
But the daily chart shows the actual prior day low is much lower (~$66,000-67,000).
The $68,840 level is the current session's low, not yesterday's low.

## Root Cause (suspected)
`fetch_prior_day()` for crypto may be using wrong day boundary:
- Crypto trades 24/7, no clear "session" boundary
- UTC date rollover vs market convention
- yfinance daily bars for crypto may return partial/current day as "prior day"

## Impact
- False "PDL reclaim" alerts on crypto symbols
- Entry levels based on wrong support zone
- Misleading for traders who check against daily chart

## Fix needed
In `analytics/intraday_data.py` → `fetch_prior_day()`:
- For crypto, ensure we use the COMPLETED prior calendar day (UTC)
- Not the current partial day
- Verify with `BTC-USD` daily bars: what does yfinance return for "yesterday"?

## Priority
HIGH — affects live crypto alerts
