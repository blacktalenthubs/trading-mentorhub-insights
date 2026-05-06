# Pine Scripts → /tv/webhook

TradingView Pine v5 scripts that fire alerts to the `/tv/webhook` endpoint.
Backend handles dedup, structural targets, Telegram delivery.

## Folder layout

```
pine_scripts/
├── active/      ← what's running on TV right now
├── archive/     ← superseded scripts, experiments, old logs
└── README.md    ← this file
```

## Active scripts

| File | TV indicator name | Purpose |
|------|-------------------|---------|
| `active/daily_ma_bounce_v3.pine` | `ma-levels-daily` | 8 daily MAs (EMA 8/21/50/100/200, SMA 50/100/200) — bounce / reclaim / rejection / lose / proximity NOTICE |
| `active/prior_day_levels_staged_v2.pine` | `pdl-pdh-vwap` | PDH/PDL break/reclaim/reject/sweep + VWAP NOTICE |

Both use `alert.freq_once_per_bar_close`. Spam control is split:

- **Pine**: one alert per bar close (no intra-bar refire)
- **Backend**: identity dedup on `(user, symbol, direction, alert_type+ma_tag)` with 60-min window

## Archive

Anything in `archive/` is **not** wired to TV. Kept for reference / git
history. Includes:

- earlier versions of v3 (`daily_ma_bounce.pine`, `_bold.pine`, `_bold_v2.pine`)
- predecessors merged into v3 (`daily_ma_reclaim_15m.pine`)
- predecessors merged into staged_v2 (`prior_day_levels.pine`, `prior_day_levels_staged.pine`)
- experiments not in current alert set (RSI, MACD, swing pivot, EMA5 trail, EMA bias scorecard)
- the rejected 5/9 EMA approach (`daily_ma_bounce_5ema.pine`) — Scott Redler framework is 8/21/50/100/200, not 5/9
- old setup docs (`MONDAY_CHECKLIST.md`, `staging_study_guide.html`)
- alert log CSVs

If we resurrect anything from archive, move it back to `active/` and add it
to the table above.

## Adding a new alert in TradingView

1. Open the chart, paste the script from `active/` into Pine Editor, "Add to chart".
2. Right-click the indicator → "Add alert on …".
3. **Condition** = the indicator, "Any alert() function call".
4. **Trigger** = "Once Per Bar Close".
5. **Webhook URL** = `https://YOUR-RAILWAY-APP.up.railway.app/tv/webhook`.
6. **Message** = `{{alert.message}}` (single token — Pine builds the JSON).

Backend payload schema is documented in `api/app/routers/tv_webhook.py` (`TVWebhookPayload`).
