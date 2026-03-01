# Duplicate Alerts & Signal Noise — Fix Notification Dedup and One-Shot Rules

## Problem

Friday 2/27 alert session exposed several issues:

1. **Duplicate SMS messages** — Same signal sent 2x within 1-2 minutes (e.g., AAPL MA Bounce at 8:38 AND 8:39 with identical price $269.69). Doubles SMS costs and creates noise.

2. **Gap Fill fires endlessly** — PLTR Gap Fill sent **8 times** in 70 minutes (8:31, 8:49, 9:04, 9:09, 9:24, 9:29, 9:39, 9:44). Once a gap fills, it stays filled — the rule fires every poll for the rest of the day.

3. **Opening Range Breakout (ORB) re-fires** — TSLA ORB sent repeatedly in prime time. Once price is above OR high, the rule fires every poll instead of just the first break.

4. **Post-stop-out cooldown not persisting** — AAPL stopped at 8:50, fires again at 8:54 (PDL Reclaim, different rule type). Stopped again at 9:48, fires again at 9:49 (same MA Bounce type, 1 minute later). Cooldown stored in volatile `st.session_state`, lost between processes.

5. **BUY signals fire freely on bearish SPY days** — Every single alert on 2/27 fired with "SPY: bearish" context. Code adds CAUTION note but never suppresses. Docstring says "skip BUY if SPY below 20MA" but implementation only warns.

## Observed On

2026-02-27 — 48+ SMS messages in ~80 minutes of market hours. SPY bearish all day. Multiple auto stop-outs followed by immediate re-entries.

## Root Causes

### Duplicates: Two processes both send notifications independently
- `monitor.py` polls every 3 min, dedupes via `was_alert_fired()` (DB-based), sends via `notify()`
- `app.py` (Streamlit) also evaluates rules, dedupes via `st.session_state["alert_history"]` (in-memory only), sends via `send_email()` + `send_sms()` directly
- The two processes never share state — monitor writes to DB, app uses session state
- Result: both fire within seconds of each other for every signal

### Gap Fill / ORB: Stateless rules fire every poll
- `check_gap_fill()` fires whenever `gap_info["is_filled"] == True` — stateless, re-computes from bars
- `check_opening_range_breakout()` fires whenever `bar["Close"] > or_high` — condition, not event
- `evaluate_rules()` has `fired_today` dedup (line 1371), but app.py builds it from session state which can be empty

### Cooldown: Volatile storage
- app.py stores cooldown in `st.session_state["cooldown"]` — lost on page refresh or between processes
- monitor.py stores in module-level `_cooldown` dict — lost on process restart
- Neither is persistent

## Acceptance Criteria

- [ ] Each unique signal sends at most 1 SMS and 1 email per session
- [ ] Gap Fill sends 1 notification when gap fills, never again
- [ ] ORB sends 1 notification on first break above OR high, never again
- [ ] After a stop-out, no BUY signals fire for that symbol for COOLDOWN_MINUTES
- [ ] Cooldown persists across page refreshes and process restarts
- [ ] BUY signals suppressed (not just cautioned) when SPY regime is TRENDING_DOWN
