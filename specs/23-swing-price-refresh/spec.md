# Feature Specification: Swing Scanner Price Refresh

**Status**: Draft (Updated 2026-04-09 — audit findings added)
**Created**: 2026-04-08
**Author**: Claude (via /speckit.specify)
**Priority**: High — swing alerts show stale prices, eroding user trust

## Overview

The EOD swing scanner fires alerts at 3:30 PM ET using yesterday's closing price as entry. By the time users see the alert (next morning), the stock may have gapped 2-10%, making the entry/stop/target prices meaningless. This feature adds a premarket price refresh that updates swing alert levels before market open, and changes the alert format to use condition-based entries tied to key levels rather than stale close prices.

## Problem Statement

Every swing alert shows **yesterday's closing price** as the entry:

- "SWING LONG SPY $659.22" — but SPY opened at $674 today (2.2% gap)
- "SWING LONG GOOGL $305.46" — but GOOGL is at $317 today (3.8% higher)
- EMAs in the alert are also stale (EMA5 at $297 when current price is $317)

**Root cause**: `evaluate_swing_rules()` receives `prior_day` data where `close` = yesterday's close. All 12 swing setups use `entry = close`. The alert fires at 3:30 PM and sits in the Signal Feed until the user checks it the next day.

**Impact**: Users see entry prices that are clearly wrong compared to real-time quotes. This destroys confidence in the platform's swing signals even when the setup identification (pattern, MA structure) is correct.

## Functional Requirements

### FR-1: Premarket Swing Alert Refresh
- At 9:00 AM ET (before market open), refresh all pending swing alerts from the previous session
- For each alert, fetch the current premarket/latest price for the symbol
- Recalculate entry, stop, and target prices based on the current price and the original setup's structure (e.g., if the setup was "pullback to 20 EMA", use the current 20 EMA value)
- Update the alert record in the database with refreshed prices
- Acceptance: Swing alert prices viewed after 9:00 AM reflect current market conditions, not yesterday's close

### FR-2: Condition-Based Entry Format
- Swing alert messages use level-based conditions instead of fixed prices:
  - Instead of "Entry $659.22" → "Entry: near 20 EMA ($657.81)" or "Entry: on pullback to $657"
  - Instead of "Stop $655.52" → "Stop: daily close below 20 EMA"
  - Instead of "Target: RSI 70" → "Target 1: prior resistance $665, Target 2: 50 SMA $673"
- The condition tells the user WHAT level matters, so the alert is valid even if price gaps
- Acceptance: Every swing alert includes the setup condition and the key level, not just a stale price

### FR-3: Gap Detection Suppression
- If a stock gaps more than 5% from the prior close used in the alert, mark the alert as "GAP INVALIDATED"
- The setup may no longer be valid after a large gap (e.g., "pullback to 20 EMA" is meaningless if price gapped 8% above the EMA)
- Show a warning in the Signal Feed: "Setup invalidated — price gapped 5.2% from alert level"
- Acceptance: Alerts with >5% gap show invalidation warning; users are not misled into acting on stale setups

### FR-4: Refresh EMAs and Indicators in Alert Message
- When the premarket refresh runs, update the EMA/MA values in the alert message to reflect current computed values
- Example: If alert said "EMA5 297.70 > EMA20 297.18" but current EMAs are EMA5 315 > EMA20 310, update the message
- Acceptance: EMA/MA values in refreshed alerts match current daily computed values

### FR-5: Premarket Update Notification
- After the premarket refresh, send a single summary Telegram message to users with pending swing positions:
  - "SWING UPDATE: 3 alerts refreshed. SPY entry adjusted to $673 (was $659). GOOGL setup invalidated (5.2% gap)."
- Only sent if there are material changes (>1% price difference or invalidations)
- Acceptance: Users receive one consolidated premarket update, not individual re-alerts

### FR-6: Signal Feed Shows Refreshed Data
- The Signal Feed in the web app shows the refreshed prices, not the original stale prices
- If an alert was refreshed, show a small "Updated 9:00 AM" badge
- If an alert was invalidated, show it dimmed with the invalidation reason
- Acceptance: Signal Feed reflects current market reality for all swing alerts

## User Scenarios

### Scenario 1: Normal Premarket Refresh
**Actor**: Swing trader checking alerts before market open
**Trigger**: 9:00 AM premarket refresh runs
**Steps**:
1. EOD scan fired "SWING LONG SPY — pullback to 20 EMA" at $659 yesterday
2. SPY premarket is $673 (gap up)
3. Refresh recalculates: 20 EMA now at $658, SPY at $673 (14 points above EMA)
4. Alert updated: "Entry: pullback to 20 EMA ($658). Current price $673 — wait for pullback."
5. User sees updated alert in Signal Feed with "Updated 9:00 AM" badge
**Expected Outcome**: Alert levels match current market; user knows to wait for pullback

### Scenario 2: Gap Invalidation
**Actor**: Swing trader with GOOGL alert
**Trigger**: GOOGL gaps 5%+ overnight
**Steps**:
1. EOD scan fired "SWING LONG GOOGL — EMA5/20 crossover" at $305
2. GOOGL premarket is $318 (4.3% gap — but EMAs were at $297, so distance is >7%)
3. Refresh detects: price is now 7% above the EMA crossover zone
4. Alert marked "INVALIDATED — price gapped 7% above setup level"
5. User sees dimmed alert with explanation
**Expected Outcome**: User is not misled into chasing a gapped stock

### Scenario 3: Alert Stays Valid
**Actor**: Swing trader with AAPL alert
**Trigger**: AAPL opens flat near prior close
**Steps**:
1. EOD scan fired "SWING LONG AAPL — 200MA hold" at $253
2. AAPL premarket is $254 (0.4% above)
3. Refresh recalculates: 200MA at $252.50, current price $254 — setup still valid
4. Alert updated with minor price adjustment, no invalidation
5. User sees "Entry: near 200 MA ($252.50)" — actionable
**Expected Outcome**: Alert confirmed as valid with current levels

## Key Entities

| Entity | Description | Key Fields |
|--------|-------------|------------|
| SwingAlert | A swing scanner alert with refreshable prices | id, symbol, original_entry, refreshed_entry, setup_type, invalidated, refresh_time |
| PremarketRefresh | Log of the refresh run | run_time, alerts_refreshed, alerts_invalidated, summary_sent |

## Success Criteria

- [ ] Swing alert entry prices after 9:00 AM are within 1% of actual market price
- [ ] Alerts with >5% gap from setup level are marked as invalidated
- [ ] Users receive one consolidated premarket swing update via Telegram
- [ ] Signal Feed shows refreshed prices with "Updated" badge
- [ ] No swing alert shows yesterday's close as the entry after 9:00 AM

## Edge Cases

- **No premarket data available** (e.g., yfinance premarket not updating): Use most recent available price; do not invalidate without data
- **Market holiday**: Skip premarket refresh if market is closed
- **All alerts invalidated**: Send summary "All swing setups invalidated due to gap" — don't leave users waiting
- **Stock halted premarket**: Skip refresh for halted symbols, note "awaiting data" in Signal Feed
- **Crypto symbols**: Crypto doesn't have premarket — use current price directly (24/7 trading)

## Assumptions

- The premarket refresh runs as a scheduled job at 9:00 AM ET (15 min before market open)
- yfinance provides premarket price data (it does for most US equities)
- The existing `premarket_brief` job at 9:15 AM can be extended or a new job added at 9:00 AM
- Swing setups are identifiable by their alert_type in the alerts table
- The refresh only affects today's swing alerts, not historical ones

## Constraints

- **Protected files**: `alerting/swing_scanner.py` and `analytics/swing_rules.py` require impact analysis and approval before modification
- Must not delay or interfere with the existing premarket brief at 9:15 AM
- Must not re-fire dedup-blocked alerts — refresh updates existing records, doesn't create new ones
- Telegram message for premarket update must be concise (one message, not per-alert)

## Scope

### In Scope
- Premarket price refresh job (9:00 AM ET)
- Condition-based entry format in swing alerts
- Gap invalidation detection (>5% threshold)
- EMA/indicator refresh in alert messages
- Consolidated Telegram premarket update
- Signal Feed shows refreshed data with badges

### Out of Scope
- Changing the EOD scan timing (stays at 3:30 PM)
- Adding new swing setups or removing existing ones
- Real-time swing alert re-evaluation during market hours
- Websocket price streaming for continuous updates
- Changing intraday alert logic (only swing scanner affected)

## Core Design Principles (from April 9 audit)

### P1: Entries First — Get Key Levels Right
Nothing else matters if entries are wrong. The system must accurately fire at key support/resistance levels before adding informational, management, or noise-reduction features. All informational alerts (NOTICE) are disabled until entries are proven reliable.

### P2: Fire at Key Levels, No Gate Suppression
Buy dips at support, sell at resistance. Don't chase. The rules themselves define key levels — no SPY gate or regime filter should suppress signals that fire at a key level. If price is at PDL, the PDL bounce fires regardless of where VWAP is. If price is at PDH, the rejection fires. The gate is redundant on top of rules that already have proximity, volume, and price action checks.

**BUY at support levels:** PDL bounce/reclaim, MA bounce (50/100/200), EMA bounce (50/100/200), VWAP reclaim/bounce, weekly/monthly support, session low bounce, fib retracement

**SHORT at resistance levels:** PDH rejection/failed breakout, MA resistance, session high double top, hourly resistance rejection, weekly high resistance

### P3: Record Everything, Suppress Nothing at DB Level
All signals that fire from rules get recorded to the database — no filtering before persistence. Suppression only controls Telegram notification, never DB recording. This gives us the full dataset to analyze win rates, false signals, and regime performance. You can't improve what you can't measure.

### P4: Disable Informational Alerts Until Entries Are Proven
Turn off all NOTICE/informational alerts: swing_watch, monthly_ema_touch, resistance_prior_high, inside_day_forming, hourly_resistance_approach, resistance_prior_low, etc. These add noise while we're still fixing entry accuracy. Re-enable once entries are reliable.

## Audit Findings (2026-04-09)

Issues discovered during live alert audit on April 9. These directly impact swing alert quality and should be addressed alongside the price refresh work.

### AF-1: `fetch_prior_day` Uses yfinance for Crypto — Not Coinbase
**Problem**: Intraday crypto uses Coinbase (T012 premarket price also uses Coinbase), but `fetch_prior_day()` still calls `yf.Ticker(symbol).history(period="1y")` for PDH/PDL/MAs. When yfinance drops a daily bar (April 9 ETH bar was missing), the system uses wrong prior day data.
**Evidence**: ETH PDH showed $2190.51 in alerts — actual April 9 high was $2238.34. The crypto weekend gap fix tried to fill from hourly bars but produced wrong values.
**Impact**: All PDH/PDL/MA-based alerts fire at wrong levels for crypto. ETH touched PDL $2181.23, bounced — no PDL reclaim alert fired.
**Fix**: Add `fetch_prior_day_crypto()` using Coinbase daily candles, or extend existing Coinbase integration to daily timeframe.

### AF-2: 200MA Reclaim Has No MA Structure Guard
**Problem**: `check_swing_200ma_reclaim()` fires when `prev_close < MA200 AND close > MA200` with no check on MA ordering. On April 9, SPY's MA200 ($660) was the LOWEST MA — below MA50 ($673) and MA100 ($676). The "200MA reclaim" fired but the chart shows price below the 200MA line (which is actually the 100MA on the chart).
**Evidence**: SPY alert "200 MA reclaim — close 676.01 > 200MA 660.16" — misleading because MA200 was not overhead resistance.
**Fix**: Add guard: only fire when `MA200 > MA50` (200MA is actual overhead resistance, not already the lowest MA).

### AF-3: Missing 50MA/100MA Swing Reclaim Rules
**Problem**: No swing rules for 50MA or 100MA reclaim. SPY's real technical event on April 9 was reclaiming the 50MA ($673.54) and approaching the 100MA ($676.39) — neither was captured.
**Evidence**: The `ma_bounce_100` intraday rule fired (score 100) but the swing-level recognition of these crosses doesn't exist.
**Fix**: Add `check_swing_50ma_reclaim()` and `check_swing_100ma_reclaim()` with the same MA structure guard (MA must be above shorter MAs to qualify as resistance reclaim).

### AF-4: Active Entry Bloat — No Cleanup
**Problem**: Each BUY alert creates an `active_entry` but entries never expire. ETH accumulated 22 entries before manual cleanup. Current counts: PLTR 15, BTC 13, TSLA 8, AAPL 7.
**Evidence**: "Exited ETH-USD | 22 entries cleared" on April 9. T1/T2 targets track against stale entries.
**Fix**: Cap active entries per symbol (max 3). Auto-expire entries older than 5 trading days. Expire on stop_loss_hit.

### AF-5: Swing Refresher Resurfaces Old Entries as New Alerts
**Problem**: The swing refresher sends updates for old entries with "now $X" format, making them look like new alerts. Weekly high breakout with entry at $2165.67 appeared in Telegram as "LONG ETH-USD $2189.33" — confusing.
**Evidence**: ETH weekly_high_breakout from days ago appeared at 7:03 PM alongside fresh alerts.
**Fix**: Refreshed alerts should clearly indicate "UPDATED" and not appear as new actionable entries. Only send refresh if setup is still valid relative to current price.

### AF-6: Contradictory Rapid-Fire Signals
**Problem**: BUY-STOP-BUY-SELL signals within 25 seconds. No cooldown window between opposing signals for the same symbol.
**Evidence**: ETH at 00:03-00:04 UTC April 10: weekly_high_breakout BUY → stop_loss_hit → fib_bounce BUY → T1_hit. Unactionable.
**Fix**: Add 2-minute opposing signal cooldown per symbol. After a STOP or SELL, suppress new BUY for the same symbol for 2 minutes (and vice versa).

### AF-7: Re-enable VWAP Reclaim & Bounce
**Problem**: `vwap_reclaim` and `vwap_bounce` rules exist in code but are disabled in `alert_config.py`. They were turned off because they "fade consistently" and have "0% win rate in bearish." But VWAP is a key institutional level — the rules were likely disabled before the SPY gate was mature enough to handle bearish suppression.
**Evidence**: SPY reclaimed VWAP at 10:45 AM on April 9 and ran to $681 (+0.9%). No alert fired. The `vwap_loss` SHORT rule IS enabled and works — the BUY side is the gap.
**Fix**: Simply re-enable both rules. The existing SPY gate already suppresses BUY signals when the market is bearish (RED gate, below morning low) — no special gating needed in the rules themselves. Same as PDH breakout, PDL bounce, MA bounce, etc.
- **vwap_reclaim (BUY)**: Re-enable in ENABLED_RULES. SPY gate handles bearish suppression.
- **vwap_bounce (BUY)**: Re-enable in ENABLED_RULES. SPY gate handles bearish suppression.
- **vwap_loss (SHORT)**: Already enabled, no change.

## Alert Engine Redesign — Based on April 9 Audit

This section is the **core design reference** for the alert engine going forward. All changes must align with the principles (P1-P4) above.

### Current State: 122 Alert Types

| Category | Enabled | Disabled | Total |
|----------|---------|----------|-------|
| BUY entry (intraday) | 34 | 13 | 47 |
| SHORT entry | 11 | 1 | 12 |
| SELL exit/management | 13 | 1 | 14 |
| Informational (NOTICE) | 1 | 9 | 10 |
| Swing (EOD) | 19 | 0 | 19 |
| **Total** | **78** | **24** | **122** |

### Proposed State: Entries + Exits Only

**KEEP ENABLED — BUY entries at key support levels:**

| Alert Type | Key Level | Keep/Change |
|-----------|-----------|-------------|
| prior_day_low_bounce | PDL | Keep |
| prior_day_low_reclaim | PDL | Keep |
| prior_day_high_breakout | PDH | Keep — add to range filter exempt list |
| pdh_retest_hold | PDH | Keep |
| ma_bounce_50/100/200 | Daily MAs | Keep |
| ema_bounce_50/100/200 | Daily EMAs | Keep |
| ema_reclaim_20/50/100/200 | EMA cross | Keep |
| session_low_bounce_vwap | Session low + VWAP | Keep |
| session_low_double_bottom | Session low | Keep |
| multi_day_double_bottom | Multi-day low | Keep |
| weekly_level_touch | Weekly S/R | Keep |
| weekly_high_breakout | Weekly high | Keep |
| monthly_level_touch | Monthly S/R | Keep |
| morning_low_retest | Morning low | Keep |
| inside_day_breakout | Inside day range | Keep |
| inside_day_reclaim | Inside day range | Keep |
| consol_breakout_long | Consolidation | Keep |
| consol_15m_breakout_long | 15m consol | Keep |
| fib_retracement_bounce | Fib levels | Keep |
| bb_squeeze_breakout | Bollinger squeeze | Keep |
| gap_and_go | Gap level | Keep |
| session_low_reversal | Session low | Keep |
| **vwap_reclaim** | **VWAP** | **RE-ENABLE** |
| **vwap_bounce** | **VWAP** | **RE-ENABLE** |

**KEEP ENABLED — SHORT entries at key resistance levels:**

| Alert Type | Key Level | Keep/Change |
|-----------|-----------|-------------|
| pdh_failed_breakout | PDH | Keep |
| session_high_double_top | Session high | Keep |
| hourly_resistance_rejection_short | Hourly R | Keep |
| ema_rejection_short | EMA | Keep |
| intraday_ema_rejection_short | Intraday EMA | Keep |
| vwap_loss | VWAP | Keep |
| morning_low_breakdown | Morning low | Keep |
| session_low_breakdown | Session low | Keep |
| consol_breakout_short | Consolidation | Keep |
| consol_15m_breakout_short | 15m consol | Keep |
| spy_short_entry | SPY-specific | Keep |

**KEEP ENABLED — Trade management (exits):**

| Alert Type | Purpose |
|-----------|---------|
| stop_loss_hit | Exit — stop reached |
| auto_stop_out | Exit — auto stop |
| target_1_hit | Exit — T1 reached |
| target_2_hit | Exit — T2 reached |
| _t1_notify | Position management |

**DISABLE — Informational (not entries, add noise):**

| Alert Type | Why Disable |
|-----------|-------------|
| monthly_ema_touch | 229 alerts in 4 days — pure noise |
| swing_watch | 189 alerts — already partially disabled |
| resistance_prior_high | 104 alerts — "watch for rejection" not actionable |
| pdh_rejection | 98 alerts — informational, SHORT entry rules cover this |
| prior_day_low_resistance | 89 alerts — not an entry |
| ma_resistance | 75 alerts — not an entry |
| hourly_resistance_approach | 69 alerts — "approaching" not actionable |
| weekly_high_resistance | 65 alerts — not an entry |
| prior_day_low_breakdown | 32 alerts — not an entry |
| monthly_high_resistance | 6 alerts — not an entry |
| inside_day_forming | 6 alerts — not an entry |
| resistance_prior_low | 11 alerts — not an entry |
| inside_day_breakdown | Not an entry |
| support_breakdown | Not an entry |
| weekly_low_breakdown | Not an entry |
| monthly_low_breakdown | Not an entry |
| weekly_low_test | Not an entry |
| monthly_low_test | Not an entry |

### Suppression Architecture — Record Everything, Gate Nothing

**Current (broken):**
```
Rule fires → 9 filters drop signals → survivors reach DB → 4 more filters at notification
```

**Proposed:**
```
Rule fires → ALL signals recorded to DB with tags → notification filters only at Telegram level
```

| Current Filter | Action | New Behavior |
|---------------|--------|-------------|
| SPY gate (lines 8085-8157) | Drops BUY/SHORT | **REMOVE** — key level rules fire at key levels |
| Trending down filter (7930) | Drops weak BUY | **REMOVE** — let data show if these work |
| Range filter (7975) | Drops BUY in consolidation | **REMOVE** — was killing PDH breakouts |
| SPY above VWAP (7959) | Drops non-index SHORT | **REMOVE** — shorts at resistance should fire |
| Opening wait (7948) | Drops BUY first 15 min | **KEEP** — data quality guard (not enough bars) |
| Noise filter (8173) | Drops low-volume BUY | **TAG** — record with `low_volume` flag, don't drop |
| Staleness filter (8184) | Drops BUY past entry+1R | **TAG** — record with `stale` flag, don't drop |
| Dedup in evaluate_rules (8016) | Drops repeated types | **KEEP** — prevents same alert every 5 min |
| Burst cooldown (monitor.py) | Suppresses notification | **KEEP** — notification-level only |
| Zone clustering (monitor.py) | Suppresses notification | **REVIEW** — $10 bucket too coarse, fix to $5 or per-type |

### Swing Rules — Fixes

| Rule | Issue | Fix |
|------|-------|-----|
| swing_200ma_reclaim | Fires when 200MA is lowest MA | Add guard: `MA200 > MA50` |
| swing_50ma_reclaim | **Missing** | Add new rule |
| swing_100ma_reclaim | **Missing** | Add new rule |

### Data Layer — Fixes

| Issue | Fix |
|-------|-----|
| `fetch_prior_day` uses yfinance for crypto | Use Coinbase daily candles, yfinance fallback |
| Per-user duplication (3x everything) | Global dedup, not per-user |
| Active entry bloat (22 ETH entries) | Cap 3 per symbol, auto-expire 5 days, clear on stop |
| Contradictory rapid-fire (BUY-STOP-BUY in 25s) | 2-min opposing signal cooldown |

## Revised Scope

### Added to In Scope (from audit)
- AF-1: Coinbase daily data for `fetch_prior_day` crypto path
- AF-2: 200MA reclaim MA structure guard
- AF-3: 50MA/100MA swing reclaim rules
- AF-4: Active entry cleanup (max 3 per symbol, auto-expire)
- AF-5: Refresher "UPDATED" labeling (ties into FR-6)
- AF-6: Opposing signal cooldown (2-min window)
- AF-7: Re-enable VWAP reclaim/bounce — key level rules fire at key levels

## Clarifications

_Added during `/speckit.clarify` sessions_
