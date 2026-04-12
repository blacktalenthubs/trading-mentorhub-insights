# Tasks: AI-Powered Multi-Timeframe Chart Analysis

**Spec**: [spec.md](spec.md)
**Plan**: [plan.md](plan.md)
**Created**: 2026-04-07

## User Story Map

| Story | Priority | Description | FRs |
|-------|----------|-------------|-----|
| US1 | P1 | Analyze a chart and get a structured trade plan | FR-1, FR-2 |
| US2 | P1 | Multi-timeframe confluence scoring | FR-3, FR-4 |
| US3 | P2 | Historical pattern win-rate references | FR-5 |
| US4 | P2 | Alert auto-analysis (AI Take on alerts) | FR-6 |
| US5 | P3 | Save analyses to journal + track outcomes | FR-7 |
| US6 | P3 | Usage limits by tier | FR-8 |

---

## Phase 1: Setup

- [x] T001 Add `chart_analyses` table DDL to `init_db()` in `db.py`
- [x] T002 [P] Create SQLAlchemy ORM model in `api/app/models/chart_analysis.py`
- [x] T003 [P] Add `auto_analysis_enabled` column to User model in `api/app/models/user.py`
- [x] T004 [P] Add `AnalyzeChartRequest` and `ChartAnalysisResponse` schemas to `api/app/schemas/intel.py`
- [x] T005 Add migration for `auto_analysis_enabled` in `api/app/main.py` lifespan startup
- [x] T006 Import new model in `api/app/models/__init__.py`

## Phase 2: Foundational — Fix MTF Infrastructure

- [x] T007 Add `get_mtf_analysis(symbol) -> dict` wrapper in `analytics/intel_hub.py` that calls `get_daily_bars()`, `get_weekly_bars()`, `analyze_daily_setup()`, `analyze_weekly_setup()` internally and returns structured dict with `daily`, `weekly`, `alignment`, `confluence_score`
- [x] T008 Fix `GET /intel/mtf/{symbol}` endpoint in `api/app/routers/intel.py` to call `get_mtf_analysis()` instead of broken `build_mtf_context()` with wrong args
- [x] T009 Write tests for `get_mtf_analysis()` in `tests/test_mtf_analysis.py` — test returns dict, handles missing data, computes alignment correctly

## Phase 3: User Story 1 — Core Chart Analysis (P1)

**Goal**: User clicks "Analyze Chart" on any symbol/timeframe and receives a structured trade plan within 5 seconds.

**Test Criteria**: Given a symbol and timeframe, the system returns a trade plan with all required fields (direction, entry, stop, targets, R:R, confidence, confluence_score, reasoning).

- [x] T010 [US1] Create `analytics/chart_analyzer.py` with timeframe hierarchy mapping: `TF_HIERARCHY = {"1m": ["5m", "1H"], "5m": ["1H", "D"], "15m": ["1H", "D"], "30m": ["D", "W"], "1H": ["D", "W"], "4H": ["D", "W"], "D": ["W", "M"], "W": ["M", "M"]}`
- [x] T011 [US1] Implement `assemble_analysis_context(symbol, timeframe, bars=None) -> dict` in `analytics/chart_analyzer.py` — fetches user TF bars (if not provided), fetches 2 higher TFs from hierarchy, computes MAs + RSI for each, calls `get_mtf_analysis()` for daily/weekly, fetches SPY context and S/R levels
- [x] T012 [US1] Implement `build_analysis_prompt(context: dict) -> str` in `analytics/chart_analyzer.py` — constructs system prompt with: OHLCV bars (last 50-100), indicators, higher TF summaries, S/R levels, explicit structured output format instructions (direction, entry, stop, T1, T2, R:R, confidence, confluence, timeframe_fit, key_levels, reasoning)
- [x] T013 [US1] Implement `parse_trade_plan(ai_text: str) -> dict` in `analytics/chart_analyzer.py` — extracts structured fields from AI response using section markers; returns dict with all trade plan fields; handles "No Trade" responses
- [x] T014 [US1] Write unit tests in `tests/test_chart_analyzer.py` — test `assemble_analysis_context` fetches correct higher TFs, test `build_analysis_prompt` includes all sections, test `parse_trade_plan` extracts fields from sample responses, test "No Trade" parsing
- [x] T015 [US1] Add `POST /intel/analyze-chart` SSE endpoint in `api/app/routers/intel.py` — validates request, calls `assemble_analysis_context()` + `build_analysis_prompt()`, streams via `ask_coach()`, emits plan/reasoning/done events
- [x] T016 [US1] Add 5-minute in-memory cache for analysis results keyed by `(user_id, symbol, timeframe)` in `analytics/chart_analyzer.py`

## Phase 4: User Story 2 — Multi-Timeframe Confluence (P1)

**Goal**: Every analysis includes a confluence score (0-10) and adapts stops/targets to the user's timeframe.

**Test Criteria**: Confluence score correctly reflects TF alignment; scalp analysis has tight stops, swing analysis has wide stops.

- [x] T017 [US2] Implement `compute_confluence_score(user_tf_data: dict, higher_tf_analyses: list[dict]) -> tuple[int, str]` in `analytics/chart_analyzer.py` — scores trend alignment (0-4), level proximity (0-3), momentum alignment (0-3); returns (score, explanation)
- [x] T018 [US2] Add timeframe-specific parameters to `build_analysis_prompt()` in `analytics/chart_analyzer.py` — scalp (1m-5m): "tight stops 0.1-0.3%, targets within session", day trade (15m-1H): "session stops, VWAP matters", swing (4H-D): "multi-day, 1-3% stops", position (W-M): "weekly structure, major levels only"
- [x] T019 [US2] Write unit tests in `tests/test_chart_analyzer.py` — test `compute_confluence_score` returns 8+ for all-bullish TFs, 0-3 for conflicting, test prompt adapts language per timeframe
- [x] T020 [US2] Integrate confluence score into `/analyze-chart` response — include in `plan` SSE event and `higher_tf` event

## Phase 5: User Story 3 — Historical Pattern Context (P2)

**Goal**: Analysis references how similar setups have performed historically.

**Test Criteria**: When 5+ occurrences exist, the analysis includes win rate and count.

- [x] T021 [US3] Add `get_pattern_win_rate(symbol, alert_type) -> dict | None` helper in `analytics/chart_analyzer.py` — wraps existing `get_alert_win_rates()` from `intel_hub.py`, filters to relevant symbol+type, returns `{win_rate, wins, losses, total}` if total >= 5 else None
- [x] T022 [US3] Inject win rate data into analysis prompt in `build_analysis_prompt()` — section `[HISTORICAL TRACK RECORD]` with pattern name, win rate, sample size
- [x] T023 [US3] Write unit test in `tests/test_chart_analyzer.py` — test win rate included when data sufficient, omitted when < 5 samples

## Phase 6: User Story 4 — Alert Auto-Analysis (P2)

**Goal**: When an alert fires and user has auto-analysis enabled, a follow-up "AI Take" message is sent via Telegram.

**Test Criteria**: Auto-analysis runs asynchronously; alert delivery is never delayed; AI Take message appears in Telegram after the alert.

- [x] T024 [US4] Add `PUT /settings/auto-analysis` endpoint in `api/app/routers/settings.py` — toggles `auto_analysis_enabled` on User model
- [x] T025 [US4] Implement `generate_alert_analysis(symbol, timeframe, alert_signal) -> str` in `analytics/chart_analyzer.py` — lightweight analysis prompt that produces a 2-3 line "AI Take" (direction, entry, stop, target, R:R, confluence score)
- [x] T026 [US4] Add async auto-analysis trigger in `alerting/notifier.py` — after successful `_send_telegram_to()`, if user has `auto_analysis_enabled`, spawn background task to call `generate_alert_analysis()` and send follow-up Telegram DM
- [x] T027 [US4] Write tests in `tests/test_auto_analysis.py` — test auto-analysis only fires when enabled, test alert delivery not blocked by AI failure, test follow-up message format

## Phase 7: User Story 5 — Journal Integration (P3)

**Goal**: Users can save analyses and track actual outcomes vs AI predictions.

**Test Criteria**: Analysis saved to DB; outcome can be recorded; history endpoint returns past analyses.

- [x] T028 [US5] Add save-to-DB logic in `/analyze-chart` endpoint — after stream completes, insert into `chart_analyses` table with parsed plan fields, return `analysis_id` in `done` event
- [x] T029 [US5] Add `GET /intel/analysis-history` endpoint in `api/app/routers/intel.py` — query `chart_analyses` by user_id with optional symbol/days/limit filters
- [x] T030 [US5] Add `PUT /intel/analysis/{id}/outcome` endpoint in `api/app/routers/intel.py` — update `actual_outcome` and `outcome_pnl` on saved analysis (must belong to user)
- [ ] T031 [US5] Write integration tests in `tests/test_analysis_history.py` — test save, retrieve, filter by symbol, record outcome

## Phase 8: User Story 6 — Usage Limits (P3)

**Goal**: Analysis counts against existing AI query usage limits per tier.

**Test Criteria**: Free tier limited to 5/day, Pro to 50/day; 429 returned when exceeded.

- [x] T032 [US6] Add `check_usage_limit(user, "ai_queries", db)` call at the start of `/analyze-chart` endpoint in `api/app/routers/intel.py` — reuses existing usage limit infrastructure
- [x] T033 [US6] Return `remaining` count in `done` SSE event from `/analyze-chart`
- [ ] T034 [US6] Write test in `tests/test_analyze_chart_api.py` — test 429 after limit exhausted, test remaining count decrements

## Phase 9: Frontend — AI CoPilot Page

- [x] T035 Create new "AI CoPilot" page component in `web/src/pages/AICoPilotPage.tsx` — top-level nav tab with symbol picker (from watchlist), timeframe dropdown, and "Analyze" button
- [x] T036 Add mini candlestick chart panel (read-only Plotly) to AI CoPilot page in `web/src/pages/AICoPilotPage.tsx` — displays bars being analyzed, fetched from `/charts/ohlcv`
- [x] T037 Add structured Trade Plan card to AI CoPilot page in `web/src/components/ai/TradePlanCard.tsx` — direction badge (LONG/SHORT/NO TRADE), entry/stop/T1/T2, R:R, confidence, confluence score (0-10), timeframe fit, streaming AI reasoning + higher TF summary
- [x] T038 Add analysis history feed to AI CoPilot page in `web/src/components/ai/AnalysisHistory.tsx` — recent analyses list with outcome tracking, "Record Outcome" button (WIN/LOSS/SCRATCH)
- [x] T039 [P] Register AI CoPilot page in app router and navigation in `web/src/App.tsx` and `web/src/components/AppLayout.tsx`
- [x] T040 [P] Add auto-analysis toggle to Settings page in `web/src/pages/SettingsPage.tsx`
- [ ] T041 [P] Add confluence score badge to alert cards in Signal Feed in `web/src/components/alerts/AlertCard.tsx`

## Phase 10: Polish & Cross-Cutting

- [x] T042 Run full test suite: `python3 -m pytest tests/ -v` — verify no regressions (648 existing + 41 new = all pass)
- [ ] T043 Verify on localhost: test AI CoPilot page with SPY on 1H, check structured plan output
- [ ] T044 Test "No Trade" scenario: analyze a choppy symbol, verify No Trade response
- [ ] T045 Test auto-analysis flow: enable auto-analysis, trigger an alert, verify follow-up Telegram DM
- [x] T046 Add "Not financial advice" disclaimer to analysis response output (included in TradePlanCard.tsx)

---

## Dependencies

```
Phase 1 (Setup) → Phase 2 (MTF Fix) → Phase 3 (US1: Core Analysis)
                                         ↓
Phase 4 (US2: Confluence) ← depends on Phase 3
Phase 5 (US3: Win Rates) ← depends on Phase 3
Phase 6 (US4: Auto-Analysis) ← depends on Phase 3
Phase 7 (US5: Journal) ← depends on Phase 3
Phase 8 (US6: Usage Limits) ← depends on Phase 3
Phase 9 (Frontend) ← depends on Phases 3-8
Phase 10 (Polish) ← depends on all
```

## Parallel Execution Examples

**Phase 1** (all [P] tasks can run in parallel):
- T002 (ORM model) + T003 (User column) + T004 (schemas) → all independent files

**Phase 3** (after T010-T013 are done):
- T014 (tests) can start as soon as T010-T013 are written

**Phase 9** (all frontend tasks independent):
- T035 + T036 + T037 → different pages, can run in parallel

## Implementation Strategy

**MVP (ship first)**: Phase 1 + 2 + 3 = Setup + MTF Fix + Core Analysis
- This delivers the core "Analyze Chart" feature with structured trade plans
- Users get immediate value; other stories enhance it

**Iteration 2**: Phase 4 + 5 = Confluence + Win Rates
- Enriches analysis quality with multi-TF scoring and historical context

**Iteration 3**: Phase 6 + 7 + 8 = Auto-Analysis + Journal + Limits
- Adds automation, tracking, and monetization guardrails

**Iteration 4**: Phase 9 + 10 = Frontend + Polish
- Full UI integration and production readiness

---

**Legend**:
- `T###` — Task ID (sequential)
- `[P]` — Parallelizable (can run alongside other [P] tasks in same phase)
- `[US#]` — User story label
- All file paths are relative to project root
