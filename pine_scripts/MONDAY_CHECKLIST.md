# Monday morning checklist — TradingView PDH/PDL system

> First-time setup for the PDH/PDL + Sweep + Daily Bias indicators.
> Allow ~30 min total. Do this once, then Tuesday onwards is just "open TV."

## What's already done

- ✅ TradingView MCP server installed (`~/tradingview-mcp-jackson`)
- ✅ Webhook live: `https://worker-production-f56f.up.railway.app/tv/webhook`
- ✅ Webhook → Telegram delivery proven (alert id 10 in DB, Telegram landed)
- ✅ Pine scripts committed: `pine_scripts/prior_day_levels.pine`, `pine_scripts/daily_ema_bias.pine`
- ✅ PDH/PDL indicator already loaded on SPY 1H

## 1. 8:00 ET — Open TradingView

If TV isn't running with CDP enabled, restart via Claude:

```
"run tv_launch with kill_existing=true"
```

Verify with `tv_health_check`. Should show `cdp_connected: true`.

## 2. 8:05 ET — Add Daily Bias + Daily MA Bounce indicators (one-time)

Two scripts to add as **separate** Pine slots (not overwriting the PDH/PDL one).

### 2a. Daily EMA Bias Score

1. Open Pine Editor in TV (bottom panel → "Pine")
2. Click **the small ▼ next to "Save"** at top of editor → **"New blank indicator"**
   - This creates a *separate* script slot — critical, do not skip the dropdown
3. Open `pine_scripts/daily_ema_bias.pine` in your text editor → copy all
4. Paste into the new Pine Editor tab
5. Click **Save** (Cmd+S)
6. Click **Add to chart**
7. Repeat 6 for each watchlist symbol (SPY, QQQ, NVDA, MSFT, META, AMD, TSLA, MSTR)
   - You can drag the indicator off the indicator panel onto another chart's pane to copy faster

Result: each chart shows daily EMA stack + a colored badge (A+ BULL / BULL / NEUTRAL / BEAR / A+ BEAR / score 0-7).

### 2b. Daily MA Bounce (visual-only V1)

Same procedure with `pine_scripts/daily_ma_bounce.pine`. New blank indicator → paste → save → add to chart.

You'll see 8 horizontal-ish daily MA lines (8/21/50/100/200 EMA + 50/100/200 SMA) plus historical BOUNCE/REJECT labels showing where price bounced off each level today and prior days.

**No alerts wired** — this is observation-only this week. After watching the signals fire during live trading, we'll add `alert()` calls for the MA bounces that prove tradeable.

## 3. 8:15 ET — Create TV alerts (the actual "deploy")

Recommended Monday-morning scope: **SWEEP+ alerts only** on CORE watchlist. 8 alerts total. ~10 min.

Why just SWEEP+ to start? They're the highest-conviction LONG signals (sweep + reclaim of PDL). False positive rate is the lowest of all 6 rules. You can add more rule types after you trust the system.

### For each of (SPY, QQQ, NVDA, MSFT, META, AMD, TSLA, MSTR):

1. Open the symbol's chart, set timeframe to **1H**
2. Press `Alt+A` (or click "Alert" in the top toolbar)
3. **Condition tab**:
   - First dropdown → `Prior Day Levels (PDH/PDL)`
   - Second dropdown → `SWEEP+ HC LONG`
   - Operator → `Greater than`
   - Value → `0`
   - Trigger → `Once Per Bar` (NOT "Once Per Bar Close" — that's the bug we fixed)
   - Expiration → `Open-ended`
   - Alert name → `PDH/PDL SWEEP+ · {SYMBOL} 1H`
4. **Notifications tab**:
   - Webhook URL: ✅ ON
   - URL: `https://worker-production-f56f.up.railway.app/tv/webhook`
5. **Message tab**: paste exactly:

```
{"symbol": "{{ticker}}", "exchange": "{{exchange}}", "interval": "{{interval}}", "price": "{{close}}", "high": "{{high}}", "low": "{{low}}", "volume": "{{volume}}", "rule": "pdl_sweep_reclaim", "direction": "BUY", "fired_at": "{{timenow}}"}
```

6. Click **Create**
7. Repeat for next symbol

After all 8 are created, your alert panel (right sidebar) should show 8 active SWEEP+ alerts.

### Optional: add SWEEP- (high-conviction SHORT)

Same flow but:
- Second dropdown → `SWEEP- HC SHORT`
- Message JSON: change `"rule": "pdh_sweep_reversal"` and `"direction": "SHORT"`

## 4. 9:00 ET — Pre-market scan

1. Open each CORE watchlist chart at 1H
2. Glance at the Daily Bias badge (top-right of each chart)
3. Filter: only consider longs on charts where bias is **BULL** or **A+ BULL**
4. Filter: only consider shorts where bias is **BEAR** or **A+ BEAR**
5. Skip NEUTRAL — chop day, no edge

This is your `decision_hierarchy` from `rules.json` made visible:
> "Daily chart says YES → 4H confirms → 1H gives entry timing"

## 5. 9:30–9:45 ET — Observe only

Per your `rules.json`: no trades in the first 15 minutes. Watch how price interacts with PDH/PDL on each chart. Take screenshots if something looks like it's setting up.

## 6. 9:45 ET — Live

When a SWEEP+ fires:

1. **Telegram lands** with: symbol, price, rule, direction
2. **Check chart**: confirm bias (BULL/A+ BULL on daily badge)
3. **If yes**: place limit order at PDL level (Model B from your strategy doc) with stop just below sweep wick low
4. **If no** (bias bearish/neutral): skip. Counter-trend with low conviction.

Apply `risk_rules` from `rules.json`:
- 1% risk per trade
- Stop set in platform before entry
- Min 1:2 R:R, prefer 1:3
- Max 3 concurrent positions

## 7. End of day

Check Telegram alert history. Note:
- How many SWEEP+ fired today?
- How many were tradeable (passed bias filter)?
- How many were profitable?

This gives baseline for evaluating signal quality after week 1.

## Troubleshooting

| Issue | Fix |
|---|---|
| Telegram alert doesn't arrive | Check Railway worker is running. `curl -X POST` test from earlier still works. |
| Alert fires but no Telegram | Webhook returned 4xx — check the JSON message format (must be valid JSON, no trailing commas) |
| Alert fires too often | Trigger is "Once Per Bar Close" instead of "Once Per Bar" — recreate alert |
| Indicator missing on a chart | Re-add via the indicator panel — it's saved in your TV scripts list |
| Daily Bias badge not showing | Indicator added to wrong chart. Right-click indicator → settings → "Show bias score badge" |

## Known issues (deferred for this week)

- TV alert dialog doesn't show "Any alert() function call" option (TV quirk) — that's why we use the plot-based alert with hardcoded JSON
- Telegram message format doesn't yet show "suggested limit at level" — coming this week
- No bulk alert creation automation yet — manual setup tonight, automation possible after we work around the alert() registration issue

## What's next on the roadmap

Build order, after this week of live testing:
1. **Compression-at-level pre-break detector** — alert when price compresses near PDL (Wyckoff spring setup)
2. **Volume profile pillar** — POC/VAH/VAL levels alongside PDH/PDL
3. **Server-side bias gating** — webhook handler checks daily EMA score before forwarding to Telegram (auto-filters counter-trend signals)
4. **Bulk alert creation script** — once we figure out the TV dropdown issue
