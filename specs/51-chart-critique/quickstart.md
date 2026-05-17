# Quickstart Runbook — Spec 51 Chart Critique (image-input extension)

**Purpose**: Sequenced phases for shipping image input on top of the already-live `/analyze-chart` pipeline.
**Audience**: maintainer / agent — next session.
**Estimated**: ~4–5 working days for the full set (Phase A alone is the user-visible win).

---

## Pre-flight (15 min)

1. **Operator decision**: confirm "extend existing" vs "build greenfield." Default per [plan.md](./plan.md) is extend.
2. **Operator decision**: Phase C (TradingView MCP) scope — defer / Capacitor-only / browser-extension. Default: defer until Phase A proves user demand.
3. **Operator decision**: image storage — discard after analysis (default) / inline base64 / S3.
4. **Pick vision model**: `claude-3-5-sonnet-20241022` is the default. Verify availability before Phase A.
5. **Pick daily cost cap**: vision calls are ~10–20× the cost of text calls. Recommend `CHART_CRITIQUE_DAILY_USD_CAP=20` to start. Operator sets in Railway env.

---

## Phase A — Image upload from browser (1–2 days)

### A1 — Backend extension

1. Add `AnalyzeChartContext` + `AnalyzeChartImage` + discriminated `AnalyzeChartRequest` per [contracts/image-upload-api.md](./contracts/image-upload-api.md).
2. In `analyze_chart` endpoint, branch on `body.kind`:
   - `"context"` — existing flow unchanged
   - `"image"` — new vision flow
3. Add `analytics/chart_analyzer.py::build_vision_prompt` + `parse_vision_response` per [contracts/vision-prompt.md](./contracts/vision-prompt.md).
4. Wire Anthropic vision model call (`messages.create` with image content blocks).
5. Pre-validate image: size cap, magic bytes, MIME match. Reject early (400) before any LLM call.
6. Parse response; if `extraction.confidence < 0.60` → emit `error: "low_confidence_extraction"`, do NOT decrement quota, do NOT persist.
7. On success: persist `ChartAnalysis` row with `input_kind="image"`, `extraction_confidence`, `image_ref` (per storage policy from pre-flight #3).
8. Add daily cost cap (`CHART_CRITIQUE_DAILY_USD_CAP`); enforce in the endpoint before vision call.

### A2 — DB migration

1. Generate Alembic migration per [data-model.md](./data-model.md).
2. Apply locally (`alembic upgrade head`).
3. Verify existing rows backfill with `input_kind="context"`.

### A3 — Frontend extension

1. Add paste/upload dropzone component on `AICoPilotPage` (drag-drop OR file picker OR `ctrl-v` paste).
2. Toggle UI between "Analyze current chart" (existing button, kind=context) and "Analyze pasted image" (new flow, kind=image).
3. On image submit:
   - Show preview thumbnail
   - Convert to base64
   - POST with `kind: "image"` payload
   - Stream SSE per existing flow
4. Handle new error codes: `low_confidence_extraction`, `vision_provider_degraded`, `image_too_large`, `unsupported_format`. Each shows a specific message.
5. Verify disclaimer appears in result rendering (FR-304 / SC-307).

### A4 — Tests

1. Backend: `tests/test_chart_analyzer_vision.py` (new). Mock Anthropic vision API. Assert request shape, response parsing, confidence gating, persistence, error events.
2. Backend: extend `tests/test_tv_webhook.py`-style integration test for the `/analyze-chart` endpoint with both `kind="context"` and `kind="image"` payloads.
3. Frontend: snapshot test for the dropzone and the new error message UIs.
4. `python3 -m pytest tests/ -v` must be green.
5. `npm run build` must be green.

### A5 — Acceptance

- POST with valid PNG returns SSE `done` event with `analysis_id` within 15 s (90% of 50-sample test).
- Free-tier user gets `upgrade_required` → /billing redirect (existing behavior unchanged).
- Paid-tier user at quota gets `quota_exhausted` event.
- Low-confidence image gets `low_confidence_extraction` event; quota unchanged; no DB row.
- Disclaimer renders in 100% of result UIs (SC-307).

---

## Phase B — Failure handling polish (1 day)

### B1 — Vision provider degradation (FR-317)

1. Wrap vision call in try/except for Anthropic 5xx / timeout.
2. On failure: emit `error: "vision_provider_degraded"`, do NOT decrement quota, do NOT persist.
3. Frontend shows: "Vision provider degraded, try again in a few minutes."

### B2 — Low-confidence UX (FR-318)

1. When `low_confidence_extraction` event arrives, frontend shows:
   - "Couldn't read this chart clearly."
   - Specific reason from `confidence_note` field.
   - Recommendation: "Try a higher-resolution screenshot, or zoom in before capturing."
   - "Try again" button reopens the dropzone.

### B3 — Verification

- Inject a vision error via feature flag → verify graceful UX + 0 quota decrement.
- Submit a deliberately blurry chart → verify low-confidence path.
- Submit a chart of a non-supported market (e.g., a futures contract) → vision will likely return low confidence; verify graceful handling.

---

## Phase C — TradingView MCP capture (DEFERRED)

Per [contracts/tv-mcp-capture.md](./contracts/tv-mcp-capture.md), this needs operator decision on transport (Capacitor-only vs browser-extension vs defer). Default: skip until Phase A proves user demand. Documented as a follow-up ticket.

---

## Phase D — Direct-entry `/chart-critique` route (0.5 day)

### D1

1. Create `web/src/pages/ChartCritiquePage.tsx` — thin wrapper around the image-upload flow from Phase A3. No chart selector, no symbol dropdown — just the upload UX + result display.
2. Add `<Route path="chart-critique" element={<ProtectedRoute>...</ProtectedRoute>} />` to `App.tsx`.
3. Add nav link from `AppLayout` (alongside Trading / Co-Pilot / etc.).
4. Update landing page (spec 50) to deep-link "AI Chart Critique" deliverable to `/chart-critique` instead of the current waitlist mailto.

### D2 — Verification

- Directly visiting `/chart-critique` (logged in) renders the page.
- Logged-out user gets redirected to `/login` then back.
- Spec 50 "what you get" card for Chart Critique now has a real link, not a mailto.

---

## Phase E — Validation + cost cap soak (0.5 day + 30 days of light watching)

### E1 — Reviewer audit (SC-302 / SC-307)

1. Collect a 30-chart representative sample (mix of clean setups, mid-trades, messy charts; mix of equities, ETFs, crypto).
2. Run each through Phase A.
3. Reviewer scores each: did the bias call match the reasonable read? Bar: ≥21 of 30 (70%) correct.
4. Record results in `decision.md`.

### E2 — Cost cap soak

1. Watch `CHART_CRITIQUE_DAILY_USD_CAP` actual spend for 30 days.
2. Adjust cap if real usage diverges from estimate.
3. Add Telegram alert when daily spend > 80% of cap.

---

## Rollback plan

- DB migration is additive (only adds nullable columns + a NOT NULL with default). Rollback is `alembic downgrade -1`.
- Endpoint extension is backward-compatible only at the new payload shape; existing clients (pre-Phase-A-frontend) keep working because they send the `kind="context"` shape — which the new Pydantic union still accepts.
- Frontend: revert the dropzone component; existing analyze button keeps working.

Each phase is independently revertable.

---

## Done definition (per phase)

### Phase A
- [ ] Backend accepts `kind="image"` payloads
- [ ] DB migration applied
- [ ] Frontend has working paste/upload UX
- [ ] Disclaimer renders 100% of time
- [ ] Cost cap configured
- [ ] Tests green

### Phase B
- [ ] Vision degradation handled gracefully
- [ ] Low-confidence path enforced
- [ ] Quota never decremented on error

### Phase D
- [ ] `/chart-critique` route reachable
- [ ] Spec 50 landing updated to deep-link

### Phase E
- [ ] 30-chart audit ≥21/30 bias accurate
- [ ] Cost cap measured in production
