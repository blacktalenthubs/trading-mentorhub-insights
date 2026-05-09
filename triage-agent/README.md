# Alert Triage Agent

Side-car agent that listens for new alerts and routes the high-conviction ones to a separate Telegram channel. Decoupled from the existing trade-analytics pipeline — adds a single Postgres trigger and a separate worker process.

## Architecture

```
   Existing pipeline (unchanged)
   ─────────────────────────────
   TV alert → tv_webhook.py → INSERT INTO alerts → notifier → Telegram

                                    │ (the trigger fires after the insert
                                    │  and broadcasts the alert id over
                                    │  pg_notify; insert path is unaffected)
                                    ▼
                          NOTIFY 'new_alert' <id>

                                    │
                                    ▼
   ┌─────────────────────────────────────────────┐
   │ live.py — separate worker process           │
   │   LISTEN on 'new_alert' channel              │
   │   triage()  →  HIGH | NORMAL | MUTE         │
   │     │                                       │
   │     HIGH    → 🔥 conviction Telegram chat  │
   │     NORMAL  → no extra (existing TG has it) │
   │     MUTE    → audit log only                │
   └─────────────────────────────────────────────┘
```

## File map

| File | Purpose |
|---|---|
| `triage.py` | Per-alert agent loop (LLM + tools + safety net + sector/index enrichment) |
| `live.py` | **The live worker.** LISTEN + cursor catchup + routing |
| `telegram_post.py` | Telegram poster + HIGH-conviction message formatter |
| `migrations/001_alerts_notify.sql` | DB trigger that fires `pg_notify('new_alert', id)` on insert |
| `_no_llm_scan.py` | Deterministic-only scan (proximity + sector + index, no LLM) |
| `_smoke_test_enrichment.py` | Smoke test for compute functions |

## One-time setup

### 1. Apply the trigger migration

```bash
# Verify your DATABASE_URL points at the right env first.
psql "$DATABASE_URL" -f migrations/001_alerts_notify.sql

# Sanity check
psql "$DATABASE_URL" -c \
  "SELECT tgname, tgrelid::regclass FROM pg_trigger WHERE tgname='alerts_notify_new';"
```

The trigger is purely additive — no existing code path is modified. To roll back:

```sql
DROP TRIGGER alerts_notify_new ON alerts;
DROP FUNCTION notify_new_alert();
```

### 2. Set up Telegram conviction channel

1. **Bot:** use your existing bot or create one with `@BotFather`.
2. **Channel:** create a new private channel in Telegram (or a topic in an existing forum group).
3. **Add the bot as admin** of the new channel.
4. **Get the chat_id:**
   ```bash
   # Send any message in the new channel, then:
   curl "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates"
   # The chat_id will be in the response (channels are negative, like -1001234567890).
   ```
5. Put both into `.env`:
   ```
   TELEGRAM_BOT_TOKEN=...
   CONVICTION_CHAT_ID=-100...
   ```

### 3. Configure environment

```bash
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, DATABASE_URL, TELEGRAM_BOT_TOKEN, CONVICTION_CHAT_ID
```

## Run modes

### Backtest (no Telegram, no LLM cost issues with credits)

```bash
# Triage every alert from a session date
python triage.py --dry-run --since 2026-05-08 --user-id 3

# Or just the last 10 alerts
python triage.py --dry-run --last 10 --user-id 3

# No-LLM enrichment scan (proves sector/index confluence works without spending credits)
python _no_llm_scan.py
```

### Live mode (dry-run — does NOT post to Telegram)

```bash
python live.py --dry-run
```

Watches for new alerts and prints what it would do. Safe to leave running.

### Live mode (real — posts to your conviction channel)

```bash
python live.py
```

The worker honors `TRIAGE_POST_MODE`:

| Mode | What posts | When to use |
|---|---|---|
| `all` (default) | HIGH + NORMAL + MUTE | **Validation phase** — see every agent decision next to the Pine alerts you already received. Judge accuracy. |
| `high_mute` | HIGH + MUTE | Middle ground after partial trust — drop NORMAL chatter but still verify what the agent muted |
| `high_only` | HIGH only | Steady-state once the agent is fully trusted |

Each verdict has a distinct prefix in the Telegram channel:

- 🔥 **HIGH** — full Pine signal block + agent enrichment context
- ⚪ **NORMAL** — concise: alert id + agent's reasoning tag (sector aligned, etc.)
- 🔕 **MUTE** — what was muted and why — *the most important format to spot-check*

Why MUTE matters for validation: a wrongly-muted alert is the only way the agent can hurt you. Posting them gives you the final-say veto: if you disagree with a mute, you change the prompt or rule.

### Backlog catch-up only (process anything since cursor, then exit)

```bash
python live.py --catchup-only --dry-run
```

## Deployment to Railway

The agent runs as a **new Railway service** in the same project as your existing trade-analytics. It does NOT replace any existing service.

### Steps

1. **Create a new Railway service** in your existing project. Point it at this folder (or a separate repo containing it).
2. **Set env vars** on the new service: `ANTHROPIC_API_KEY`, `DATABASE_URL` (same as your other services), `TELEGRAM_BOT_TOKEN`, `CONVICTION_CHAT_ID`, `TRIAGE_USER_ID=3`, `TRIAGE_DAILY_USD_CAP=1.50`.
3. **Mount a volume at `/data`** — the cursor file and audit log live there. Without a volume, the worker resets its cursor on every restart (still safe; will run catchup).
4. **Start command:** `python -u live.py` (already in `Procfile` and `Dockerfile`).
5. **Verify:** the Railway log should show `LISTEN on 'new_alert' — waiting for new alerts` within 5 seconds of boot.

### What runs on Railway after deploy

- Your existing API service (unchanged)
- Your existing worker.py (unchanged)
- Your existing Streamlit (unchanged)
- **NEW:** triage-agent service running `live.py`

The new service:
- Holds one Postgres LISTEN connection
- Is mostly idle (waiting for notifies)
- Spends ~$2–5/month on LLM calls
- Has its own logs, deploys, and restart story

## Cost & resource expectations

| Metric | Expected |
|---|---|
| LLM cost (Haiku) | ~$0.001–$0.005 per alert |
| LLM cost @ 30 alerts/day | ~$1–4/month |
| Memory | ~80 MB |
| CPU | <1% (idle 99% of time, spike on alert) |
| DB connections held | 1 (LISTEN) + N (during processing) |
| Daily cost cap (configurable) | $1.50 — overflow logs only, no LLM call |

## Operational checks

```bash
# Is the trigger live?
psql "$DATABASE_URL" -c \
  "SELECT tgname FROM pg_trigger WHERE tgname='alerts_notify_new';"

# Inspect the audit log (last 20 decisions)
tail -20 /data/triage-audit.jsonl | jq .

# Where is the cursor?
cat /data/triage-cursor

# Force a catchup pass (if worker was down)
python live.py --catchup-only
```

## Backout

If you want to disable the agent entirely:

1. Stop the Railway service. Existing pipeline keeps running unaffected.
2. Optionally drop the trigger:
   ```sql
   DROP TRIAGE alerts_notify_new ON alerts;
   DROP FUNCTION notify_new_alert();
   ```
   (Even with the trigger live but no listener, NOTIFY is a no-op.)

Nothing in your protected files (`tv_webhook.py`, `monitor.py`, `worker.py`, `alert_store.py`) was modified.

## What "value" the agent adds (the test you ran)

For yesterday's 37 alerts on user_id=3:

- **7 sector-confluence events** that Pine can't see (MU+SNDK breaking together, AVGO+AMD+INTC chips cascade, ETH+MSTR crypto-equity, etc.)
- **Zero MUTE** — proved by your principle "low volume is not a mute reason." The mute rule only fires for proximity matches without override signals.
- **Cost:** ~$0.45 for the full backtest (~$0.005/alert avg)

The deterministic part (proximity + sector + index) finds the confluence; the LLM weaves it into a natural-language reason for the HIGH push.

## Troubleshooting

**Worker boots but doesn't process anything:**
- Check the trigger exists (sanity SQL above).
- Check the agent is filtering for the right user_id (`TRIAGE_USER_ID` env).
- `python live.py --catchup-only --dry-run` — does it find recent alerts?

**Telegram messages don't arrive:**
- Verify the bot is an admin of the channel.
- Verify `CONVICTION_CHAT_ID` (channels are `-100...`, groups are `-...`, DMs are positive).
- Try `curl "https://api.telegram.org/bot<TOKEN>/sendMessage" -d chat_id=<ID> -d text="hi"`.

**LLM cost spike:**
- Daily cap kicks in automatically. After cap, alerts are audit-logged only, no LLM call.
- Lower the cap with `TRIAGE_DAILY_USD_CAP=0.50`.

**Multiple notifies for the same alert:**
- Shouldn't happen — Postgres dedupes notifies per transaction.
- The cursor file ensures we don't re-process on restart.
