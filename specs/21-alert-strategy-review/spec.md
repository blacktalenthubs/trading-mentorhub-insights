# Alert Strategy Review — Audit & Gap Analysis

**Status**: Research Complete
**Created**: 2026-04-08
**Author**: AI-assisted

## Current State: 78 Strategies Across 10 Categories

| Category | Count | Examples |
|----------|-------|---------|
| Bounces (support entries) | 14 | MA bounce 20/50/100/200, EMA bounce 20/50/100/200, PDL reclaim, PDL bounce, intraday support bounce, session low bounce VWAP |
| Breakouts (continuation) | 8 | PDH breakout, PDH retest hold, inside day breakout, outside day breakout, weekly high breakout, opening range breakout, first hour high breakout, consolidation breakout |
| Reversals (pivot entries) | 5 | Multi-day double bottom, fib retracement bounce, gap fill, morning low retest, seller exhaustion |
| Shorts (breakdown entries) | 8 | PDH failed breakout, EMA rejection short, intraday EMA rejection short, session high double top, hourly resistance rejection short, opening range breakdown, 15m consolidation breakdown |
| Technical (advanced) | 4 | MACD crossover, BB squeeze breakout, gap-and-go, VWAP bounce |
| Swing (daily timeframe) | 7 | EMA crossover 5/20, 200MA reclaim, pullback 20EMA, RSI 30 bounce, 200MA hold, 50MA hold, weekly support |
| Management/Exit | 6 | Stop loss hit, T1 hit, T2 hit, resistance prior high, MA resistance, EMA resistance |
| Informational | 8 | VWAP loss, VWAP reclaim, session low double bottom, PDH rejection, hourly resistance approach, morning low breakdown, inside day forming, resistance prior low |
| Gap management | 2 | Gap fill, gap-and-go |
| 15m consolidation | 2 | 15m breakout long, 15m breakdown short |

## Identified Gaps & Issues

### Gap 1: Session Low Bounce Fires Too Late
**Problem**: Required 3-bar hold + 0.3% recovery. LRCX held $241 but alert fired at $245.
**Fixed**: Reduced to 1-bar hold, no recovery % requirement. Still needs 2x test count.
**Remaining concern**: Entry price is current close (after bounce started), not the support level itself. Consider using the support level as entry instead.

### Gap 2: Targets Are Fixed R:R, Not Structural
**Problem**: Most strategies use T1 = Entry + 1R, T2 = Entry + 2R. These are arbitrary math, not real chart levels.
**Better approach**: Use structural targets — next resistance level, VWAP, prior day high, weekly high. The system already has these levels computed. Some strategies (session_low_bounce_vwap) already use VWAP as T1 — this should be the standard.

### Gap 3: No VWAP Reclaim Entry
**Problem**: VWAP reclaim is a NOTICE (informational), not a BUY entry. When price drops below VWAP then reclaims above it, that's an actionable momentum shift. Many traders use VWAP reclaim as their primary entry signal.
**Recommendation**: Add `vwap_reclaim_entry` — BUY when price closes above VWAP after being below for 3+ bars. Entry = VWAP, Stop = session low, T1 = prior high.

### Gap 4: No Pre-Market Level Entries
**Problem**: Pre-market high/low are key intraday levels but no rules use them. Gap-and-go is the only pre-market-aware rule. Traders watch for:
- Pre-market high breakout (continuation of overnight strength)
- Pre-market low reclaim (failed breakdown)
**Recommendation**: Add pre-market level entries using existing `fetch_premarket_bars()` data.

### Gap 5: Duplicate MA/EMA Strategies
**Problem**: 8 nearly identical bounce strategies (MA20/50/100/200 + EMA20/50/100/200). Each has the same logic with different MA values. This creates duplicate alerts when price is near both MA and EMA of the same period.
**Recommendation**: Consolidate to one function with parameter: `check_ma_bounce(period, use_ema)`. Dedup: if MA20 and EMA20 are within 0.2% of each other, fire only once.

### Gap 6: No Volume Breakout Confirmation
**Problem**: Several breakout strategies don't require volume. PDH breakout requires 0.8x (below average!). Real breakouts need above-average volume.
**Recommendation**: Increase volume requirement for breakouts to 1.2x average minimum. Add volume as a score factor — 2x volume = high confidence.

### Gap 7: Swing Entries Only at EOD
**Problem**: Swing entries only fire at 3:30 PM (EOD scan). If AAPL holds the 200MA at 10 AM, the user doesn't know until afternoon.
**Fixed**: Swing watch was intended to handle this but was too noisy (disabled). 
**Better approach**: Run swing scan at 2 checkpoints — 11:00 AM (morning confirmation) and 3:30 PM (EOD confirmation). Morning scan is "watch" level, EOD is "confirmed entry."

### Gap 8: Stop Logic Too Tight on Volatile Stocks
**Problem**: MA bounce stop = 0.5% below MA. For a $250 stock like AAPL, that's $1.25 stop. One wick triggers it. For NVDA at $178, the stop is $0.89 — way too tight.
**Recommendation**: Use ATR-based stops instead of fixed percentage. Stop = MA - (1.5 × ATR). This adapts to each stock's volatility.

### Gap 9: No Time-of-Day Weighting
**Problem**: Same alert at 9:35 AM (volatile open) and 1:30 PM (lunch chop) and 3:45 PM (power hour) all have equal weight. But historically, 10-11 AM and 3-4 PM have the highest win rates.
**Recommendation**: Add time-of-day factor to score. The Performance Breakdown feature already tracks win rate by hour — use that data to boost/demote confidence.

### Gap 10: No Sector Correlation
**Problem**: Alerts fire independently per symbol. If XLK (tech sector) is -2% and the system fires a BUY on NVDA (tech stock), that's fighting the sector trend.
**Recommendation**: Use the new Sector Rotation data to add a sector alignment factor. If the symbol's sector is in outflow, demote BUY confidence.

## Priority Ranking

| Priority | Gap | Impact | Effort |
|----------|-----|--------|--------|
| 1 | Structural targets (Gap 2) | High — better exits = more profit | Medium |
| 2 | VWAP reclaim entry (Gap 3) | High — most-requested setup | Low |
| 3 | ATR-based stops (Gap 8) | High — fewer false stop-outs | Medium |
| 4 | Time-of-day weighting (Gap 9) | Medium — better signal quality | Low |
| 5 | Sector correlation (Gap 10) | Medium — context-aware signals | Low |
| 6 | Pre-market levels (Gap 4) | Medium — captures opening plays | Medium |
| 7 | MA/EMA dedup (Gap 5) | Low — reduces noise | Low |
| 8 | Volume breakout (Gap 6) | Low — already decent | Low |
| 9 | Morning swing check (Gap 7) | Low — needs careful dedup | Medium |
| 10 | Entry at support price (Gap 1) | Low — minor improvement | Low |

## Recommendations: Next 3 Actions

### Action 1: Structural Targets
Replace fixed R:R targets with structural levels. For every BUY alert:
- T1 = nearest overhead resistance (VWAP, prior high, MA above)
- T2 = next resistance after T1
- Stop = below the support level that triggered the entry

### Action 2: VWAP Reclaim Entry
Add new BUY entry: price closes above VWAP after being below for 3+ bars. This is the #1 mean-reversion setup institutional traders use. Entry = VWAP, Stop = session low, T1 = prior high.

### Action 3: ATR-Based Stops
Replace fixed % stops with volatility-adjusted stops. Stop = support level - (1.5 × ATR14). A volatile stock gets a wider stop, a calm stock gets a tighter one. Fewer false stop-outs, same risk management.

## Data Needed to Validate

Once we have 1 week of ad campaign data (spec 18), analyze:
- Win rate by strategy type (Performance Breakdown already tracks this)
- Average time to T1/T2 per strategy
- False stop-out rate per strategy
- Best/worst performing hour by strategy
- Sector alignment impact on win rate

This data will tell us which strategies to keep, tune, or remove.
