# Sub-spec F — AI Services & Token Economy (P2)

**Parent:** #64 Launch Value Master · **Pillar:** Monetizable value · **Priority:** P2

## Overview
Turn AI from a scattered feature into a **token-metered value product**: the user spends tokens to have AI do the chart-staring — analyze a name, write a trade thesis, review their journal, synthesize timeframes, coach them. One unified, telemetered generation path, a visible balance, and honest per-call accounting.

## Problem (current state)
AI works but isn't a product: alert **narratives** (Haiku/Sonnet) and an **AI Trade Coach** exist, plus scattered analysis buttons. **But:** metering is **feature-count, not token-based** (`usage_limits`: free = 3 `ai_query`/day); there's **no generation telemetry**, **no visible quota meter**, BYOK keys are **plaintext**, Stripe is scaffolded-not-wired, and each AI call resolves its provider/key/model independently (no single contract). The interview-copilot specs already define the better pattern (internal `generate()` contract, BYOK-with-platform-default, visible monthly quota, per-generation telemetry).

## Target state
A clean AI value menu, every call flowing through **one `generate()` contract** that resolves provider/key/model, counts tokens, records telemetry, and gates on the user's token balance. The user sees their balance, spends it on clearly-priced services, and can bring their own key (encrypted).

## Scope

**Infrastructure:**
- **Unified `generate()` contract** — single path for all AI calls (narratives, coach, analysis); handles model routing (Haiku/Sonnet), key resolution (BYOK → platform default), token counting, and quota gating atomically.
- **Generation telemetry** — per call: feature, model, input/output tokens, cost, success/failure, timestamp.
- **Token-based metering** — replace feature-count with token budgets per tier (e.g. Free ~10K/mo, Pro ~100K/mo, Elite unlimited) + optional **token packs**.
- **Visible quota meter** — tokens used / remaining, in Settings and at point-of-use.
- **Encrypt BYOK keys at rest.**

**The AI value menu (token-metered services):**
1. **Analyze this chart / name** — on-demand technical read (levels, trend, structure, the "what would I do here").
2. **Trade thesis on an alert** — the narrative, on demand, for any fired or candidate setup.
3. **Journal review** — multi-trade analysis of P&L, psychology, recurring mistakes (highest willingness-to-pay).
4. **Multi-timeframe synthesis** — daily + weekly + monthly + macro into one read.
5. **Trade Coach** — multi-turn conversational (token-per-turn).
6. **Win-rate / optimization analysis** — cohort review by pattern/symbol/timeframe.

## Acceptance criteria
- **F-1:** All AI calls route through one `generate()` path; no feature resolves provider/key independently.
- **F-2:** Every AI call records token telemetry (feature, model, tokens, cost).
- **F-3:** Users see a token balance and remaining quota; spending a service decrements it.
- **F-4:** At least three services from the menu are live (e.g. chart analysis, trade thesis, journal review).
- **F-5:** BYOK keys are encrypted at rest.

## Out of scope
- Full billing/Stripe wiring beyond what gates token packs (can follow).
- Real-time streaming for every service (coach streams; others may be request/response at launch).

## Notes
The interview-copilot specs (005 LLM-provider-config, 008 session-history) are the reference architecture — reuse the internal-contract + BYOK + quota patterns. Journal review + chart analysis are the two services with the clearest "I'd pay tokens for that" pull for a busy trader.
