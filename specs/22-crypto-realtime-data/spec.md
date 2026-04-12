# Feature Specification: Real-Time Crypto Data via Coinbase API

**Status**: Draft
**Created**: 2026-04-08
**Author**: Claude (via /speckit.specify)

## Overview

Replace yfinance as the crypto data source with the Coinbase Advanced Trade API for BTC-USD and ETH-USD. yfinance crypto data lags 15-60 minutes, causing stale charts, inaccurate alert levels, and user confusion when comparing to real-time prices on Webull/Coinbase. The Coinbase API provides free, real-time OHLCV candles with no API key required and no US geo-restrictions.

## Problem Statement

Crypto traders on TradeCoPilot see prices that are 15-60 minutes behind reality:

1. **Stale charts**: ETH shows $2,245 on the platform while Webull shows $2,252 — a $7 gap that erodes trust
2. **Inaccurate alerts**: MA bounce alerts fire based on stale data, meaning the actual price may have already moved past the entry level
3. **AI CoPilot analysis**: The AI analyzes stale bars, producing entry/stop levels that may already be invalidated by the time the user sees them
4. **User confusion**: Paying users compare the platform to Webull/Coinbase and wonder why prices don't match

**Impact**: Crypto users (BTC-USD, ETH-USD watchlists) experience lower trust in the platform's data accuracy. This is the #1 data quality issue for crypto users.

## Functional Requirements

### FR-1: Real-Time Crypto Price Quotes
- Current price for BTC-USD and ETH-USD updates within 5 seconds of actual market price
- The live price ticker, watchlist prices, and chart current-price label all reflect real-time data
- Acceptance: Compare platform price to Coinbase.com — difference is less than $1 for BTC, less than $0.50 for ETH

### FR-2: Real-Time OHLCV Candles
- Intraday candles (5m, 15m, 30m, 1H) for crypto symbols are fetched from Coinbase instead of yfinance
- Daily and weekly candles also sourced from Coinbase for consistency
- Candle data returns within 2 seconds of request
- Acceptance: 5-minute candle on ETH-USD matches Coinbase Pro chart within $0.50 on close price

### FR-3: Seamless Fallback
- If the Coinbase API is unavailable (down, rate-limited, network error), the system falls back to yfinance transparently
- Fallback is logged but does not disrupt the user experience
- Acceptance: Kill network access to Coinbase API — platform continues showing crypto data (from yfinance) with no user-visible error

### FR-4: Same DataFrame Interface
- The replacement data source returns the exact same DataFrame format as yfinance: columns `[Open, High, Low, Close, Volume]` with timezone-naive ET index
- All 26+ downstream consumers (`intraday_rules.py`, `signal_engine.py`, `chart_analyzer.py`, etc.) work without modification
- Acceptance: Swap the data source and run the full test suite — all 648+ tests pass

### FR-5: Crypto Alert Accuracy
- Alerts (MA bounce, PDL reclaim, support bounce, etc.) fire based on real-time data instead of 15-60 minute delayed data
- Alert entry/stop/target prices reflect current market conditions
- Acceptance: Compare alert prices to Coinbase at the time of alert delivery — within 0.3% of actual price

### FR-6: AI CoPilot Accuracy
- The AI CoPilot's chart analysis for crypto symbols uses real-time data
- Entry/stop/target levels in the structured trade plan reflect current prices, not stale data
- Acceptance: AI analysis entry price is within 0.5% of actual Coinbase price at analysis time

## User Scenarios

### Scenario 1: Trader Checks ETH Price
**Actor**: Day trader monitoring ETH-USD
**Trigger**: Opens platform during active crypto session
**Steps**:
1. Platform fetches current ETH price from Coinbase
2. Watchlist shows $2,252.29 (matches Coinbase within $0.50)
3. Chart shows current candle close at real-time price
4. AI CoPilot analysis references the real-time price for levels
**Expected Outcome**: Price matches what the trader sees on Coinbase/Webull

### Scenario 2: Alert Fires on BTC Support
**Actor**: Swing trader with BTC-USD on watchlist
**Trigger**: BTC drops to 20 EMA support
**Steps**:
1. Monitor polls BTC data from Coinbase (5-min candles)
2. Detects MA bounce at $83,500 (real-time)
3. Alert fires with entry $83,600, stop $82,900 (based on real prices)
4. Trader receives Telegram with accurate levels
**Expected Outcome**: Alert levels match actual BTC price — trader can act immediately

### Scenario 3: Coinbase API Unavailable
**Actor**: System (automated)
**Trigger**: Coinbase API returns 503 or times out
**Steps**:
1. Crypto data fetch fails
2. System logs warning and falls back to yfinance
3. Alerts continue firing (with delayed data)
4. Next poll cycle retries Coinbase
**Expected Outcome**: No disruption to alert delivery; slightly delayed data until Coinbase recovers

## Key Entities

| Entity       | Description                            | Key Fields                         |
|-------------|----------------------------------------|------------------------------------|
| CryptoBar   | A single OHLCV candle from Coinbase    | timestamp, open, high, low, close, volume |
| DataSource  | Which provider served the data         | source ("coinbase" or "yfinance"), latency_ms |

## Success Criteria

- [ ] Crypto prices on the platform match Coinbase within $1 (BTC) / $0.50 (ETH) during active trading
- [ ] 5-minute candle data refreshes within 5 seconds of the actual candle close
- [ ] Alert delivery prices for crypto are within 0.3% of actual market price at time of delivery
- [ ] Zero additional monthly cost (Coinbase public API is free)
- [ ] All existing tests pass without modification (same DataFrame interface)
- [ ] Fallback to yfinance works within 1 poll cycle when Coinbase is unavailable

## Edge Cases

- **Coinbase maintenance windows**: Coinbase occasionally has scheduled downtime. System should retry 3 times with backoff, then fall back to yfinance.
- **Symbol mapping**: Platform uses "BTC-USD" / "ETH-USD" but Coinbase uses "BTC-USD" as product_id. Mapping is 1:1 for these two symbols.
- **Volume differences**: Coinbase volume is exchange-specific (not global). yfinance aggregates across exchanges. Volume-based indicators (RVOL) may show different values. Document this difference.
- **UTC midnight boundary**: Coinbase returns UTC timestamps. Existing ET normalization in `_normalize_index_to_et()` must handle Coinbase timestamps correctly.
- **Rate limiting**: Coinbase allows 10 req/sec on public endpoints. With 2 crypto symbols polled every 2-3 minutes, we use ~0.02 req/sec — well within limits.
- **Weekend gaps for equities**: This change only affects crypto. Equities continue using yfinance. No cross-contamination.

## Assumptions

- Only BTC-USD and ETH-USD need the Coinbase upgrade (these are the only crypto alert symbols)
- Coinbase public API remains free and stable (it has been for 5+ years)
- The existing `fetch_intraday_crypto()` function is the single point of change — all downstream consumers use its output
- Coinbase candle data is accurate and reflects real market conditions
- The 2-3 minute polling interval is maintained (no websocket streaming for v1)

## Constraints

- Zero additional cost — Coinbase public API is free, no API key required
- No new Python dependencies required — `requests` is already in the project
- Must maintain identical DataFrame output format for backward compatibility
- Only crypto symbols switch to Coinbase — equities remain on yfinance
- No websocket implementation in v1 (polling only)

## Scope

### In Scope
- Replace `fetch_intraday_crypto()` to use Coinbase API for 5m/15m/30m/1H candles
- Replace crypto daily/weekly OHLCV fetching via Coinbase
- Add real-time price endpoint for crypto (or update existing live prices hook)
- Fallback to yfinance on Coinbase failure
- Maintain identical DataFrame interface for all consumers
- Logging of data source used per fetch

### Out of Scope
- Equity data upgrade (remains on yfinance — Polygon migration is a separate spec)
- Websocket streaming (v1 uses polling)
- Additional crypto symbols beyond BTC-USD and ETH-USD
- Volume normalization across exchanges
- Historical backtesting data migration

## Clarifications

_Added during `/speckit.clarify` sessions_
