# Plan: Fix Duplicate Alerts & Signal Noise

## Problem Statement

Two processes (monitor.py + app.py) independently evaluate rules and send notifications with separate dedup stores, causing duplicate SMS/email. Stateless rules (Gap Fill, ORB) fire every poll cycle. Cooldowns are volatile. Result: 48+ SMS messages in 80 minutes when ~15 were expected.

**Why it matters:** SMS costs, alert fatigue, loss of trust in the signal system before beta launch.

**Success:** Each unique signal fires exactly 1 notification per session. Gap fill and ORB fire once. Cooldowns survive restarts.

## Solution Architecture

```
                    ┌─────────────────────┐
                    │   evaluate_rules()   │ ← Pure function, no changes
                    │ (returns all matches)│
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
     ┌────────▼─────────┐  ┌──▼──────────────┐ │
     │   monitor.py      │  │   app.py         │ │
     │ (notifications)   │  │ (display only)   │ │
     │                   │  │                  │ │
     │ was_alert_fired() │  │ DB-backed dedup  │ │
     │ notify()          │  │ NO send_email()  │ │
     │ record_alert()    │  │ NO send_sms()    │ │
     │ save_cooldown()   │  │ read cooldowns   │ │
     └───────┬───────────┘  └──────┬───────────┘ │
             │                     │              │
         ┌───▼─────────────────────▼───┐          │
         │         SQLite              │          │
         │  alerts (dedup + history)   │          │
         │  cooldowns (persistent)     │◄─────────┘
         └─────────────────────────────┘
```

**Key principle:** monitor.py owns notifications. app.py displays only.

## Codebase Analysis

### Files to Modify

| File | Changes | Lines |
|------|---------|-------|
| `db.py` | Add `cooldowns` table to schema | ~157 |
| `alert_store.py` | Add `save_cooldown()`, `get_active_cooldowns()`, `is_cooled_down()` | new functions |
| `app.py` | Remove `send_email()`/`send_sms()` calls; use DB for dedup + cooldowns | ~302-346 |
| `monitor.py` | Use DB cooldowns instead of module-level dict; pass `fired_today` from DB | ~52-54, ~70-72, ~128 |
| `analytics/intraday_rules.py` | Add SPY TRENDING_DOWN suppression for BUY signals | ~1174-1186 |

### No files to add

All changes fit within existing modules.

## Implementation Approach

### Step 1: Add `cooldowns` table to DB schema

In `db.py`, add to the `init_db()` schema:

```sql
CREATE TABLE IF NOT EXISTS cooldowns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    cooldown_until TEXT NOT NULL,
    reason TEXT,
    session_date TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, session_date)
);
```

### Step 2: Add cooldown persistence functions to `alert_store.py`

```python
def save_cooldown(symbol: str, minutes: int, reason: str = "", session_date: str | None = None):
    """Persist a cooldown for a symbol (survives restarts)."""

def get_active_cooldowns(session_date: str | None = None) -> set[str]:
    """Return set of symbols currently in cooldown."""

def is_symbol_cooled_down(symbol: str, session_date: str | None = None) -> bool:
    """Check if a specific symbol is in cooldown."""
```

### Step 3: Remove notification sending from `app.py`

**Current (lines 306-330):**
```python
for sig in all_signals:
    key = (sig.symbol, sig.alert_type.value, sig.direction)
    if key not in existing_keys:
        new_signals.append(sig)
        if send_email(sig):           # ← REMOVE
            notifications_sent += 1
        send_sms(sig)                 # ← REMOVE
        st.session_state["alert_history"].append({...})
```

**New:**
```python
for sig in all_signals:
    key = (sig.symbol, sig.alert_type.value, sig.direction)
    if key not in existing_keys:
        new_signals.append(sig)
        st.session_state["alert_history"].append({...})
```

Also change `existing_keys` to be built from DB (via `get_alerts_today()`) instead of session state, so it's authoritative even after page refresh:

```python
# Build fired_today from DB (authoritative) + session state (fast)
db_alerts = get_alerts_today()
existing_keys = {
    (a["symbol"], a["alert_type"], a["direction"])
    for a in db_alerts
}
```

And build `fired_today` for `evaluate_rules()` from DB:
```python
fired_today = {(a["symbol"], a["alert_type"]) for a in db_alerts}
```

And read cooldowns from DB:
```python
cooled_symbols = get_active_cooldowns()
```

Remove the `st.session_state["cooldown"]` tracking entirely. Remove the cooldown write on stop-out (monitor.py handles it).

### Step 4: Update monitor.py to use DB cooldowns

Replace module-level `_cooldown` dict with DB calls:

```python
# Before each poll cycle:
cooled_symbols = get_active_cooldowns(session)

# On stop-out:
save_cooldown(symbol, COOLDOWN_MINUTES, reason=signal.alert_type.value, session_date=session)
```

Also pass `fired_today` to `evaluate_rules()` from DB to prevent re-evaluation of already-fired signals:
```python
# Build fired_today from DB
db_alerts = get_alerts_today(session)
fired_today = {(a["symbol"], a["alert_type"]) for a in db_alerts}

signals = evaluate_rules(
    symbol, intraday, prior_day, active,
    spy_context=spy_ctx,
    auto_stop_entries=_auto_stop_entries.get(symbol),
    is_cooled_down=symbol in cooled_symbols,
    fired_today=fired_today,
)
```

This means Gap Fill and ORB are caught at the `evaluate_rules()` level — once `record_alert()` writes them to DB, subsequent polls see them in `fired_today` and filter them out before they even reach the dedup check.

### Step 5: SPY TRENDING_DOWN suppression

In `evaluate_rules()` at `intraday_rules.py:1174-1186`, add actual suppression when SPY regime is TRENDING_DOWN:

```python
# --- BUY rules ---
spy_regime = spy.get("regime", "CHOPPY")
suppress_buys = spy_regime == "TRENDING_DOWN"

if not is_cooled_down and not suppress_buys:
    # ... all BUY rules ...
```

This is a targeted change — only TRENDING_DOWN (SPY below all MAs, reverse stacked) suppresses. BEARISH and CHOPPY still show with caution notes. This matches the market-regime-detection ticket's design.

## Test Plan

### Unit Tests

1. **`test_save_cooldown`** — saves cooldown to DB, `is_symbol_cooled_down()` returns True
2. **`test_cooldown_expires`** — cooldown with 0 minutes returns False immediately
3. **`test_get_active_cooldowns`** — returns correct set of cooled symbols
4. **`test_trending_down_suppresses_buys`** — `evaluate_rules()` returns no BUY signals when `spy_regime="TRENDING_DOWN"`
5. **`test_bearish_allows_buys_with_caution`** — BUY signals still fire when `spy_trend="bearish"` but `spy_regime != "TRENDING_DOWN"`
6. **`test_fired_today_prevents_gap_fill_refire`** — Gap Fill in `fired_today` → `evaluate_rules()` filters it out

### Integration Tests

7. **`test_monitor_dedup_prevents_double_notification`** — simulate two poll cycles, second one should not re-notify
8. **`test_cooldown_persists_across_poll_cycles`** — stop-out in cycle 1, BUY suppressed in cycle 2

### Edge Cases

9. **Cooldown + different rule type** — after MA Bounce stop-out, PDL Reclaim should also be suppressed (same symbol cooldown)
10. **Gap Fill across sessions** — gap fill from yesterday doesn't suppress today's

## E2E Validation

### Prerequisites
- Local dev environment running
- SQLite DB accessible

### Steps

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ 1. Setup │────▶│ 2. Test  │────▶│ 3. Verify│────▶│4. Cleanup│
└──────────┘     └──────────┘     └──────────┘     └──────────┘
```

1. **Setup**: Run `python monitor.py --dry-run` to verify rules fire
2. **Test notification dedup**:
   - Insert a fake alert into `alerts` table for TEST symbol
   - Run monitor.py dry-run for TEST — should show "[DRY RUN]" but `was_alert_fired` would skip in real mode
3. **Test cooldown persistence**:
   - Insert a cooldown via `save_cooldown("TEST", 30)`
   - Verify `is_symbol_cooled_down("TEST")` returns True
   - Verify `get_active_cooldowns()` includes "TEST"
4. **Test app.py doesn't send**:
   - Open Streamlit app, verify signals display
   - Check no new SMS/email sent (monitor logs only)
5. **Test SPY suppression**:
   - Mock SPY context with `regime="TRENDING_DOWN"`
   - Run `evaluate_rules()` — verify no BUY signals returned
6. **Cleanup**: Delete test rows from DB

### Failure Scenario Testing
- What if DB is locked? Both processes use WAL mode, should handle concurrent access
- What if monitor.py crashes mid-cycle? Alerts already recorded won't re-fire on restart
- What if cooldown table migration fails on existing DB? Use `CREATE TABLE IF NOT EXISTS`

## Implementation Order

1. `db.py` — add cooldowns table (migration-safe)
2. `alert_store.py` — add cooldown CRUD functions
3. `monitor.py` — switch to DB cooldowns + pass `fired_today`
4. `app.py` — remove notification sending, use DB for dedup/cooldowns
5. `analytics/intraday_rules.py` — add TRENDING_DOWN suppression
6. Tests — write unit tests for new functions
7. Manual E2E validation

## Out of Scope

- Changing any rule logic (MA Bounce, ORB, Gap Fill conditions) — rules are pure and correct
- Adding new alert types
- Changing notification delivery method (Twilio/SMTP)
- Score threshold changes
- Gap Fill one-shot at the rule level — handled by `fired_today` dedup instead (simpler, same effect)
- Rate limiting SMS (not needed once dedup works)
