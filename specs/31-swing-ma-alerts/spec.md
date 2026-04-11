# Feature Specification: AI Swing Trade Alerts at Key Moving Averages

**Status**: Draft
**Created**: 2026-04-11
**Author**: Claude (speckit)

## Overview

Proactive AI-powered swing trade alerts that fire when watchlist symbols bounce off or get rejected at key daily moving averages (20, 50, 100, 200 — both MA and EMA). The AI monitors daily charts, detects when price interacts with these levels, confirms the bounce or rejection with a daily close, and sends a Telegram notification with a complete swing trade plan: entry, stop, targets, and conviction.

## Problem Statement

Swing traders watch daily charts for price reactions at key moving averages — the 20, 50, 100, and 200 day MA and EMA are the most widely followed institutional levels. When a stock or crypto pulls back to its 50-day EMA and holds, that's a high-probability swing entry. When price gets rejected at the 200-day MA, that's a warning to take profits or stay out.

**The problem**: Monitoring 10-25 symbols across 8 moving averages (4 MAs + 4 EMAs) daily is tedious. Traders miss setups because they checked the chart too late, or they misread whether price actually held the level vs just wicked through it.

**The solution**: AI scans all watchlist symbols on the daily timeframe, detects confirmed bounces and rejections at key MAs, and sends a swing trade plan via Telegram — before the next session opens. The trader wakes up to a clear plan: "AAPL bounced off 50 EMA, entry at $197.80, stop below 200 EMA at $194.50, T1 at $205."

## Functional Requirements

### FR-1: MA Bounce Detection (LONG entries)
- AI scans daily chart data for each watchlist symbol
- Detects when price pulls back to a key daily moving average and the daily candle CLOSES above it
- Moving averages monitored: 20 MA, 50 MA, 100 MA, 200 MA, 20 EMA, 50 EMA, 100 EMA, 200 EMA
- **Bounce confirmation**: Daily candle low touches or dips within 1% of the MA, AND daily close is above the MA
- The MA must be rising (today's value > value 5 days ago) to qualify as a bounce — falling MAs are not support
- When confirmed, AI generates a LONG swing trade plan:
  - Entry = MA level (the support being tested)
  - Stop = below the next MA down, or below the daily candle low (whichever is the structural level)
  - T1 = next overhead resistance (next MA above, prior swing high, or PDH)
  - T2 = second resistance level or measured move
  - Conviction: HIGH if the bounce is at a rising MA with volume confirmation; MEDIUM if MA is flat; LOW if volume is weak
- Acceptance: When a daily candle closes above a rising MA after touching it, the system fires a LONG alert with entry at the MA level within 1 hour of daily close

### FR-2: MA Rejection Detection (Resistance warnings)
- AI detects when price approaches a key MA from below and gets rejected — daily candle closes below the MA after testing it
- **Rejection confirmation**: Daily candle high reaches within 1% of the MA, AND daily close is below the MA
- The MA should be flat or declining to confirm resistance — a rising MA that price fails to clear is less meaningful
- When confirmed, AI sends a RESISTANCE warning (informational, not an entry):
  - Level = the MA being tested
  - What it means: "Price rejected at 200 MA — overhead resistance confirmed"
  - Suggestion: "Consider taking profits on existing longs" or "Wait for price to close above before entering"
- Acceptance: When a daily candle closes below a MA after wicking above it, the system sends a RESISTANCE warning within 1 hour of daily close

### FR-3: Swing Trade Plan Format (Telegram Output)
- Every bounce alert follows this exact format:
  ```
  SWING LONG [SYMBOL] $[current price]
  Entry $[MA level] · Stop $[structural level below] · T1 $[target] · T2 $[target]
  Setup: [MA name] bounce (e.g. "50 EMA bounce")
  Conviction: HIGH/MEDIUM/LOW
  ```
- Every rejection warning follows this format:
  ```
  SWING RESISTANCE [SYMBOL] $[current price]
  Level: [MA name] at $[level]
  Action: Tighten stops on existing longs / Wait for close above to enter
  ```
- Bounce alerts include Took/Skip buttons for tracking
- Resistance warnings are informational only (no Took/Skip)
- Acceptance: 100% of swing alerts include all required fields; format matches specification

### FR-4: Scan Schedule and Frequency
- Swing MA scan runs twice daily:
  - **Pre-market scan (9:00 AM ET)**: Evaluates yesterday's daily close against MAs, sends alerts before market opens so traders can prepare
  - **End-of-day scan (4:15 PM ET)**: Evaluates today's daily close, sends alerts for overnight review and next-day action
- For crypto (24/7 markets): scan runs twice daily at 9:00 AM ET and 9:00 PM ET (captures the US session close and the Asian session)
- Each symbol is scanned at most once per MA per day — no duplicate alerts
- Acceptance: Swing alerts arrive in Telegram before 9:30 AM ET (pre-market) and before 5:00 PM ET (end-of-day)

### FR-5: Dedup and Alert Limits
- One alert per symbol per MA per day — if AAPL bounces off both 20 EMA and 50 EMA, both fire (different MAs = different setups)
- If the same MA fires on consecutive days (price still at the level), do not repeat — the alert was already sent
- Maximum 3 swing alerts per symbol per day (prevent alert flood if multiple MAs converge)
- Resistance warnings also deduped: one per MA per day per symbol
- Acceptance: No duplicate swing alerts for the same symbol + MA combination within a 24-hour period

### FR-6: User Configuration
- Users can select which MAs they want alerts for via Settings page
- Default: all 8 (20/50/100/200 MA + 20/50/100/200 EMA) enabled
- Users can toggle swing alerts on/off independently of day trade alerts
- Users can set preferred conviction threshold: receive only HIGH, or HIGH+MEDIUM, or all
- Acceptance: User who disables "50 MA" does not receive 50 MA bounce or rejection alerts

## User Scenarios

### Scenario 1: Pre-Market Swing Alert
**Actor**: Swing trader with AAPL, NVDA, TSLA on watchlist
**Trigger**: AAPL daily close yesterday was at the 50 EMA ($197.80) after a 3-day pullback
**Steps**:
1. Pre-market scan runs at 9:00 AM ET
2. AI evaluates AAPL: daily low touched 50 EMA, close above it, 50 EMA is rising
3. Telegram notification sent:
   ```
   SWING LONG AAPL $198.50
   Entry $197.80 · Stop $194.50 · T1 $205.00 · T2 $210.00
   Setup: 50 EMA bounce
   Conviction: HIGH
   ```
4. Trader reviews before market open, decides to enter at open
**Expected Outcome**: Trader has a clear swing plan before the market opens, with specific levels to act on

### Scenario 2: Resistance Warning on Crypto
**Actor**: Swing trader holding BTC-USD long from $68,000
**Trigger**: BTC daily candle wicks above 200 MA ($73,500) but closes below at $72,900
**Steps**:
1. 9:00 PM ET scan runs for crypto
2. AI detects: BTC high reached 200 MA, close below it, 200 MA is flat
3. Telegram notification sent:
   ```
   SWING RESISTANCE BTC-USD $72,900
   Level: 200 MA at $73,500
   Action: Tighten stop on existing long / Wait for daily close above $73,500 to add
   ```
4. Trader tightens stop to breakeven, waits for confirmation
**Expected Outcome**: Trader is warned about overhead resistance and manages position accordingly

### Scenario 3: Multiple MA Bounce (Convergence)
**Actor**: Swing trader watching ETH-USD
**Trigger**: ETH pulls back to an area where 20 EMA and 50 EMA are close together
**Steps**:
1. AI detects: daily candle touches both 20 EMA ($2,180) and 50 EMA ($2,170), closes above both
2. Two alerts fire (one for each MA), but with the higher one noting convergence:
   ```
   SWING LONG ETH-USD $2,195
   Entry $2,180 · Stop $2,150 · T1 $2,280 · T2 $2,350
   Setup: 20 EMA + 50 EMA bounce (MA convergence)
   Conviction: HIGH
   ```
3. Convergence of two MAs at the same price increases conviction
**Expected Outcome**: Trader sees a high-conviction swing setup backed by multiple MA support

## Key Entities

| Entity | Description | Key Fields |
|--------|-------------|------------|
| SwingMAAlert | AI-generated swing MA bounce or rejection alert | symbol, ma_type (20MA/50EMA/etc), direction (LONG/RESISTANCE), entry, stop, t1, t2, conviction, scan_time |
| UserSwingPrefs | User's swing alert configuration | user_id, enabled_mas (list), conviction_threshold, swing_alerts_enabled |

## Success Criteria

- [ ] Swing MA alerts fire for at least 80% of confirmed daily MA bounces across watchlist symbols
- [ ] Every LONG alert includes entry, stop, T1, T2, and conviction — no missing fields
- [ ] Entry price is the actual MA level (within 0.5% of the computed MA value)
- [ ] No duplicate alerts for the same symbol + MA within 24 hours
- [ ] Pre-market alerts arrive in Telegram before 9:30 AM ET
- [ ] End-of-day alerts arrive within 1 hour of market close
- [ ] Users can customize which MAs trigger alerts via Settings
- [ ] Swing alerts work for both equities (market hours) and crypto (24/7)
- [ ] Resistance warnings fire when price rejects at a flat/declining MA

## Edge Cases

- **MA convergence**: When 2+ MAs are within 1% of each other, fire one combined alert noting convergence instead of separate alerts per MA
- **Gap through MA**: If price gaps below a MA at open (never tested it intraday), do not fire a bounce — the level was never tested
- **MA crossing**: If the 20 EMA crosses above the 50 EMA while price is near both (golden cross), note this in the alert but don't change the entry logic
- **Flat MA**: If a MA is flat (< 0.1% change over 5 days), bounce conviction is reduced to MEDIUM regardless of other factors
- **Crypto weekend gaps**: yfinance may skip daily bars on weekends — use Coinbase daily candles to fill gaps (already implemented)
- **No MA data**: New IPOs or symbols with < 200 trading days won't have 200 MA — skip that MA, still check available ones
- **Price far from all MAs**: If price is > 5% from all MAs, skip scan (no setup possible)

## Assumptions

- Daily bar data is available and accurate for all watchlist symbols (Coinbase for crypto, yfinance/Alpaca for equities)
- MA/EMA values are computed on daily close prices with standard lookback periods (20/50/100/200 days)
- Users primarily receive alerts via Telegram and act within the same or next trading session
- "Bounce" means daily candle tests the MA and closes above — not just an intraday wick that recovers
- Swing trades are held for days to weeks, not minutes to hours

## Constraints

- AI costs must stay within $5/user/month budget — swing scans run 2x/day (not every 3 minutes)
- Swing alerts must not conflict with day trade alerts — both can fire for the same symbol at different timeframes
- All swing alerts must include "Education only, not financial advice" disclaimer
- Must work for both equities and crypto without separate configuration

## Scope

### In Scope
- AI detection of daily MA/EMA bounces (LONG entries)
- AI detection of daily MA/EMA rejections (RESISTANCE warnings)
- Telegram notifications with complete swing trade plans
- Pre-market and end-of-day scan schedules
- Dedup per symbol per MA per day
- User configuration for which MAs to monitor
- Support for 8 moving averages: 20/50/100/200 MA + 20/50/100/200 EMA

### Out of Scope
- Intraday MA bounces (covered by day trade scanner, Spec 27)
- Weekly or monthly MA analysis (future enhancement)
- Automated trade execution (user decides and enters manually)
- Position management (trailing stops, partial exits) — separate feature
- Backtesting swing MA strategies — future feature

## Clarifications

_Added during `/speckit.clarify` sessions_
