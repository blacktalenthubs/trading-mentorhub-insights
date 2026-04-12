# Feature Specification: AI-Powered Multi-Timeframe Chart Analysis

**Status**: Draft
**Created**: 2026-04-07
**Author**: Claude (via /speckit.specify)

## Overview

Give every TradeCoPilot user — day trader or swing trader — the ability to ask the AI to analyze any chart on any timeframe and receive specific, actionable entry and exit instructions. Today the AI coach has market context and can answer questions, but it doesn't systematically analyze the chart the user is looking at across multiple timeframes to produce a structured trade plan. This feature makes the AI a true co-pilot: "I'm looking at SPY on the hourly — what should I do?" and getting back a precise entry, stop, targets, R:R ratio, and confidence score with plain-English reasoning.

## Problem Statement

Traders using TradeCoPilot face three pain points that limit the value of the existing AI coach:

1. **No chart-aware analysis**: The AI coach receives some market context but doesn't systematically analyze the specific chart the user is viewing. A trader looking at NVDA on the 4-hour chart can't say "analyze this chart" and get a structured trade plan for that timeframe.

2. **Single-timeframe blind spots**: Alerts fire on 5-minute bars only. A swing trader looking at the daily chart gets intraday alerts that don't match their trading style. A day trader on the 1-minute chart gets signals calibrated to 5-minute bars. There's no way to get AI analysis tailored to the user's chosen timeframe.

3. **No structured trade plan output**: The AI coach gives conversational responses, but traders need structured output: entry price, stop loss, target 1, target 2, risk/reward ratio, confidence level, and the reasoning — formatted consistently so they can act on it instantly.

**Impact**: Users who trade on timeframes other than 5-minute bars feel the platform wasn't built for them. Swing traders on daily/weekly charts and scalpers on 1-minute charts both underutilize the AI because it doesn't speak their timeframe.

## Functional Requirements

### FR-1: "Analyze This Chart" Action
- On any chart page, the user can trigger an AI analysis of the currently displayed chart
- The analysis uses the exact timeframe and symbol the user is viewing (1m, 5m, 15m, 30m, 1H, 4H, Daily, Weekly)
- The AI receives the last 50-100 bars of OHLCV data for that timeframe plus computed indicators (MAs, RSI, VWAP where applicable)
- Acceptance: User clicks "Analyze Chart" on any symbol/timeframe combination and receives a structured response within 5 seconds

### FR-2: Structured Trade Plan Output
- Every AI chart analysis produces a structured trade plan with these fields:
  - **Direction**: Long, Short, or No Trade (with reason)
  - **Entry Price**: Specific price or condition ("on break above $185.50" or "at current price $184.20")
  - **Stop Loss**: Specific price with reasoning ("below the 50EMA at $182.10")
  - **Target 1**: First profit target with R:R ratio
  - **Target 2**: Extended target with R:R ratio
  - **Risk per Share**: Dollar amount at risk (entry minus stop)
  - **Confidence**: High / Medium / Low with explanation
  - **Timeframe Fit**: How long this trade should take (hours, days, weeks) based on the chart timeframe
  - **Key Levels**: 2-3 levels to watch that could invalidate or confirm the trade
- Acceptance: Every analysis returns all fields in a consistent, parseable format; no fields are omitted

### FR-3: Multi-Timeframe Confluence Scoring
- When analyzing a chart, the AI automatically checks the next two higher timeframes for alignment
  - If user is on 5m: also checks 1H and Daily
  - If user is on 1H: also checks Daily and Weekly
  - If user is on Daily: also checks Weekly and Monthly
- Produces a confluence score (0-10) based on:
  - Trend alignment across timeframes (all bullish = high, conflicting = low)
  - Key level proximity on higher timeframes (near resistance on daily = caution for hourly longs)
  - Momentum alignment (RSI direction, MA slopes agreeing across timeframes)
- Acceptance: Every analysis includes a confluence score with a one-sentence explanation of what the higher timeframes show

### FR-4: Timeframe-Appropriate Analysis
- The AI adapts its analysis style and targets to the user's timeframe:
  - **Scalp (1m-5m)**: Tight stops (0.1-0.3%), quick targets, focus on order flow and momentum
  - **Day trade (15m-1H)**: Session-based stops/targets, VWAP and daily levels matter, focus on intraday structure
  - **Swing (4H-Daily)**: Multi-day hold, wider stops (1-3%), focus on MA structure, support/resistance zones
  - **Position (Weekly-Monthly)**: Multi-week hold, stops based on weekly structure, focus on trend and major levels
- Stop distances, target multipliers, and hold-time expectations adjust automatically to the timeframe
- Acceptance: A 1-minute chart analysis never suggests a 3-day hold; a weekly chart analysis never suggests a 0.1% stop

### FR-5: Historical Pattern Context
- The AI references how similar setups have performed historically on this symbol
- Uses the platform's existing win-rate data (alerts by type, symbol, time of day) to ground the analysis
- Example: "This 20EMA bounce pattern on AAPL has triggered 12 times in the last 90 days with a 75% win rate"
- Acceptance: When historical data is available (5+ occurrences), the analysis includes a track record reference

### FR-6: Alert-Triggered AI Analysis
- When an existing alert fires (MA bounce, breakout, support test, etc.), the system can automatically generate an AI analysis for that symbol on the alert's timeframe
- This analysis is included in the alert notification (Telegram, web) as an expandable "AI Take" section
- Users can enable/disable auto-analysis per alert category in Settings
- Acceptance: Alerts with auto-analysis enabled include a structured trade plan; users can toggle this in Settings

### FR-7: Saved Analysis & Journal Integration
- Users can save an AI chart analysis to their trading journal
- Saved analyses include the trade plan, the chart snapshot context (price, time, indicators at that moment), and the AI reasoning
- After the trade resolves, the system can compare the AI's prediction against what actually happened
- Acceptance: Analyses can be saved with one click; resolved trades show AI prediction vs actual outcome

### FR-8: Analysis Usage Limits by Tier
- AI chart analyses consume the same usage quota as AI coach queries
- Free tier: 5 analyses per day
- Pro tier: 50 analyses per day
- Elite tier: Unlimited
- Each multi-timeframe analysis counts as one query (even though it checks 3 timeframes)
- Acceptance: Usage limits are enforced; users see remaining analysis count; limit resets daily

## Non-Functional Requirements

### Performance
- AI analysis completes within 5 seconds for single-timeframe, 8 seconds for multi-timeframe
- Chart data assembly (fetching bars + computing indicators) completes within 2 seconds

### Reliability
- If AI analysis fails (API timeout, model error), the user sees a clear error message and is not charged a usage credit
- Partial responses (streaming interrupted) are discarded, not shown as complete analyses

### Cost Efficiency
- Use the most cost-effective model tier that produces accurate trade plans
- Batch indicator computation per symbol (compute once, use for all timeframes)
- Cache recently computed analyses for the same symbol/timeframe (5-minute TTL) to avoid duplicate API calls

## User Scenarios

### Scenario 1: Day Trader Analyzes Hourly SPY Chart
**Actor**: Day trader viewing SPY on the 1-hour chart during market hours
**Trigger**: Clicks "Analyze Chart"
**Steps**:
1. System assembles last 100 hourly bars + indicators (20/50 EMA, RSI, VWAP)
2. System also fetches Daily and Weekly context for confluence
3. AI analyzes: SPY hourly shows pullback to rising 20EMA at $520, RSI at 45, daily uptrend intact, weekly bullish
4. Returns structured plan: Long at $520.50 (break above last bar high), Stop $517.80 (below 50EMA), Target 1 $524 (2:1 R:R), Target 2 $528 (3:1 R:R), Confidence High, Confluence 8/10
5. User acts on the plan or saves it to journal
**Expected Outcome**: Trader gets a complete, timeframe-appropriate trade plan in under 5 seconds

### Scenario 2: Swing Trader Analyzes Weekly AAPL Chart
**Actor**: Swing trader looking at AAPL on the weekly chart
**Trigger**: Clicks "Analyze Chart"
**Steps**:
1. System assembles last 52 weekly bars + indicators
2. Also fetches Monthly context for confluence
3. AI analyzes: AAPL weekly in consolidation near all-time high, above rising 10/20 WMA, RSI 58
4. Returns: Long on weekly close above $198, Stop $188 (below 20WMA, ~5% risk), Target 1 $215 (prior ATH breakout measured move), Timeframe 2-4 weeks, Confidence Medium (consolidation could break either way), Confluence 6/10 (monthly bullish, weekly neutral)
**Expected Outcome**: Swing trader gets a multi-week trade plan calibrated to weekly timeframe

### Scenario 3: Alert Fires with Auto-Analysis
**Actor**: Day trader with NVDA on watchlist, auto-analysis enabled
**Trigger**: MA bounce alert fires on NVDA 5-minute chart
**Steps**:
1. Alert system detects NVDA 20EMA bounce at $142.30
2. AI auto-analysis runs: checks 5m context + 1H + Daily alignment
3. Telegram notification includes: alert text + "AI Take: Long $142.50, Stop $141.80, Target $144.20 (2.4:1 R:R). Confluence 7/10 — hourly uptrend, daily above 50MA. This pattern has 72% win rate on NVDA over 90 days."
4. User sees complete actionable plan without opening the app
**Expected Outcome**: Alert becomes instantly actionable with AI-generated trade plan

### Scenario 4: AI Says "No Trade"
**Actor**: Trader asking for analysis on a choppy, directionless chart
**Trigger**: Clicks "Analyze Chart" on AMD daily chart
**Steps**:
1. AI analyzes: AMD in tight range, no clear direction, MAs converging, RSI flat at 50
2. Returns: Direction "No Trade" — "AMD is in a consolidation range between $155-$162. No clear edge. Wait for a breakout above $162 (long) or breakdown below $155 (short) before entering."
3. Includes key levels to watch and what would change the analysis
**Expected Outcome**: AI protects the trader from a low-probability setup by recommending patience

## Key Entities

| Entity              | Description                                               | Key Fields                                                                                  |
|---------------------|-----------------------------------------------------------|---------------------------------------------------------------------------------------------|
| Chart Analysis      | A single AI analysis of a symbol/timeframe                | symbol, timeframe, direction, entry, stop, target_1, target_2, confidence, confluence_score |
| Confluence Check    | Higher-timeframe alignment data                           | symbol, timeframes_checked, trend_alignment, level_conflicts, momentum_alignment, score     |
| Trade Plan          | Structured output from analysis                           | direction, entry, stop, targets, rr_ratio, risk_per_share, hold_time, key_levels            |
| Analysis History    | Saved analysis linked to journal                          | analysis_id, user_id, created_at, symbol, timeframe, plan, actual_outcome                   |

## Success Criteria

- [ ] 80% of users who try "Analyze Chart" use it at least 3 more times in the same week (feature stickiness)
- [ ] AI trade plans include all required fields (direction, entry, stop, targets, R:R, confidence) in 95%+ of responses
- [ ] Analysis completes within 5 seconds for 90% of requests
- [ ] Multi-timeframe confluence score correlates with actual trade outcomes (high confluence = higher win rate) within 60 days of data
- [ ] Users on non-5-minute timeframes (daily, weekly, hourly) increase their engagement by 30% within the first month
- [ ] "No Trade" recommendations are perceived as valuable (>60% approval in user feedback) rather than unhelpful
- [ ] Alert auto-analysis increases the "Took It" rate by 15% compared to alerts without AI analysis

## Edge Cases

- **Insufficient data**: New IPO or thinly traded symbol may not have 100 bars of history. System should analyze with available data and note "limited history" in confidence assessment.
- **Pre-market / after-hours**: Hourly and intraday charts during extended hours have sparse data. AI should note "extended hours — volume and price action may not reflect regular session behavior."
- **Crypto weekends**: Crypto trades 24/7 but traditional indicators (VWAP, session high/low) may not apply. AI should adapt context for crypto assets.
- **Conflicting timeframes**: When higher timeframes directly contradict the lower timeframe signal (e.g., 5m bullish but daily bearish), the AI must explicitly flag the conflict and adjust confidence downward rather than ignoring it.
- **Fast-moving markets**: During high-volatility events (earnings, FOMC), prices may move past the AI's suggested entry by the time the user reads the analysis. Include a "still valid if price is between X and Y" range.
- **Same analysis requested repeatedly**: If a user clicks "Analyze Chart" multiple times within 5 minutes on the same symbol/timeframe, return the cached result to avoid redundant API costs.

## Assumptions

- The existing AI coach infrastructure (Anthropic API, streaming, usage tracking) can be extended for structured chart analysis without new infrastructure
- OHLCV data from yfinance is available for all supported timeframes (1m through Monthly) with sufficient history
- Numerical analysis (OHLCV + indicators) is the primary input — chart screenshot/vision analysis is not required for accurate trade plans
- The AI model can produce consistent, structured trade plan output when given a well-designed prompt with structured data
- Historical win-rate data from the existing alert system provides a meaningful track record for pattern references
- Users understand that AI analysis is a decision-support tool, not financial advice — existing disclaimers apply

## Constraints

- AI analysis must use the same Anthropic API billing as the existing coach (no separate billing pipeline)
- Analysis must work without any additional data subscriptions (yfinance provides all needed timeframes)
- The structured trade plan format must be consistent across all timeframes (same fields, adapted values)
- "Not financial advice" disclaimer must be visible on every analysis output
- Auto-analysis on alerts must not delay alert delivery — analysis runs asynchronously after the alert is sent

## Scope

### In Scope
- Dedicated "AI CoPilot" page/tab — separate from Trading and Analysis pages
- Symbol picker (from user's watchlist) and timeframe selector on the AI page
- "Analyze Chart" action with structured trade plan output (direction, entry, stop, targets, R:R, confidence)
- Mini chart display showing the bars being analyzed
- Multi-timeframe confluence scoring (automatic higher-timeframe checks)
- Timeframe-appropriate analysis (stops, targets, hold times scaled to timeframe)
- Historical pattern context from existing win-rate data
- Alert auto-analysis (optional, asynchronous)
- Analysis history feed on the same AI page with outcome tracking
- Usage limits by tier (shared with coach quota)

### Out of Scope
- Chart screenshot / vision-based analysis (numerical data approach is more accurate and cheaper)
- Autonomous trade execution (AI suggests, human decides)
- Backtesting AI recommendations against historical data (future feature)
- Custom indicator support (user-defined indicators in AI analysis)
- Real-time streaming analysis (continuous updates as price moves — too expensive and distracting)
- Options-specific analysis (options Greeks, IV, chain analysis)
- Social/copy trading (sharing AI analyses between users)

## Clarifications

_Added during `/speckit.clarify` sessions_
