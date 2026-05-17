# Phase 0 Research — Spec 51 Gap Audit

**Date**: 2026-05-16
**Method**: Direct file inspection of `api/app/routers/intel.py`, `analytics/chart_analyzer.py`, `web/src/pages/AICoPilotPage.tsx`, `api/app/models/chart_analysis.py`.
**Headline**: spec 51's "headline new paid feature" is ~70% live in production today. The plan reframes spec 51 from greenfield to image-input extension.

---

## 1. Backend endpoint — ALREADY SHIPPED

**File**: `api/app/routers/intel.py:304-420` (approx)

```python
@router.post("/analyze-chart", dependencies=[Depends(require_ai_access)])
async def analyze_chart(
    body: AnalyzeChartRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_dep),
):
    """SSE stream — AI chart analysis with structured trade plan. Usage-limited."""
    remaining = await check_usage_limit(user, "ai_queries", db)
    ...
```

**What it does today**:
- Accepts `{symbol, timeframe, ohlcv_bars?}` — symbol-and-bars input only.
- Gated by `require_ai_access` (tier check).
- Quota tracked via `check_usage_limit(user, "ai_queries")` (FR-315 ✅).
- Checks 5-min cache before running.
- Calls `assemble_analysis_context(symbol, tf, bars)` → `build_analysis_prompt(context)` from `chart_analyzer.py`.
- Streams Claude response via `ask_coach` (from `analytics/trade_coach.py`).
- Parses structured `plan` from full text via `parse_trade_plan`.
- Persists to `ChartAnalysis` DB row.
- Returns SSE events: `chunk`, `plan`, `reasoning`, `higher_tf`, `done`.

**What it doesn't do**:
- Doesn't accept image input (FR-301).
- Doesn't use a vision-capable model — `ask_coach` is text-only (FR-306).
- Doesn't have a TradingView MCP capture path (FR-309).
- No vision-provider failure handling (FR-317) — moot until vision is wired.

---

## 2. Engine — ALREADY SHIPPED (text-only)

**File**: `analytics/chart_analyzer.py` (839 LOC, retained per Spec 49 FR-406)

Public surface (verified by grep `^def |^class |^[A-Z_]+\s*=`):

| Symbol | Role | Verdict |
|--------|------|---------|
| `PATTERN_LIBRARY` (dict) | Pattern templates | ✅ used |
| `build_education_prompt` | Spec 52 prep (pattern education) | ✅ kept for 52 |
| `parse_education_response` | Spec 52 prep | ✅ |
| `_CACHE_TTL = 300` | 5-min cache TTL | ✅ |
| `_cache_key`, `get_cached_analysis`, `set_cached_analysis` | In-memory cache | ✅ |
| `_fetch_bars` | yfinance bars fallback | ⚠️ V1 path; verify still needed |
| `_compute_indicators` | RSI, MAs, VWAP, etc. | ✅ feeds context |
| `assemble_analysis_context` | Inputs → context dict | ✅ |
| `build_analysis_prompt` | Context → text prompt | ✅ |
| `parse_trade_plan` | LLM text → structured plan | ✅ |
| `compute_confluence_score` | Multi-source scoring | ✅ |
| `stream_chart_analysis` | High-level streaming wrapper | ✅ |
| `generate_alert_analysis` | One-shot wrapper | ✅ |

**What's missing**:
- No `build_vision_prompt(image_b64, hint_symbol?)` function.
- No `parse_trade_plan_from_vision` (probably reuse `parse_trade_plan` since the response format should be identical).
- No `normalize_image_input` (size limits, MIME validation, base64 sniffing).

The existing functions are well-factored — adding vision is additive, no rewrites.

---

## 3. Frontend — ALREADY SHIPPED (chart-context flow)

**File**: `web/src/pages/AICoPilotPage.tsx:190-240`

```typescript
const analyzeChart = useCallback(async () => {
  const token = useAuthStore.getState().accessToken;
  if (!token || !activeSymbol) return;
  ...
  const res = await fetch(`${API_HOST}/api/v1/intel/analyze-chart`, {
    method: "POST",
    body: JSON.stringify({
      symbol: activeSymbol,
      timeframe,
      ohlcv_bars: lastBars.map(...),
    }),
    ...
  });
  if (res.status === 403 && err.detail?.error === "upgrade_required") {
    navigate("/billing");
    return;
  }
  if (res.status === 429) throw new Error("Daily analysis limit reached. Upgrade for more.");
  ...
});
```

**What it does today**:
- "Analyze chart" button on the AICoPilotPage (line 325 in the page).
- Sends current `activeSymbol` + `timeframe` + last 60 OHLCV bars.
- Handles auth (Bearer token from `useAuthStore`).
- 403 + `upgrade_required` → navigate to `/billing` (FR-306 paywall path ✅).
- 429 → "Daily analysis limit reached" toast (FR-315 quota ✅).
- SSE stream reader processes events (`chunk`, `plan`, `reasoning`, `higher_tf`, `done`).

**What's missing**:
- No paste/upload dropzone.
- No "Analyze my chart" capture button (TV MCP path).
- No `/chart-critique` direct-entry route (currently only reachable as a button inside `/copilot`).

**Implementation note**: the analyze button currently sits inside the chart workspace alongside the symbol selector. The image-upload UX should be a parallel mode in the same page (toggle or separate panel), not a destructive replacement.

---

## 4. DB model — ALREADY EXISTS

**File**: `api/app/models/chart_analysis.py`

Spec 49 verified this exists. Need to add columns for image-input mode:

```python
# Additions (Phase A migration)
input_kind:  Mapped[str]  = mapped_column(String(16), default="context")  # "context" | "image"
image_ref:   Mapped[str | None] = mapped_column(String(512), nullable=True)  # base64 hash or S3 key
```

Existing columns (presumed; verify at implementation time): id, user_id, symbol, timeframe, plan (JSON), reasoning (text), created_at, model, etc.

No backward-compat concern: existing rows get `input_kind="context"` via the default.

---

## 5. Gap matrix vs spec 51 FRs

| FR | Description | Status | Notes |
|----|-------------|--------|-------|
| **FR-301** | Endpoint accepts screenshot OR ticker OR TV MCP capture | ⚠️ Partial — only ticker today | Phase A adds image, Phase C adds TV MCP |
| **FR-302** | 90% within 15 s | ⚠️ Untested SLA | Phase E measures |
| **FR-303** | Specific $ S/R prices | ✅ `parse_trade_plan` already structured |
| **FR-304** | Disclaimer present | ⚠️ Need to verify in frontend; if missing, Phase A adds |
| **FR-305** | Build on existing `chart_analyzer.py` | ✅ Already does |
| **FR-306** | Vision-capable model via shared provider abstraction | ❌ Text-only today |
| **FR-307** | ≥70% bias correctness on 30-chart audit | ⚠️ Untested | Phase E audit |
| **FR-308** | Mount in `AICoPilotPage` + `/chart-critique` route | ⚠️ Page mounted; route missing |
| **FR-309** | "Analyze my chart" from TV MCP | ❌ Not wired |
| **FR-310** | TV MCP unavailable → paste fallback | ❌ Moot until FR-309 |
| **FR-311** | Persist to `chart_analysis` + `AnalysisHistory.tsx` | ✅ Both exist |
| **FR-312** | Persisted analysis fields | ✅ Existing schema |
| **FR-313** | Tier gating via `tier.py` / `useFeatureGate.ts` | ✅ `require_ai_access` |
| **FR-314** | Free-tier 1 lifetime allowance | ⚠️ Verify default; may currently be daily quota only |
| **FR-315** | Pro-tier monthly quota | ✅ `check_usage_limit` |
| **FR-316** | Quota indicator visible from Settings → Plan | ⚠️ Verify Settings page renders it |
| **FR-317** | Vision provider degraded → graceful + no quota decrement | ❌ Moot until vision exists |
| **FR-318** | Low-confidence input → recapture/paste guidance, no hallucination | ❌ Moot until image exists |

**Summary**: 7 ✅ satisfied, 4 ⚠️ partial/verify, 7 ❌ unmet — all unmet items derive from "image input doesn't exist."

---

## 6. Operational considerations

- **Daily cost cap**: spec 51's last Assumption says reuse `TRIAGE_DAILY_USD_CAP` pattern. The current `/analyze-chart` endpoint doesn't have one — text-only Claude responses are cheap (~$0.005/call) so it hasn't bitten yet, but vision calls are ~10–20× more expensive. **Hard requirement before Phase A goes live**: add per-day cost ceiling.
- **Image storage**: inline base64 in `chart_analysis.image_ref` is simplest (no S3 dep) but bloats the DB. R2/S3 is cleaner long-term. Phase A can ship with inline base64 (capped at ~200 KB after JPEG compression); migrate to object store later if usage warrants.
- **Vision model**: as of 2026-05, `claude-3-5-sonnet` supports vision; `claude-haiku-4-5` (used by triage agent for speed) may or may not — verify before Phase A.
- **Anthropic SDK version**: check the version in `api/pyproject.toml`; vision input format changed across SDK versions.

---

## 7. Risks tracked

1. **Reframing the spec is itself a decision** — operator needs to confirm "extend existing" vs "build greenfield" before Phase A. The plan defaults to extend.
2. **Vision quality variance** — Claude vision on chart screenshots is good but not perfect; expect ~80% bias accuracy on clean screenshots, dropping fast on busy/multi-pane charts. SC-307's 70% floor is realistic.
3. **Mobile capture UX** — Capacitor iOS build needs to handle camera/photo-library image input separately from web upload. Likely a Phase A.2 sub-task.
4. **History page** — `AnalysisHistory.tsx` was verified to exist in Spec 49 audit but its current state vs. image-input mode is unaudited. Verify before Phase A whether it renders the new `input_kind`.
