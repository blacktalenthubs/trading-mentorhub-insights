# Tasks: Swing Scanner Price Refresh

**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)
**Created**: 2026-04-08

## User Story Map

| Story | Priority | Description | FRs |
|-------|----------|-------------|-----|
| US1 | P1 | Premarket price refresh + gap detection | FR-1, FR-3 |
| US2 | P1 | Condition-based entry format | FR-2, FR-4 |
| US3 | P2 | Telegram premarket summary | FR-5 |
| US4 | P2 | Signal Feed refreshed display | FR-6 |

---

## Phase 1: Setup — Database Columns

- [x] T001 Add `setup_level REAL`, `setup_condition TEXT`, `refreshed_entry REAL`, `refreshed_stop REAL`, `refreshed_at TIMESTAMP`, `gap_invalidated INTEGER DEFAULT 0`, `gap_pct REAL` columns to alerts table DDL in `db.py`
- [x] T002 [P] Add `setup_level REAL`, `setup_condition TEXT`, `refreshed_entry REAL` columns to swing_trades table DDL in `db.py`
- [x] T003 Add ALTER TABLE migrations for all new columns in `api/app/main.py` lifespan (try/except for both SQLite and Postgres)

## Phase 2: Foundational — Setup Level in Swing Rules (PROTECTED)

**Impact Analysis**: Only ADDS `setup_level` and `setup_condition` fields to AlertSignal returns. Does NOT change any trigger conditions, thresholds, or evaluation logic. All existing tests continue to pass because AlertSignal accepts extra kwargs.

- [x] T004 Read `analytics/swing_rules.py` completely and document all check_ function signatures (impact analysis prerequisite)
- [x] T005 Add `setup_level` and `setup_condition` kwargs to AlertSignal returns in `check_swing_pullback_20ema()` in `analytics/swing_rules.py` — setup_level=ema20, condition="Pullback to rising 20 EMA"
- [x] T006 [P] Add `setup_level` and `setup_condition` to `check_swing_ema_crossover_5_20()` in `analytics/swing_rules.py` — setup_level=ema20, condition="EMA5/20 bullish crossover"
- [x] T007 [P] Add `setup_level` and `setup_condition` to `check_swing_200ma_reclaim()` in `analytics/swing_rules.py` — setup_level=ma200, condition="Close reclaims 200 MA"
- [x] T008 [P] Add `setup_level` and `setup_condition` to `check_swing_200ma_hold()` and `check_swing_50ma_hold()` in `analytics/swing_rules.py`
- [x] T009 [P] Add `setup_level` and `setup_condition` to `check_swing_weekly_support()`, `check_swing_rsi_30_bounce()`, `check_swing_candle_patterns()` in `analytics/swing_rules.py`
- [x] T010 Modify `alerting/swing_scanner.py` to pass `setup_level` and `setup_condition` when calling `record_alert()` — store in the alerts table
- [x] T011 Run full test suite to verify no regressions: `python3 -m pytest tests/ -v` — 656 passed

## Phase 3: User Story 1 — Premarket Refresh + Gap Detection (P1)

**Goal**: At 9:00 AM ET, refresh all pending swing alerts with current premarket prices. Detect and flag gaps >5%.

**Test Criteria**: Swing alerts viewed after 9:00 AM have refreshed_entry set; alerts with >5% gap are marked invalidated.

- [x] T012 [US1] Create `alerting/swing_refresher.py` with `fetch_premarket_price(symbol) -> float | None` — uses yfinance for equities, Coinbase for crypto. Returns None on failure.
- [x] T013 [US1] Implement `refresh_pending_swing_alerts(session_factory) -> dict` in `alerting/swing_refresher.py` — queries today's swing alerts, fetches premarket price, computes gap from setup_level, invalidates >5% gaps, refreshes others
- [x] T014 [US1] Write tests in `tests/test_swing_refresher.py` — 8 tests covering gap detection, refresh, invalidation, formatting, edge cases
- [x] T015 [US1] Add `_premarket_swing_refresh` scheduler job at 9:00 AM ET in `api/app/main.py`

## Phase 4: User Story 2 — Condition-Based Entry Format (P1)

**Goal**: Swing alerts show level-based conditions instead of fixed stale prices.

**Test Criteria**: Alert messages contain setup condition and key level, not just yesterday's close.

- [ ] T016 [US2] Modify swing alert message format in `alerting/notifier.py` — if `setup_condition` is present, format as "Setup: {condition} ({setup_level})" instead of just "Reason: {alert_type}". Entry line becomes "Entry: near {setup_level_name} (${setup_level})"
- [ ] T017 [US2] Modify `_maybe_create_trade()` in `alerting/swing_scanner.py` to pass `setup_level` and `setup_condition` to `create_swing_trade()`
- [ ] T018 [US2] Write test in `tests/test_swing_refresher.py` — test that formatted message includes setup_condition and setup_level

## Phase 5: User Story 3 — Telegram Premarket Summary (P2)

**Goal**: One consolidated Telegram message with all refresh results.

**Test Criteria**: Users receive a single message with counts and material changes.

- [ ] T019 [US3] Implement `format_refresh_summary(summary: dict) -> str` in `alerting/swing_refresher.py` — formats "SWING PREMARKET UPDATE: N alerts refreshed, M invalidated. [symbol details]"
- [ ] T020 [US3] Add Telegram send after refresh in the scheduler job in `api/app/main.py` — only sends if material changes (>1% price diff or invalidations). Sends per-user to those with swing positions.
- [ ] T021 [US3] Write test for `format_refresh_summary()` — test contains counts, symbol names, gap percentages

## Phase 6: User Story 4 — Signal Feed Display (P2)

**Goal**: Frontend shows refreshed prices and invalidation warnings.

- [ ] T022 [US4] Update alert card rendering in Signal Feed (`web/src/pages/TradingPage.tsx` or relevant component) — if `refreshed_entry` exists, show as primary price with "(was $659)" and "Updated 9 AM" badge
- [ ] T023 [US4] Add invalidation display — if `gap_invalidated`, show alert dimmed with "Setup invalidated — {gap_pct}% gap" warning text
- [ ] T024 [US4] Show `setup_condition` as subtitle under alert type in Signal Feed cards

## Phase 7: Entries First — Clean Signal Pipeline (P0)

**Goal**: Strip the system down to entries + trade management only. Remove all suppression. Record everything to DB.

**7A: Disable informational alerts**
- [ ] T029 Disable NOTICE alerts in ENABLED_RULES in `alert_config.py`: `monthly_ema_touch`, `resistance_prior_high`, `inside_day_forming`, `hourly_resistance_approach`, `resistance_prior_low`, `monthly_low_test`, `weekly_low_test`, `swing_watch`
- [ ] T030 Disable informational SELL alerts: `pdh_rejection`, `ma_resistance`, `prior_day_low_resistance`, `weekly_high_resistance`, `prior_day_low_breakdown`, `monthly_high_resistance`, `monthly_low_breakdown`, `weekly_low_breakdown`
- [ ] T031 Keep enabled: `stop_loss_hit`, `target_1_hit`, `target_2_hit`, `_t1_notify` (trade management)

**7B: Remove gate suppression — fire at key levels regardless**
- [ ] T032 Remove SPY gate suppression from `evaluate_rules()` — delete gate logic at lines 8085-8157 in intraday_rules.py. Key level rules fire at key levels, period.
- [ ] T033 Remove trending_down filter (line 7930), range filter (line 7975), SPY above VWAP SHORT suppression (line 7959)
- [ ] T034 Keep opening wait (first 15 min) — this is a data quality guard, not a regime filter
- [ ] T035 Keep noise filter (low volume) and staleness filter — but change to tag `signal.suppressed_reason` instead of dropping. Record all signals to DB. Only check suppressed flag at Telegram notification time.

**7C: Re-enable VWAP rules**
- [ ] T036 Uncomment `vwap_reclaim` and `vwap_bounce` in ENABLED_RULES in `alert_config.py`
- [ ] T037 Review VWAP config thresholds (VWAP_RECLAIM_MAX_DISTANCE_PCT, VWAP_BOUNCE_TOUCH_PCT) — verify reasonable

**7D: Fix per-user duplication**
- [ ] T038 Deduplicate alerts globally, not per-user — if `(symbol, alert_type, price_level)` already fired this session, skip for all users

## Phase 8: Crypto Data Fix (P0, from AF-1)

**Goal**: `fetch_prior_day` for crypto uses Coinbase daily candles. Prevents wrong PDH/PDL.

- [ ] T039 Add `_fetch_coinbase_daily(symbol, days=5) -> pd.DataFrame` in `analytics/intraday_data.py`
- [ ] T040 Modify `fetch_prior_day()` crypto path — Coinbase daily first, yfinance fallback. Simplify hourly gap fix.
- [ ] T041 Write tests for Coinbase daily fetch

## Phase 9: Swing Rule Fixes (P1, from AF-2, AF-3)

**Goal**: Fix false 200MA reclaim, add 50MA/100MA reclaim rules.

- [ ] T042 Add MA structure guard to `check_swing_200ma_reclaim()` — only fire when `MA200 > MA50`
- [ ] T043 Add `check_swing_50ma_reclaim()` — fire when `prev_close < MA50 AND close > MA50 AND MA50 > MA20`
- [ ] T044 Add `check_swing_100ma_reclaim()` — fire when `prev_close < MA100 AND close > MA100 AND MA100 > MA50`
- [ ] T045 Add `SWING_50MA_RECLAIM` and `SWING_100MA_RECLAIM` to AlertType enum, register in `evaluate_swing_rules()`
- [ ] T046 Write tests for MA structure guard and new reclaim rules

## Phase 10: Entry Cleanup (P1, from AF-4, AF-5, AF-6)

**Goal**: Cap active entries, fix rapid-fire contradictions.

- [ ] T047 Active entry cap — max 3 per symbol, auto-expire after 5 trading days
- [ ] T048 Expire active entries on stop_loss_hit
- [ ] T049 Swing refresher: label as "UPDATED", skip entries > 3 days old
- [ ] T050 Opposing signal cooldown — 2 min window after STOP before new BUY
- [ ] T051 Write tests for entry cap, expiry, opposing signal cooldown

## Phase 11: Polish & Validation

- [ ] T052 Run full test suite: `python3 -m pytest tests/ -v`
- [ ] T053 Test locally with live data — verify entries fire at key levels, no gate suppression
- [ ] T054 Push to production, monitor for 1 trading day, review signal quality

---

## Dependencies

```
Phase 1 (DB columns) → Phase 2 (setup_level in rules)    [DONE]
                          ↓
Phase 3 (US1: refresh) ← depends on Phase 2              [DONE]
Phase 4 (US2: format) ← depends on Phase 2
Phase 5 (US3: Telegram) ← depends on Phase 3
Phase 6 (US4: frontend) ← depends on Phase 3

Phase 7 (Crypto data)   ← independent, P0 priority
Phase 8 (Swing rules)   ← independent, P1 priority
Phase 9 (Entry cleanup) ← independent, P1 priority

Phase 10 (Polish) ← depends on all
```

## Parallel Execution

**Phase 2** (after T004 impact analysis):
- T005-T009 can all run in parallel (different check_ functions in same file, but independent sections)

**Phase 6** (all frontend tasks):
- T022 + T023 + T024 can run in parallel (different display concerns in same component)

**Phases 7 + 8 + 9** (audit fixes):
- All three can run in parallel — independent concerns (data layer, rule logic, entry management)
- Phase 7 (crypto data) is P0 — blocks correct crypto alerts
- T032-T037 (swing rules) are isolated changes to swing_rules.py
- T038-T042 (entry cleanup) are isolated changes to monitor.py

## Implementation Strategy

**MVP (DONE)**: Phase 1 + 2 + 3 = DB columns + setup_level in rules + premarket refresh
- ✅ Delivered: stale prices get refreshed at 9 AM with gap detection

**Hotfix (next — from April 9 audit)**: Phase 7 + 8 = Clean pipeline + crypto data fix
- P0: Disable informational alerts, remove gate suppression, re-enable VWAP, fix duplication
- P0: Coinbase daily data for crypto `fetch_prior_day`

**Iteration 2**: Phase 9 + 10 = Swing rules + entry cleanup
- P1: 200MA guard + 50MA/100MA reclaim rules
- P1: Active entry cap + opposing signal cooldown

**Iteration 3**: Phase 4 + 5 = Condition-based format + Telegram summary

**Iteration 4**: Phase 6 + 11 = Frontend + polish

---

**Legend**:
- `T###` — Task ID (sequential)
- `[P]` — Parallelizable
- `[US#]` — User story label
- PROTECTED files require impact analysis + approval before modification
