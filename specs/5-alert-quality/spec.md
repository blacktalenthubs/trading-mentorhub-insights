# Feature Specification: Alert Quality & Noise Management

**Status**: Research Complete — Ready for Optimization
**Created**: 2026-04-04
**Priority**: High — core product quality

---

## The Problem

A trader with 20 symbols on their watchlist gets 50-85 alerts per day. Most are noise. The system needs to send fewer, higher-conviction alerts that traders actually act on.

**Current daily volume:** 14-85 alerts/day (varies by market volatility)
**Goal:** 10-20 high-conviction alerts/day for a 20-symbol watchlist

---

## Production Win Rates (Last 30 Days)

### Top Performers (>80% win rate, 10+ signals)

| Alert Type | Dir | Total | Win | Loss | WR% | Avg Score |
|-----------|-----|-------|-----|------|-----|-----------|
| **vwap_reclaim** | BUY | 20 | 14 | 0 | **100%** | 72 |
| **consol_breakout_long** | BUY | 15 | 10 | 0 | **100%** | 84 |
| **consol_breakout_short** | SHORT | 27 | 22 | 1 | **95.7%** | 80 |
| **prior_day_high_breakout** | BUY | 24 | 12 | 1 | **92.3%** | 68 |
| **vwap_bounce** | BUY | 18 | 11 | 1 | **91.7%** | 73 |
| **pdh_retest_hold** | BUY | 17 | 9 | 1 | **90.0%** | 66 |
| **vwap_loss** | SHORT | 23 | 16 | 2 | **88.9%** | 61 |
| **session_low_bounce_vwap** | BUY | 40 | 27 | 4 | **87.1%** | 55 |
| **prior_day_low_reclaim** | BUY | 36 | 20 | 3 | **87.0%** | 66 |
| **prior_day_low_bounce** | BUY | 18 | 12 | 2 | **85.7%** | 69 |
| **ema_rejection_short** | SHORT | 20 | 11 | 2 | **84.6%** | 56 |
| **opening_low_base** | BUY | 7 | 5 | 1 | **83.3%** | 64 |
| **hourly_resistance_rejection_short** | SHORT | 18 | 9 | 2 | **81.8%** | 57 |

### Moderate Performers (60-80% win rate)

| Alert Type | Dir | Total | Win | Loss | WR% | Avg Score |
|-----------|-----|-------|-----|------|-----|-----------|
| **planned_level_touch** | BUY | 31 | 16 | 5 | 76.2% | 67 |
| **weekly_level_touch** | BUY | 14 | 9 | 3 | 75.0% | 48 |
| **intraday_support_bounce** | BUY | 34 | 17 | 6 | 73.9% | 59 |
| **morning_low_retest** | BUY | 20 | 11 | 4 | 73.3% | 68 |
| **fib_retracement_bounce** | BUY | 13 | 8 | 3 | 72.7% | 74 |
| **ema_bounce_100** | BUY | 10 | 5 | 2 | 71.4% | 62 |
| **ma_bounce_200** | BUY | 9 | 5 | 2 | 71.4% | 51 |
| **session_low_double_bottom** | BUY | 43 | 23 | 11 | 67.6% | 53 |
| **ema_bounce_200** | BUY | 23 | 12 | 6 | 66.7% | 58 |
| **multi_day_double_bottom** | BUY | 33 | 17 | 9 | 65.4% | 61 |

### Weak/Low Sample

| Alert Type | Dir | Total | Win | Loss | WR% | Notes |
|-----------|-----|-------|-----|------|-----|-------|
| ma_bounce_50 | BUY | 7 | 1 | 1 | 50% | Low sample |
| intraday_ema_rejection_short | SHORT | 3 | 1 | 1 | 50% | Low sample |
| pdh_failed_breakout | SHORT | 8 | 4 | 2 | 66.7% | Moderate |

---

## Key Insights

### 1. Score ≠ Win Rate
- `session_low_bounce_vwap` has **87% win rate** but avg score 55 (B)
- `ma_bounce_50` has avg score 88 (A+) but only 50% win rate
- **Scoring needs recalibration** — VWAP-based signals outperform MA-based ones

### 2. High-Volume Winners (Signal, Not Noise)
These fire often AND win consistently:
- `session_low_bounce_vwap` (40 signals, 87% WR) — VWAP support bounce
- `prior_day_low_reclaim` (36 signals, 87% WR) — PDL structural level
- `consol_breakout_short` (27 signals, 96% WR) — range breakdown
- `prior_day_high_breakout` (24 signals, 92% WR) — PDH structural level

### 3. High-Volume Losers (Noise Candidates)
These fire often but win less:
- `session_low_double_bottom` (43 signals, 68% WR) — too loose?
- `multi_day_double_bottom` (33 signals, 65% WR) — false bottoms
- `intraday_support_bounce` (34 signals, 74% WR) — broad support

### 4. VWAP Signals Dominate
- `vwap_reclaim` 100%, `vwap_bounce` 92%, `session_low_bounce_vwap` 87%
- VWAP is the institutional benchmark — signals based on it have structural edge

### 5. Daily Volume
- Average: ~50 alerts/day for current watchlist (6-8 symbols)
- With 20 symbols: projects to ~120-170 alerts/day — **too noisy**
- Need 70-80% reduction for usable experience

---

## Noise Reduction Strategies

### Strategy 1: Score Threshold Per Tier
```
Free tier:  Only A+ alerts (score ≥ 90) → ~5-8/day
Pro tier:   A and above (score ≥ 75) → ~15-25/day  
Elite tier: B+ and above (score ≥ 65) → ~30-50/day
```
**Problem:** Score doesn't correlate well with win rate (see insight #1)

### Strategy 2: Win-Rate Weighted Scoring
Adjust base score by historical win rate for that alert type:
```
adjusted_score = base_score * (1 + (historical_wr - 0.70) * 2)
```
- 90% WR rule: 80 * 1.40 = 112 → capped at 100
- 65% WR rule: 80 * 0.90 = 72 → demoted from A to B+

### Strategy 3: Conviction Tiers (Not Just Score)
```
TIER 1 (Push immediately):
  - vwap_reclaim, consol_breakout_*, prior_day_high_breakout
  - pdh_retest_hold, vwap_bounce
  → Rules with >85% historical win rate

TIER 2 (Push with context):
  - prior_day_low_reclaim, prior_day_low_bounce
  - session_low_bounce_vwap, ema_rejection_short
  → Rules with 75-85% win rate

TIER 3 (Dashboard only, no push):
  - session_low_double_bottom, multi_day_double_bottom
  - intraday_support_bounce, ema_bounce_200
  → Rules with <75% win rate OR low sample

TIER 4 (Disabled):
  - Consistently underperforming rules
```

### Strategy 4: Per-Symbol Daily Alert Budget
```
Max alerts per symbol per day: 3 (entry) + unlimited (exit)
After 3 BUY signals for NVDA → suppress further BUY until next session
```

### Strategy 5: Confluence Requirement
```
Single signal alone: Dashboard only (no push)
2+ confirming signals: Push notification (consolidated)
```
Forces multiple structural levels to agree before notifying.

---

## Current Noise Filters (Already Implemented)

| Filter | What It Does | Effectiveness |
|--------|-------------|---------------|
| SPY Gate (VWAP <40%) | Suppresses equity BUY when SPY weak | High |
| Opening Wait (15 min) | No BUY first 3 bars | High |
| Burst Cooldown (10 min) | Suppress repeat BUY notification | Medium |
| Post-Stop Cooldown (30 min) | No BUY after stop-out | Medium |
| Dedup (per session) | One alert_type per symbol per day | Medium |
| Low Volume Skip (<0.4x) | Drop thin-volume signals | Medium |
| ADX Choppy Penalty (-10) | Demote in trendless markets | Low |
| Staleness Filter (>1R moved) | Drop signals where price ran | Medium |
| User Preferences | Toggle categories on/off | User-controlled |

---

## Recommended Optimization Plan

### Phase 1: Score Recalibration (Based on Data)
- Weight VWAP alignment higher (currently 25 pts, should be 35)
- Add historical win rate multiplier to score
- Reduce MA position weight for non-bounce alerts (currently 25 pts)

### Phase 2: Conviction Tiers
- Classify rules into Tier 1-4 based on 30-day rolling win rate
- Only Tier 1+2 get push notifications by default
- Users can opt into Tier 3 in settings

### Phase 3: Per-Symbol Budget
- Max 3 push alerts per symbol per session
- Consolidation counts as 1 (not 3)
- Exit alerts exempt

### Phase 4: Confluence Gate (Aggressive Noise Cut)
- Require 2+ confirming signals for push
- Single signals → dashboard only
- Exception: Tier 1 rules (proven >85% WR) always push

---

## Acceptance Criteria

- [ ] Daily alert volume drops from 50-85 to 15-25 for 8-symbol watchlist
- [ ] Win rate of pushed alerts increases from 77% to 85%+
- [ ] No Tier 1 signals are suppressed (zero false negatives on best rules)
- [ ] Users can see all alerts on dashboard (only push is filtered)
- [ ] Score correlates with actual win rate (R² > 0.5)

---

## Bugs Found (2026-04-05)

### BUG-1: Consolidation Uses Lowest Entry Instead of Primary Signal Entry

**What happened:** ETH-USD session_low_double_bottom fired at $2052.49 with [+3 confirming: Ma Bounce 50, PDL Reclaim, Inside Day Reclaim]. The consolidation logic picked the LOWEST entry from all signals ($2046.06 from MA Bounce 50) instead of the primary signal's entry ($2052.49).

**Problem:** The 50MA entry ($2046.06) was BELOW the current price ($2052). The stop was set at $2044.56 — only $1.50 below the artificial entry. Price was actually at $2052 so the stop was $8 above the real risk level. Stop hit immediately → false stop-out.

**Fix needed:** `_consolidate_signals()` should use the PRIMARY signal's entry (highest scored) as the base, not the lowest entry from all confirming signals. Confirming signals should validate the thesis, not change the entry point.

**File:** `analytics/intraday_rules.py` → `_consolidate_signals()` function

**Impact:** False stop-outs on consolidated signals. Traders lose money on trades that should have held.

### BUG-2: Entry Price Not Actionable — Alert Fires After Bounce

**What happened:** ETH-USD multi-day double bottom detected at $66,615. System waits for "recovery confirmed" before firing. By the time alert sends, price is at $66,786 — $170 above entry.

**Problem:** Trader sees "Entry $66,615" but can't buy at that price — it's gone. If they buy at $66,786 (current), their real risk is much larger than the trade plan suggests.

**Fix options:**
- Show TWO entries: "Ideal entry: $66,615 (if retests)" / "Market entry: $66,786 (current)"
- Or use current price as entry and adjust stop/targets accordingly

### BUG-3: Broken Support Still Labeled "Support" on Chart

**What happened:** ETH-USD broke below $2,044.87 support. Chart still showed it as green "Support" instead of red "Resistance".

**Status:** FIXED (2026-04-05) — chart dynamically flips label based on price position.

### BUG-4: Target Ignores Overhead Resistance

**What happened:** ETH-USD BUY at $2,024 with T1 at $2,065. But $2,044 (broken support = new resistance) is in the way. Target should be $2,044 first, not $2,065.

**Fix needed:** Target calculation should check for overhead resistance levels (broken support, MAs, prior highs) and use the NEAREST one as T1, not a fixed R:R multiple.

**File:** `analytics/intraday_rules.py` — target calculation in each check_* function

### BUG-5: SHORT Alert Fires While User Has Active LONG Position

**What happened:** ETH-USD fired an EMA rejection SHORT alert while the user had an active LONG trade (multi-day double bottom). This is confusing — the system is telling the trader to go short on the same symbol they're long on.

**Fix needed:** When a user has an active entry (status='active') for a symbol, suppress SHORT alerts for that symbol. Only send exit alerts (T1/stop) for the active trade direction.

**File:** `api/app/background/monitor.py` — check active_entries before sending conflicting direction alerts

### BUG-6: First Touch of MA50 Treated as Rejection — Should Wait for Confirmation

**What happened:** ETH-USD touched the 50MA ($2,045) for the first time after it broke below. System immediately fired "MA50 REJECTION" SHORT. But on the daily chart, the 50MA had been support for days — the first retest from below is often a reclaim attempt, not a rejection.

**Fix needed:** MA resistance rejection should require:
1. At least 2 bars of rejection (not just one bar close below)
2. Check if the MA was recently support (within last 5 sessions) — if so, demote confidence or suppress
3. First touch after a break should be labeled "MA50 TEST" (NOTICE) not "MA50 REJECTION" (SHORT)

**File:** `analytics/intraday_rules.py` — `check_ema_rejection_short()` and `check_ma_resistance()`

### ENHANCEMENT-1: Targets = Nearest Resistance (Not Fixed R:R)

**Observation:** Target at $2,065 is the hourly resistance where price was rejected multiple times. When price approaches it, traders should know it's a DECISION POINT — take partial profits or hold for breakout.

**Current:** Target labeled "Target" in blue — implies price will reach it.
**Fixed:** Target labeled "T1/Resist" in amber — communicates both target AND resistance.

**Status:** FIXED (2026-04-05) — chart label changed.

**Future:** Target calculation should use nearest overhead resistance as T1, not fixed R:R multiple. When resistance breaks and price closes above, it flips to support and next resistance becomes T2.

### INSIGHT-1: Daily Close Matters for MA Rejection

Observation from live trading: ETH touched 50MA intraday but hadn't closed below on the daily chart. The 50MA had been support for days. System should only fire MA rejection SHORT after a daily close below the MA — intraday wicks don't confirm bearish.

This reinforces BUG-6 fix (2-bar confirmation) but goes further: for DAILY MAs, require a DAILY CLOSE below, not just intraday bars.

### BUG-7: Breakout Alert at Resistance Should Be Exit Alert for Active Longs

**What happened:** ETH-USD rallied from $2,024 (double bottom) up to $2,065 resistance (T1/Resist). System fired a "CONSOLIDATION BREAKOUT" BUY alert at $2,061 — right at the resistance level. 

**Problem:** For a trader who is LONG from $2,024, the $2,065 level is their EXIT POINT (T1), not a new entry. The breakout alert encourages them to ADD at the worst possible spot — right at resistance where sellers appear.

**The dual-purpose level:**
- For a trader WITH NO POSITION: a breakout above $2,065 confirmed with a close IS a valid new long entry
- For a trader WITH AN ACTIVE LONG from below: $2,065 is their T1 — they should be taking profits, not adding

**Fix needed (two parts):**

**Part A: Breakout alerts at resistance need CLOSE confirmation**
- Current: consolidation breakout fires when price BREAKS the range
- Needed: require a CLOSE above the resistance level (not just a wick/break)
- Implementation: check if the bar CLOSES above the resistance, not just if high exceeds it
- For PDH breakout this already exists (0.15% above close required) — apply same logic to consol breakout

**Part B: When user has active LONG approaching T1, send EXIT alert instead of BUY**
- If user has active entry at $2,024 and price reaches $2,065 (their T1):
  → Send "T1 APPROACHING — consider taking partial profits" (EXIT)
  → Do NOT send "CONSOLIDATION BREAKOUT — new long entry" (BUY)
- This is an extension of BUG-5 (conflicting direction)
- The system should check: is this breakout level near any active entry's T1?

**File:** `analytics/intraday_rules.py` — `check_consol_breakout_long()`, `check_prior_day_high_breakout()`
**File:** `api/app/background/monitor.py` — check active entries before sending breakout alerts near T1

### INSIGHT-2: Levels Are Context-Dependent

A price level is not inherently "support" or "resistance" or "target" — it depends on WHERE THE TRADER IS:

| Trader Position | Level $2,065 Is |
|----------------|-----------------|
| Long from $2,024 | T1 / EXIT (take profits) |
| No position | Breakout entry IF confirmed with close |
| Short from $2,080 | T1 / EXIT (cover short) |

The system should be AWARE of the user's position when labeling levels and deciding what alert to send. This is the foundation of "position-aware alerts."

### BUG-8: System Sends BUY Then SHORT at Same Level Within Minutes

**What happened:** BTC-USD fired CONSOLIDATION BREAKOUT BUY at $67,375, then SESSION HIGH DOUBLE TOP SHORT at $67,368 — same price, opposite direction, minutes apart.

**Problem:** Trader gets told to go LONG then SHORT at the same level. This is maximum confusion and destroys trust in the system.

**Root cause:** Each rule evaluates independently. The breakout rule sees range broken. The double top rule sees two tests at the same high. Both are technically correct but mutually exclusive.

**Fix needed — Direction Lock:**
1. Once a BUY signal fires for a symbol, suppress SHORT signals for that symbol for N minutes (15-30 min)
2. Once a SHORT signal fires, suppress BUY signals
3. Only EXIT alerts (T1/stop) override the lock
4. The lock is per-symbol, per-session
5. This is an extension of BUG-5 (conflicting direction) but applies even without active entries

**Implementation:**
- Add `_last_direction: dict[str, tuple[str, datetime]]` to monitor
- Before sending any BUY/SHORT: check if opposite direction fired recently
- If conflict: suppress the newer signal, log it

**Principle: COMMIT to a direction. Signal exit before flipping.**

### BUG-9: System Auto-Closes Trades Without User Input — Misleading P&L

**What happened:** System fires "STOPPED OUT" alert and auto-closes the trade at $2,044.56 with P&L: -$36. But the user may have already exited at a profit manually, or may choose to hold through the dip.

**Problem:**
1. User takes trade, exits at profit on their broker — but never reports exit price to system
2. System sees stop level breached, auto-records as loss
3. Win rate and P&L data become misleading — doesn't reflect actual trading results
4. V1 had same issue — win rates can't be trusted because many profitable exits went unreported

**Fix — User-Controlled Exits Only:**
1. System should NEVER auto-close a trade. Only NOTIFY that stop/target level was reached.
2. Stop/target alerts become INFORMATIONAL: "Stop level $2,025 was breached — consider exiting"
3. User closes the trade manually:
   - From Dashboard: Click "Close" → enter exit price → P&L calculated
   - From Telegram: Tap "Exit" → system uses current market price (best we can do)
   - `/exit SYMBOL PRICE` command for specific exit price
4. If user doesn't close, trade stays OPEN indefinitely
5. This gives ACCURATE P&L data — only user-reported exits count

**Impact on win rate tracking:**
- Current: auto-stop creates false losses (user may have exited profitably)
- Fixed: only user-reported exits → accurate win rate → trustworthy track record
- The track record becomes the user's ACTUAL results, not theoretical system outcomes

**Implementation:**
- Stop `check_auto_stop_out()` and `check_stop_loss_hit()` from closing real trades
- These alerts NOTIFY only — direction = "NOTICE" instead of closing entries
- Dashboard/Telegram exit flow asks for exit price
- Remove auto-close logic from monitor
