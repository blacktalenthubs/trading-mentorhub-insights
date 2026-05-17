# Implementation Plan: V1 Cleanup (Spec 49)

**Branch**: `main` (no separate cleanup branch — staged deletions on main per the spec) | **Date**: 2026-05-16 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `trade-analytics/specs/49-v1-cleanup/spec.md`
**Manifest**: [Spec 48 (V3 Cleanup & Paid AI Revamp)](../48-v3-cleanup-and-paid-ai-revamp/spec.md)

## Summary

Spec 49 deletes the V1 vestiges (Streamlit dashboard, AI-scanner stack, rule-engine helpers) and reshapes `analytics/intraday_rules.py` into two focused modules so the V2 Pine + `tv_webhook` + `triage-agent` pipeline keeps running on a clean codebase. Pre-flight research revealed **six spec-affecting findings** that require FR amendments before implementation begins — most importantly, the SPY-gate function is named `compute_spy_gate` (not `spy_regime_gate`), `tv_webhook` reaches into private helpers in `intraday_rules.py`, and four modules listed for Tier 3 deletion (`htf_bias`, `intel_hub`, `trade_coach`, `options_trade_store`) have live V2 importers that the spec must either preserve or refactor first. Without those amendments the deletion batches will break production. The plan sequences the work so amendments land in Phase A (1–2 days) before any deletion executes.

Technical approach: incremental, gate-protected deletion batches with a green test suite between each batch, plus a one-shot surgical extraction of `intraday_rules.py`'s live symbols into two new focused modules. CLAUDE.md is rewritten alongside the extraction (mandatory — outside agents otherwise refuse to touch live V2 files). Spec 46 gets a superseded notice. Operator records the `tradesignalwithai.com` sunset decision in a `decision.md` artifact.

## Technical Context

**Language/Version**: Python 3.13 (per CLAUDE.md), TypeScript 5.x (React 18 + Vite), Pine v5 (TradingView indicators)
**Primary Dependencies**: FastAPI, psycopg2-binary, yfinance (being deleted with V1), Anthropic SDK, React 18, Vite, Tailwind, Capacitor (iOS)
**Storage**: Production = Railway Postgres (`DATABASE_URL`); local dev SQLite (`data/trades.db` — being deleted)
**Testing**: pytest. No `pytest.ini` exists today — see Constitution Check.
**Target Platform**: Railway (FastAPI + `worker` + `triage-agent` services); Streamlit Cloud (V1, being deleted); App Store (iOS Capacitor)
**Project Type**: Multi-service monorepo. Active services: `api/app/` (FastAPI), `triage-agent/`, `web/` (React+iOS). Retired: root Streamlit (`app.py`, `pages/`, `monitor.py`, `worker.py`).
**Performance Goals**: V2 alert pipeline already meets latency targets (Pine → Telegram in ~3s); cleanup MUST NOT regress.
**Constraints**: Zero V1-related errors for 7 trading days post-cleanup (SC-103). Test suite green after each batch (SC-102). No silent skipped tests.
**Scale/Scope**: 228,404 LOC across 646 tracked files today (Python 188,124 / TSX 35,617 / TS 4,573 / JS 90). Target: ≥34,261 LOC removed (SC-101).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Constitution status**: `.specify/memory/constitution.md` is the unfilled template — no project-level constitution has been ratified. Substituting the cross-cutting rules from [Spec 48 manifest](../48-v3-cleanup-and-paid-ai-revamp/spec.md) as effective gates for this plan:

| Gate | From | Status |
|------|------|--------|
| **No revival of "AI picks the trades."** | Spec 48 | ✅ PASS — cleanup deletes the AI-scanner stack |
| **No new Streamlit dashboard.** | Spec 48 | ✅ PASS — deletes V1 Streamlit |
| **All paid LLM calls via shared abstraction.** | Spec 48 | N/A — no new LLM calls in this spec |
| **Tier model coordination.** | Spec 48 | N/A — no billing changes |
| **CLAUDE.md update is hard prerequisite.** | Spec 49 FR-413 | ⚠️ GATED — must rewrite before further agent-driven work |
| **`chart_analyzer.py` preservation.** | Spec 49 FR-406 / Spec 51 FR-305 | ✅ PASS — research confirms clean import graph |
| **`notifier.py` + `alert_store.py` preservation.** | Spec 49 FR-406 | ✅ PASS — research confirms no Tier 3 dependencies |

**Test-config gap (new gate not in any spec)**: There is no `pytest.ini`, `pyproject.toml`, or `setup.cfg` for pytest. The spec's "run full test suite between batches" workflow has no way to mark tests by tier. Either Spec 49 must add `pyproject.toml [tool.pytest.ini_options]` markers (small amendment) OR the runbook accepts a manual file-list approach. Documented in [research.md §8](./research.md#section-8) — the plan chooses the file-list approach to keep the spec lean.

**Six FR amendments required before implementation** — these are the Constitution Check failures most likely to break production if ignored:

| # | Amendment | Why | Affected FR |
|---|-----------|-----|-------------|
| A1 | Rename live symbol: `compute_spy_gate` (not `spy_regime_gate`) | Function actually named this at `intraday_rules.py:7642` | FR-407, FR-408 |
| A2 | Preserve `_targets_for_long` + `_targets_for_short`; promote to public in `alert_types.py` | `tv_webhook.py:378` reaches into these private helpers | FR-407 (new bullet) |
| A3 | Remove `htf_bias.py` from Tier 3 (retain) | Used by `tv_webhook.py:368` and `monitor.py:24` — V2 hot path | FR-405 |
| A4 | Remove `intel_hub.py` from Tier 3 (retain — trim instead) | `intel.py` exposes 13 endpoints to the React app, 11 reach `intel_hub` | FR-405 |
| A5 | Remove `trade_coach.py` from Tier 3 (retain) | `intel.py:163,322` calls it; `intel.py` is non-deletable | FR-405 |
| A6 | Remove `options_trade_store.py` from Tier 3 pending owner confirmation | 6 imports in `routers/real_trades.py` — options-trading UI may still be shipped | FR-405 |

Plus: **the Tier 3 deletion order must be re-sequenced.** Several Tier 3 modules have V2 importers that must be cut FIRST. See [quickstart.md "Phase B sequencing"](./quickstart.md#phase-b---tier-3-sequenced-deletions) for the order: `ai_*_scanner` (cut `main.py:319,329,339,357` scheduler block + `routers/auth.py:325`, `routers/admin.py:239`, `routers/ai_coach.py:88` first), `signal_engine` (cut `routers/backtest.py:23` + `services/scanner.py:20` first), `swing_rules` (cut `routers/swing.py:34,76,93,104,112` + `alerting/swing_scanner.py` first), then the dependent V1 modules.

The Phase B sequencing is captured in the runbook, not as new FRs — it's an implementation detail, not a spec change. The 6 amendments above ARE spec changes and need `/speckit-clarify` confirmation or direct spec edit before Phase B begins.

## Project Structure

### Documentation (this feature)

```text
trade-analytics/specs/49-v1-cleanup/
├── spec.md                            # The spec (already exists)
├── plan.md                            # This file — /speckit-plan output
├── research.md                        # Phase 0 — concrete findings from pre-flight audit
├── data-model.md                      # Phase 1 — repurposed: "Extracted Module Signatures"
├── quickstart.md                      # Phase 1 — the sequenced runbook
├── checklists/
│   └── requirements.md                # Already exists
└── contracts/
    ├── alert-types-module.md          # The public surface of new analytics/alert_types.py
    ├── regime-gate-module.md          # The public surface of new analytics/regime_gate.py
    ├── claude-md-draft.md             # The rewritten root CLAUDE.md (the FR-413 contract)
    ├── spec-46-supersedence.md        # The notice text to add to Spec 46
    └── decision-tradesignalwithai.md  # Template for FR-417 operator decision
```

### Source Code (repository — what changes)

```text
trade-analytics/                       # The active project root
├── analytics/
│   ├── intraday_rules.py              # DELETED at end of Phase C (post-extraction)
│   ├── alert_types.py                 # NEW (Phase C) — AlertType, AlertSignal, _targets_*
│   ├── regime_gate.py                 # NEW (Phase C) — compute_spy_gate + deps
│   ├── tv_signal_adapter.py           # KEEP (live V2)
│   ├── chart_analyzer.py              # KEEP (Spec 51 foundation)
│   ├── market_data.py, market_hours.py # KEEP (live)
│   ├── htf_bias.py                    # KEEP (research §3 surprise — V2 importer)
│   ├── intel_hub.py                   # KEEP — trim unused funcs (research §6)
│   ├── trade_coach.py                 # KEEP — required by intel.py
│   └── [27+ DELETED Tier 3 files]     # See FR-405 amended list
├── alerting/
│   ├── notifier.py, alert_store.py    # KEEP (live V2, protected)
│   └── [6+ DELETED Tier 3 files]      # See FR-405
├── api/app/
│   ├── routers/
│   │   ├── tv_webhook.py              # KEEP — update imports post-extraction (alert_types)
│   │   ├── ai_coach.py                # KEEP — update import (alert_types); cut ai_best_setups call
│   │   ├── settings.py                # KEEP — update imports (alert_types)
│   │   ├── intel.py                   # KEEP — trim 9 unreferenced routes (research §6)
│   │   ├── auth.py                    # KEEP — cut ai_day_scanner import at :325
│   │   ├── admin.py                   # KEEP — cut ai_day_scanner import at :239
│   │   ├── swing.py                   # DELETE? (depends on UI confirmation)
│   │   ├── backtest.py                # DELETE (no V2 path)
│   │   └── real_trades.py             # KEEP if options UI is live, else DELETE
│   ├── background/
│   │   └── monitor.py                 # DELETE (V1 rule engine)
│   ├── services/
│   │   └── scanner.py                 # DELETE (V1 signal_engine consumer)
│   └── main.py                        # EDIT — cut V1 scheduler block lines 293–427
├── triage-agent/                       # NO CHANGES — V2 production, untouched
├── web/src/
│   ├── App.tsx                        # EDIT — drop V1 React page routes (handled in Spec 50)
│   └── pages/                         # 11 V1 pages DELETED (Spec 50 FR-208 coordinates)
├── tests/
│   ├── [21 V2 + shared infra tests]   # KEEP (research §8)
│   └── [28 V1 tests DELETED]          # See FR-412 + research §8
├── pages/                              # ENTIRE DIRECTORY DELETED (V1 Streamlit dashboard)
├── parsers/                            # ENTIRE DIRECTORY DELETED
├── data/                               # SQLite + spy_*.csv artifacts DELETED
├── CLAUDE.md                          # REWRITTEN (FR-413 — see contracts/claude-md-draft.md)
└── specs/46-stable-state-reference/spec.md  # PREPENDED notice (FR-416)
```

**Structure Decision**: Multi-service monorepo, single Python virtualenv at root, React subproject under `web/`. Cleanup respects existing service boundaries (V2: `api/app/` + `triage-agent/` + `web/` survive; V1: everything else under root `*.py` + `pages/` + V1 modules in `analytics/`+`alerting/` removed). No new services created; no service boundaries moved.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| Plan requires 6 FR amendments before Phase B starts | Pre-flight research found V2 hot imports of modules the spec called "dead" — including `htf_bias.py` consumed by `tv_webhook`, `intel_hub` consumed by `intel.py` (13 React endpoints), and a function-name mismatch (`compute_spy_gate` vs spec's `spy_regime_gate`) | Plowing ahead would break the V2 pipeline; amendments are cheap (text edit to spec.md) compared to a Railway rollback |
| Extracting `_targets_for_long` / `_targets_for_short` from `intraday_rules.py` even though they're underscore-prefixed | `tv_webhook.py:378` calls them as a load-bearing path; renaming them to public + extracting is safer than leaving them in the doomed file | Refactoring tv_webhook to not use them adds scope to a cleanup spec; promotion is the smaller diff |
| Keeping `intel_hub.py` (69 KB) and `trade_coach.py` (31.6 KB) alive | Both are reachable from production React via `intel.py`'s 13 live endpoints | Deleting them would break the AI co-pilot landing-page stats, analysis history, and chat surface — substantial UX regression on V2 |
| No `pytest.ini` markers added to spec | Adding test markers is scope creep for a cleanup spec | Runbook prescribes the explicit kept/deleted test file list instead |

---

## Phase 0: Outline & Research

**Status**: COMPLETE — see [research.md](./research.md) for full findings. Summary of what was resolved:

| Unknown | Resolution | Where |
|---------|------------|-------|
| What does `intraday_rules.py` actually export that's live? | `AlertType` enum, `AlertSignal` dataclass, `compute_spy_gate`, `_targets_for_long`, `_targets_for_short`. Plus `evaluate_rules` if `RULE_ENGINE_ENABLED=true` (gated). | research.md §2 |
| Function name for the SPY gate? | `compute_spy_gate(spy_bars, spy_vwap)` at line 7642 — NOT `spy_regime_gate`. FR amendment A1 needed. | research.md §2 |
| Hidden V2 importers of any Tier 3 doomed module? | YES — 5 surprises: `ai_day_scanner` (3 V2 sites), `ai_swing_scanner` (1), `ai_best_setups` (1), `signal_engine` (2), `swing_rules` (1), `htf_bias` (2), `intel_hub` (11 via intel.py), `trade_coach` (2 via intel.py), `options_trade_store` (6). FR amendments A3–A6 needed; sequencing fix needed. | research.md §3 |
| Are `notifier.py` and `alert_store.py` truly clean (FR-406)? | YES — only depend on `analytics.intraday_rules.{AlertSignal, AlertType}` + stdlib + `alert_config`. After extraction, imports redirect to `analytics.alert_types`. | research.md §4 |
| Is `chart_analyzer.py` safe to retain? | YES — only depends on stdlib + pandas. Zero internal coupling. | research.md §5 |
| Is `api/app/routers/intel.py` deletable? | NO — React app consumes 13 of its 22 endpoints. Plan: keep `intel.py`, trim 9 unreferenced routes, retain `intel_hub` + `trade_coach`. Re-classify FR-405. | research.md §6 |
| How does the operator confirm Railway env flags are off? | Dashboard (Variables tab) + log search for the two startup messages emitted from `main.py:276` and `:427`. CLI alternative: `railway variables --service worker`. Procedure documented. | research.md §7 |
| Test suite topology? | 44 test files; 28 doomed alongside Tier 3 modules; 21 survive (V2 + shared infra). No `pytest.ini` exists — runbook uses explicit file list. | research.md §8 |
| Baseline LOC for SC-101? | 228,404 LOC across 646 tracked files. 15% reduction target = 34,261 LOC removed. Achievable from Tier 3 + test housekeeping alone (`test_intraday_rules.py` is 7,700 LOC). | research.md §1 |

## Phase 1: Design & Contracts

**Prerequisites**: research.md complete ✅

**Outputs** (all present in this feature directory):

1. **[data-model.md](./data-model.md)** — Repurposed for this cleanup spec as "Extracted Module Signatures." Defines the public surface of the two new modules (`alert_types.py`, `regime_gate.py`): exports, type signatures, import contracts. This is the "data model" for a cleanup spec — the new file boundaries.
2. **[contracts/alert-types-module.md](./contracts/alert-types-module.md)** — Contract for the new `analytics/alert_types.py`. Lists every symbol exported, its type signature, which V2 callers depend on it.
3. **[contracts/regime-gate-module.md](./contracts/regime-gate-module.md)** — Contract for the new `analytics/regime_gate.py`. Same shape.
4. **[contracts/claude-md-draft.md](./contracts/claude-md-draft.md)** — The full rewritten root `CLAUDE.md` (the FR-413 deliverable as a contract artifact, so reviewers can approve the wording before the file flip).
5. **[contracts/spec-46-supersedence.md](./contracts/spec-46-supersedence.md)** — The exact superseded notice to prepend to `specs/46-stable-state-reference/spec.md`.
6. **[contracts/decision-tradesignalwithai.md](./contracts/decision-tradesignalwithai.md)** — Template for the FR-417 operator decision (sunset / redirect / dormant).
7. **[quickstart.md](./quickstart.md)** — The sequenced runbook with safety gates between each batch.

**Agent context update**: SKIPPED. The skill prescribes updating `<!-- SPECKIT START --><!-- SPECKIT END -->` markers in the master-domain-hub CLAUDE.md to reference this plan. The relevant CLAUDE.md being rewritten is `trade-analytics/CLAUDE.md`, and the rewrite IS the work this spec prescribes — circular. The new `trade-analytics/CLAUDE.md` (in `contracts/claude-md-draft.md`) explicitly references this plan in its V3-status section, which is the closest analog.

**Constitution Check (post-design re-evaluation)**: Same six amendments still required. Plan does not proceed to implementation without them. Recommend the user run `/speckit-clarify` on this spec OR amend `spec.md` directly via edit before `/speckit-tasks`.

## Phase 2: Task Planning Approach (DO NOT EXECUTE — preview only)

`/speckit-tasks` will generate `tasks.md`. Anticipated structure based on this plan:

- **Phase A — Amendments + Pre-flight** (1–2 days):
  - T-A1: Apply 6 FR amendments to `spec.md` (text edit or `/speckit-clarify` round)
  - T-A2: Operator flips Railway env flags + waits 1 trading session
  - T-A3: Capture FR-402 LOC baseline (`find ... | xargs wc -l` per research §1)
  - T-A4: Confirm `options_trade_store.py` UI status with owner (research surprise #4)
- **Phase B — Tier 1 + Tier 2 deletions** (1 day):
  - T-B1–B?: Tier 1 batch (10+ files; no risk; pre-deletion grep audit per FR-411)
  - T-B?–B?: Tier 2 batch (V1 stack; pre-deletion grep audit)
- **Phase C — Extraction + Tier 3 sequenced deletions** (3–4 days):
  - T-C1: Create `analytics/alert_types.py` with the public surface from contracts/
  - T-C2: Create `analytics/regime_gate.py` with the public surface from contracts/
  - T-C3: Repoint every importer; run test suite
  - T-C4: Cut V2-hot import sites for Tier 3 modules (per Phase B sequencing in quickstart.md)
  - T-C5: Delete remaining Tier 3 modules in sequenced order
  - T-C6: Delete `intraday_rules.py`
  - T-C7: Trim `intel.py` (9 unreferenced routes)
- **Phase D — Documentation + tests** (1 day):
  - T-D1: Replace root `CLAUDE.md` with `contracts/claude-md-draft.md`
  - T-D2: Prepend supersedence notice to Spec 46
  - T-D3: Record FR-417 operator decision in `decision-tradesignalwithai.md`
  - T-D4: Move abandoned-direction tickets to `tickets/archive/`
  - T-D5: Delete dead test files per research §8
  - T-D6: Capture post-cleanup LOC; verify ≥15% reduction
- **Phase E — Validation** (7 trading days):
  - T-E1: Monitor Railway logs for V1-related errors (SC-103)
  - T-E2: 20-prompt CLAUDE.md outside-agent audit (SC-105)

Estimated total: ~7 working days + 7 trading days of validation soak.

---

## Stop and report

Branch: `main` (no cleanup branch — staged deletions per spec).
Plan file: `trade-analytics/specs/49-v1-cleanup/plan.md`.
Generated artifacts: `research.md`, `data-model.md`, `quickstart.md`, `contracts/alert-types-module.md`, `contracts/regime-gate-module.md`, `contracts/claude-md-draft.md`, `contracts/spec-46-supersedence.md`, `contracts/decision-tradesignalwithai.md`.

**Blocker before `/speckit-tasks`**: Apply the six FR amendments listed in Constitution Check. Without them, the deletion batches will break the V2 production pipeline.
