# Implementation Plan: AI Chart Critique (Spec 51)

**Branch**: `main` | **Date**: 2026-05-16 | **Spec**: [spec.md](./spec.md)
**Manifest**: [Spec 48 (V3 Revamp)](../48-v3-cleanup-and-paid-ai-revamp/spec.md)

## Summary

**Spec 51 is ~70% already shipped.** A pre-flight audit of `api/app/routers/intel.py:304-420`, `analytics/chart_analyzer.py` (full surface), and `web/src/pages/AICoPilotPage.tsx:190-240` found a working chart-analysis pipeline in production today: SSE-streamed Claude analysis of a symbol + OHLCV bars, structured plan parsing, tier gating, quota tracking, DB persistence, frontend UX with auth + billing-upgrade redirect on 403 + 429 quota errors. **The only major gap is image-input mode** — today's pipeline takes a *chart context* (symbol + bars from the chart already on screen), but spec 51 FR-301 / FR-309 promises an *image-input* path (paste a screenshot OR capture from TradingView). That's the real work of spec 51.

Technical approach: this plan reclassifies spec 51 from "build the headline paid feature" into "extend an existing live feature with image input." Phase A (image upload), Phase B (vision-model integration in the engine), Phase C (TradingView MCP capture), Phase D (`/chart-critique` direct-entry route). Each phase is small enough to ship independently; the existing pipeline keeps running throughout. No new DB tables; existing `ChartAnalysis` model just gets an `input_kind` column ("context" | "image").

## Pre-flight findings (see [research.md](./research.md) for detail)

| Area | State today | Verdict vs Spec 51 |
|------|-------------|---------------------|
| Endpoint `/api/v1/intel/analyze-chart` | Exists (POST, SSE streaming) | ✅ keep; add `input_kind` discriminator |
| Engine `analytics/chart_analyzer.py` | 800+ LOC: PATTERN_LIBRARY, prompt builders, cache, parse_trade_plan, stream | ✅ keep; add vision-prompt builder |
| Tier gate (`require_ai_access`) | Wired | ✅ FR-313 satisfied |
| Quota (`check_usage_limit(user, "ai_queries")`) | Wired, returns `remaining` | ✅ FR-315 satisfied |
| Persistence (`models/chart_analysis.py`) | Wired | ✅ FR-311 satisfied; add `input_kind`, `image_ref` columns |
| Frontend surface (`AICoPilotPage`) | Wired; handles 403/429 cleanly | ✅ FR-308 partial — needs paste/upload UI added |
| `AnalysisHistory.tsx` | Exists (per earlier audit) | ✅ FR-311 history view exists |
| Caching | `get_cached_analysis` / `set_cached_analysis` (5-min TTL) | ✅ bonus |
| Image upload | ❌ Not implemented | **GAP** — FR-301 |
| Vision-capable LLM | ❌ Pipeline uses text-only `ask_coach` | **GAP** — FR-306 |
| TradingView MCP capture | ❌ Not wired | **GAP** — FR-309/310 |
| `/chart-critique` direct route | ❌ Today is only reachable from `AICoPilotPage` | **GAP** — FR-A4 |
| Vision-provider degradation handling | ❌ Moot until vision exists | **GAP** — FR-317 |
| Low-confidence extraction handling | ❌ Moot | **GAP** — FR-318 |
| Daily-cost cap (per Spec 51 Assumptions) | ⚠️ Triage-agent has `TRIAGE_DAILY_USD_CAP`; chart-critique endpoint doesn't | **GAP** — operational |

**Headline**: 7 FRs are satisfied, 7 are unmet. The 7 unmet all derive from "image input doesn't exist yet."

## Technical Context

**Language/Version**: Python 3.13 (backend), TypeScript 5.x (frontend)
**Primary Dependencies**: FastAPI, Anthropic SDK, SQLAlchemy (async), React 18, TanStack Query, SSE
**Storage**: Postgres (Railway prod) / SQLite (local dev)
**Testing**: pytest; `tests/test_chart_analyzer.py` already exists (verified passing in Spec 49 smoke)
**Target Platform**: V2 stack — `api` service on Railway, React via Vite/Capacitor
**Project Type**: Web full-stack feature extension
**Performance Goals**: FR-302 — analysis returns within 15 s end-to-end for 90% of requests
**Constraints**: SC-302 — 70% bias-correctness floor on a 30-chart audit at launch; SC-304 — 0 free-tier paywall bypasses; SC-307 — disclaimer present on 100% of renderings
**Scale/Scope**: Endpoint + ~3 frontend deltas + ~150 LOC of vision-prompt scaffolding

## Constitution Check

| Gate | Status |
|------|--------|
| No revival of "AI picks the trades" | ✅ Chart Critique is "user pastes, we analyze" — opposite of unattended scanning |
| Single LLM provider abstraction | ✅ Reuses `ask_coach` for text path; vision path goes through the same Anthropic client |
| Tier model coordination | ✅ `require_ai_access` + `check_usage_limit` already shared infrastructure |
| `chart_analyzer.py` preservation (Spec 49 FR-406) | ✅ Verified retained; this spec extends, not replaces |

No FR amendments to spec 51 required *if* the spec is reframed as "extend existing chart-analysis with image input." If the user wants to keep spec 51 as "build the headline new feature," then add **one** amendment:

| # | Amendment | Why |
|---|-----------|-----|
| **A-Recl** | Reclassify scope: spec body says "new headline paid feature." Audit shows the feature is 70% shipped. Update spec to read "image-input extension of the existing chart-analysis pipeline." | Honesty + prevents duplicate work |

## Project Structure

### Documentation (this feature)

```text
trade-analytics/specs/51-chart-critique/
├── spec.md                       # (existed)
├── plan.md                       # this file
├── research.md                   # the gap analysis (Phase 0 findings)
├── data-model.md                 # ChartAnalysis schema delta
├── quickstart.md                 # phased runbook (A → D)
├── checklists/requirements.md    # (existed)
└── contracts/
    ├── image-upload-api.md       # POST /analyze-chart accepts image_data
    ├── vision-prompt.md          # the prompt template for vision input
    └── tv-mcp-capture.md         # TradingView MCP integration contract
```

### Source Code (what changes)

```text
trade-analytics/
├── analytics/
│   └── chart_analyzer.py             # ADD: build_vision_prompt(), normalize_image_input()
├── api/app/
│   ├── routers/
│   │   └── intel.py                  # EXTEND: analyze_chart accepts image_data | ohlcv_bars
│   └── models/
│       └── chart_analysis.py         # ADD: input_kind, image_ref columns (Alembic migration)
└── web/src/
    ├── pages/
    │   ├── AICoPilotPage.tsx         # ADD: paste/upload dropzone + status
    │   └── ChartCritiquePage.tsx     # NEW: direct-entry route per FR-A4
    └── App.tsx                       # ADD: <Route path="chart-critique" .../>
```

## Phase 0: Research (COMPLETE — see research.md)

Key findings (also tabulated above):
1. `/api/v1/intel/analyze-chart` already exists, SSE-streamed, tier-gated, quota-tracked.
2. `chart_analyzer.py` has the full prompt/parse machinery; just lacks vision branch.
3. Frontend has the analyze button, error handling, billing redirect.
4. `models/chart_analysis.py` exists; just needs `input_kind`/`image_ref` columns.
5. Real gap = image input + vision LLM + TradingView MCP + direct route.

## Phase 1: Design & Contracts

**Outputs**:

1. **[data-model.md](./data-model.md)** — schema delta for `ChartAnalysis` (just the new columns + migration outline).
2. **[contracts/image-upload-api.md](./contracts/image-upload-api.md)** — the extended request schema for `POST /analyze-chart` (discriminated union: `{kind: "context", symbol, ohlcv_bars}` vs `{kind: "image", image_data, hint_symbol?}`).
3. **[contracts/vision-prompt.md](./contracts/vision-prompt.md)** — the prompt template for the vision branch (what the LLM sees + the response structure expectation).
4. **[contracts/tv-mcp-capture.md](./contracts/tv-mcp-capture.md)** — the TradingView MCP `capture_screenshot` integration shape.
5. **[quickstart.md](./quickstart.md)** — phased runbook A → D.

## Phase 2: Task planning preview (NOT executed)

- **Phase A — Image upload from browser (1–2 days)**:
  - Backend: extend `AnalyzeChartRequest` with `kind` discriminator; accept `image_data` (base64 PNG/JPEG, capped at 4 MB); validate; route to vision branch.
  - Engine: `build_vision_prompt(image_b64, hint_symbol?)`; switch to Anthropic vision-capable model.
  - DB: add `input_kind`, `image_ref` (object-store key or inline base64 hash) columns + Alembic migration.
  - Frontend: paste/upload dropzone on `AICoPilotPage` next to the existing "Analyze chart" button; show preview thumbnail; submit via new payload shape.
- **Phase B — Failure handling (1 day)**:
  - FR-317: vision-provider 5xx → graceful "try again" + don't decrement quota.
  - FR-318: low-confidence extraction → "couldn't read this clearly, try a higher-res screenshot."
- **Phase C — TradingView MCP capture (1 day)**:
  - Conditional: only if the MCP server is reachable from the api process.
  - Wire `mcp__tradingview__capture_screenshot` → image bytes → same vision pipeline.
  - Frontend "Capture from TradingView" button next to paste/upload.
- **Phase D — Direct-entry route (0.5 day)**:
  - New `web/src/pages/ChartCritiquePage.tsx` (thin wrapper around the analyzer UX, no chart selector — just the upload/capture flow).
  - Add `<Route path="chart-critique" />` to App.tsx.
- **Phase E — Validation + cost cap (0.5 day)**:
  - Reuse triage-agent's `TRIAGE_DAILY_USD_CAP` pattern: per-day spend ceiling on the chart-critique endpoint specifically.
  - Reviewer audit on a 30-chart sample to verify SC-302 ≥70% bias correctness.

Estimated total: ~4–5 working days for the full set. Phase A alone delivers the user-visible win.

## Stop and report

Plan complete. No implementation in this session — per "no rush" and the discovery that the feature is already 70% live, the next move is operator review of:

1. The reclassification (spec 51 = image-input extension, not greenfield)
2. The Phase A/B/C/D sequencing
3. The choice of Anthropic vision model (claude-3-5-sonnet currently supports vision; pick a specific model id)
4. The image storage choice (inline base64 in `ChartAnalysis.image_ref` vs S3/R2 object store)

Once reviewed, `/speckit-tasks` (or direct work) can start with Phase A.
