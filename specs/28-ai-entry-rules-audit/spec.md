# AI Entry Rules Audit — Current State Documentation

**Status**: Complete
**Created**: 2026-04-11
**Author**: Claude (speckit)

## Overview

This document evaluates and documents all current AI-based entry and resistance detection rules as implemented in the platform. Two systems run in parallel: the **AI Day Scanner** (Spec 27, primary) and the **Rule-Based Engine** (legacy, fallback). This audit captures exactly what rules each system uses, how they confirm entries, what data they consume, and known issues.

## Current AI Day Scanner (Primary)

**File**: `analytics/ai_day_scanner.py`
**Model**: Claude Haiku (`claude-haiku-4-5-20251001`)
**Schedule**: Every 10 minutes during market hours (crypto 24/7)
**Prompt type**: Specialized day trade entry detection with structural stop rules

### AI Entry Rules (LONG only)

| # | Rule Name | Trigger | Confirmation | Entry Price | Stop Price |
|---|-----------|---------|--------------|-------------|------------|
| 1 | PDL HOLD/RECLAIM | Price touches or dips below prior day low | 2-3 bars close above PDL | PDL level | Below session low |
| 2 | PDH BREAKOUT ON VOLUME | Price closes above prior day high | Volume >= 1.5x average | PDH level | Below breakout bar low or PDH |
| 3 | VWAP HOLD | Price was above VWAP, pulled back, reclaimed | 2-3 bars close above VWAP | VWAP level | Below session low (structural) |
| 4 | DOUBLE BOTTOM HOLD | Same low tested from prior session (within 0.5%) | 2+ bars hold above level | Double bottom level | Below the double bottom low |
| 5 | MA/EMA HOLD | Price touches 20/50/100/200 MA or EMA | Bar low touches MA, 2-3 bars close above | MA level | Below the MA |

### AI Resistance Rules (Informational only — not entries)

| Trigger | Output | Purpose |
|---------|--------|---------|
| Price approaching PDH from below | RESISTANCE warning | Help manage existing longs |
| Price approaching weekly high from below | RESISTANCE warning | Take profits / tighten stop |
| Price approaching key MA from below | RESISTANCE warning | Watch for rejection |

### AI Stop Rules

The AI prompt explicitly instructs: **"NEVER use a fixed % for stop. Always find the structural level."**

- Stop must be below the NEXT SUPPORT LEVEL down from entry
- Uses real levels: session low, PDL, VWAP, MAs
- Example given: VWAP hold entry at $2243 → stop below session low $2230, NOT $2236 (0.3% math)

### AI Position Detection (Code-Calculated)

Before calling Claude, the code pre-calculates position relative to key levels:
- **AT** a level: within 0.3% distance
- **APPROACHING** a level: 0.3-0.8% distance
- **MID-RANGE**: >0.8% from all levels

Levels checked: Session Low, Session High, VWAP, PDL, PDH, 50MA, 100MA, 200MA

This position is injected into the prompt to guide the AI's decision.

### AI Data Context (What Claude Receives)

| Data | Source | Bars/Count |
|------|--------|------------|
| 5-min intraday bars | Coinbase (crypto), Alpaca (equity) | Last 20 bars |
| 1-hour bars | yfinance | Last 10 bars |
| Prior day levels | Coinbase daily (crypto), yfinance (equity) | PDH, PDL, Close |
| Moving averages | Computed on daily data | 20/50/100/200 MA + EMA |
| RSI | Wilder's method on daily close | RSI14 |
| Weekly levels | Resampled from daily | Prior week high/low |
| VWAP | Computed from intraday bars | Session VWAP |
| Volume ratio | Last bar vol / session avg vol | Single ratio |

### AI Output Format

```
SETUP: [rule name]
Direction: LONG / RESISTANCE / WAIT
Entry: $price
Stop: $price
T1: $price
T2: $price
Conviction: HIGH / MEDIUM / LOW
Reason: 1 sentence
```

### AI Dedup Logic

- Key: `(symbol, setup_type, level_bucket)` per session date
- Level bucket: rounded to 2 significant figures
- Resistance warnings: deduped per `(symbol, "RESISTANCE", level_bucket)`
- Session reset: midnight UTC (crypto), market open (equity)
- WAIT results: recorded to DB (one per symbol, not per user), not sent to Telegram

### AI Swing Scanner (Currently Disabled)

**File**: `analytics/ai_swing_scanner.py`
**Model**: Claude Sonnet
**Status**: DISABLED — entry below current price was confusing users
**Schedule (when enabled)**: 2x/day at 9:05 AM + 3:30 PM ET

Swing entry rules when active:
1. Daily EMA close above (20/50/100/200)
2. Weekly level hold
3. Trend continuation pullback to rising EMA

---

## Rule-Based Engine (Legacy Fallback)

**File**: `analytics/intraday_rules.py` (~8,000 lines)
**Schedule**: Every 3 minutes via monitor poll cycle
**Status**: Running in parallel, but known to be inconsistent

### Enabled Rule Types (60+ rules in 4 categories)

**BUY — Support / Bounce (Tier 1)**

| Rule | Alert Type | What It Does |
|------|-----------|--------------|
| MA Bounce 20/50/100/200 | `ma_bounce_*` | Bar low touches MA, bounces with hold confirmation |
| EMA Bounce 20/50/100/200 | `ema_bounce_*` | Same as MA bounce but exponential moving average |
| PDL Reclaim | `prior_day_low_reclaim` | Dips below PDL, closes back above with 2/3 bars hold |
| PDL Bounce | `prior_day_low_bounce` | Touches near PDL (within 0.2%), holds without breaking |
| VWAP Reclaim | `vwap_reclaim` | Crosses above VWAP from below |
| VWAP Bounce | `vwap_bounce` | Pullback to VWAP, holds |
| Session Low Double Bottom | `session_low_double_bottom` | Two tests of same session low |
| Multi-Day Double Bottom | `multi_day_double_bottom` | Same low across multiple sessions |
| EMA Reclaim 20/50/100/200 | `ema_reclaim_*` | Close above EMA after being below |
| Session Low Reversal | `session_low_reversal` | Reversal candle + volume at session low |

**BUY — Breakout**

| Rule | Alert Type | What It Does |
|------|-----------|--------------|
| PDH Breakout | `prior_day_high_breakout` | Close above PDH with volume |
| PDH Retest Hold | `pdh_retest_hold` | Breaks above PDH, pulls back, holds |
| Inside Day Breakout | `inside_day_breakout` | Breaks above inside day high |
| Inside Day Reclaim | `inside_day_reclaim` | Dips below inside day low, reclaims |
| Weekly High Breakout | `weekly_high_breakout` | Close above prior week high with volume |
| Monthly High Breakout | `monthly_high_breakout` | Close above prior month high |
| BB Squeeze Breakout | `bb_squeeze_breakout` | Bollinger Band squeeze → expansion |
| Gap and Go | `gap_and_go` | Gap up that holds and extends |
| Fib Retracement Bounce | `fib_retracement_bounce` | Bounce at 50% or 61.8% Fibonacci level |
| Consolidation Breakout | `consol_breakout_long` | Breakout from hourly or 15-min consolidation |

**SHORT / RESISTANCE — Warnings**

| Rule | Alert Type | What It Does |
|------|-----------|--------------|
| Resistance Prior High | `resistance_prior_high` | Price approaching yesterday's high from below |
| PDH Rejection | `pdh_rejection` | Price tests PDH and fails (2-bar rejection) |
| Weekly High Resistance | `weekly_high_resistance` | Price near prior week high |
| Monthly High Resistance | `monthly_high_resistance` | Price near prior month high |
| PDH Failed Breakout | `pdh_failed_breakout` | Breaks above PDH but falls back below |
| EMA Rejection Short | `ema_rejection_short` | Price rejects off EMA from below |
| Session High Double Top | `session_high_double_top` | Two tests of same session high, fails |

**EXIT / MANAGEMENT**

| Rule | Alert Type | What It Does |
|------|-----------|--------------|
| Target 1 Hit | `target_1_hit` | Price reaches T1 level |
| Target 2 Hit | `target_2_hit` | Price reaches T2 level |
| Stop Loss Hit | `stop_loss_hit` | Price breaks stop level |
| Auto Stop Out | `auto_stop_out` | Trailing stop triggered |
| VWAP Loss | `vwap_loss` | Price drops below VWAP |
| Support Breakdown | `support_breakdown` | Key support level breaks |
| PDL Breakdown | `prior_day_low_breakdown` | Price breaks below PDL |

### Disabled Rules (Noise)

| Rule | Reason Disabled |
|------|----------------|
| `ma_approach` | Price is always near some MA — noise |
| `ma_resistance` | Better as a filter, not standalone alert |
| `ema_resistance` | Same — noise as standalone |
| `hourly_consolidation` | 40% of hours are tight range |
| `session_high_retracement` | Describes normal intraday pullback |
| `first_hour_summary` | 5 alerts/day with no actionable value |
| `opening_low_base` | Redundant with morning_low_retest, 0% win rate |
| `macd_histogram_flip` | Low trust, needs evaluation data |

### Rule Engine Known Issues

1. **Inconsistent firing**: Rules don't fire at some key levels — missed setups
2. **Stale entries**: Entry price sometimes doesn't match current price (timezone/data bugs partially fixed)
3. **Too many rule types**: 60+ rules create noise, hard to tell what's working
4. **Suppression filters removed**: Cooldown, SPY gate, trending-down filter, range filter, and contradictory signal filter were all stripped out (commit `da2b870`), reducing signal quality
5. **No outcome tracking**: Rules don't know their own win rates — no self-improvement
6. **Rigid confirmation**: Fixed bar counts and percentages, can't adapt to volatility

---

## AI vs Rule Engine Comparison

| Aspect | AI Scanner | Rule Engine |
|--------|-----------|-------------|
| Entry rules | 5 focused rules | 60+ rules |
| Confirmation | AI reads bar context | Fixed bar counts + thresholds |
| Stop logic | Structural (next support) | Mixed (some structural, some fixed %) |
| Resistance | Warnings only (deduped) | Full SHORT entries + warnings |
| Dedup | (symbol, setup, level) | (symbol, alert_type, price_bucket) |
| Frequency | Every 10 min | Every 3 min |
| Model | Claude Haiku | No AI (mechanical) |
| Adaptability | Reads context per call | Rigid thresholds |
| Cost | ~$0.001/symbol/scan | Free |
| Known issues | Entry sometimes not at level | Inconsistent, misses levels, stale entries |

## Recommendations

1. **Track outcomes for both systems**: Record win/loss for AI signals and rule-based signals to compare objectively over 30+ days
2. **Keep rule engine as fallback only**: AI scanner is the primary signal source going forward
3. **Fix swing scanner**: Entry-at-current-price issue needs resolution before re-enabling
4. **Reduce rule engine noise**: Disable remaining low-win-rate rules once outcome data confirms which ones are losers
5. **Add regime filter to AI scanner**: Currently disabled — re-enable when CHOPPY regime suppression is validated

## Assumptions

- Both systems use the same underlying market data (Coinbase for crypto, Alpaca for equities, yfinance fallback)
- Prior day levels (PDH/PDL) are now correct after the Coinbase timezone fix
- Users interact with signals via Telegram (Took/Skip buttons)
- Win rate is measurable via Took + T1/T2/Stop hit tracking

## Scope

### In Scope
- Document all current AI entry rules and their confirmation criteria
- Document all enabled rule-based entry and resistance types
- Compare AI vs rule engine approaches
- Identify known issues and gaps

### Out of Scope
- Implementing new rules or modifying existing ones
- Win rate analysis (requires 30+ days of outcome data)
- Swing trade rules evaluation (scanner currently disabled)

## Clarifications

_Added during `/speckit.clarify` sessions_
