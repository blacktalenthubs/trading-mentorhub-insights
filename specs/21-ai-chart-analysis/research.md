# Research Notes: AI-Powered Multi-Timeframe Chart Analysis

## Decision 1: Numerical vs Vision-Based Chart Analysis

**Decision**: Use numerical OHLCV + indicator analysis as the sole input to AI. No chart screenshot/vision analysis.

**Rationale**:
- Vision models (Claude, GPT-4V) cannot extract precise price levels from screenshots ($182.40 vs $182.80 matters for stops)
- Numerical analysis is 3-10x cheaper per API call
- Latency: <1s for text vs 2-5s for vision
- Numerical data is deterministic and backtestable; screenshots are not
- The platform already computes all needed indicators (MAs, RSI, VWAP, ADX, S/R levels)

**Alternatives Considered**:
- Vision-only: Too imprecise for trade plan generation, too expensive at scale
- Hybrid (numerical + screenshot): Added cost and latency for marginal benefit; could add later as a premium feature

## Decision 2: Structured Output Approach

**Decision**: Use a dedicated system prompt with explicit JSON-like output format instructions, parsed into structured trade plan fields.

**Rationale**:
- Claude reliably produces structured output when given explicit format instructions
- The existing `ask_coach()` streaming mechanism can be reused with a different system prompt
- Structured fields (entry, stop, targets, R:R) can be extracted from the stream and displayed in UI cards
- The same structured output works for both web display and Telegram notification

**Alternatives Considered**:
- Tool use / function calling: More reliable extraction but doesn't support streaming; latency unacceptable
- Post-processing regex: Fragile; structured prompting is more robust

## Decision 3: Multi-Timeframe Data Assembly

**Decision**: For each analysis, fetch the user's timeframe + 2 higher timeframes. Use existing `get_daily_bars()`, `get_weekly_bars()`, and `fetch_intraday()` functions.

**Rationale**:
- Higher timeframe context is critical for confluence scoring (documented in research)
- The platform already has `analyze_daily_setup()` and `analyze_weekly_setup()` which return structured dicts
- `build_mtf_context()` already exists but has a signature mismatch with the MTF endpoint (bug)
- Reuse these functions rather than building new data pipelines

**Alternatives Considered**:
- Single timeframe only: Loses confluence scoring, which is the key differentiator
- All timeframes simultaneously: Too much data, increases prompt size and cost unnecessarily

## Decision 4: Model Selection for Analysis

**Decision**: Use Claude Haiku for standard analysis (cost-effective), Claude Sonnet for "deep analysis" (premium feature).

**Rationale**:
- Haiku produces acceptable trade plans at ~$0.003-0.01 per analysis
- 50 analyses/day for Pro user = $0.15-0.50/day — sustainable
- Sonnet provides deeper reasoning for complex setups
- The existing `ask_coach()` already accepts a `model` parameter override

**Alternatives Considered**:
- Sonnet-only: 10x cost increase, not sustainable for high-volume usage
- Haiku-only: Loses the "deep analysis" upsell opportunity for Premium tier

## Decision 5: Caching Strategy

**Decision**: Cache analysis results for 5 minutes per (symbol, timeframe, user_id) key. Return cached result on duplicate requests.

**Rationale**:
- Prevents duplicate API calls when users click "Analyze Chart" multiple times
- 5-minute TTL matches the existing context cache in `assemble_context()`
- In-memory cache (existing pattern) is sufficient; no Redis needed

**Alternatives Considered**:
- No cache: Wasteful, expensive, poor UX
- Longer TTL (15-30 min): Stale during fast markets; 5 min balances freshness vs cost
- Persistent DB cache: Overkill; in-memory is fine since analyses are ephemeral

## Decision 6: Alert Auto-Analysis Architecture

**Decision**: Run AI analysis asynchronously after alert delivery. Fire-and-forget with retry on failure.

**Rationale**:
- Alert delivery must not be delayed by AI analysis (constitution: Alert Quality Over Quantity)
- The analysis can be appended to the alert record in DB and pushed to Telegram as a follow-up message
- If AI analysis fails, the alert itself is unaffected

**Alternatives Considered**:
- Synchronous (block alert until AI responds): Violates alert delivery speed requirements
- Pre-compute all watchlist analyses: Too expensive; only analyze when an alert actually fires

## Decision 7: Existing MTF Endpoint Bug

**Decision**: Fix the `build_mtf_context()` signature mismatch as part of this feature. Create a wrapper function that fetches data internally.

**Rationale**:
- The `/intel/mtf/{symbol}` endpoint currently calls `build_mtf_context(symbol)` with 1 arg, but the function requires 7 args
- This is a prerequisite for the multi-timeframe confluence feature
- Fix creates a clean `get_mtf_analysis(symbol)` function that handles all data fetching internally

**Alternatives Considered**:
- Leave broken, build new: Duplicates logic; better to fix and extend
