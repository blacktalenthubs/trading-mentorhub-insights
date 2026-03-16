# Alert Conviction Tuning — Research & Analysis

**Date:** 2026-03-14
**Goal:** Analyze which alerts are delivering value, which to disable, and how to capture more high-conviction entries (historical S/R, improved confidence scoring)

---

## 1. This Week's Alert Data (Mar 9-11)

### Volume by Alert Type
| Alert Type | Confidence | Count | Notes |
|---|---|---|---|
| first_hour_summary | info | 32 | Informational — keep |
| target_1_hit | — | 16 | Trade management |
| ma_resistance | — | 15 | SELL signal — working well |
| resistance_prior_high | medium | 13 | SELL warning — high conviction per user |
| **vwap_reclaim** | **medium** | **12** | **Low conviction per user** |
| ema_bounce_100 | medium | 10 | Working — user trusts |
| ema_resistance | — | 10 | SELL signal — useful |
| hourly_resistance_approach | — | 9 | Exit helper |
| auto_stop_out | high | 8 | Risk management |
| session_low_double_bottom | medium | 8 | Already capturing — user wants more |
| intraday_support_bounce | medium/high | 9 | User trusts these |
| ma_bounce_20/50/100 | high/medium | 10 | User's highest conviction |
| prior_day_low_reclaim | high | 4 | User's highest conviction |
| prior_day_high_breakout | medium | 4 | User trusts |
| weekly_high_resistance | — | 4 | User trusts weekly levels |
| pdh_retest_hold | medium/high | 7 | Useful |

### Win Rate Analysis (All-Time from DB)
| Alert Type | Conf | Total | T1 Hit | Stopped | Win% | Verdict |
|---|---|---|---|---|---|---|
| **intraday_support_bounce** | **high** | **4** | **4** | **0** | **100%** | **KEEP — best performer** |
| **pdh_retest_hold** | **high** | **4** | **4** | **0** | **100%** | **KEEP — excellent** |
| ema_bounce_50 | medium | 7 | 7 | 6 | 100% | Noisy — hits T1 but also stops |
| **vwap_reclaim** | **medium** | **30** | **25** | **9** | **83%** | **Surprisingly good T1 hit rate!** |
| intraday_support_bounce | medium | 22 | 16 | 14 | 73% | Good but gets stopped often |
| macd_histogram_flip | high | 3 | 2 | 0 | 67% | Small sample |
| ema_bounce_100 | medium | 42 | 22 | 30 | 52% | OK but high stop rate |
| session_low_double_bottom | medium | 23 | 12 | 9 | 52% | Decent |
| prior_day_low_reclaim | high | 8 | 4 | 0 | 50% | Good — never stopped |
| ma_bounce_100 | medium | 11 | 4 | 2 | 36% | Below average |
| planned_level_touch | medium | 17 | 5 | 7 | 29% | Poor |
| prior_day_high_breakout | medium | 8 | 2 | 6 | 25% | Poor — needs volume filter |
| prior_day_low_reclaim | medium | 8 | 2 | 4 | 25% | Medium conf underperforms |
| vwap_bounce | medium/high | 13 | 2 | 2 | 15% | Poor T1 hit rate |
| prior_day_low_bounce | medium | 9 | 0 | 4 | 0% | DISABLE candidate |
| ema_crossover_5_20 | medium | 5 | 0 | 5 | 0% | Already disabled |

---

## 2. Key Insights from Charts

### img.png — SPY Daily
- Price broke below 20MA and 50MA, trading near 100MA/200MA zone
- Clear downtrend with lower highs — explains why VWAP reclaims feel unreliable (overall market weakness)
- MA resistance (50MA) is acting as overhead — these SELL alerts are accurate

### img_1.png — Individual Stock Daily (appears bearish)
- Below all key MAs, heavy selling
- Prior day low reclaims in this context are counter-trend bounces — lower confidence justified

### img_2.png — NVDA Daily
- Bouncing off 200MA area — this is the kind of structural support the user trusts
- MA bounce alerts at major MAs (100, 200) are the highest conviction in weak markets

### img_3.png — SPY Weekly (zoomed out)
- Massive selloff from highs, breaking weekly structure
- Weekly levels (prior week high/low) are major decision points

### img_4.png — SPY Weekly (longer term)
- Shows recovery attempt from lows, with MAs as clear decision levels
- Historical support from months ago (consolidation zones) NOT currently tracked

---

## 3. User's Conviction Ranking

### HIGH conviction (keep and improve):
1. **MA/EMA resistance & support bounces** — especially 100MA, 200MA
2. **Prior day low reclaim** — especially on gap-down days (high conf = 50% win, never stopped)
3. **Prior day high rejection** — good for exits/profit-taking
4. **Weekly levels** — structural importance
5. **Session low double bottom** — 52% win, confirms reversals
6. **Intraday support bounce (strong)** — 100% win when high confidence

### LOW conviction (review/disable):
1. **VWAP bounce** — 15% T1 hit rate despite the concept being sound
2. **VWAP reclaim** — 83% T1 hit rate but user doesn't trust in weak markets
3. **Prior day low bounce** — 0% T1 hit rate, DISABLE
4. **Planned level touch** — 29% win rate, needs work

---

## 4. What's Missing — Historical S/R Gaps

### Currently Captured:
- Prior day high/low
- Prior week high/low
- Intraday swing lows (1H + 5min from last 5 days)
- Hourly swing high resistance
- MAs/EMAs (20, 50, 100, 200)
- VWAP
- Opening range

### NOT Captured (opportunities):
1. **Multi-day consolidation zones** — Price ranges where stock spent 3+ days (volume-weighted)
2. **Monthly high/low** — Like weekly but on monthly timeframe
3. **Pivot Points (classic/Camarilla)** — Widely used by institutions
4. **Volume Profile POC** — Point of Control from prior sessions
5. **Prior week's VWAP close** — Anchored VWAP from significant dates
6. **Failed breakout levels** — Where price broke above resistance but failed and fell back (now acts as stronger resistance)
7. **Gap levels** — Unfilled gap boundaries from previous sessions act as magnets
8. **Prior swing highs/lows (multi-week)** — 2-4 week swing structure

---

## 5. Recommendations

### Phase 1: Quick Wins (disable/tune)

| Action | Alert | Reason |
|---|---|---|
| **DISABLE** | `prior_day_low_bounce` | 0% win rate, 9 signals, 0 T1 hits |
| **DISABLE** | `vwap_bounce` | 15% T1 hit rate, user lacks conviction |
| **TUNE** | `vwap_reclaim` | 83% T1 hit but user skips — add SPY trend filter: only fire when SPY above 20MA or in recovery mode |
| **TUNE** | `planned_level_touch` | 29% win — tighten proximity from 0.5% to 0.3%, require volume confirmation |
| **TUNE** | `prior_day_high_breakout` | 25% win — require vol >= 1.5x (not 0.8x) to avoid false breakouts |

### Phase 2: Add Historical S/R Levels

| Feature | Implementation | Confidence Impact |
|---|---|---|
| **Prior month high/low** | Add to `prior_day` dict calculation in market_data, check in rules | Major structural levels |
| **Multi-week swing highs/lows** | Scan 20-day window for local maxima/minima (3-bar pivots) | Captures the levels user sees on daily/weekly charts |
| **Pivot Points (Classic)** | P = (H+L+C)/3, R1/S1/R2/S2 | Institutional reference levels |
| **Unfilled gap boundaries** | Track gap open/close from last 5 sessions | Price magnets |

### Phase 3: Context-Aware Confidence

| Improvement | How |
|---|---|
| **Market regime filter** | SPY below 20MA = "weak market" — boost MA bounce confidence (mean reversion), reduce breakout confidence |
| **Multi-timeframe confirmation** | If daily trend aligns with intraday signal = boost confidence |
| **Volume profile** | High volume at support level = stronger support = boost confidence |
| **Confluence scoring** | Signal near 2+ S/R levels simultaneously = boost confidence |

---

## 6. VWAP Deep Dive — Why Low Conviction?

The data tells an interesting story:
- **vwap_reclaim**: 83% T1 hit rate — objectively the best performer!
- **vwap_bounce**: 15% T1 hit rate — genuinely poor

The user's instinct about VWAP being low conviction likely comes from:
1. **Market context** — In a weak market (SPY below 20/50MA), VWAP reclaims are counter-trend bounces that feel risky even when they work
2. **VWAP bounce specifically** is failing — the "continuation" setup (60% of bars above VWAP, then pullback to VWAP) doesn't work when the broader trend is down
3. **Score quality** — Many VWAP reclaims scored 45-55 (C range) with CAUTION tags, signaling low conviction even when T1 was hit

**Recommendation:** Keep `vwap_reclaim` but gate it behind SPY regime (only fire when SPY is not in "bearish" regime OR when recovery is strong > 1.5% from low). Disable `vwap_bounce` entirely for now.