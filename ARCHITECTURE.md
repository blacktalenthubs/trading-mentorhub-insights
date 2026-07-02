# TradeSignal — Architecture Reference (Alert System)

> **Purpose:** the durable map of how alerts flow, so future changes are grounded in how the
> system actually works — not rediscovered under fire. Read this before touching the pipeline.
> Last verified: 2026-07-02.

---

## 1. Services (what runs where)

| Service | Code | Runs on | Responsibility |
|---|---|---|---|
| **API** | `api/app/main.py` (FastAPI) | Railway | Serves the frontend API **and the TV webhook**. Ingests TV alerts, runs dedup, saves to `alerts`, does per-user delivery + push/Telegram fan-out. Some APScheduler jobs. |
| **Triage worker** | `triage-agent/live.py` | Railway (separate service) | `LISTEN`s on Postgres `new_alert` (pg_notify) → AI triage/enrichment + posting. **Skips alerts with a `suppressed_reason` (logs `NOT_ROUTED … skipping`).** Cron jobs: premarket signals (7:00–9:45 ET), EOD recap, trend setups, morning focus. |
| **Frontend** | `web/` (React) | Built by Railway on deploy, served by API | Feed, Settings, Admin. Loaded by mobile app + desktop Electron (both hit the live site). |
| **Postgres** | Railway (`trolley.proxy…`) | Railway | Shared by API + triage worker. The `alerts` table is the source of truth for the feed. |
| ~~Legacy worker~~ | ~~`worker.py`/`monitor.py`~~ | ~~Railway~~ | **RETIRED 2026-07-02** (poll-and-notify zombie). Code removed; stop the Railway service. |

Deploying = restarting the API + triage worker (brief ingestion gap). **Do not rapid-deploy.**

---

## 2. The alert lifecycle

```
TradingView  (pine indicator + an ALERT bound to a TV watchlist)
   │  a setup triggers on a symbol in that TV watchlist
   ▼
webhook POST ──► API  api/app/routers/tv_webhook.py :: _route_alert()
   │  1. GLOBAL dedup/collapse  (may set suppressed_reason)
   │  2. per-user routing + gates
   │  3. save row(s) to `alerts`  +  pg_notify('new_alert')
   ├──► FEED  (reads `alerts` table; shows suppressed rows badged)
   ├──► push/Telegram fan-out  (webhook, after commit, for routed users)
   └──► TRIAGE worker  (LISTEN new_alert → AI triage; SKIPS suppressed rows)
```

**The app does not detect setups — TradingView does.** The app receives and routes.

---

## 3. The TWO watchlists (the most-confused thing)

| | **TV firing watchlist** | **Platform watchlist** |
|---|---|---|
| Where | Inside TradingView | DB `watchlist` table (per user) |
| Controls | **What FIRES** | **What's DELIVERED** |
| Rule | A pine alert only evaluates symbols in the TV watchlist it's bound to | A fired alert routes only to users tracking that symbol |
| Must be | The **union of all users' symbols** (else those users go dark) | Whatever each user curates |

- A symbol reaches a user only if it's in **BOTH**: TV (to fire) **and** the user's watchlist (to deliver).
- **Empty user watchlist = broadcast fallback** (gets everything) — `_users_watching` in tv_webhook.
- Keep TV in sync via the generator: `analytics/tv_build_import.py --out ~/Downloads/…` (crypto de-dashed, sectioned). **Repeatable — always use it, never hand-roll.**

---

## 4. Dedup (why delivery can silently go to 0)

**Two independent layers — do not confuse them:**

1. **Global cross-type collapse** — merges same-price/same-bar alerts of *different* types into one.
   - `_check_level_confluence`, `_check_same_bar_collapse`, `_check_entry_time_dedup` (price-confluence).
   - Env flags: `V2_SAME_BAR_COLLAPSE_ENABLED` (default `true`), `V2_ENTRY_DEDUP_ENABLED` (default `true`).
2. **Per-user identity dedup** — `_alert_already_fired`, per `(user, symbol, direction, type)`, 90-min window + daily cap. This is the **flood control**; keep it.

- A collapsed alert is saved with `suppressed_reason` → shown in feed badged → **NOT delivered** (triage skips it).
- **KNOWN FLAW (open):** the global collapse picks the survivor **globally, before** the per-user type filter → a type a user **disabled** can swallow one they **enabled**; under a flood it chains to **no survivor → 0 delivered**. The real fix is a **per-user** cross-type dedup.

---

## 5. Per-user delivery gates (what suppresses/routes a fired alert)

In order, in `_route_alert` after the global dedup:
1. `_users_watching` — tracks the symbol (or empty-watchlist broadcast); **excludes** `master@busytradersdesk`.
2. `_filter_users_by_type_pref` — user enabled this type (`user_alert_type_prefs`, **default OFF**).
3. `_filter_users_by_market_gate` — SPY 8/21 gate (opt-in): drops day-trade longs in a weak tape unless exempt.
4. Short allowlist — shorts only on the user's `market_gate_exempt` names.
5. Focus-scope — day-trade alerts only to Focus symbols if `daytrade_focus_only`.
6. Grade — `min_alert_grade` (A/B/C).

---

## 6. Non-TV alert sources (scanners)

- `analytics/swing_scanner.py` — polls **symbols at least one user watches** (the union), fires swing types (rsi_oversold, ema cross, key-level bounces). Cost-controlled by `SCAN_USER_EMAIL`. **No TV binding needed.**
- `analytics/ai_day_scanner.py` — AI day-trade scanner.
- These are a *smaller* set. Your core day-trade/level signals (RC, PDH/PDL, MA bounce, gaps) are **TV-pine-based and require TV binding.**

---

## 7. Data model (key columns)

- **`alerts`**: `id`, `symbol`, `alert_type` (**`tv_`-prefix = webhook**; non-`tv_` = scanner/legacy), `user_id`, `direction`, `entry`, `price`, **`suppressed_reason`** (NULL = delivered/SENT), `created_at`, `session_date`, `stage`. ⚠️ `style` is computed at API-response time, **not stored** (don't query it).
- **`watchlist`**: `id`, `user_id`, `symbol`, `added_at`, `group_id`, `focus`.
- **`users`** (delivery-relevant): `telegram_chat_id`, `push_enabled`, `apns_enabled`, `min_alert_grade`, `daytrade_focus_only`, `market_gate_enabled`/`market_gate_exempt`. Alert on/off is in **`user_alert_type_prefs`** (separate table). `master_alerts` column is **dormant** (feature retired).

---

## 8. Retired — do NOT resurrect

- **Master Alerts** (opt-in "receive the admin's whole curated feed") — removed 2026-07-02. Delivery is **purely per-user**. Kept: scan-universe infra + admin master-watchlist panel (not user-facing).
- **Legacy poll worker** (`worker.py`/`monitor.py`/`monitor_thread.py`) — removed 2026-07-02. **KEPT the shared modules** (`alerting/notifier.py`, `analytics/intraday_rules.py`, `alert_config.py`, `analytics/signal_engine.py`, root `db.py`) — the live app imports them; deleting them breaks production.

---

## 9. Known failure modes + how to diagnose (from the 2026-07-02 incident)

| Symptom | Cause | Diagnose / Fix |
|---|---|---|
| **0 delivered, feed full of suppressed** | A TV alert on **"Once Per Minute"** (freq 60) floods ~2000/min → dedup collapses to no-survivor | **`alert_list` shows `frequency`+`resolution`+`last_fired` — CHECK FIRST.** Delete the offending TV alert (user must confirm; `alert_delete` only opens the menu). |
| **Ingestion stalls (no new rows)** | Flood overwhelms the webhook's background save | `max(id)` on `alerts` frozen. Stop the flood; API restart clears it. |
| **Alert not firing after a chart change** | TV alerts **lock to their TF+frequency at creation** | Delete + recreate the alert. Changing the chart does nothing. |
| **Collapses even after flood stops** | In-memory `_entry_dedup_state` stuck-seeded | API restart (redeploy) clears it. |
| **Webhook 200 but no row** | Silent ingestion error (`_dispatch_background` swallows errors) | Verify via `max(id)`, not `created_at`. |
| **"Notification I can't find in the feed"** | The legacy zombie worker (retired) or a **local** `worker.py` | Stop the Railway worker / kill the local process. |

---

## 10. Change checklist (the consistency routine — follow every time)

1. **Check state first** — query the DB / read the code. Don't assume.
2. **Use the real tool, not a one-off** — e.g. `tv_build_import.py` for the TV list.
3. **Branch → test (`pytest` + `cd web && npx tsc -b`) → verify → deploy → tag** (`stable-*`).
4. **One change at a time** — no batching. Two things → two commits, two checks.
5. **Touching `tv_webhook.py`** → spot-check delivery after the deploy.
6. **Rollback floor** — `stable-*` tags. `git reset --hard <tag> && git push --force-with-lease`.

> The difference between the 6 rollbacks and the clean single commits (master-alerts, worker
> removal) on 2026-07-02 was this checklist. Skipping it is what breaks things.
