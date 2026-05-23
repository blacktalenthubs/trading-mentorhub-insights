# Quickstart — Spec 58 End-to-End Validation

**Date**: 2026-05-22
**Audience**: The trader, validating the redesigned alert system after deploy.

This is the smoke-test playbook. Run after Phase B (backend deploy) is live.

---

## Pre-deploy checklist

- [ ] `pine_scripts/active/ma_ema_daily.pine` updated and re-saved in TradingView Pine Editor
- [ ] Pine alert re-bound to the updated script (TradingView caches the old version until you re-add the alert)
- [ ] `api/app/routers/tv_webhook.py` updated with confluence detection
- [ ] `api/app/models/alert_type_config.py` updated (new `*_held` types added; default_enabled=false for retired types)
- [ ] DB migration ran on startup (check Railway logs for "Spec 58 — retire open-line and breakout-into-resistance entry types")
- [ ] Railway worker restarted (so the new scheduler/webhook code is active)

---

## Smoke test 1 — Uptrend gate (FR-001, SC-002)

**Goal**: Confirm no entry fires on a stock with overhead MAs.

1. Open TradingView → set chart to **META** (any timeframe with the MA suite loaded — META has 7+ overhead MAs).
2. Wait for an intraday bar that triggers the old MA-bounce condition (price tagging a MA and closing above).
3. Check Telegram + the signal feed in the web UI.

**Expected**:
- **No Telegram alert** for META.
- DB row in `alerts` with `suppressed_reason='uptrend_gate_failed'` AND `message` containing `overhead_mas: [EMA 100, EMA 200, SMA 200]` (or similar).
- Visible in the web feed under the "Not routed" filter, NOT in the routed feed.

**Failure mode**: If META fires to Telegram → uptrend gate not enforced in Pine OR webhook isn't honoring `uptrend_pass=false`. Roll back.

---

## Smoke test 2 — Clean uptrend with confluence (FR-013, the AVGO case)

**Goal**: Confirm a confluent alert is annotated, not duplicated.

1. Wait for a stock in your watchlist with **clean uptrend** (zero overhead MAs) to bounce off a key MA that's near another support level (PDL/PWL or MTD AVWAP within 1%).
2. Or, force it on a test stock by setting the chart to a recently-bounced name (the AAOI / AVGO setups we analyzed tonight will recur).

**Expected**:
- **Exactly ONE Telegram alert** for that symbol.
- Message includes a `Confluence:` line listing the other level(s) by label and price.
- DB row has the full confluence text in `Alert.message`.

**Failure mode**:
- Two separate alerts fire (one MA bounce, one PDL reclaim) → confluence dedup not running. Check `_format_confluence` is being called.
- One alert fires but no `Confluence:` line → `nearby_levels` empty or band logic broken.

---

## Smoke test 3 — Retired open-line entry (FR-007, SC-003)

**Goal**: Confirm no entry fires from the open line.

1. Pick a chop day on any watchlist symbol. Watch price cross the day's open line multiple times intraday.

**Expected**:
- **No `tv_open_reclaimed` / `tv_open_held` / `tv_open_wick_reclaim` alerts** in Telegram or the routed feed.
- The open-line **plot** is still visible on the chart (visual reference preserved).

**Failure mode**: Open-line alerts firing → Pine `alertcondition()` calls weren't removed, or `alert_type_config` rows still have `enabled=true`. Check both.

---

## Smoke test 4 — No breakout-into-resistance long (FR-005, SC-003)

**Goal**: Confirm no long fires when price rises into a PDH from below.

1. Find a stock where intraday price approaches the PDH from below (was below it, now climbing into it).
2. Wait for the close above PDH.

**Expected**:
- **No `tv_staged_pdh_break` long alert** fires.
- If the close above PDH eventually retraces, then a second push back up to the now-reclaimed PDH (from above) WOULD fire `tv_staged_pdh_held` — that's the correct Buy-2 pattern.

**Failure mode**: `tv_staged_pdh_break` LONG alert fires → Pine still has the old break-as-entry logic. Replace with `tv_staged_pdh_held` logic (level held from above).

---

## Smoke test 5 — Higher-high chop gate (FR-006)

**Goal**: Confirm Buy-2 continuation alerts stop firing after price stops making new session highs.

1. Watch a stock that runs strong in the morning (multiple new session highs) then chops sideways for 30+ minutes.
2. While it's chopping, watch for any pullback-to-support that *would* trigger a Buy-2 (e.g., pullback to a held PDH).

**Expected**:
- During the morning run → Buy-2 alerts fire normally on valid pullbacks.
- After 30 min without a new session high → Buy-2 alerts **stop firing** until a new session high prints.

**Failure mode**: Buy-2 alerts firing in the afternoon chop → chop gate not enforced. Check Pine `lastNewHighBar` timer logic.

---

## Validation week — Success Criteria check

Run for **one week** of normal trading sessions. Use the ✓/✗ scorecard daily.

### SC-001 (≤ 6 entry rules)
- Open Settings → Alert Types → count enabled entry rules. Should be ≤ 6 family heads (per-MA suffixes count as ONE family).

### SC-002 (no fires on downtrends)
- At end of week, query the DB: `SELECT count(*) FROM alerts WHERE created_at >= NOW() - INTERVAL '7 days' AND direction='BUY' AND suppressed_reason='uptrend_gate_failed';`
- Count should be substantial (the noise that's now correctly suppressed).

### SC-003 (no open-line / no breakout-into-resistance)
- `SELECT count(*) FROM alerts WHERE created_at >= NOW() - INTERVAL '7 days' AND alert_type IN ('tv_open_reclaimed', 'tv_open_held', 'tv_open_wick_reclaim', 'tv_staged_pdh_break');`
- Count should be **zero** (Pine no longer fires these).

### SC-004 (≥ 70% trader-judged usable)
- Daily ✓/✗ marks. End of week: `(✓ count) / (total marked) >= 0.70`.

### SC-005 (≥ 50% alert volume drop)
- Compare last week's volume to a representative pre-deploy week. The 8-alert day from 2026-05-22 should land at 2-3 alerts under the new rules (the 6 blocked by uptrend gate would not fire).

### SC-006 (alert names rule + support)
- Eyeball check — every Telegram alert mentions the rule and the level.

---

## Rollback plan

If validation fails materially:

1. **Pine rollback** — Pine Editor → click the script's version history → restore the prior version → re-add to chart. Restores old behavior immediately for *new* alerts.
2. **Backend rollback** — Railway → previous deploy → redeploy. Webhook stops parsing new payload fields (treats as legacy). Retired types stay disabled unless explicitly re-enabled in DB.
3. **Alert type re-enable** — `UPDATE alert_type_config SET enabled=true WHERE alert_type IN (...)` for any retired type that turned out to be valuable.

Rollback restores volume to baseline within one bar cycle (15-30 min for daily-MA scripts).

---

## When to declare victory

After **one full week** of clean validation (all five smoke tests + all six SC checks pass), the spec is done. Move to the **cleanup pass** (Phase D in `research.md` R9):

- Delete `analytics/swing_scanner.py` + `analytics/swing_quality.py`
- Remove the 15-min `_swing_scan` job from `api/app/main.py`
- Delete the 9 `swing_*` types from `alert_type_config.py`
- Delete `api/app/routers/swing.py` + `api/app/schemas/swing.py`
- Delete `web/src/pages/SwingTradesPage.tsx` (or repurpose to render daily-MA filtered alerts)
- Mark spec 56 as **superseded by spec 58** in its header

That's the full lifecycle.
