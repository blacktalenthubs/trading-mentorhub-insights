# Spec 45: Multi-Timeframe Confluence

**Status:** SHIPPED  
**Date:** 2026-04-17

## Problem

The Spec 44 WAIT override fires LONG when the AI describes a valid 5-min setup (bounce, reclaim, etc.) but returns WAIT. However, some of these are counter-trend bounces — the 5m shows a PDL bounce, but the 4H trend is bearish (lower highs, price below EMA). Counter-trend entries stop out quickly.

## Solution

Add a higher-timeframe (HTF) bias computed from 4H and 1H bars:

1. **`_compute_htf_bias(bars)`** — pure Python, no AI call. Returns BULL/BEAR/NEUTRAL from EMA-20 position + higher-lows/lower-highs on last 3 bars.
2. **Prompt enrichment** — one-line `[HIGHER TIMEFRAME BIAS]` block added to AI prompt so Claude factors 4H/1H trend into its own decisions.
3. **Post-parse gate** — blocks counter-trend WAIT overrides (LONG when 4H=BEAR, SHORT when 4H=BULL). AI's own committed LONG/SHORT decisions are NOT gated.

## Design Decisions

- **Only gate overrides, not AI's own LONGs.** The AI already sees HTF context in the prompt. Gating AI LONGs would be too aggressive (e.g., a strong PDL double-bottom at MA200 should fire even in a 4H downtrend).
- **NEUTRAL = no gating.** Insufficient signal is not a reason to block.
- **4H bars via existing data layer.** Alpaca `("Hour", 4)` for equities, Coinbase `14400` for crypto. No new API dependencies.
- **Env flag `MTF_CONFLUENCE_ENABLED`** for instant rollback (default "true").

## Files Changed

| File | Change |
|------|--------|
| `analytics/ai_day_scanner.py` | `_compute_htf_bias()`, `_format_htf_context()`, env flag, prompt param, 4H fetch, override gate |
| `tests/test_ai_day_scanner.py` | 16 tests in `TestSpec45MTFConfluence` |

## Rollback

Set `MTF_CONFLUENCE_ENABLED=false` in Railway env vars. No code rollback needed.
