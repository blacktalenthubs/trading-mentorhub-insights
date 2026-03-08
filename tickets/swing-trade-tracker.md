# Swing Trade Tracker — Daily EOD Scanner with RSI Zones & Burns-Style Setups

## Problem Statement

The current alerting system is entirely intraday (5m bars, 3-minute polling). There is no daily-timeframe swing trade detection. Veteran traders like Steve Burns use daily MAs + RSI to enter multi-day positions with defined exits. We need a separate swing trade scanner that:

1. Only activates when SPY is trending (above 20 EMA)
2. Detects RSI approach zones (nearing 30/70) as early warnings
3. Generates Burns-style swing setups: MA-based entries/stops, RSI-based profit targets
4. Runs EOD (not intraday) since swing trades use daily bars

## Why It Matters

- Intraday alerts are noise in choppy markets — swing trades thrive in trending markets
- RSI is already computed (`compute_rsi_wilder`) but only used as a confidence modifier — it should fire its own alerts
- Burns' approach (30+ years experience) gives us a proven framework: MA crossover entry, MA cross-under stop, 70-RSI exit

## Acceptance Criteria

- [ ] SPY regime gate: swing alerts only fire when SPY close > 20 EMA
- [ ] RSI zone notices fire for watchlist symbols at 4 thresholds (30, 35, 65, 70)
- [ ] Burns-style swing setups detected: EMA 5/20 crossover, price reclaiming 200 MA
- [ ] EOD scan runs once daily after market close (4:15 PM ET)
- [ ] New Streamlit page shows active swing setups, RSI heatmap, regime status
- [ ] Alerts stored with `swing_` prefix types, separate from intraday alerts

## Feature Details

### 1. SPY Regime Gate

```
SPY Trending = SPY close > 20-day EMA
Optional secondary filter: VIX close < 25
```

When SPY is NOT trending, swing alerts are suppressed. A NOTICE alert fires:
> "Swing scanner paused — SPY below 20 EMA (bearish regime)"

### 2. RSI Zone Alerts

| RSI Level | Zone | Direction | Alert Type |
|-----------|------|-----------|------------|
| Crosses below 35 | Approaching oversold | NOTICE | `swing_rsi_approaching_oversold` |
| Crosses below 30 | Oversold | BUY watchlist | `swing_rsi_oversold` |
| Crosses above 65 | Approaching overbought | NOTICE | `swing_rsi_approaching_overbought` |
| Crosses above 70 | Overbought (exit signal) | SELL | `swing_rsi_overbought` |

**Important:** These are *crossover* alerts, not static level alerts. RSI must cross the threshold today vs. yesterday to fire. Requires RSI series (last 2+ values), not just a single scalar.

### 3. Burns-Style Swing Setups

**Setup A — EMA 5/20 Bullish Crossover:**
- Trigger: Daily EMA5 crosses above EMA20 (yesterday below, today above)
- Entry: Current close
- Stop: Bearish EMA 5/20 cross-under (dynamic, checked daily)
- Target: RSI reaches 70
- Alert type: `swing_ema_crossover_5_20`

**Setup B — 200 MA Reclaim:**
- Trigger: Close crosses back above 200-day MA AND above 10-day EMA
- Entry: Current close
- Stop: Close below 200-day MA
- Target: RSI reaches 70
- Alert type: `swing_200ma_reclaim`

**Setup C — Pullback to Rising 20 EMA:**
- Trigger: Close touches/near 20 EMA (within 0.5%) while 20 EMA is rising (today > 5 days ago)
- Entry: Current close
- Stop: Close below 20 EMA
- Target: RSI reaches 70
- Alert type: `swing_pullback_20ema`

### 4. Active Swing Trade Tracking

Once a swing setup fires, track it in a `swing_trades` table:
- Monitor stop condition daily (MA cross-under or close below MA)
- Monitor target condition daily (RSI >= 70)
- Fire `swing_target_hit` or `swing_stopped_out` when conditions met
- Calculate P&L on close

### 5. Swing Trade Categories (Burns Watchlist Style)

Categorize each watchlist symbol nightly:

| Category | Criteria |
|----------|----------|
| **Buy Zone** | Active swing setup fired, entry within 1% of current price |
| **Strongest** | Above all short-term MAs (5, 10, 20 EMA), RSI 50-65 |
| **Building Base** | Consolidating near 50 MA, RSI 40-55, narrowing range (ATR declining) |
| **Overbought** | RSI > 65, extended above 20 EMA by >3% |
| **Weak** | Below 20 EMA or RSI < 40 |

## Technical Notes

### What exists today
- `compute_rsi_wilder()` in `analytics/intraday_data.py` — returns single float, needs a series variant
- `fetch_prior_day()` — already fetches 1y daily bars and computes MA20/50/100/200, EMA20/50
- `get_spy_context()` — already has SPY MAs and RSI
- RSI thresholds in `alert_config.py`: `SYM_RSI_OVERSOLD=35`, `SYM_RSI_OVERBOUGHT=70`
- EMA5 exists only on 15m timeframe (`check_mtf_alignment`), not daily

### What needs to be added
- `compute_rsi_series()` — return last N RSI values (not just scalar) for crossover detection
- Daily EMA5, EMA10 computation in `fetch_prior_day()`
- EOD scheduler job (run at ~4:15 PM ET, separate from 3-minute intraday poll)
- New `AlertType` entries with `swing_` prefix
- `swing_trades` DB table for position tracking
- New Streamlit page (page 10)

### New files
| File | Purpose |
|------|---------|
| `analytics/swing_rules.py` | Swing trade rule evaluation (daily bars) |
| `alerting/swing_scanner.py` | EOD orchestrator — fetch data, check regime, run rules |
| `pages/10_Swing_Trades.py` | UI — active setups, RSI heatmap, regime status, categories |

### Modified files
| File | Change |
|------|--------|
| `analytics/intraday_data.py` | Add `compute_rsi_series()`, add daily EMA5/EMA10 to `fetch_prior_day()` |
| `alert_config.py` | Add swing thresholds, RSI zone levels |
| `db.py` | Add `swing_trades` table |
| `alerting/alert_store.py` | Add swing alert storage/retrieval functions |
| `monitor_thread.py` | Add daily EOD trigger alongside intraday poll |
