# V2 Production Cutover Plan

> **Goal:** Deploy V2 (FastAPI + React) to production on Railway with zero alert downtime and safe rollback to V1 (Streamlit) if issues arise.

---

## Current Production State

```
┌─────────────────┐     ┌───────────────┐
│ Railway Worker   │────▶│ Railway       │
│ worker.py (V1)   │     │ Postgres      │
│ Single-user      │     │ (shared DB)   │
└────────┬────────┘     └───────┬───────┘
         │                      │
    ┌────▼──────┐        ┌──────▼──────┐
    │ Telegram  │        │ Streamlit   │
    │ Bot (V1)  │        │ Cloud (V1)  │
    │ Group msg │        │ Dashboard   │
    └───────────┘        └─────────────┘
```

**Risks:**
- V1 worker and V2 monitor use the SAME Telegram bot token — both running = duplicate alerts
- V1 Postgres schema lacks user_id on some tables — V2 expects it
- DNS change takes 5-60 min to propagate

---

## Cutover Phases

### Phase 0: Pre-Cutover Performance Test (1 hour)

Run locally against a copy of production data to validate V2 handles real load.

**Test 1: Monitor Poll Throughput**
```bash
# Simulate 50 Pro users with 10 symbols each
python3 tests/perf_monitor_load.py --users 50 --symbols-per-user 10
```
- Measures: poll cycle duration, symbols fetched, alerts generated
- Pass: poll completes in <90 seconds (half of 3-min interval)
- Fail: >120 seconds = need to optimize dedup or batch yfinance calls

**Test 2: Alert Delivery Latency**
```bash
# Measure time from signal detection to Telegram delivery
python3 tests/perf_alert_latency.py --count 10
```
- Measures: detect → record → notify round-trip
- Pass: <10 seconds average
- Fail: >30 seconds = notification pipeline bottleneck

**Test 3: Concurrent API Load**
```bash
# Simulate 50 concurrent users hitting key endpoints
python3 tests/perf_api_load.py --users 50 --duration 60
```
- Endpoints tested: `/scanner/scan`, `/alerts/today`, `/watchlist`, `/charts/ohlcv`
- Measures: p50/p95/p99 latency, error rate
- Pass: p95 <2 seconds, 0% errors
- Fail: >5 second p95 or >1% errors

**Test 4: Database Connection Pool**
```bash
# Hammer Postgres with concurrent read/writes
python3 tests/perf_db_pool.py --connections 30 --duration 30
```
- Measures: connection wait time, query latency, pool exhaustion
- Pass: no pool exhaustion, p95 query <100ms
- Fail: connection errors or >500ms queries

---

### Phase 1: Database Migration (30 min)

**Before touching production, take a full DB backup:**
```bash
# Railway CLI
railway run pg_dump -Fc > backup_pre_v2_$(date +%Y%m%d).dump
```

**Schema changes needed:**
1. V2 SQLAlchemy models auto-create tables on startup (`Base.metadata.create_all`)
2. Existing tables (alerts, watchlist, active_entries, cooldowns) already have user_id — safe
3. New tables (if any) will be created automatically

**Data backfill:**
- Verify all existing users have subscriptions: `SELECT u.id, s.tier FROM users u LEFT JOIN subscriptions s ON s.user_id = u.id`
- Create missing subscriptions (default to 'free')
- Verify watchlist data is user-scoped

---

### Phase 2: Deploy V2 API (15 min)

**On Railway, create a NEW service (don't modify V1):**

```
┌─────────────────┐     ┌─────────────────┐
│ V1 Worker        │     │ V2 API          │  ← NEW
│ (keep running)   │     │ FastAPI + React  │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
              ┌──────▼──────┐
              │ Railway     │
              │ Postgres    │
              │ (shared)    │
              └─────────────┘
```

**Steps:**
1. Create new Railway service: `v2-api`
2. Set environment variables (copy from V1 + add new ones):
   ```
   DATABASE_URL=<same postgres>
   TELEGRAM_BOT_TOKEN=<same token>
   JWT_SECRET=<generate new production secret>
   ANTHROPIC_API_KEY=<same>
   SQUARE_ACCESS_TOKEN=<production>
   SQUARE_APP_ID=<production>
   SQUARE_LOCATION_ID=<production>
   ```
3. Deploy: `railway up` or push to linked branch
4. Verify: `curl https://v2-api.railway.app/healthz`
5. **DO NOT start the V2 background monitor yet** — V1 worker is still sending alerts

---

### Phase 3: Build & Deploy Frontend (15 min)

```bash
cd web
npm run build
# Output in web/dist/
```

**Option A: Serve from FastAPI (simplest)**
- Add `StaticFiles` mount in FastAPI to serve `web/dist/`
- Single Railway service serves both API + frontend

**Option B: Separate static hosting (Vercel/Netlify)**
- Deploy `web/dist/` to Vercel
- Set `VITE_API_URL` to point at Railway V2 API
- Better CDN performance but more moving parts

**Recommended: Option A** for simplicity at launch. Move to B later for CDN.

---

### Phase 4: Smoke Test V2 (30 min)

**With V1 worker still running (it owns alerts), test V2 frontend + API:**

1. Access V2 at its Railway URL (not production domain yet)
2. Login with your account
3. Verify: Dashboard loads, watchlist shows, alerts display
4. Verify: Settings page works, Telegram shows connected
5. Verify: Trading page charts load, scanner runs
6. Verify: Signal Library loads with live stats
7. **DO NOT test "Took" button** — it writes to shared DB, V1 worker might conflict

---

### Phase 5: Monitor Switchover — THE CRITICAL MOMENT (5 min)

This is the only moment with risk. We're swapping which process sends Telegram alerts.

```
BEFORE:  V1 Worker → Telegram     V2 API → Dashboard only
AFTER:   V1 Worker → STOPPED      V2 API → Telegram + Dashboard
```

**Steps (execute in rapid sequence):**

1. **Stop V1 worker on Railway** (Deployments → stop service)
   - Alerts stop flowing. Clock is ticking.

2. **Enable V2 monitor** — it starts automatically with the API (already configured in `lifespan`)
   - V2 monitor picks up on next 3-min cycle
   - Maximum alert gap: 3 minutes

3. **Verify V2 monitor is polling:**
   ```bash
   railway logs v2-api | grep "Poll complete"
   ```
   Should see: `Poll complete: X alerts across Y users`

4. **Send test alert** to verify Telegram delivery:
   ```bash
   railway run python3 -c "
   from alerting.notifier import notify_user
   from analytics.intraday_rules import AlertSignal, AlertType
   signal = AlertSignal(symbol='TEST', alert_type=AlertType.MA_BOUNCE_20, direction='BUY', price=100, entry=100, stop=99, target_1=102, target_2=104, confidence='test', score=0, message='V2 CUTOVER TEST')
   notify_user(signal, {'telegram_enabled': True, 'telegram_chat_id': '455162498', 'email_enabled': False})
   "
   ```

5. **Check your Telegram** — you should receive the test alert.

**If anything fails:** Restart V1 worker immediately (Railway → redeploy). V1 takes over within 1 minute.

---

### Phase 6: DNS Cutover (5 min)

Once V2 is confirmed working with alerts flowing:

1. Update DNS: `tradesignalwithai.com` → V2 Railway service URL
2. Wait for propagation (check with `dig tradesignalwithai.com`)
3. Verify production URL loads V2 frontend

**Keep V1 Streamlit running** at its old URL for 1 week as a read-only fallback.

---

### Phase 7: Post-Cutover Monitoring (24 hours)

**First hour — watch closely:**
- [ ] Monitor logs: `railway logs v2-api --tail`
- [ ] Verify alerts fire during market hours for all Pro users
- [ ] Verify each user gets ONLY their watchlist alerts (no cross-contamination)
- [ ] Check Telegram delivery for multiple users
- [ ] Verify dashboard shows correct data

**First day:**
- [ ] Monitor poll cycle duration — should be stable
- [ ] Check Postgres connection count (`SELECT count(*) FROM pg_stat_activity`)
- [ ] Verify no duplicate alerts
- [ ] Check error logs for any 500s

**After 1 week:**
- [ ] Shut down V1 Streamlit
- [ ] Remove V1 worker service from Railway
- [ ] Update memory/docs to reflect V2 is production

---

## Rollback Procedure

**If V2 has critical issues after cutover:**

| Step | Action | Time |
|------|--------|------|
| 1 | Stop V2 API service on Railway | 30 sec |
| 2 | Restart V1 worker on Railway | 1 min |
| 3 | Revert DNS to V1 Streamlit URL | 5 min |
| 4 | Verify V1 alerts are flowing | 3 min |
| **Total** | | **~10 min** |

**Data safety:** Both V1 and V2 write to the same Postgres. Alerts recorded by V2 are visible to V1 (same table schema). No data loss on rollback.

**What you lose on rollback:**
- Multi-user alerts (V1 is single-user admin only)
- React frontend (back to Streamlit)
- Signal Library, onboarding wizard, billing page

**What you keep:**
- All alert data (shared DB)
- User accounts
- Watchlists
- Telegram links

---

## Pre-Cutover Checklist

```
Before starting:
- [ ] Full Postgres backup taken
- [ ] Performance tests pass (Phase 0)
- [ ] V2 tested locally with production DB snapshot
- [ ] Square billing configured (if launching paid tiers)
- [ ] All users have subscriptions (at least 'free')
- [ ] JWT_SECRET set to production value (not "change-me-in-production")
- [ ] CORS_ORIGINS includes production domain
- [ ] Telegram bot token same as V1

During cutover:
- [ ] V1 worker stopped
- [ ] V2 monitor confirmed polling
- [ ] Test Telegram alert received
- [ ] DNS updated
- [ ] Production URL loads V2

After cutover:
- [ ] Monitor for 1 hour
- [ ] Verify multi-user alert routing
- [ ] Check Postgres health
- [ ] No duplicate alerts
```

---

## Timeline Estimate

| Phase | Duration | Risk |
|-------|----------|------|
| 0. Perf test | 1 hour | None |
| 1. DB migration | 30 min | Low |
| 2. Deploy V2 API | 15 min | Low |
| 3. Build frontend | 15 min | Low |
| 4. Smoke test | 30 min | Low |
| 5. Monitor switch | 5 min | **HIGH** |
| 6. DNS cutover | 5 min | Medium |
| 7. Post-monitoring | 24 hours | Watching |
| **Total active work** | **~2.5 hours** | |

Maximum alert downtime: **3 minutes** (one poll cycle gap between V1 stop and V2 first poll).
