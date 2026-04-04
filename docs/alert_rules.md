# Alert Rules Reference

Complete inventory of all alert types in `analytics/intraday_rules.py`.

Source of truth: `AlertType` enum (line 106) and `ENABLED_RULES` in `alert_config.py`.

---

## BUY Rules (24)

| # | AlertType | Check Function | Trigger | Key Thresholds | Enabled |
|---|-----------|----------------|---------|----------------|---------|
| 1 | `ma_bounce_20` | `check_ma_bounce_20()` | Price pulls back to 20MA and bounces | proximity=0.3%, stop=0.5% below MA | Yes |
| 2 | `ma_bounce_50` | `check_ma_bounce_50()` | Price pulls back to 50MA and bounces | proximity=0.3%, stop=0.5% below MA | Yes |
| 3 | `ma_bounce_100` | `check_ma_bounce_100()` | Price pulls back to 100MA and bounces | proximity=0.5%, stop=0.7% below MA | Yes |
| 4 | `ma_bounce_200` | `check_ma_bounce_200()` | Price pulls back to 200MA and bounces — institutional level | proximity=0.8%, stop=1.0% below MA | Yes |
| 5 | `ema_bounce_20` | `check_ema_bounce_20()` | Price pulls back to EMA20 and bounces | Same as MA20 | Yes |
| 6 | `ema_bounce_50` | `check_ema_bounce_50()` | Price pulls back to EMA50 and bounces | Same as MA50 | Yes |
| 7 | `ema_bounce_100` | `check_ema_bounce_100()` | Price pulls back to EMA100 and bounces | Same as MA100 | Yes |
| 8 | `ema_bounce_200` | `check_ema_bounce_200()` | Price pulls back to EMA200 and bounces — major level | Same as MA200 | Yes |
| 9 | `prior_day_low_reclaim` | `check_prior_day_low_reclaim()` | Price dips below PDL then reclaims above it | dip_min=0.03%, max_distance=0.8%, stop=0.5% below PDL | Yes |
| 10 | `prior_day_low_bounce` | `check_prior_day_low_bounce()` | Price approaches PDL and holds above (no break) | proximity=0.5%, hold_bars=2, stop=0.5% below PDL | Yes |
| 11 | `prior_day_high_breakout` | `check_prior_day_high_breakout()` | Price breaks above PDH with volume | volume_ratio=1.2x | Yes |
| 12 | `inside_day_breakout` | `check_inside_day_breakout()` | Price breaks above inside day high | — | Yes |
| 13 | `inside_day_reclaim` | `check_inside_day_reclaim()` | Price dips below inside day low then reclaims | dip_min=0.03% | Yes |
| 14 | `outside_day_breakout` | `check_outside_day_breakout()` | Price breaks above bullish outside day high | Requires bullish outside day pattern | **No** |
| 15 | `weekly_level_touch` | `check_weekly_level_touch()` | Price touches prior week low and bounces | proximity=0.4%, stop=0.5% below | Yes |
| 16 | `weekly_high_breakout` | `check_weekly_high_breakout()` | Price breaks above prior week high with volume | volume confirmation | Yes |
| 17 | `vwap_reclaim` | `check_vwap_reclaim()` | Price reclaims VWAP from below — morning reversal | morning_bars=12 (60min), recovery=0.5%, volume=1.2x | Yes |
| 18 | `vwap_bounce` | `check_vwap_bounce()` | Price trending above VWAP pulls back to test and holds | min_bars=18 (~90min), above_pct=60%, touch=0.3% | Yes |
| 19 | `opening_low_base` | `check_opening_low_base()` | Session low set in first 15 min, price bases above it | window=3 bars, hold=3 bars, dip=0.3% | Yes |
| 20 | `intraday_support_bounce` | `check_intraday_support_bounce()` | Price bounces off held intraday support level | lookback=6, proximity=0.3%, max_distance=1.0% | Yes |
| 21 | `session_low_double_bottom` | `check_session_low_retest()` | Session low tested twice (double bottom) with recovery | proximity=0.3%, min_age=4 bars, recovery=0.3% | Yes |
| 22 | `opening_range_breakout` | `check_opening_range_breakout()` | Price breaks above 30-min opening range with volume | min_range=0.3%, volume=1.2x | **No** |
| 23 | `planned_level_touch` | `check_planned_level_touch()` | Price touches Scanner daily plan levels and bounces | proximity=0.3% | Yes |
| 24 | `ema_crossover_5_20` | `check_ema_crossover_5_20()` | Daily 5 EMA crosses above 20 EMA | min_bars=25, separation=0.05% | **No** |

---

## SELL Rules (13)

| # | AlertType | Check Function | Trigger | Enabled |
|---|-----------|----------------|---------|---------|
| 25 | `resistance_prior_high` | `check_resistance_prior_high()` | Price hits prior day high — take profits | Yes |
| 26 | `ma_resistance` | `check_ma_resistance()` | Price rejected at overhead MA | Yes |
| 27 | `ema_resistance` | `check_ema_resistance()` | Price rejected at overhead EMA | Yes |
| 28 | `resistance_prior_low` | `check_resistance_prior_low()` | Price rejected at PDL from below | Yes |
| 29 | `weekly_high_resistance` | `check_weekly_high_resistance()` | Price approaches prior week high — resistance | Yes |
| 30 | `inside_day_breakdown` | `check_inside_day_breakdown()` | Price breaks below inside day low | Yes |
| 31 | `opening_range_breakdown` | `check_orb_breakdown()` | Price breaks below opening range with volume | **No** |
| 32 | `support_breakdown` | `check_support_breakdown()` | Support broken with high volume + conviction close | **No** |
| 33 | `hourly_resistance_approach` | `check_hourly_resistance_approach()` | Active trade approaching hourly swing resistance | **No** |
| 34 | `target_1_hit` | `check_target_1_hit()` | Price reaches Target 1 (1R) | **No** |
| 35 | `target_2_hit` | `check_target_2_hit()` | Price reaches Target 2 (2R) | **No** |
| 36 | `stop_loss_hit` | `check_stop_loss_hit()` | Price hits stop loss level | **No** |
| 37 | `auto_stop_out` | `check_auto_stop_out()` | Prior BUY entry's stop breached — exit now | **No** |

---

## INFO Rules (2)

| # | AlertType | Check Function | Trigger | Enabled |
|---|-----------|----------------|---------|---------|
| 38 | `first_hour_summary` | `check_first_hour_summary()` | Summary after first hour closes | Yes |
| 39 | `gap_fill` | `check_gap_fill()` | Gap fully fills — informational | **No** |

---

## Post-Processing Filters

Applied in `evaluate_rules()` after all individual checks fire. Order matters.

### 1. Breakdown Day Suppression

If `support_breakdown` fires, **all BUY signals are dropped** for that symbol on that bar.

### 2. Dedup Filter

Signals already in `fired_today` set (keyed by `(symbol, alert_type)`) are removed. Each alert type fires at most once per symbol per session.

### 3. Noise Filter (Low Volume)

| Condition | Action |
|-----------|--------|
| Volume ratio < 0.4x average | Drop all BUY signals on that bar |

Config: `LOW_VOLUME_SKIP_RATIO = 0.4`

### 4. Staleness Filter (Price Ran Past Entry)

Drops BUY signals where current price > entry + 1R (risk). The signal is "stale" — the move already happened.

**Exempt alert types** (price running confirms their thesis):
- Breakouts: `prior_day_high_breakout`, `inside_day_breakout`, `outside_day_breakout`, `weekly_high_breakout`, `opening_range_breakout`
- Deep levels: `ma_bounce_100`, `ma_bounce_200`, `ema_bounce_100`, `ema_bounce_200`
- PDL: `prior_day_low_reclaim`, `prior_day_low_bounce`

### 5. Overhead MA Resistance Filter

Drops BUY signals when a major MA sits within 0.5% above the entry price — heading into resistance.

Config: `OVERHEAD_MA_RESISTANCE_PCT = 0.005`

**Exempt alert types** (the MA is the level being tested, or nearby MA is a target):
- `ma_bounce_100`, `ma_bounce_200`, `ema_bounce_100`, `ema_bounce_200`
- `prior_day_low_reclaim`, `prior_day_low_bounce`

---

## Context Enrichment

Before post-processing, `evaluate_rules()` enriches each signal with:

| Context | Source | What it adds |
|---------|--------|-------------|
| Session phase | `get_session_phase()` | Opening range, mid-session, power hour, etc. |
| VWAP position | `compute_vwap()` | "above VWAP" (bullish) or "below VWAP" (caution) |
| Gap context | `classify_gap()` | Gap up/down type and percentage |
| Volume label | `_volume_label()` | Volume vs average classification |
| SPY context | `spy_context` dict | SPY trend, regime, bounce correlation |
| Caution notes | SPY trend + regime + session | Appended as `CAUTION:` suffix on BUY signals |

---

## Execution Flow

```
worker.py poll loop (every 2 min during market hours)
  │
  ├─ For each symbol in watchlist:
  │    │
  │    ├─ Fetch 5-min intraday bars (yfinance)
  │    ├─ Fetch prior day context (close, high, low, MAs, EMAs)
  │    ├─ Fetch active entries, daily plan, SPY context
  │    │
  │    ├─ evaluate_rules()
  │    │    ├─ Compute context: VWAP, gap, volume, opening range, MTF
  │    │    ├─ Detect intraday supports (5m swing lows + hourly levels)
  │    │    │
  │    │    ├─ BUY rules (if not cooled down)
  │    │    │    └─ Each rule checks ENABLED_RULES before running
  │    │    ├─ INFO rules (gap fill, first hour summary)
  │    │    ├─ SELL rules (always fire)
  │    │    │    ├─ Resistance checks (PDH, MA, EMA, weekly)
  │    │    │    ├─ Target/stop hits (per active entry)
  │    │    │    └─ Support breakdown (EXIT LONG if active position)
  │    │    │
  │    │    ├─ Post-processing filters:
  │    │    │    ├─ Breakdown day suppression
  │    │    │    ├─ Dedup (fired_today)
  │    │    │    ├─ Noise (volume < 0.4x)
  │    │    │    ├─ Staleness (price > entry + 1R)
  │    │    │    └─ Overhead MA resistance (MA within 0.5% above)
  │    │    │
  │    │    └─ Return filtered signals
  │    │
  │    ├─ Dedup check: was_alert_fired() in DB
  │    ├─ Cooldown check: is_symbol_cooled_down()
  │    ├─ record_alert() → DB
  │    └─ notify() → Telegram + Email
  │
  └─ Sleep until next poll
```

---

## Cooldown System

After a `stop_loss_hit` or `auto_stop_out` fires, BUY signals for that symbol are suppressed for 30 minutes.

Config: `COOLDOWN_MINUTES = 30`

This prevents chasing re-entries immediately after a failed trade.

---

## Scoring & Notification Tiers

| Score Range | Grade | Telegram? |
|-------------|-------|-----------|
| >= 65 | A+ / A | Yes (Tier 1) |
| 50-64 | B | Email only |
| < 50 | C | Email only |

Config: `TELEGRAM_TIER1_MIN_SCORE = 65`

Free tier users: max 3 push notifications/day (`FREE_DAILY_ALERT_LIMIT = 3`).

---

## Disabled Rules — Rationale

| Rule | Why Disabled |
|------|-------------|
| `outside_day_breakout` | Breakout-based, noisy in choppy markets |
| `ema_crossover_5_20` | Momentum signal, too many false positives intraday |
| `opening_range_breakout` | Breakout-based, disabled during Phase 1 validation |
| `opening_range_breakdown` | Sell-side breakout, disabled during Phase 1 |
| `gap_fill` | Informational noise — not actionable |
| `support_breakdown` | Choppy-day noise |
| `hourly_resistance_approach` | Disabled during Phase 1 |
| `target_1_hit` | Targets/stops from stored entries can be inaccurate |
| `target_2_hit` | Same — rely on core S/R alerts for exits instead |
| `stop_loss_hit` | Same — Phase 1 prioritizes S/R accuracy |
| `auto_stop_out` | Same — deferred until entry tracking is validated |

---

## Swing Rules (separate from intraday)

The `AlertType` enum also includes swing-timeframe rules. These are **not** evaluated by `evaluate_rules()` — they run on a separate daily cadence.

| AlertType | Purpose |
|-----------|---------|
| `swing_rsi_approaching_oversold` | RSI approaching 35 |
| `swing_rsi_oversold` | RSI below 30 |
| `swing_rsi_approaching_overbought` | RSI approaching 65 |
| `swing_rsi_overbought` | RSI above 70 |
| `swing_ema_crossover_5_20` | Daily 5/20 EMA crossover |
| `swing_200ma_reclaim` | Price reclaims 200MA on daily chart |
| `swing_pullback_20ema` | Pullback to rising 20 EMA |
| `swing_target_hit` | Swing trade target reached |
| `swing_stopped_out` | Swing trade stopped out |
