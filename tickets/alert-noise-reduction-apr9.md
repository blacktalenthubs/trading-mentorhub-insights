# Alert Noise Reduction — Based on Apr 9 Analysis

**Date**: 2026-04-09
**Data**: SPY (16 alerts), ETH-USD (27 alerts), AMD (4 alerts)
**Priority**: High

## Fix 1: T1 Notify Dedup (QUICK WIN)
**Problem**: ETH got 3 identical T1 notifications ($2,243.74) in 3 minutes (02:15, 02:18, 02:18).
**File**: `analytics/intraday_rules.py` — the `_t1_notify` rule
**Fix**: Add dedup check — if T1 for this entry was already fired this session, skip. Check `was_alert_fired(symbol, "_t1_notify", session)` before firing.
**Impact**: Eliminates ~3 duplicate alerts per active trade per day.

## Fix 2: Zone Clustering (MEDIUM)
**Problem**: Same price zone gets 3 different alert types within minutes:
- ETH $2,250: double top + PDH rejection + hourly resistance rejection (3 alerts, 1 trade idea)
- SPY $677: double top + hourly resistance rejection (2 alerts, 1 trade idea)
**File**: `api/app/background/monitor.py` — the per-user evaluation loop
**Fix**: After firing a SHORT signal at a price level, suppress other SHORT signals within ±0.5% of that price for 30 minutes. Implement as a per-session, per-user "zone cooldown" dict: `{(symbol, "SHORT", price_bucket): last_fired_time}`.
**Impact**: Eliminates ~5 redundant alerts per day across symbols.

## Fix 3: Swing Watch Cooldown (QUICK WIN)
**Problem**: SPY got 5 "approaching 50MA" notices in 42 minutes (every poll cycle).
**File**: `analytics/intraday_rules.py` — the `swing_watch` rule
**Fix**: Swing watch notices should fire at most once per session per level. Add to the dedup set after first fire.
**Impact**: Eliminates ~4 duplicate notices per symbol per day.

## Fix 4: Weekly Trend Gate for BUY Alerts (HIGH IMPACT)
**Problem**: ETH fired 11 BUY alerts while in a massive weekly downtrend (below all weekly MAs, RSI 39). All those longs were counter-trend — most failed.
**File**: `api/app/background/monitor.py` — add weekly trend check before BUY evaluation
**Fix**: Before evaluating BUY rules for a symbol:
- Fetch weekly RSI and MA position
- If weekly RSI < 40 AND price below weekly MA20: demote BUY alerts to NOTICE with "⚠️ Counter-trend — weekly bearish" prefix
- SHORT alerts unaffected
- SPY gate already exists; this extends the concept per-symbol
**Impact**: Would have eliminated ~8 bad BUY signals on ETH today. Biggest quality improvement.

## Fix 5: Multi-Test Weakening (LOW)
**Problem**: ETH "session low bounce — tested 7x" was framed as bullish, but 7 tests means support is exhausting, not strengthening.
**File**: `analytics/intraday_rules.py` — session_low_bounce_vwap rule
**Fix**: If test_count > 3, add "⚠️ support weakening after {N} tests" to message and lower confidence from medium to low.
**Impact**: Better signal quality on 1-2 alerts per day.

## Fix 6: T1 Below Entry Bug (BUG FIX)
**Problem**: AMD weekly_high_breakout had T1=$222 on a LONG from $217. T1 must always be ABOVE entry for LONG.
**File**: `analytics/swing_rules.py` — `check_swing_weekly_high_breakout` or wherever T1 is calculated
**Fix**: Add validation: if direction=="BUY" and target_1 < entry, swap or recalculate using entry + (entry - stop) * R_multiple.
**Impact**: Fixes incorrect exit targets on swing alerts.

## Implementation Order
1. T1 notify dedup (Fix 1) — 10 min, biggest bang for buck
2. Swing watch cooldown (Fix 3) — 10 min
3. Zone clustering (Fix 2) — 30 min
4. Weekly trend gate (Fix 4) — 1 hour, highest impact on quality
5. Multi-test weakening (Fix 5) — 15 min
6. T1 below entry (Fix 6) — 15 min
