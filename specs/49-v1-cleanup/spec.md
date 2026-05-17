# Spec 49 — V1 Cleanup (2026-05-16)

**Status**: Draft — buildable child of [Spec 48](../48-v3-cleanup-and-paid-ai-revamp/spec.md) (V3 manifest).
**Depends on**: nothing in this spec series; gates 51 / 52 / 53 / 54.
**Coexists with**: [Spec 50 (Landing Revamp)](../50-landing-revamp/spec.md) — can be worked in parallel; landing copy does not depend on cleanup completing.
**Supersedes/updates**: portions of [Spec 46 (Stable State Reference)](../46-stable-state-reference/spec.md) and the root [CLAUDE.md](../../CLAUDE.md) — both are V1-era and now misalign with V2 production.

## Why this spec exists

The repo carries the corpse of V1: a yfinance-polled Streamlit dashboard, an "AI picks the trades" scanner stack, and a rule-engine that was retired when the Pine + `tv_webhook` + `triage-agent` pipeline became the production source of truth. The dead code is roughly 80% of `analytics/`, most of root-level `.py`, all of the Streamlit `pages/`, and a long tail of stale artifacts. Worse, the protected-files list in `CLAUDE.md` still names those V1 modules, which means any outside agent (including future Claude Code sessions) reads it and refuses to touch the live V2 files because they look "protected" under the V1 rules. Cleanup is the precondition for every subsequent V3 spec.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Safe, staged deletion of V1 with zero V2 regressions (Priority: P1)

The operator confirms `AI_SCAN_ENABLED=false` and `RULE_ENGINE_ENABLED=false` on Railway. One trading session passes with no V1 alert traffic. The maintainer then executes four ordered deletion batches (Tier 1 safe → Tier 2 V1 stack → Tier 3 abandoned AI-scanner → Tier 4 surgical trim), running the test suite between each batch. V2 (`tv_webhook` → triage-agent → Telegram + EOD page) continues to fire correctly through the entire process. Result: ≥15% LOC reduction in the tracked repo with zero in-flight bugs.

**Why this priority**: Every new V3 feature shipped onto a half-deprecated codebase compounds technical debt. This is the foundation work.

**Independent Test**: For 7 consecutive trading days after the cleanup completes, the live V2 alert pipeline has zero V1-related errors in logs, the test suite is green, and `cloc` confirms ≥15% LOC reduction versus the pre-cleanup baseline.

**Acceptance Scenarios**:

1. **Given** the operator confirms `AI_SCAN_ENABLED=false` and `RULE_ENGINE_ENABLED=false`, **When** one full trading session passes with no V1-related alert traffic, **Then** Tier 2 deletions are safe to execute.
2. **Given** a deletion batch is staged, **When** the pre-deletion `grep` audit runs against `api/app/`, `triage-agent/`, and `web/src/`, **Then** no unexpected import of a batched file is found.
3. **Given** a deletion batch executes, **When** `python3 -m pytest tests/ -v` runs, **Then** the suite is green with no collection errors and no test references a deleted module.
4. **Given** the full cleanup completes, **When** Railway logs are reviewed for the next 7 trading days, **Then** zero V1-related errors appear.

---

### User Story 2 — `intraday_rules.py` surgically reduced, not blindly deleted (Priority: P1)

`analytics/intraday_rules.py` is 9,438 LOC. Inside it: the `AlertType` enum is live (consumed by `tv_signal_adapter.py`) and the SPY-regime gate is live (consumed by `triage-agent`). Everything else (the V1 rule-engine body) is dead. The two live pieces are extracted into focused new modules (`analytics/alert_types.py` and `analytics/regime_gate.py`); the rest of the file is deleted; all importers are repointed.

**Why this priority**: Cannot ship 51 (Chart Critique) cleanly while a 9,000+ LOC file in `analytics/` quietly mixes live and dead code. The extraction is also a load-bearing precondition for FR-107's CLAUDE.md rewrite.

**Independent Test**: After extraction, `grep -r "from analytics.intraday_rules import"` returns zero hits. `grep -r "from analytics.alert_types import"` and `from analytics.regime_gate import` resolve correctly across V2 consumers. Tests pass.

**Acceptance Scenarios**:

1. **Given** `intraday_rules.py` is unchanged, **When** a maintainer runs `grep -rn "AlertType\|spy_regime_gate" --include='*.py' .`, **Then** the live consumers are catalogued.
2. **Given** the extraction PR, **When** code review runs, **Then** the new modules contain only the symbols actually consumed by V2 and nothing from the rule-engine body.
3. **Given** the extraction has merged, **When** `intraday_rules.py` is deleted, **Then** the test suite passes and the live alert pipeline continues without regression for one trading session.

---

### User Story 3 — CLAUDE.md rewritten to reflect V2 production (Priority: P1)

The root `CLAUDE.md` is rewritten. The "protected files" list is replaced with the V2 set (`tv_webhook.py`, `tv_signal_adapter.py`, `notifier.py`, `alert_store.py`, `triage-agent/live.py`, `triage.py`, `telegram_post.py`, `alert_config.py`, and the new `alert_types.py` + `regime_gate.py`). The "test locally with Streamlit" workflow is replaced with the V2 "run FastAPI dev server and trigger `/tv/webhook` with a sample payload" workflow. The dual-mode SQLite-vs-Postgres section is retained but trimmed of references to deleted modules.

**Why this priority**: Without this, every future agent-driven dev session in this repo gets misled. Hard prerequisite for further automation.

**Independent Test**: An outside agent reading only `CLAUDE.md` correctly identifies the V2 protected-files list and the V2 dev workflow in ≥95% of test prompts.

**Acceptance Scenarios**:

1. **Given** the updated `CLAUDE.md`, **When** a reader skims the "Protected Files" table, **Then** every listed file exists in the repo and is part of the V2 live pipeline; no listed file has been deleted as part of this spec.
2. **Given** the updated `CLAUDE.md`, **When** a reader follows the "Deployment Workflow" steps, **Then** the steps reflect the V2 stack (FastAPI + triage-agent + React + iOS) rather than the V1 Streamlit + monitor.py + worker.py stack.
3. **Given** the updated `CLAUDE.md`, **When** an outside agent is prompted with "what are the protected files in this repo?", **Then** the response matches the V2 list with ≥95% accuracy across a 20-prompt audit.

---

### User Story 4 — Spec 46 explicitly superseded; legacy domain decision recorded (Priority: P2)

A clear superseded notice is added at the top of `specs/46-stable-state-reference/spec.md` linking to Spec 48 (the V3 manifest). The V1 baseline content remains intact for historical record. Separately, the operator records an explicit decision on the legacy `tradesignalwithai.com` Streamlit deployment: sunset (with holding page), redirect DNS to `tradingwithai.ai`, or leave dormant.

**Why this priority**: Two live brands tax SEO and confuse new visitors. Spec 46 supersedence is a hygiene item, not blocking, but it should ship with the cleanup so historical readers don't get misled.

**Independent Test**: A reader landing on Spec 46 sees the superseded banner before any V1 content. A visitor going to `tradesignalwithai.com` sees the operator's recorded decision in effect.

**Acceptance Scenarios**:

1. **Given** Spec 46, **When** a reader opens it, **Then** the first content visible is a clearly-labeled superseded notice pointing at Spec 48.
2. **Given** `tradesignalwithai.com`, **When** a visitor browses to it, **Then** the operator's chosen behavior is in effect (302 redirect to `tradingwithai.ai`, a static "this product has moved" page, or a documented dormant state).

---

### Edge Cases

- **Hidden V2 importer of a doomed module** — a router or React component imports something we thought was V1-only. Pre-deletion `grep` audit (FR-1106 in Spec 48 / FR-405 here) is mandatory before each batch.
- **A deletion batch breaks a test the suite previously skipped silently** — counts as a failure; the suite must be green, not "no new failures."
- **Operator forgets to flip the Railway env flags before Tier 2 deletion** — Tier 2 deletion is gated on operator confirmation (FR-402); the maintainer must not assume.
- **`alerting/notifier.py` and `alerting/alert_store.py` are accidentally swept into Tier 3** — these are V2-live (CLAUDE.md flags them as protected and they're called from `tv_webhook.py`). FR-403 explicitly excludes them.
- **`analytics/chart_analyzer.py` is accidentally swept into Tier 3** — it's currently dormant but is the foundation for Spec 51 (Chart Critique). FR-403 explicitly excludes it.
- **iOS Capacitor build still references deleted React pages** — App.tsx redirects are in place, but the iOS bundle must be rebuilt and re-uploaded after Tier 2 deletion lands.
- **A `tickets/ai-*.md` ticket gets dusted off in the future** — the abandoned-direction backlog should be moved to an `archive/` subfolder, not silently left in `tickets/` where someone might think it's actionable.

## Requirements *(mandatory)*

### Functional Requirements

#### Pre-flight

- **FR-401**: Before any deletion batch, a maintainer MUST verify the operator has flipped `AI_SCAN_ENABLED=false` and `RULE_ENGINE_ENABLED=false` on Railway and that no V1 alert traffic has been observed for one full trading session.
- **FR-402**: A snapshot of repo LOC via `cloc` MUST be captured before the cleanup begins; SC-101 (≥15% reduction) is measured against this baseline.

#### Tier 1 — Safe deletions (no live consumers)

- **FR-403**: The following MUST be deleted with no further analysis required:
  - `=0.31.0` (accidental pip output)
  - `monitor.log`
  - `backup_pre_v2_20260404_0854.json`
  - `data/trades.db`, `data/trades.db.bak`, and all WAL/SHM files
  - `api/tradesignal_dev.db`
  - `pages/_archive/`, `pages/_archive_v1/`
  - `web/alert-dashboard.html`
  - `prototype/redesign-v2.html`
  - `signal-pro-images/`, `docs/img*.png`, `docs/tradecopilot_alerts_2026-03-*.pdf`
  - `improvements/alert-rules-inventory.html`
  - Contents of `images/`
  - `data/spy_*.csv`, `data/spy_pattern_report.txt`

#### Tier 2 — V1 stack (gated on operator confirmation)

- **FR-404**: After FR-401's confirmation and one trading session of zero V1 traffic, the following MUST be deleted:
  - Root: `monitor.py`, `worker.py`, `monitor_thread.py`, `app.py`, root `auth.py`, root `models.py`, root `config.py`, `ui_theme.py`, `alerts_pdf.py`
  - All of `pages/*.py` (Streamlit dashboard)
  - `parsers/parser_1099.py`, `parsers/parser_statement.py`
  - V1 React pages no longer routed by `App.tsx`: `AlertsPage`, `ScannerPage`, `ChartsPage`, `ScorecardPage`, `HistoryPage`, `ImportPage`, `BacktestPage`, `PaperTradingPage`, `SwingTradesPage`, `AICoachPage`, `TradingPage` (v1)

#### Tier 3 — Abandoned AI-scanner & V1 rule-engine helpers

- **FR-405** (AMENDED 2026-05-16 per pre-flight audit — A3/A4/A5/A6): The following MUST be deleted:
  - `analytics/ai_day_scanner.py`, `ai_swing_scanner.py`, `ai_best_setups.py`, `ai_conviction.py`
  - `analytics/signal_engine.py`, `swing_rules.py`
  - `analytics/spy_patterns.py`, `cluster_narrator.py`, `regime_narrator.py`, `post_market_review.py`, `weekly_review.py`, `monthly_report.py`, `eod_review.py`, `position_advisor.py`, `pretrade_check.py`, `exit_coach.py`, `game_plan.py`, `trade_replay.py`, `trade_review.py`, `journal_insights.py`, `confluence.py`, `trade_matcher.py`, `wash_sale.py`, `categorizer.py`, `_cache.py`
  - `alerting/swing_scanner.py`, `swing_refresher.py`, `paper_trader.py`, `narrator.py`, `real_trade_store.py`
  - **Removed from this list per amendments (RETAINED)**: `htf_bias.py` (A3 — `tv_webhook.py:368` + `monitor.py:24` import it), `intel_hub.py` (A4 — `intel.py` exposes 13 React endpoints, 11 use it), `trade_coach.py` (A5 — `intel.py:163,322` calls it).
  - **Owner-confirm before delete (A6)**: `alerting/options_trade_store.py` — `routers/real_trades.py` has 6 import sites; deletion gated on confirmation that the options-trading UI is not shipped.
- **FR-406**: `alerting/notifier.py`, `alerting/alert_store.py`, `analytics/chart_analyzer.py`, `analytics/htf_bias.py`, `analytics/intel_hub.py`, and `analytics/trade_coach.py` MUST be retained. The first two are live in the V2 path; `chart_analyzer.py` is the foundation for Spec 51; the last three are V2-reachable per A3/A4/A5 amendments.

#### Tier 4 — Surgical extraction from `intraday_rules.py`

- **FR-407** (AMENDED 2026-05-16 — A2): The `AlertType` enum + `AlertSignal` dataclass currently in `analytics/intraday_rules.py` MUST be extracted into a new module `analytics/alert_types.py`, plus the private helpers `_targets_for_long` and `_targets_for_short` (promoted to public `targets_for_long` and `targets_for_short` since `tv_webhook.py:378` is a load-bearing live consumer). The new module MUST contain only the symbols consumed by V2.
- **FR-408** (AMENDED 2026-05-16 — A1): The SPY-regime gate currently in `analytics/intraday_rules.py:7642` MUST be extracted into a new module `analytics/regime_gate.py`. The gate function is named `compute_spy_gate` (NOT `spy_regime_gate` as earlier drafts named it). The new module MUST contain `compute_spy_gate` plus its direct dependency `detect_hourly_consolidation_break` (currently at `intraday_rules.py:7411`). The function returns gate ∈ {"green", "yellow", "red"} (NOT {"allow", "mute"}).
- **FR-409**: After extraction is merged and the test suite is green, `analytics/intraday_rules.py` MUST be deleted.
- **FR-410**: All importers of `intraday_rules.py` across `api/app/`, `triage-agent/`, `analytics/`, and `tests/` MUST be repointed at the new modules; no import of `intraday_rules` MUST remain in the repo after FR-409.

#### Pre-deletion safety + tests

- **FR-411**: Before each deletion batch (FR-403, FR-404, FR-405, FR-409), an automated `grep` audit MUST verify no file in `api/app/`, `triage-agent/`, or `web/src/` imports any file in the batch. Unexpected imports MUST block the batch.
- **FR-412**: The following test files MUST be deleted alongside their modules: `test_swing_rules.py`, `test_ai_day_scanner.py`, `test_ai_best_setups.py`, `test_signal_engine_bar.py`, `test_mtf_analysis.py`, `test_breakout_confirmation.py`, `test_ema_resistance.py`, `test_htf_bias.py`, `test_phase*`, `test_eod_review.py`, `test_copilot_education.py`. After deletion, `python3 -m pytest tests/ -v` MUST pass with no collection errors.

#### Documentation updates

- **FR-413**: The root `CLAUDE.md` MUST be rewritten. The "Protected Files" list MUST be exactly: `api/app/routers/tv_webhook.py`, `analytics/tv_signal_adapter.py`, `alerting/notifier.py`, `alerting/alert_store.py`, `triage-agent/live.py`, `triage-agent/triage.py`, `triage-agent/telegram_post.py`, `alert_config.py`, `analytics/alert_types.py`, `analytics/regime_gate.py`.
- **FR-414**: The CLAUDE.md "Deployment Workflow" section MUST be replaced with V2 instructions: how to run the FastAPI dev server, how to trigger `/tv/webhook` with a sample payload, how to inspect the resulting row in Postgres, how to verify the triage-agent processes it.
- **FR-415**: The CLAUDE.md "Dual-mode SQLite + Postgres" section MUST be retained but pruned of references to deleted modules.
- **FR-416**: A superseded notice MUST be added at the top of `specs/46-stable-state-reference/spec.md` linking to Spec 48. The V1 baseline content below MUST be preserved unchanged for historical record.

#### Operational decision recording

- **FR-417**: An explicit operator decision on the legacy `tradesignalwithai.com` deployment MUST be recorded in this spec directory (a `decision.md` file or in the operator's preferred decision log): sunset with holding page, redirect DNS to `tradingwithai.ai`, or leave dormant. The chosen behavior MUST then be in effect at the live URL.

#### Post-cleanup hygiene

- **FR-418**: After cleanup, the abandoned-direction backlog in `tickets/` (every `tickets/ai-*.md` referencing AI-trade-picking, AI-scanner, AI-conviction, AI-swing) MUST be moved into `tickets/archive/` to prevent future accidental revival.

### Key Entities *(if applicable)*

- **Deletion Batch**: An ordered set of files removed together, gated by a pre-deletion grep audit and a post-deletion test pass.
- **Extraction Module**: A new focused module (`alert_types.py`, `regime_gate.py`) carved from a larger dead-mostly file.
- **Protected File**: A file whose modification requires explicit approval per `CLAUDE.md`. Post-FR-413, this set is the V2 production pipeline.

## Success Criteria *(mandatory)*

- **SC-101**: After cleanup, repo tracked LOC is reduced by ≥15% (target: 20–25%) versus the FR-402 baseline, verified by `cloc`.
- **SC-102**: `python3 -m pytest tests/ -v` is green after each deletion batch and at the end, with no collection errors and no skipped tests pointing at deleted modules.
- **SC-103**: For 7 consecutive trading days after Tier 2 + Tier 3 + Tier 4 land, the live V2 alert pipeline has zero V1-related errors in Railway logs.
- **SC-104**: `grep -r "from analytics.intraday_rules import"` returns zero hits across the repo after FR-409.
- **SC-105**: An outside agent reading only `CLAUDE.md` correctly identifies the V2 protected-files list and the V2 dev workflow in ≥95% of test prompts (sampled across a 20-prompt audit).
- **SC-106**: Spec 46's superseded notice is visible above any V1 content.
- **SC-107**: The `tradesignalwithai.com` operator decision is recorded and in effect at the live URL.

## Assumptions

- The operator (not the maintainer) flips Railway env flags. The maintainer waits for explicit confirmation.
- The V2 pipeline is the source of truth for production behavior; this spec does not modify it.
- The iOS Capacitor app will be re-bundled and re-submitted after FR-404 lands. That release-engineering work is out of scope for this spec.
- Backup branches mentioned in Spec 46 (`backup-2026-04-16-experiments`, `backup-2026-04-15-state`) remain intact as the historical baseline; deletions happen on `main`.
- The `tradesignalwithai.com` operator decision is genuinely the operator's choice; FR-417 requires the decision to be recorded, not which decision is made.
- All deletions are on `main` and propagate through normal CI/CD. There is no separate "cleanup branch" promised here.
