# Market Regime Detection — Trending vs Choppy Environment Filter

## Problem

The system currently tracks SPY direction (bullish/bearish based on 20MA) but doesn't distinguish between **trending** and **choppy/range-bound** markets. MA bounce signals work well in trending markets but get chopped up in directionless environments. When SPY is below 5/20/50 day MAs with no clear trend, uncertainty is high and BUY signal reliability drops significantly.

## Observed on

2026-02-27 — SPY below 5/20/50 MAs, choppy intraday action. MA bounces fired but follow-through was limited due to market uncertainty. The environment called for higher selectivity.

## Current State

- SPY trend filter: adds "CAUTION: SPY bearish (below 20MA)" to BUY signals
- RS filter: demotes confidence when symbol underperforms SPY
- No concept of market REGIME (trending vs choppy vs volatile)

## Proposed Solution

### 1. MA Alignment Score
Classify SPY's MA structure:
- **Trending Up**: 5 > 20 > 50 (stacked, clean) — full confidence on BUY signals
- **Pullback**: Below 5 but above 20/50 — normal pullback, signals still valid
- **Choppy**: Below 20, MAs tangled (within 0.3% of each other or disordered) — reduce confidence, filter low-grade signals
- **Trending Down**: Below all three, 50 > 20 > 5 (reverse stacked) — SHORT setups, suppress BUY

### 2. Regime Tag on Every Alert
Replace simple "SPY bearish" with richer context:
- `TRENDING UP` / `PULLBACK` / `CHOPPY` / `TRENDING DOWN`
- In CHOPPY regime: only A/A+ grade BUY signals pass through, B/C get suppressed or demoted

### 3. Volatility Overlay (optional, future)
- ATR-based or VIX-based volatility classification
- High ATR + aligned MAs = trending with volatility (tradeable)
- High ATR + tangled MAs = chop (avoid)

## Key Decisions

- Threshold for "tangled MAs" (0.3% spread between all three?)
- Whether to SUPPRESS low-grade signals in choppy regime or just DEMOTE confidence
- Daily MA data source for 5/20/50 (already available in prior_day context?)
- Should regime affect position sizing too? (smaller in choppy)

## Impact

Prevents taking low-probability BUY signals in choppy markets. Reduces stop-outs on days where the market has no direction. The regime filter would sit above all BUY rules as a meta-filter.
