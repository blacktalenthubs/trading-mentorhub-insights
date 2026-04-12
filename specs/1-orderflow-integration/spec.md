# Feature Specification: Orderflow Integration (Zero-Cost Approach)

**Status**: Draft
**Created**: 2026-04-06
**Updated**: 2026-04-06
**Author**: Claude (via /speckit.specify)

## Overview

Add "poor man's orderflow" analysis to the TradeSignal platform using data already available from yfinance (OHLCV bars). Instead of expensive tick-level data feeds, the system derives orderflow-like signals from bar-level volume, price position within bars, and volume-price relationships. These approximations — volume delta proxy, relative volume spikes, volume-price divergence, and session volume profile — provide 70-80% of the insight at zero additional data cost.

## Problem Statement

TradeSignal currently generates alerts based on price action and technical indicators (moving averages, support/resistance levels, VWAP, volume ratios). While effective for identifying *where* setups occur, these signals lack insight into buyer/seller conviction behind the move.

Day traders face two recurring pain points:

1. **False breakouts**: A breakout alert fires, but without volume conviction context, traders cannot distinguish genuine momentum (high relative volume, bullish bar closes) from low-conviction moves (thin volume, wicky bars).
2. **Missed conviction signals**: A support bounce alert fires, but the trader has no way to see that volume is surging at the level with bullish bar closes — a sign that buyers are stepping in aggressively.

True orderflow (tick-level, aggressor-side data) costs $100-400/month. This spec delivers approximated orderflow signals using existing free yfinance data, with a clear upgrade path to true orderflow when budget allows.

## Functional Requirements

### FR-1: Volume Delta Proxy
- The system estimates buyer/seller dominance per 5-minute bar using the bar's close position relative to its high-low range
- Formula: `delta_proxy = volume * ((close - low) - (high - close)) / (high - low)` — positive = net buying, negative = net selling
- A cumulative delta proxy is maintained as a running sum from session open
- Acceptance: Each 5-minute bar has a delta proxy value; cumulative delta proxy updates each poll cycle; a bar that closes at its high produces maximum positive delta

### FR-2: Relative Volume (RVOL) at Key Levels
- The system computes time-normalized relative volume: current bar volume divided by the average volume for that time-of-day over the prior 10 sessions
- Bars with RVOL >= 2.0x at a known support/resistance level are flagged as "volume surge at level"
- Acceptance: RVOL is computed per bar with time-of-day normalization; surges at S/R levels are detected and available for alert enrichment

### FR-3: Volume-Price Divergence Detection
- The system detects when price makes a new session high/low but volume is declining compared to the prior swing (measured over the last N bars)
- Bearish divergence: rising price + declining volume = weakening momentum
- Bullish divergence: falling price + declining volume = selling exhaustion
- Acceptance: Divergence events are detected when price extends beyond the prior swing while volume is at least 30% below the prior swing's average volume

### FR-4: Session Volume Profile
- The system builds a volume-by-price distribution from 5-minute bars for the current session
- Identifies Point of Control (POC): the price level with the highest traded volume
- Identifies Value Area (70% of volume): Value Area High (VAH) and Value Area Low (VAL)
- Acceptance: POC, VAH, and VAL are computed and updated each poll cycle; values are available for alert enrichment and dashboard display

### FR-5: Volume-Enhanced Alert Rules
- New alert rules that combine existing price-action setups with volume conviction:
  - **Confirmed Breakout**: Breakout + RVOL >= 2.0x + positive cumulative delta proxy = high-conviction breakout
  - **Volume Absorption**: Support bounce + RVOL surge (>= 2.0x) + bullish delta proxy (close near high of bar) = buyers stepping in
  - **Delta Divergence Warning**: Price makes new high but cumulative delta proxy is falling over the last 5+ bars = momentum weakening
  - **POC Magnet**: Price approaching yesterday's POC or current session's developing POC = potential reversal/pause zone
- Acceptance: Each rule fires when both the price-action condition AND the volume condition are met; rules are added to the existing rule evaluation pipeline

### FR-6: Volume Context in Notifications
- Existing alert notifications (Telegram, email) include volume conviction context when available
- Context includes: RVOL value, delta proxy direction, and POC proximity
- Acceptance: Alert messages show volume enrichment (e.g., "MA Bounce + 2.8x RVOL + buyers in control") without breaking existing message format

### FR-7: Volume Flow Dashboard Display
- The dashboard shows a cumulative delta proxy overlay on the existing intraday chart (green/red bars below the price chart)
- RVOL indicator shows current bar's relative volume vs historical average
- Session volume profile displayed as a horizontal histogram on the price axis
- POC, VAH, VAL lines are drawn on the chart
- Acceptance: Users can view volume flow data alongside price action on their existing chart page

### FR-8: Volume Flow Signal Scoring
- The existing signal score (currently 0-100 based on 4 factors) is extended with a volume flow component
- Volume flow score considers: RVOL (above/below average), delta proxy alignment with trade direction, and POC proximity
- Acceptance: Signals with strong volume confirmation score higher than signals without

## Non-Functional Requirements

### Performance
- Volume flow computations must complete within the existing poll cycle (2-3 minutes) without delaying price-action alerts
- Dashboard overlays render within 2 seconds of page load

### Reliability
- Volume flow analysis uses the same yfinance data source as existing alerts — no additional failure modes
- If volume data is insufficient for a bar (e.g., bar has zero volume), that bar is skipped in flow calculations

### Cost
- Zero additional data cost — all computations use existing yfinance 5-minute OHLCV bars
- No new API subscriptions, data feeds, or infrastructure required

## User Scenarios

### Scenario 1: Breakout with Volume Conviction
**Actor**: Day trader monitoring NVDA
**Trigger**: NVDA breaks above prior day high
**Steps**:
1. Existing breakout rule detects price crossing prior day high
2. Volume flow module checks: RVOL is 3.1x (well above 2.0x threshold), cumulative delta proxy is rising, last bar closed near its high
3. Alert fires with enriched message: "NVDA Breakout above PDH $142.50 — 3.1x RVOL, buyers in control"
4. Trader receives Telegram notification with volume context
**Expected Outcome**: Trader has higher confidence this breakout has volume behind it

### Scenario 2: Buyers Stepping In at Support
**Actor**: Day trader watching AAPL at 20MA support
**Trigger**: AAPL pulls back to 20MA with a volume surge
**Steps**:
1. Existing MA bounce rule detects price touching 20MA
2. Volume flow module detects: RVOL is 2.5x at this level, bar closes in upper 75% of range (bullish delta proxy)
3. Alert fires: "AAPL 20MA Bounce $185.20 — 2.5x RVOL, bar closed bullish (buyers stepping in)"
**Expected Outcome**: Trader sees volume conviction at support, increasing confidence for a long entry

### Scenario 3: Momentum Weakening Warning
**Actor**: Trader holding a long position in SPY
**Trigger**: SPY makes a new session high
**Steps**:
1. Price prints a new intraday high
2. Volume flow module detects: volume over the last 5 bars is 40% below the prior push's average, cumulative delta proxy is flattening
3. Delta divergence notice fires: "SPY New High $520.30 — WARNING: volume declining on this push, momentum weakening"
**Expected Outcome**: Trader considers tightening stop or taking partial profits

### Scenario 4: POC as a Magnet Level
**Actor**: Day trader reviewing the intraday chart
**Trigger**: Price pulls back toward yesterday's POC
**Steps**:
1. Volume profile shows yesterday's POC at $148.50 for NVDA
2. Price is within 0.3% of that level
3. Alert fires: "NVDA approaching yesterday's POC $148.50 — high-volume level, potential support/reversal zone"
**Expected Outcome**: Trader adds POC to their mental map of key levels

## Key Entities

| Entity                | Description                                              | Key Fields                                                              |
|-----------------------|----------------------------------------------------------|-------------------------------------------------------------------------|
| Bar Delta Proxy       | Estimated net buying/selling for a 5-minute bar          | symbol, bar_timestamp, delta_proxy, cumulative_delta_proxy              |
| RVOL                  | Time-normalized relative volume for a bar                | symbol, bar_timestamp, volume, avg_volume_at_time, rvol_ratio           |
| Volume-Price Divergence | Detected divergence between price trend and volume     | symbol, timestamp, divergence_type (bullish/bearish), price, volume_ratio |
| Session Volume Profile | Volume distribution by price for the session            | symbol, session_date, poc_price, vah_price, val_price, volume_by_price  |

## Success Criteria

- [ ] At least 60% of traders report that volume context improves their alert decision-making (survey/feedback)
- [ ] Breakout alerts with RVOL >= 2.0x have a measurably higher follow-through rate than breakouts without volume surge
- [ ] Alert delivery time does not increase by more than 2 seconds with volume flow processing added
- [ ] Volume profile levels (POC, VAH, VAL) are cited by users as useful reference points within 30 days of launch
- [ ] 70% of active users engage with at least one volume flow feature within the first month

## Edge Cases

- **Pre-market / after-hours**: yfinance may return sparse or no volume data outside regular hours. System should skip volume flow enrichment during extended hours and rely on price-action only.
- **Crypto 24/7 markets**: Cumulative delta proxy resets at midnight ET (aligned with existing session boundaries). RVOL time-of-day normalization uses 24-hour clock for crypto.
- **Low-volume symbols**: If a bar has fewer than 100 shares traded, delta proxy is unreliable. System should require a minimum bar volume before computing flow metrics.
- **Opening bar anomaly**: The first 5-minute bar (9:30-9:35 ET) often has abnormally high volume. RVOL normalization must account for this by comparing against the same time-of-day average.
- **Flat bars (high == low)**: If a bar has zero range (high equals low), the delta proxy formula produces a division by zero. Treat these bars as neutral (delta_proxy = 0).
- **Gaps**: After a gap up/down, the first bar's delta proxy may be misleading. System should not use the first bar alone for divergence detection.

## Assumptions

- yfinance 5-minute OHLCV data is sufficient to approximate buyer/seller dominance (close-position-in-range is a well-known proxy for aggressor-side)
- The delta proxy (close position in bar range * volume) provides directionally useful signal even though it's not true tick-level delta
- 10-session lookback for RVOL time-of-day normalization provides a stable baseline
- Volume profile built from 5-minute bars (not tick data) is coarse but still identifies meaningful POC/value area levels
- Users understand that these are approximations, not true orderflow — tooltips and labels will say "Volume Flow" not "Orderflow"

## Constraints

- Zero additional data cost — must work entirely with existing yfinance data
- Must not break or slow down existing alert rules
- Volume flow is labeled as "Volume Flow" (not "Orderflow") to set accurate expectations
- Must work within the existing polling architecture (no streaming infrastructure)
- Volume profile resolution is limited by 5-minute bar granularity (tick-level precision requires a paid data upgrade)

## Scope

### In Scope
- Volume delta proxy computation (per-bar and cumulative)
- Time-normalized RVOL calculation
- Volume-price divergence detection
- Session volume profile with POC, VAH, VAL
- 4 new volume-enhanced alert rules (confirmed breakout, volume absorption, delta divergence, POC magnet)
- Volume context appended to existing alert notifications
- Dashboard overlays (cumulative delta bars, RVOL indicator, volume profile histogram)
- Signal score extension with volume flow component

### Out of Scope
- True tick-level orderflow / aggressor-side data (requires paid data feed — future upgrade path)
- Full order book / Level 2 depth visualization
- Footprint charts
- Options flow / unusual options activity
- Historical volume flow backtesting (v1 focuses on real-time)
- Custom volume flow rule builder (v1 ships with 4 predefined rules)
- Real-time streaming (v1 uses polling)

## Upgrade Path to True Orderflow

When budget allows ($100-300/month), the volume flow module can be upgraded:
1. Replace delta proxy with true cumulative delta from tick-level data (Polygon.io or Databento)
2. Replace RVOL approximation with tick-count-based relative volume
3. Add true bid/ask imbalance detection (requires aggressor-side classification)
4. Add large print detection (requires trade-level data with size)
5. The alert rules, dashboard, and scoring infrastructure built in this phase carry over — only the data source changes

## Clarifications

_Added during `/speckit.clarify` sessions_
