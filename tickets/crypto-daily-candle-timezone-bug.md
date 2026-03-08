# Crypto Daily Candle Timezone Bug + Missing Prior Day Low Hold Rule

## Problem

Two issues preventing BTC-USD from firing alerts when the prior day low is held at the start of a new daily candle:

### Bug 1: No "Prior Day Low Hold/Bounce" Rule

The existing `prior_day_low_reclaim` rule requires price to **dip below** the prior day low first, then reclaim. If BTC approaches the prior day low and **holds above it** (bounces without breaking), no alert fires. This is a high-conviction bullish signal that's completely missing.

**Example:** BTC new daily candle opens, price pulls back to prior day low (~$66,584), holds above it and bounces — no alert. Meanwhile ETH-USD fires a VWAP bounce alert because that rule only needs intraday data.

### Bug 2: `fetch_prior_day()` Timezone Mismatch for Crypto

`analytics/intraday_data.py` line 170-173:
```python
today = pd.Timestamp.now().normalize()        # LOCAL machine time (Eastern)
last_bar_date = hist.index[-1].normalize()    # UTC date (tz stripped on line 153)
```

yfinance returns BTC-USD daily bars with **UTC midnight** boundaries. After `tz_localize(None)` strips the timezone, the comparison is between a UTC date and a local Eastern date. At UTC midnight (7-8 PM Eastern):

- yfinance says March 8 (new UTC candle)
- Local machine says March 7 still
- `last_bar_date >= today` is True → takes `hist.iloc[-2]` as prior day
- But `fetch_intraday(period="1d")` returns only minutes of the new UTC day

This creates a window where prior day low is correct but intraday bars are near-empty, making it impossible for any dip-and-reclaim pattern to fire.

### Bug 3: `fetch_intraday(period="1d")` Returns Only Current UTC Day for Crypto

For equities, `period="1d"` returns the current trading session (9:30-16:00 ET). For crypto, it returns bars from **UTC midnight onward**. At the start of a new UTC day, this means only 1-2 five-minute bars exist — not enough for any meaningful pattern detection.

## Root Cause

- `fetch_prior_day()` uses `pd.Timestamp.now().normalize()` (local time) but compares against UTC-anchored yfinance timestamps
- `fetch_intraday()` returns current UTC day bars for crypto, creating a data gap at UTC midnight
- No rule exists for "price approaching prior day low and bouncing/holding above it"

## Impact

- BTC-USD and ETH-USD miss prior day low bounce signals at every UTC midnight transition
- High-conviction "level holding" setups go completely unalerted
- The system has no concept of "approaching a key level" — only "broke through and reclaimed"

## Observed on

2026-03-08 — BTC-USD held prior day low ~$66,584 at new daily candle open, no alert fired. ETH-USD VWAP bounce fired correctly (different rule, not affected by daily candle boundary).
