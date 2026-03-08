# New User Default Watchlist + Per-User Data Isolation

## Problem

When a new free user registers and logs in:

1. **No watchlist is seeded for them** — the default watchlist migration (`_migrate_ensure_default_watchlist`) only seeds for the first admin user
2. **`app.py` home page calls `get_watchlist()` without `user_id`** — new users see the admin's watchlist instead of their own
3. **`get_watchlist()` fallback** returns `DEFAULT_WATCHLIST` when a user has no rows, which is correct, but symbols are never persisted to the new user's watchlist table until they manually add/remove
4. **Alert history is not scoped to user** — `get_alerts_today()`, `get_session_summary()`, and `get_session_dates()` are all called without `user_id` in `app.py`, so new users see **all alerts from all users** (the global/admin view)

## Current Behavior

| Scenario | What happens |
|----------|-------------|
| Admin user (uid=1) | Watchlist seeded by migration, works fine |
| New free user registers | No watchlist rows created, falls back to DEFAULT_WATCHLIST |
| New user adds a symbol | First `add_to_watchlist()` creates a single row — now their watchlist is just that one symbol (default fallback stops) |
| `app.py` home page | `get_watchlist()` without user_id → always shows admin's watchlist |
| New user views alert history | `get_alerts_today()` without user_id → sees **all users' alerts** |
| New user views EOD summary | `get_session_summary()` without user_id → global summary, not theirs |
| New user views daily report | Same — global view, not scoped to their watchlist or alerts |

## Expected Behavior

1. **On registration**: Seed new user's watchlist with a free-tier default (e.g., SPY + 2 popular symbols)
2. **Free tier limit**: Max 5 symbols on watchlist (enforced at add time)
3. **All pages**: `get_watchlist(user_id)` should always pass the logged-in user's ID
4. **First login UX**: Show onboarding prompt to customize watchlist

## Proposed Fix

### 1. Seed watchlist on user creation

In `ui_theme.py` `render_landing_page()` after `create_user()`:

```python
user_id = create_user(reg_email, reg_pass, reg_name or None)
upsert_subscription(user_id, "free")
# Seed default watchlist for new user
from config import DEFAULT_WATCHLIST
for sym in DEFAULT_WATCHLIST[:5]:  # Free tier: max 5
    add_to_watchlist(sym, user_id)
```

### 2. Fix app.py to pass user_id everywhere

```python
# Watchlist
watchlist = st.session_state.get("watchlist", get_watchlist(user["id"]))

# Alert history (line 232, 681)
db_alerts = get_alerts_today(user_id=user["id"])
_db_history = get_alerts_today(user_id=user["id"])

# EOD summary (line 721)
summary = get_session_summary(user_id=user["id"])

# Daily report (line 768, 781)
_rpt_summary = get_session_summary(_sel_str, user_id=user["id"])
_rpt_alerts = get_alerts_today(_sel_str, user_id=user["id"])
```

All these functions already accept `user_id` — they just aren't being passed it.

### 3. Enforce free tier watchlist limit

In `add_to_watchlist()`:

```python
if tier == "free":
    current_count = len(get_watchlist(user_id))
    if current_count >= 5:
        raise ValueError("Free tier limited to 5 watchlist symbols. Upgrade to Pro for unlimited.")
```

## Files Involved

| File | Change |
|------|--------|
| `ui_theme.py` | Seed watchlist on registration |
| `app.py` | Pass `user["id"]` to `get_watchlist()` |
| `db.py` | Add watchlist limit enforcement in `add_to_watchlist()` |
| `alerting/alert_store.py` | Functions already support `user_id` — no changes needed |
| `pages/1_Scanner.py` | Already passes `user["id"]` — correct |

## Questions for User

- Should free tier default watchlist be the same 6 symbols as admin, or a smaller set (e.g., SPY, QQQ, AAPL)?
- Should free users see a "You're at your 5-symbol limit" message when they try to add more?
- Should the home page alert scanning also be scoped to the user's watchlist?
