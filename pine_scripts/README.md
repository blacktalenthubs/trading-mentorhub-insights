# Pine Script alerts → /tv/webhook

Reference Pine Script alerts for the Phase 5a TradingView ingest endpoint.

These are **TradingView Pine Script v5** scripts. Each one defines an alert
condition and the JSON message template that TradingView POSTs to our
`/tv/webhook` endpoint when the condition fires.

Three indicators that we explicitly deferred from Python ports in earlier
phases (RSI divergence, MACD histogram flip, swing pivot break) — each one
would have been ~200+ LOC of Python; in Pine they're 30-50 LOC and use
TradingView's built-in indicator math.

## Setup once per script

1. Open the symbol's chart on TradingView (Premium tier required for
   webhook delivery).
2. Click **Pine Editor** at the bottom of the chart.
3. Paste the contents of one of the `.pine` files in this folder.
4. Click **Add to chart**.
5. Click the **Alerts** clock icon → **Create Alert**.
6. **Condition**: select the indicator and the alert label that the script
   defines (each script declares its own alertcondition() calls).
7. **Trigger**: `Once Per Bar Close`.
8. **Notifications → Webhook URL**:
   `https://YOUR-RAILWAY-APP.up.railway.app/tv/webhook`
9. **Message**: paste the JSON template printed at the top of the script
   file. Pine substitutes `{{ticker}}`, `{{exchange}}`, `{{interval}}`,
   `{{close}}`, `{{high}}`, `{{low}}`, `{{volume}}`, `{{timenow}}` at
   fire time. The `direction` field MUST be hardcoded per alert (LONG or
   SHORT) — pick the right side for the indicator.
10. Save.

## Schema the endpoint expects

```json
{
  "symbol": "{{ticker}}",
  "exchange": "{{exchange}}",
  "interval": "{{interval}}",
  "price": "{{close}}",
  "high": "{{high}}",
  "low": "{{low}}",
  "volume": "{{volume}}",
  "rule": "rsi_div_bullish_daily",
  "direction": "BUY",
  "fired_at": "{{timenow}}"
}
```

Required: `symbol`, `price`, `rule`, `direction`. Everything else is
informational (used by the structural targets pipeline + dedup).

## What each script provides

| File | Indicator | Direction | When it fires |
|------|-----------|-----------|---------------|
| `rsi_divergence_bullish.pine` | RSI(14) bullish divergence | BUY | Price makes a lower low while RSI makes a higher low (oversold reversal pattern) |
| `macd_histogram_flip.pine` | MACD(12,26,9) histogram | BUY/SHORT | Histogram crosses zero — momentum shift |
| `swing_pivot_break.pine` | Pivot high/low (5-bar lookback) | BUY/SHORT | Price breaks above a 5-bar swing high (BUY) or below a 5-bar swing low (SHORT) |

Each script gates by `Once Per Bar Close` so you get at most one alert per
closed bar. The endpoint adds level-based dedup (30-min window) on top of
that — same level firing twice is suppressed automatically.
