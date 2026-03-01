# Learning: Duplicate Alerts & Signal Noise

## Codebase Analysis

### Notification Architecture (current)

Two independent processes evaluate rules and send notifications:

```
┌───────────────────┐        ┌───────────────────┐
│   monitor.py      │        │   app.py           │
│ (APScheduler)     │        │ (Streamlit)        │
│                   │        │                    │
│ poll every 3 min  │        │ autorefresh 3 min  │
│ evaluate_rules()  │        │ evaluate_rules()   │
│ was_alert_fired() │        │ session_state dedup│
│ notify() → email  │        │ send_email()       │
│            + SMS  │        │ send_sms()         │
│ record_alert()    │        │ session_state.append│
└───────┬───────────┘        └──────────┬─────────┘
        │                               │
    ┌───▼───┐                    ┌──────▼──────┐
    │ SQLite │                    │ session_state│
    │ alerts │                    │ (in-memory)  │
    └────────┘                    └──────────────┘
```

**Problem**: Two dedup stores, no cross-communication. Both fire independently.

### Dedup Mechanism Comparison

| Layer | Location | Key | Storage | Persistent? |
|-------|----------|-----|---------|------------|
| `evaluate_rules()` | `intraday_rules.py:1371` | `(symbol, alert_type)` | passed-in set | No — rebuilt each call |
| `app.py` existing_keys | `app.py:302` | `(symbol, alert_type, direction)` | `st.session_state` | Browser tab only |
| `monitor.py` DB check | `alert_store.py:16` | `(symbol, alert_type)` | SQLite | Yes |

### Rule Statefulness Analysis

| Rule | Fires When | Stateless? | Re-fires? |
|------|-----------|------------|-----------|
| MA Bounce 20/50 | Bar low near MA + close above | Yes | Yes — any bar near MA |
| Prior Day Low Reclaim | Bars dipped below + close above | Yes (checks all bars) | Less likely — needs full dip+reclaim pattern |
| Inside Day Breakout | Close above inside high | Yes | Yes — any bar above |
| Opening Range Breakout | Close above OR high + volume | Yes | **Yes — every poll while above** |
| Gap Fill | `gap_info["is_filled"]` | **Yes — worst offender** | **Every poll once filled** |
| Intraday Support Bounce | Low near support + close above | Yes | Yes — any bar near support |
| Session Low Double-Bottom | Complex multi-bar pattern | Mostly stateful | Less likely |
| Planned/Weekly Level Touch | Low near level + close above | Yes | Yes — any bar near level |

### Cooldown Architecture

```
monitor.py: _cooldown = {symbol: datetime}  # module-level dict
app.py:     st.session_state["cooldown"] = {symbol: datetime}  # browser session

Neither checks the other. Neither is DB-persistent.
```

### Existing Patterns to Follow

1. **`was_alert_fired()`** — correct DB-based dedup pattern, already used by monitor.py
2. **`active_entries` table** — has `UNIQUE(symbol, session_date, alert_type)` constraint
3. **`alerts` table** — has no unique constraint but `was_alert_fired()` queries it effectively
4. **`record_alert()`** — inserts into DB, should be the single source of truth

### Gap Analysis

1. **No `cooldowns` DB table** — cooldowns are volatile, need persistence
2. **app.py sends notifications directly** — bypasses the DB dedup that monitor.py uses
3. **evaluate_rules() is pure** — returns all matching signals, doesn't know what was already fired. Correct design, but callers must dedup.
4. **notifier.py has no dedup** — `send_email()` and `send_sms()` fire unconditionally. Correct — dedup belongs upstream.

## Key Decisions

### Who owns notifications?
`monitor.py` should be the single notification sender. It has the right architecture:
1. Evaluate rules
2. Check DB dedup (`was_alert_fired`)
3. Send notification (`notify`)
4. Record to DB (`record_alert`)

`app.py` should display signals but NEVER send notifications.

### How to fix stateless rules?
Don't change the rules — they're pure functions, correctly returning "this condition is true right now." The fix belongs in the dedup layer:
- `evaluate_rules()` already accepts `fired_today` and filters
- monitor.py already uses `was_alert_fired()` per signal
- Just need to make sure app.py also reads from DB

### How to persist cooldowns?
Add a `cooldowns` table. Both processes read from it. monitor.py writes to it on stop-outs.
