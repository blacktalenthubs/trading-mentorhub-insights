# tradingwithai.ai shutdown — Phase 1 (today)

Owner: solo founder
Goal: stop bleeding cost + cognitive load on V1/V2 product, while preserving the TradingView → Telegram pipeline that drives current trading.

## What stays alive after Phase 1

```
TV alerts → POST /tv/webhook → Postgres (dedup) → Telegram bot → phone
```

Everything else can sleep.

## Phase 1 changes (today)

### Code change (already pushed)
- **`api/app/main.py`**: gated `trade_replay` (4:40 PM ET) and `weekly_review` (Fri 5 PM ET) behind `AI_SCAN_ENABLED`. Previously these ran unconditionally and called Anthropic. Now flipping `AI_SCAN_ENABLED=false` kills all AI-backed scheduled jobs cleanly.

### Manual env-var changes on Railway dashboard
Set these on the worker service (Settings → Variables):

| Variable | Value | Effect |
|---|---|---|
| `RULE_ENGINE_ENABLED` | `false` | Stops V1 rule polling (gap fills, MA bounce, target hits via yfinance). TV alerts still fire. |
| `AI_SCAN_ENABLED` | `false` | Stops AI day scan, swing scan, auto-trade monitor, trade_replay, weekly_review. Zero Anthropic cost from scheduled jobs. |
| `AI_SCHEDULED_JOBS_ENABLED` | (already false by default) | Already off. game_plan, premarket_brief, daily_review stay off. |

After saving, Railway redeploys automatically. Look for these log lines to confirm:
```
Rule engine DISABLED (RULE_ENGINE_ENABLED=false)
AI scans DISABLED (AI_SCAN_ENABLED=false) — rule-based alerts only
```

### Manual UI actions
- [ ] **Streamlit Cloud**: pause the app at streamlit.io dashboard (or change visibility to private). No code/data lost.
- [ ] **Square dev account**: cancel/disable webhook. No active charges currently, but stop the integration.
- [ ] **Domain `tradingwithai.ai`**: switch off auto-renew at registrar. Domain expires naturally (~$15 saved). Webhook URL is the Railway domain `worker-production-f56f.up.railway.app`, not the custom domain — TV alerts unaffected.

## What's still alive (verification checklist after env-var change)

After the Railway redeploy lands, verify the TV pipeline:

- [ ] Hit `/healthz` → 200 OK
- [ ] Send a curl test POST to `/tv/webhook` → Telegram lands
- [ ] Wait for next real TV alert (PDH/PDL or MA bounce) → Telegram lands
- [ ] Confirm Postgres dedup still suppresses repeat fires within 30 min

## What dies (intentional)

- All AI narratives in alert messages (alerts now plain-text from Pine payload)
- All scheduled AI jobs (game plan, premarket brief, daily review, trade replay, weekly review)
- All V1 yfinance polling (gap fill, MA bounce, target/stop hits — these were the "alerts that competed with TV alerts")
- Streamlit dashboard (Signal Library, manual entry tools, journal UI)

## Phase 2 (deferred — only after Phase 1 stable for 1 week)

Code-level cleanup. Reduce repo from ~200 files to ~10 essentials.

- Delete `monitor.py`, `analytics/intraday_rules.py`, `analytics/signal_engine.py`, `analytics/ai_*` (the V1 rule engine + AI scanners)
- Delete `app.py` and `pages/*` (Streamlit dashboard)
- Delete `web/` (V2 React frontend, if not yet prod)
- Delete `alerting/square_*`, `alerting/billing*` (billing stack)
- Delete `alerting/narrator.py`, `alerting/coach_*` (AI narrators)
- Slim `api/app/routers/*` to just `tv_webhook.py` + `auth.py` + healthz
- Slim Postgres: drop `signals`, `signal_library`, `subscriptions`, `coach_messages`, `auto_trades` tables. Keep `alerts`, `users` (single user), `user_notification_prefs`.

## Rollback plan

If anything breaks:
1. Flip env vars back: `RULE_ENGINE_ENABLED=true`, `AI_SCAN_ENABLED=true`
2. Railway redeploys automatically
3. V1 polling and AI scans resume

No code change to revert.

## Cost savings

Phase 1 alone:
- Anthropic API: ~$10-30/mo → $0 for scheduled jobs (on-demand AI from React still works if app runs)
- Domain: $15/yr after expiry
- Streamlit Cloud: $0 (already free tier)

Phase 2 additional:
- Railway: small reduction (~$5/mo if service can downsize tier)

Total: ~$15-35/mo savings. Cognitive savings: large (no V1/V2 product surface to maintain).
