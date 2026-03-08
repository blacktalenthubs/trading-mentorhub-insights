# Ticket: MA Confluence Detection & Institutional Support Capture

## Problem

The current MA bounce rules work in isolation — each rule checks a single MA independently. In reality, the highest-conviction institutional buying happens when **multiple levels converge** at the same price zone. Today's market (2026-03-03) showed this clearly:

**Missed confluence signals:**
- **LRCX**: 50MA + horizontal support at ~$217 = double bottom bounce. We fired `session_low_double_bottom` but missed that the 50MA was *also* right there reinforcing the level.
- **NVDA**: Weekly level $177 + 50MA confluence. `weekly_level_touch` fired but didn't flag the MA alignment — this was a 2x confidence setup.
- **SPY**: 200MA is the institutional floor. Bounce was valid but all shorter MAs (20/50/100) stacked above as resistance.

**Current gaps:**
1. **No confluence detection** — MA near a horizontal level (prior low, weekly level, planned level) isn't recognized as a stronger signal
2. **MA bounce 20/50 too strict** — Requires uptrend (20MA > 50MA). Filters out valid pullback-to-50MA bounces in neutral/consolidating markets
3. **No MA role-flip awareness** — When price breaks below an MA, that MA becomes resistance. We don't track this transition or use it to upgrade resistance signals
4. **No confluence scoring boost** — Two levels at the same price = higher conviction, but we treat them as independent events

## Why This Matters

Institutional buyers accumulate at MA levels, especially MA50/100/200. When these align with a horizontal support (prior day low, weekly level), the bounce probability is significantly higher. Capturing these confluences means:
- Higher confidence alerts → more tradeable signals
- Better position sizing (higher conviction = can size up)
- Fewer false signals (confluence = natural filter)

## Requirements

### 1. MA + Horizontal Level Confluence Detection

When a BUY alert fires (support_bounce, weekly_level, prior_day_low, planned_level, session_low_double_bottom), check if any MA is within a proximity band of that level:

```
CONFLUENCE_BAND_PCT = 0.5%  (MA within 0.5% of the horizontal level)
```

If confluence found:
- Append to alert message: `"MA50 confluence at $X.XX — institutional support"`
- Boost confidence: `medium` → `high`
- Add `confluence: true` and `confluence_ma: "50"` fields to AlertSignal

MAs to check: 20, 50, 100, 200 (prioritize highest MA match — 200MA confluence > 20MA confluence).

### 2. Relax MA50 Bounce Uptrend Requirement

Current: `ma_bounce_50` requires `ma20 > ma50` (strict uptrend).

Change to: Fire in **any trend** but adjust confidence:
- `ma20 > ma50` (uptrend) → confidence `high`
- `ma20 <= ma50` (neutral/downtrend) → confidence `medium`, append "counter-trend bounce" to message

Rationale: 50MA is a major institutional level. Stocks bounce off 50MA even in consolidation phases. The uptrend filter caused us to miss LRCX's 50MA bounce today.

### 3. MA Role-Flip Tracking

Track when price **breaks below** an MA (close below MA for 2+ bars). When this happens:
- That MA becomes a **resistance level** for subsequent `ma_resistance` checks
- Boost resistance signal confidence when the MA was recently broken (within 5 bars)
- Add to message: `"MA20 flipped to resistance 2 bars ago"`

This helps identify the TSLA pattern: 20MA/50MA broke, now they're ceilings.

### 4. Confluence Scoring Boost

In `compute_signal_score()` or at alert enrichment time:
- If an alert has MA confluence → +10 to signal score
- If 2+ MAs converge at the same level → +15
- Cap at 100

## Implementation Notes

- Confluence check should be a **shared utility** called after any BUY alert fires, not duplicated per rule
- MA values are already available in the `evaluate_symbol()` context — pass them to the confluence checker
- The AlertSignal dataclass may need `confluence: bool` and `confluence_ma: str` fields
- Don't create new alert types — confluence enriches existing alerts

## Acceptance Criteria

- [ ] BUY alerts include MA confluence info in message when MA aligns with the level
- [ ] Confluence boosts confidence from medium → high
- [ ] `ma_bounce_50` fires in neutral trends (not just uptrends) with adjusted confidence
- [ ] MA resistance signals note recent MA breaks ("flipped to resistance")
- [ ] Signal score gets +10 boost for MA confluence
- [ ] All existing tests pass
- [ ] New tests: confluence detection, relaxed MA50, role-flip tracking
- [ ] Verify against today's data: LRCX should show 50MA confluence, NVDA should show weekly+MA confluence

## Out of Scope
- Multi-timeframe MA confluence (e.g., weekly 20MA = daily 100MA) — future ticket
- Auto position sizing based on confluence — future ticket
- Volume confirmation at MA levels (institutions buy with volume) — separate enhancement

## Reference Charts
- `images/img.png` — LRCX: 50MA + horizontal support confluence
- `images/img_1.png` — NVDA: weekly level + 50MA confluence
- `images/img_2.png` — TSLA: MA20/50 flipped to resistance after break
- `images/img_3.png` — SPY: 200MA institutional support, all shorter MAs as resistance
