# Spec 51 — AI Chart Critique (2026-05-16)

**Status**: Draft — buildable child of [Spec 48](../48-v3-cleanup-and-paid-ai-revamp/spec.md) (V3 manifest). The headline paid V3 feature.
**Depends on**: [Spec 49 (V1 Cleanup)](../49-v1-cleanup/spec.md) — specifically FR-406 retains `analytics/chart_analyzer.py` as the engine foundation. Should also depend on the cleanup completing so we are not building on a half-deprecated codebase.
**Foundation for**: [Spec 53 (Replay Coach)](../53-replay-coach/spec.md) — Replay Coach reuses this spec's analysis engine.
**Coexists with**: [Spec 52 (Pattern Education Live)](../52-pattern-education-live/spec.md) — independent; same tier-gating machinery; the pattern taxonomies should stay consistent.

## Why this spec exists

The V3 thesis: stop selling "AI picks the trades"; start selling on-demand AI analysis of charts the trader is already looking at. The product already has half the infrastructure: a dormant `analytics/chart_analyzer.py` with a pattern library, prompt scaffolding, and confluence scoring; a chat-style surface at `AICoPilotPage.tsx`; a `chart_analysis` data model; tier-gating + usage limits + Stripe billing already wired. This spec ties those pieces into a single shippable feature: paste a chart screenshot, pick a ticker, or capture from the live chart → within 15 seconds receive a structured analysis with bias, S/R levels, entry plan, stop, targets, invalidation, and confidence note.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Paste a chart screenshot, get a structured analysis in under 15 seconds (Priority: P1)

A Pro-tier subscriber drags a chart image into the chat surface (or pastes from clipboard), submits, and within 15 seconds receives a structured analysis: setup name, bias (long / short / no-trade), key support/resistance prices, suggested entry, stop, first target, runner target, invalidation conditions, confidence note. Every analysis includes a visible "AI guidance, not investment advice" disclaimer. The analysis is persisted to history.

**Why this priority**: This is the core value moment of the feature. Every other story is in service of it being fast, correct, and trustworthy.

**Independent Test**: With a Pro-tier account, paste 10 representative chart screenshots (mix of clean setups, mid-trade, and messy charts). ≥9 of 10 return a structured analysis within 15 seconds. ≥7 of 10 correctly identify the dominant bias as judged by reviewer audit. Each result is retrievable from history.

**Acceptance Scenarios**:

1. **Given** a Pro-tier subscriber on `AICoPilotPage.tsx` (or `/chart-critique`), **When** they paste/upload a chart and submit, **Then** within 15 seconds for 90% of requests they see a structured analysis with the fields above and a disclaimer.
2. **Given** the analysis result, **When** the subscriber views it, **Then** the result contains specific dollar-level S/R prices (not "around the support area"), an explicit bias, and an explicit invalidation condition.
3. **Given** a successful analysis, **When** the subscriber returns later, **Then** the analysis appears in `AnalysisHistory.tsx` with the chart, the result, and the timestamp.
4. **Given** a Pro-tier subscriber, **When** they ask a follow-up question in the same chat (e.g., "what if I add at the runner target?"), **Then** the assistant has the prior analysis as context and can reason about it.

---

### User Story 2 — Capture from the live TradingView chart (Priority: P2)

A subscriber clicks "Analyze my chart" from inside the live trading workspace. The system uses the TradingView MCP `capture_screenshot` integration to grab the current chart, runs it through the same critique engine, and presents the result inline next to the chart. Zero copy-paste friction.

**Why this priority**: Removes the biggest UX friction. Not blocking US1; users with screenshots cover the MVP.

**Independent Test**: From the live trading workspace, click "Analyze my chart" on five different tickers; for each, the captured frame matches the chart on screen and produces an analysis identical in shape to US1.

**Acceptance Scenarios**:

1. **Given** the subscriber is on `TradingPageV2.tsx`, **When** they trigger "Analyze my chart", **Then** the TradingView capture fires, the resulting image enters the same analysis pipeline as US1, and the result renders inline within 15 seconds.
2. **Given** the TradingView MCP integration is unavailable or fails, **When** the subscriber triggers capture, **Then** they see a graceful fallback offering paste/upload instead.

---

### User Story 3 — Paywall + quota that respect Free-tier evaluation (Priority: P1)

Free-tier users see the Chart Critique surface, can attempt one analysis as an evaluation (operator-configurable; default 1 free analysis), then see a clear paywall on subsequent attempts before any LLM call is made. Pro-tier subscribers have a monthly quota (operator-configurable; default 100 critiques/month) with a visible quota indicator and a clear quota-exhausted state.

**Why this priority**: Without a meaningful Free taste, conversion craters. Without a quota, cost spirals. Both must ship together.

**Independent Test**: From a fresh Free account, run one analysis successfully, then attempt a second and verify the paywall appears with no LLM call dispatched. From a Pro account near the monthly quota, consume the remaining quota and verify the quota-exhausted state appears with no LLM call dispatched.

**Acceptance Scenarios**:

1. **Given** a Free-tier user with the default 1 free critique remaining, **When** they paste a chart and submit, **Then** the critique completes and the quota indicator updates to 0 remaining.
2. **Given** the Free user attempts a second critique, **When** they submit, **Then** they see a paywall before any LLM call is made, with a one-tap upgrade path.
3. **Given** a Pro subscriber at quota exhaustion, **When** they attempt another critique, **Then** they see the quota-exhausted state with a clear message naming the quota, the reset date, and an upgrade or wait path.
4. **Given** a Pro subscriber, **When** they view Settings → Plan, **Then** they see a monthly Chart Critique quota indicator alongside their existing plan information.

---

### User Story 4 — Engine reuse, not rebuild (Priority: P1)

The Chart Critique engine is built on top of the existing `analytics/chart_analyzer.py` (with its `PATTERN_LIBRARY`, `assemble_analysis_context`, `build_analysis_prompt`, `compute_confluence_score`, `parse_trade_plan`). This module is currently dormant but must NOT be deleted by Spec 49 (FR-406 explicitly excludes it). Where the existing functions are insufficient, they are extended in place, not rewritten from scratch.

**Why this priority**: Reuse is the whole reason this feature is shippable in weeks rather than months. If a maintainer accidentally re-implements the engine, the timeline doubles.

**Independent Test**: A code reader can see, in the Chart Critique endpoint implementation, direct calls into `analytics/chart_analyzer.py`'s existing functions. The new code added on top is < 1.5× the existing engine's LOC.

**Acceptance Scenarios**:

1. **Given** the implementation PR, **When** code review runs, **Then** the Chart Critique endpoint imports and calls into the existing `chart_analyzer.py` functions, and any new functions added there are extensions, not replacements.
2. **Given** Spec 49's cleanup runs, **When** Tier 3 deletions execute, **Then** `analytics/chart_analyzer.py` remains in the repo and is referenced by the Chart Critique endpoint.

---

### User Story 5 — Vision provider failure handled gracefully (Priority: P2)

When the underlying vision provider is degraded or returns an error, the user sees a clear "vision provider degraded, try again in a few minutes" message, the request does NOT count against their quota, and the persisted history does NOT contain a corrupted or partial result.

**Why this priority**: Vision providers (especially during launch days for new models) have occasional outages. A noisy failure mode burns trust quickly.

**Independent Test**: Inject a vision-provider error via a feature flag or mock and verify the user sees the graceful message, quota is unchanged, and history contains no broken row.

**Acceptance Scenarios**:

1. **Given** the vision provider returns an error, **When** the user submits a critique, **Then** they see a clear "vision provider degraded, try again in a few minutes" message within 5 seconds.
2. **Given** a vision-provider error has occurred, **When** the user checks their quota indicator, **Then** the quota is unchanged.
3. **Given** a vision-provider error has occurred, **When** the user views Analysis History, **Then** no broken or partial record appears for the failed attempt.

---

### Edge Cases

- **Chart screenshot is unreadable** (low res, partial, watermarked) — engine returns "extraction confidence low, please recapture or paste at higher resolution" rather than hallucinating an analysis.
- **Chart shows multiple tickers stacked vertically** — engine processes the first identifiable ticker and notes "multiple charts detected; analyzing top".
- **Chart is from a market the engine doesn't cover** (futures, FX, crypto stable pair) — engine returns "this market is outside v1 coverage; supported: US equities + crypto majors" rather than fabricating analysis.
- **Persistent low correctness on a given pattern** — kill signal for that pattern in the analyzer; the operator can disable specific entries in `PATTERN_LIBRARY` without redeploying.
- **Subscriber uploads a chart that contains visible PII** (interviewer faces, brokerage account numbers) — same upload pipeline as any image; not specifically flagged. The disclaimer mentions data handling.
- **Concurrent submissions from one user** — debounced; only the latest submission proceeds.
- **Image larger than the configured upload cap** — rejected client-side with a clear message before any network call.

## Requirements *(mandatory)*

### Functional Requirements

#### Endpoint and contract

- **FR-301**: A new endpoint MUST accept (a) a chart screenshot upload, (b) a ticker symbol with implicit current-day chart fetch, or (c) a TradingView MCP capture, and return a structured analysis containing: setup name, bias (long / short / no-trade), key S/R prices, suggested entry, stop, first target, runner target, invalidation, confidence note.
- **FR-302**: For 90% of requests, the analysis MUST be returned within 15 seconds end-to-end (upload to response).
- **FR-303**: The analysis output MUST contain specific dollar-level S/R prices (no "around the support area") and an explicit bias.
- **FR-304**: Every analysis MUST include a visible "AI guidance, not investment advice" disclaimer in the result UI.

#### Engine

- **FR-305**: The engine MUST be built on top of the existing `analytics/chart_analyzer.py` (`PATTERN_LIBRARY`, `assemble_analysis_context`, `build_analysis_prompt`, `compute_confluence_score`, `parse_trade_plan`). Where existing functions are insufficient, they MUST be extended in place rather than reimplemented.
- **FR-306**: The engine MUST use a vision-capable LLM accessed through the same provider plumbing already in place for the triage agent. The spec does not commit to a specific vendor; the requirement is "vision-capable model under the same provider abstraction."
- **FR-307**: Reviewer audit on a 30-chart representative sample MUST find the dominant bias correctly identified in ≥70% of cases at launch. Persistent below-floor accuracy on a given pattern is a kill signal for that pattern.

#### Surfaces

- **FR-308**: The feature MUST mount inside the existing `AICoPilotPage.tsx` chat surface, reusing `ChatWindow.tsx`. A dedicated `/chart-critique` route MUST exist as a direct entry point.
- **FR-309**: From `TradingPageV2.tsx`, an "Analyze my chart" affordance MUST trigger the TradingView MCP `capture_screenshot` integration and feed the resulting image into the same pipeline.
- **FR-310**: When the TradingView MCP integration is unavailable or fails, the UI MUST gracefully fall back to offering paste/upload.

#### Persistence and history

- **FR-311**: Each analysis MUST be persisted to the existing `chart_analysis` model and viewable from the existing `AnalysisHistory.tsx` surface.
- **FR-312**: The persisted analysis MUST include the input (chart image reference + optional ticker), structured output, timestamp, model identifier, and quota cycle.

#### Paywall and quota

- **FR-313**: The feature MUST be gated by tier via the existing `tier.py` + `useFeatureGate.ts` + `TierGate.tsx` machinery.
- **FR-314**: Free-tier users MUST have a configurable evaluation allowance (default: 1 free critique per account, lifetime). Beyond the allowance, a paywall MUST appear before any LLM call is dispatched.
- **FR-315**: Pro-tier subscribers MUST have a per-cycle quota (operator-configurable; default 100 critiques/month). Exhaustion MUST surface a clear quota-exhausted message naming the quota, the reset date, and an upgrade or wait path.
- **FR-316**: A quota indicator MUST be visible from Settings → Plan and updated in real time after each critique.

#### Failure handling

- **FR-317**: When the vision provider is degraded or returns an error, the UI MUST display a clear "vision provider degraded, try again in a few minutes" message within 5 seconds. The request MUST NOT count against the user's quota. The persisted history MUST NOT contain a corrupted or partial result.
- **FR-318**: When the input image is unreadable (low confidence extraction), the engine MUST return an "extraction confidence low" response with recapture/paste guidance, NOT a hallucinated analysis.

### Key Entities *(if applicable)*

- **Chart Analysis**: A persisted record. User account, input (chart image + optional ticker), structured output (setup, bias, S/R, plan, invalidation, confidence), timestamp, model identifier, quota cycle. Schema already exists in `models/chart_analysis.py`.
- **Quota Counter (Chart Critique)**: Per-user, per-cycle counter of Chart Critique invocations consumed.
- **Pattern Entry**: A single entry in `PATTERN_LIBRARY` (existing). Carries pattern name, prompt fragment, confluence-score weight, kill-switch flag (operator-toggleable).

## Success Criteria *(mandatory)*

- **SC-301**: For ≥90% of a 50-chart representative test set, the structured analysis is returned within 15 seconds end-to-end.
- **SC-302**: For ≥70% of a reviewer-audited 30-chart sample, the dominant bias is correctly identified at launch.
- **SC-303**: ≥10% of accounts that hit a Chart Critique paywall upgrade to a paid tier within 7 days of the block, measured across the first 30 days after launch.
- **SC-304**: 0 cases of a Free-tier user successfully triggering a Chart Critique LLM call beyond their evaluation allowance, verified by integration tests on every release.
- **SC-305**: 0 cases of quota being decremented for a request that failed at the vision provider, verified by automated regression on every release.
- **SC-306**: 0 cases of a corrupted or partial analysis appearing in user-facing Analysis History after a vision-provider failure.
- **SC-307**: The disclaimer ("AI guidance, not investment advice") is present in 100% of result renderings, verified by UI snapshot tests.

## Assumptions

- The existing `analytics/chart_analyzer.py` is suitable as the foundation. If reviewer audit during the first sprint reveals the prompt scaffolding is materially below the quality bar, this spec accepts a one-time rewrite of that module without changing the FR list.
- The vision-capable model is reachable through the same provider abstraction already used by `triage-agent`. Adding a new provider abstraction is out of scope.
- Tier values (Free / Pro / Pro+) and dollar amounts are operator-configurable. The spec defines the shape of the paywall and quota, not specific amounts.
- The TradingView MCP integration (`mcp__tradingview__capture_screenshot` and related) is available in the runtime. If not, US2 falls back to paste/upload-only at launch and US2 becomes a P3 follow-up.
- The persistence schema in `models/chart_analysis.py` is suitable; if it requires new columns, they are added as a normal migration.
- Daily-cost cap mechanisms already in place for the triage agent (per `triage-agent/.env.example`'s `TRIAGE_DAILY_USD_CAP`) are extended to the Chart Critique endpoint; a global daily cap MUST be in place at launch to prevent runaway spend.
- Spec 49's `chart_analyzer.py` preservation (FR-406) holds. If it gets deleted in error, this spec is blocked.
