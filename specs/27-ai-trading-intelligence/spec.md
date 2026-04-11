# Feature Specification: AI Entry Detection Engine

**Status**: Draft
**Created**: 2026-04-11
**Author**: Claude (speckit)

## Overview

Make AI the primary entry detection system for day trades and swing trades. The current rule-based engine is inconsistent — it misses key levels and fires false alerts. The AI Scanner already exists and shows promise, but needs to become the core signal engine: continuously monitoring price action at key levels and delivering clean, actionable entry signals that users can trust and act on immediately.

## Problem Statement

The rule-based alert engine has become unreliable:
- Rules don't fire at some key levels (missed setups)
- Rules fire with stale or wrong entry prices (false alerts)
- Rules are rigid — they can't adapt to context (volume, regime, time of day)
- Too many rule types (30+) create noise and make it hard to identify which setups actually work

The AI Scanner (launched as Spec 26) runs alongside rules and shows better contextual awareness — it reads price relative to levels and only fires when price is AT a key level. But it's still in testing and needs to become more robust, cover more setup types, and deliver cleaner output.

**Goal:** AI continuously monitors all watchlist symbols and provides solid, easy-to-use entry signals for day trades and swing trades based on the platform's key entry metrics (support/resistance levels, MA bounces, breakout confirmations, VWAP positioning).

**Who is affected:** All active traders. The quality of entry signals directly determines whether the platform is worth paying $49-99/month.

## Functional Requirements

### FR-1: AI as Primary Entry Detection
- AI Scanner becomes the primary source of entry alerts, not a supplement to rules
- AI evaluates price action at every poll cycle (every 2-3 minutes during market hours, 24/7 for crypto)
- AI receives the same data the rule engine uses: intraday bars, prior day levels (PDH/PDL), MAs, EMAs, VWAP, volume, RSI
- AI determines if price is AT a key level and whether the setup is actionable
- Rule engine continues running in parallel as a fallback/comparison, but AI alerts are the primary user-facing signals
- Acceptance: AI Scanner generates entry alerts for at least 80% of setups that occur at key levels (PDL bounce, PDH breakout, MA bounce, VWAP reclaim)

### FR-2: Key Entry Metrics the AI Must Evaluate
- AI uses **specialized prompts per category** — separate AI calls for day trade setups vs swing trade setups, each with specific confirmation rules tuned to that category

**Day Trade Entry Rules** (intraday 5-min bars, session levels):
- **PDL hold/reclaim**: Price touches or dips below prior day low, then closes back above. Confirmation: 2+ bars closing above PDL. Entry = PDL level. Stop = below session low or PDL - 0.5%.
- **PDH breakout on volume**: Price closes above prior day high with volume >= 1.5x average. Confirmation: close above PDH (not just wick). Entry = PDH level. Stop = below breakout bar low.
- **VWAP hold**: Price pulls back to VWAP and holds (2+ bars closing above VWAP). Confirmation: price was above VWAP earlier in session, pulled back, and reclaimed. Entry = VWAP level. Stop = below VWAP - 0.3%.
- **Multi-day double bottom hold**: Price tests the same low from a prior session and holds. Confirmation: two separate touches of the same level (within 0.5%) on different days, with the second touch holding. Entry = double bottom level. Stop = below the level.
- **Key MA/EMA holds**: Price touches 20, 50, 100, or 200 MA/EMA on intraday chart and bounces. Confirmation: bar low touches MA, next 2+ bars close above. Entry = MA level. Stop = below MA - 0.3%.

**Swing Trade Entry Rules** (daily bars, weekly levels):
- **Daily EMA close above**: Price closes above key daily EMA (20, 50, 100, or 200) after being below. Confirmation: daily candle CLOSE above the EMA (not just intraday wick). Entry = EMA level. Stop = below EMA or prior swing low.
- **Weekly level hold**: Price tests prior week low or a multi-week support level and holds on daily close. Entry = weekly support level. Stop = below the weekly level.
- **Trend continuation pullback**: In an established uptrend (higher highs, higher lows on daily), price pulls back to a rising EMA and holds. Entry = rising EMA level. Stop = below prior swing low.

**Resistance Warnings** (not actionable entries — informational only):
- When price approaches PDH, weekly high, key MA from below, or prior resistance, AI sends a RESISTANCE warning: "RESISTANCE [SYMBOL] — approaching PDH at $[level]"
- Purpose: help users manage existing longs (tighten stop, take profits) — NOT short entries
- Deduplicated: one warning per resistance level per session

- Each LONG entry signal must include: direction, entry price, stop price, T1, T2, and conviction level
- Resistance warnings include: symbol, level name, level price — no entry/stop/targets
- Acceptance: AI correctly identifies the setup type, applies the specific confirmation rules for that category, and provides all 5 fields for LONG entries; resistance warnings include level and reason

### FR-3: Clean, Actionable Output Format
- Every AI entry signal sent to Telegram follows this exact format:
  ```
  LONG [SYMBOL] $[price]
  Entry $[entry] · Stop $[stop] · T1 $[t1] · T2 $[t2]
  Setup: [setup name — e.g. "PDL bounce + volume confirmation"]
  Conviction: HIGH/MEDIUM/LOW
  ```
- Entry price must be the actual key level price (not current price if different)
- If current price has already moved past the entry level by more than 0.5%, the signal is suppressed (stale)
- Stop must be based on the structural level (e.g., below PDL for PDL bounce, below MA for MA bounce)
- T1 must be the next resistance/support level in the trade direction
- T2 must be a stretch target (second level or measured move)
- No narrative text, no AI commentary — just the actionable signal
- Acceptance: 100% of AI signals include all required fields; entry is within 0.5% of a verifiable key level

### FR-4: Continuous Monitoring with Smart Frequency
- AI monitors every symbol on every user's watchlist during market hours
- Poll frequency: every 2-3 minutes (current cadence) for equities during market hours
- Poll frequency: every 2-3 minutes 24/7 for crypto
- AI deduplicates: same setup type at same level fires at most once per session — applies to both LONG entries and RESISTANCE warnings
- AI respects session boundaries: equity alerts reset at market open, crypto alerts reset at UTC midnight
- RESISTANCE warnings (price approaching overhead level) are deduplicated per level per session — one warning per resistance level, not repeated every poll cycle
- Acceptance: No duplicate alerts for the same setup at the same level within a single session; no duplicate resistance warnings for the same level

### FR-5: Setup Anticipation (WATCH Alerts)
- When price is approaching a key level (within 0.5-1.0%) but hasn't reached it yet, send a WATCH alert:
  ```
  WATCH [SYMBOL] $[price]
  Approaching [level name] at $[level] ([distance]% away)
  If touches and holds → [expected setup type]
  ```
- WATCH alerts fire at most once per symbol per level per session
- WATCH alerts are sent as lower-priority notifications (no Took/Skip buttons)
- Acceptance: At least 40% of WATCH alerts result in an actual entry signal firing within 30 minutes

### FR-6: Regime-Aware Signal Filtering
- AI adjusts its signal quality based on current market regime (SPY trend):
  - TRENDING_UP: Higher conviction for BUY setups, lower for SHORT
  - TRENDING_DOWN: Higher conviction for SHORT setups, lower for BUY
  - CHOPPY: Only fire HIGH conviction setups (suppress MEDIUM/LOW)
- Regime context is included in the AI prompt so it can weight signals appropriately
- Acceptance: In CHOPPY regime, at least 50% fewer total signals fire compared to trending regime

### FR-7: AI Scanner Self-Learning (Outcome Tracking)
- Track win/loss outcomes for every AI-generated signal (based on user Took/Skip + T1/T2/Stop hit)
- Compute rolling 30-day win rate per setup type
- AI prompt includes its own recent performance data: "Your PDL bounce signals are 7/10 this month"
- Setup types with win rate below 30% (minimum 10 signals) are flagged for review
- Dashboard shows AI Scanner performance by setup type
- Acceptance: After 30 days, users can see win rates for each AI setup type in the dashboard

### FR-8: Day Trade vs Swing Trade Signal Separation
- AI generates two distinct signal categories:
  - **Day trade entries**: Based on intraday 5-min bars, session levels, VWAP — expected hold time minutes to hours
  - **Swing trade entries**: Based on daily bars, weekly levels, daily EMAs — expected hold time days to weeks
- Signals are clearly labeled: "DAY TRADE" or "SWING TRADE" in the Telegram message
- Users can configure which categories they receive (both, day only, swing only)
- Swing trade signals fire at most once per symbol per day (not every poll cycle)
- Acceptance: Day trade and swing trade signals are visually distinct and configurable per user

## Non-Functional Requirements

### Performance
- AI signal generation completes within 5 seconds per symbol per poll cycle
- Total poll cycle for 10 watchlist symbols completes within 60 seconds

### Reliability
- If AI service is unavailable, rule-based engine continues as fallback — no alert blackout
- AI signals that fail to generate are logged but never block the poll cycle
- Graceful degradation: partial data (e.g., missing volume) results in lower conviction, not skipped signal

### Cost
- AI costs per user per month should not exceed $5
- Use prompt caching for repeated context (system prompt, key levels that don't change within a session)
- Use Haiku for day trade signals (fast, cheap, structured level detection) and Sonnet for swing trade signals (daily chart analysis requires more reasoning)

## User Scenarios

### Scenario 1: Day Trade Entry at PDL
**Actor**: Pro subscriber watching ETH-USD
**Trigger**: ETH price touches prior day low and holds
**Steps**:
1. AI poll cycle runs, fetches ETH intraday bars and prior day levels
2. AI detects price at PDL $2,176 with volume confirmation
3. AI generates signal: LONG ETH-USD, Entry $2,176, Stop $2,165, T1 $2,210, T2 $2,245
4. Signal sent to Telegram with Took/Skip buttons
5. User clicks Took, enters the trade
**Expected Outcome**: Clean entry signal at the exact level with proper stop and targets

### Scenario 2: WATCH Alert Before Setup
**Actor**: Trader with SPY on watchlist
**Trigger**: SPY drops toward prior day low
**Steps**:
1. AI detects SPY at $540.50, PDL at $538.20 (0.4% away)
2. WATCH alert sent: "Approaching PDL at $538.20 — if touches and holds, PDL bounce setup"
3. 10 minutes later, SPY touches $538.30 and bounces
4. AI fires entry signal: LONG SPY, Entry $538.20, Stop $536.50, T1 $541.00, T2 $543.50
**Expected Outcome**: User was prepared and can act immediately on the entry

### Scenario 3: Swing Trade Entry
**Actor**: Trader checking daily charts
**Trigger**: AAPL pulls back to daily 20 EMA
**Steps**:
1. AI daily scan detects AAPL at $198.50, daily 20 EMA at $197.80
2. AI generates swing signal: SWING LONG AAPL, Entry $197.80, Stop $194.50, T1 $205.00, T2 $210.00
3. Signal sent to Telegram labeled "SWING TRADE"
4. Signal fires once — not repeated on next poll cycle
**Expected Outcome**: One clean swing entry signal per day, not repeated every 3 minutes

### Scenario 4: AI Suppresses in Choppy Market
**Actor**: System during choppy SPY regime
**Trigger**: Multiple setups fire but SPY is ranging
**Steps**:
1. SPY regime is CHOPPY (no clear trend)
2. AI detects MA bounce on NVDA — MEDIUM conviction
3. AI suppresses: MEDIUM conviction not sent in CHOPPY regime
4. AI detects PDL reclaim on AAPL — HIGH conviction
5. AI sends: only the HIGH conviction signal passes the regime filter
**Expected Outcome**: Users see fewer, higher-quality signals during choppy markets

## Key Entities

| Entity | Description | Key Fields |
|--------|-------------|------------|
| AISignal | AI-generated entry signal | symbol, direction, setup_type, entry, stop, t1, t2, conviction, source (day/swing) |
| SignalOutcome | Win/loss tracking for AI signals | signal_id, outcome (win/loss/open), exit_price, pnl_r, closed_at |
| SetupPerformance | Rolling win rates per setup type | setup_type, window (30d), wins, losses, win_rate, last_updated |
| WatchAlert | Approaching-level anticipation alert | symbol, level_type, level_price, distance_pct, converted (bool) |

## Success Criteria

- [ ] AI Scanner detects at least 80% of setups occurring at key levels (PDL, PDH, MAs, VWAP)
- [ ] Every AI signal includes all required fields: direction, entry, stop, T1, T2, conviction
- [ ] Entry prices are within 0.5% of verified key levels — no stale entries
- [ ] No duplicate signals for the same setup at the same level within a session
- [ ] At least 40% of WATCH alerts convert to actual entry signals within 30 minutes
- [ ] In CHOPPY regime, total signal volume drops by at least 50%
- [ ] AI signal win rate (T1 hit) exceeds 50% over a 30-day rolling window
- [ ] AI costs remain under $5/user/month
- [ ] Signal delivery latency under 5 seconds from detection to Telegram
- [ ] Zero alert blackouts — rule engine provides fallback if AI service is down

## Edge Cases

- **No key levels nearby**: AI should output WAIT (no signal) — never force a signal when price is mid-range between levels
- **Gap up/down past level**: If price gaps past a key level at open, the setup is invalid — AI should not fire a bounce/breakout at a level that was never tested
- **Multiple setups at same level**: If PDL bounce and MA bounce both apply at the same price, AI fires one combined signal (not two separate alerts)
- **Crypto at UTC day boundary**: Session reset at midnight UTC — prior day levels update, signals reset
- **Extremely low volume**: AI should flag low-volume setups with reduced conviction, not suppress entirely
- **AI service timeout**: Log the timeout, skip this poll cycle for this symbol, try again next cycle — never crash the monitor

## Assumptions

- The current AI Scanner (Spec 26) provides a working foundation to build on
- Coinbase (crypto) and Alpaca (equities) provide reliable real-time intraday data
- Prior day levels (PDH/PDL) and MAs are computed correctly from daily bar data
- Users interact with signals primarily through Telegram (Took/Skip buttons)
- Win rate is measurable via the Took/Skip + T1/T2/Stop hit tracking already in place

## Constraints

- AI costs must stay under $5/user/month — limits model choice and prompt size
- Signal output must be simple and actionable — no AI commentary or narrative in entry signals
- Must work for both equities (market hours) and crypto (24/7)
- Backward compatible: existing Telegram bot, dashboard, and Took/Skip flow must work unchanged
- Rule engine stays as fallback — not removed, just deprioritized

## Scope

### In Scope
- AI as primary entry detection for day trades (FR-1, FR-2, FR-3)
- Continuous monitoring at current poll cadence (FR-4)
- WATCH alerts for approaching setups (FR-5)
- Regime-aware signal filtering (FR-6)
- AI outcome tracking and self-learning (FR-7)
- Day trade vs swing trade separation (FR-8)
- Clean, standardized signal output format

### Out of Scope
- Portfolio risk management — not part of this spec
- Behavioral coaching (revenge trading, overtrading) — separate concern
- Trade journaling and performance dashboards — existing features handle this
- News sentiment integration — requires external data source, separate spec
- AI Coach conversational improvements — separate feature
- Removing the rule engine — it stays as fallback

## Implementation Priority

| Phase | Features | Impact |
|-------|----------|--------|
| Phase 1 | FR-1 (AI primary), FR-2 (key metrics), FR-3 (output format) | Core: AI fires clean entry signals |
| Phase 2 | FR-4 (monitoring), FR-6 (regime filter), FR-8 (day vs swing) | Quality: right signals at the right time |
| Phase 3 | FR-5 (WATCH alerts), FR-7 (outcome tracking) | Intelligence: anticipation and learning |

## Clarifications

### Session 2026-04-11
- Q: How should AI Scanner and Rule Engine work together? → A: AI becomes primary entry detection — rule engine is unreliable (inconsistent, misses key levels). Rules stay as fallback only.
- Q: Single prompt or specialized prompts per setup category? → A: Specialized prompts per category. Day trade rules: PDL hold/reclaim, PDH breakout on volume, VWAP hold, multi-day double bottom hold, key MA/EMA holds. Swing trade rules: daily EMA close above, weekly level holds, trend continuation pullbacks to rising EMAs.
- Q: Hold confirmation threshold? → A: 2-3 bars on 5-min (10-15 min) for day trades, daily close for swing trades.
- Q: Should AI fire SHORT entries or resistance warnings? → A: Resistance warnings only (informational, helps manage longs). Deduplicated per level per session — no spam.
- Q: Which AI model for signals? → A: Haiku for day trade signals (fast, cheap, structured level detection). Sonnet for swing trade signals (needs more context analyzing daily charts and multi-day patterns). Keeps costs under $5/user/month.
