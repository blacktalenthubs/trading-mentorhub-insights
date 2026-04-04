# V2 Telegram Alert Integration Plan

## Problem Statement
V2 monitor records alerts to DB and publishes to SSE, but never sends to Telegram. Users expect alerts delivered to Telegram with inline Took/Skip buttons, same as V1. Users should be able to "Took" from either the web dashboard or Telegram.

## Why It Matters
Telegram is the primary notification channel for active traders. Without it, traders miss signals during market hours when they're not staring at the web app.

## Solution Architecture

```
V2 Monitor (poll_all_users)
  |
  v
evaluate_rules() -> AlertSignal
  |
  v
Record to DB (Alert table)
  |
  +---> SSE publish (alert_bus) -> Web UI Signal Feed
  |
  +---> Telegram notify (per-user) -> Telegram with inline buttons
  |
  +---> APNs push (existing)
```

```
Telegram Button Press ("Took It")
  |
  v
telegram_bot.py callback handler
  |
  v
V2 API: POST /alerts/{id}/ack?action=took
  +---> Updates Alert.user_action in DB
  +---> Opens real trade (if BUY/SHORT)
```

## Scope

### IN SCOPE
1. Wire V2 monitor to call Telegram notifier per user
2. Per-user `telegram_chat_id` field on User model
3. Telegram link flow (user sends `/start` to bot, gets linked)
4. Telegram bot button callbacks → V2 ACK endpoint
5. Settings page: Telegram link/unlink UI

### OUT OF SCOPE
- Email notifications (future)
- SMS notifications (future)
- Quiet hours enforcement (future)
- Custom webhook delivery (Premium tier)

## Codebase Analysis

### Files to Modify

| File | Change | Risk |
|------|--------|------|
| `api/app/models/user.py` | Add `telegram_chat_id` field | Low — additive |
| `api/app/background/monitor.py` | Add Telegram notify after alert record | **High** — business logic |
| `alerting/notifier.py` | Add `send_telegram_v2(chat_id, signal, alert_id)` function | Medium — new function, existing code untouched |
| `api/app/routers/alerts.py` | Add real trade creation on "took" ack | Medium |
| `api/app/routers/settings.py` | Add Telegram link token endpoint | Low |
| `scripts/telegram_bot.py` | Route callbacks to V2 API instead of V1 store | Medium |
| `web/src/pages/SettingsPage.tsx` | Add Telegram link/unlink UI | Low |

### Files NOT Modified (preserved)
- `analytics/intraday_rules.py` — signal rules unchanged
- `alert_config.py` — category definitions unchanged
- `alerting/alert_store.py` — V1 store untouched, V2 uses ORM

### Existing Patterns to Follow
- V1 notifier `_send_telegram()` and `_build_trade_buttons()` — reuse formatting + button layout
- V2 monitor `poll_all_users()` — add notify call after `publish()` line
- `ALERT_TYPE_TO_CATEGORY` + `EXIT_ALERT_TYPES` — same filtering logic

## Implementation Steps

### Step 1: Add `telegram_chat_id` to User model
- Add `telegram_chat_id: Optional[str]` column to User
- Migration: `ALTER TABLE users ADD COLUMN telegram_chat_id VARCHAR(50)`
- Settings API: return `telegram_linked: bool` based on field presence

### Step 2: Telegram link flow
- `POST /api/v1/settings/telegram-link` — generates a one-time token, returns bot deep link URL
- User clicks link → opens Telegram → sends `/start <token>` to bot
- Bot validates token → stores `telegram_chat_id` on User record
- `DELETE /api/v1/settings/telegram-link` — clears `telegram_chat_id` (unlink)

### Step 3: Wire V2 monitor → Telegram delivery
In `api/app/background/monitor.py`, after alert is recorded and published to SSE:

```python
# After: publish(user_id, alert_data)
if user.telegram_chat_id and user.telegram_enabled:
    send_telegram_alert(
        chat_id=user.telegram_chat_id,
        signal=signal,
        alert_id=alert.id,
    )
```

### Step 4: Telegram message format (reuse V1)
New function in `alerting/notifier.py`:

```python
def send_telegram_alert(chat_id: str, signal: AlertSignal, alert_id: int):
    body = _format_alert_html(signal)
    buttons = _build_v2_buttons(alert_id, signal.direction)
    _send_telegram(body, chat_id=chat_id, reply_markup=buttons)
```

Buttons use callback_data format: `v2:took:<alert_id>`, `v2:skip:<alert_id>`

### Step 5: Telegram bot callback → V2 API
In `scripts/telegram_bot.py`, handle V2 callbacks:

```python
@bot.callback_query_handler(func=lambda c: c.data.startswith("v2:"))
def handle_v2_callback(call):
    action, alert_id = parse_callback(call.data)
    # Call V2 API directly (internal, no auth needed for bot)
    requests.post(f"http://localhost:8000/api/v1/alerts/{alert_id}/ack?action={action}",
                  headers={"X-Bot-Secret": BOT_SECRET})
    # Edit Telegram message to show ack result
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.answer_callback_query(call.id, f"Marked as {action}")
```

### Step 6: ACK endpoint enhancement
When `action=took` on a BUY/SHORT alert:
- Create `ActiveEntry` record (for exit monitoring)
- Optionally create `RealTrade` record (for P&L tracking)
- Return confirmation

### Step 7: Settings UI — Telegram link
Add to SettingsPage.tsx:
- "Link Telegram" button → calls API → shows deep link
- "Unlink" button → calls DELETE → clears link
- Status indicator: linked/unlinked with chat_id preview

## Test Plan

### Unit Tests
- `test_send_telegram_v2()` — mock Telegram API, verify message format + buttons
- `test_telegram_link_flow()` — token generation, validation, chat_id storage
- `test_v2_ack_creates_trade()` — verify "took" creates active entry

### Integration Tests
- Fire test alert → verify appears in Signal Feed + Telegram
- Click "Took" in Telegram → verify alert marked in DB + web UI updates
- Click "Took" in web UI → verify same result
- Preference filtering: disabled category → no Telegram, still in dashboard

### E2E Validation
1. Start V2 API + monitor locally
2. Link Telegram in Settings
3. Wait for market hours scan
4. Verify alert appears in: Signal Feed, Dashboard, Telegram
5. Click "Took" in Telegram → verify web UI shows "Took"
6. Click "Skip" in web UI → verify Telegram button disappears

## Out of Scope
- Email delivery (separate PR)
- Quiet hours (settings fields exist, enforcement TBD)
- Rate limiting Telegram sends (V1 handles this, V2 should too)
- AI narrative in Telegram message (exists in V1, can add later)
