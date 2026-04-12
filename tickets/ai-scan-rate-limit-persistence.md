# AI Scan Rate Limit — Persist Counter to DB

**Priority**: High (blocks mid-market-hours deploys)
**Created**: 2026-04-12
**Owner**: TBD

## Problem

AI scan rate limit counters are stored in-memory in the worker (`_user_delivered_count`, `_user_limit_notified` in `analytics/ai_day_scanner.py`). When Railway redeploys the worker mid-session:

1. Free users who already hit their 7-alert cap get a fresh 7 alerts
2. The "limit reached" Telegram notification fires again (already sent today)
3. Dashboard banner disappears and reappears

**Impact**: We cannot safely deploy worker changes during market hours without resetting free tier caps, defeating the rate limit.

## Current State

- `_user_delivered_count: dict[tuple[int, str], int]` — in-memory
- `_user_limit_notified: set[tuple[int, str]]` — in-memory
- Both cleared on `_day_session != session` check (new trading day)

## Proposed Solution

Persist the counters to a lightweight DB table so they survive restarts.

### Option A — Reuse `usage_limits` table (recommended)
The existing `usage_limits` table already tracks per-user per-day feature usage (used by AI Coach rate limiting).

Schema (already exists):
```sql
usage_limits (user_id, feature, usage_date, usage_count)
```

**Changes:**
- Replace `_user_delivered_count[(uid, session)] += 1` with `INSERT ... ON CONFLICT UPDATE` on `usage_limits` (feature='ai_scan_alerts')
- On startup, counters auto-recover by querying `usage_limits` for today
- Replace `_user_limit_notified` set with a boolean column or a second feature row (e.g., `ai_scan_limit_notified`)

### Option B — Dedicated in-memory + nightly sync
Keep in-memory but also write-through to a `scan_rate_limit` table. More code, less clean.

## Implementation Plan

1. Add a helper `_increment_user_delivery(db, uid, session)` that does the `ON CONFLICT` upsert on `usage_limits`
2. Add a helper `_get_user_delivery_count(db, uid, session) -> int` that reads the counter
3. Add a helper `_mark_limit_notified(db, uid, session) -> bool` that sets a flag row, returns `True` if not previously set (atomic check-and-set)
4. Replace in-memory reads/writes in `day_scan_cycle` with these DB calls
5. Update `get_user_ai_scan_count()` (exposed for `/auth/usage` endpoint) to query DB
6. Delete `_user_delivered_count` and `_user_limit_notified` globals
7. Tests:
   - Counter persists across worker simulated restart
   - "Limit reached" message fires exactly once per user per day even if scan cycle runs twice
   - Counter resets on new session date

## Acceptance

- [ ] Worker can be redeployed mid-session without resetting free user caps
- [ ] "Limit reached" Telegram fires exactly once per user per day
- [ ] Dashboard banner reflects true cap state after worker restart
- [ ] All existing scanner tests still pass

## Related

- `analytics/ai_day_scanner.py` — rate limit logic
- `api/app/routers/auth.py` — `/auth/usage` endpoint surfaces count
- `web/src/pages/DashboardPage.tsx` — banner
- Commit `64451a3` — introduced in-memory rate limit
