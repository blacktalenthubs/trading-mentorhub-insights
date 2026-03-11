# AI Enhancements Roadmap — 6 Features, 3 Phases

## Overview

Six AI-powered features to improve trade signal accuracy, build a learning feedback loop, and give the trader deeper insight. Ordered by dependency chain and risk level.

---

## Phase 1: Feed Data INTO AI (low risk, no business logic changes)

### Feature 1: Win-Rate-Aware Coach Context
**What**: Feed per-rule-type win rates and per-symbol win rates directly into the Coach system prompt so AI gives rule-specific advice.

**Why**: Coach currently treats all alert types equally. "Your MA bounce alerts win 62% of the time, but VWAP reclaims only 41%" changes the advice completely.

**Files to modify**:
| File | Change |
|------|--------|
| `analytics/trade_coach.py` | Add win-rate-by-rule-type and win-rate-by-symbol to `assemble_context()` and `format_system_prompt()` |

**Data source**: `intel_hub.get_alert_win_rates()` already returns `by_alert_type` and `by_symbol` — just pipe it into the Coach prompt.

**Effort**: ~30 lines. **Risk**: Zero — read-only data addition to prompt.

---

### Feature 2: Score Factor Transparency
**What**: Surface the `score_factors` breakdown (MA: 25, Vol: 15, Conf: 25, VWAP: 10, RR: 5) in the alert notification and Coach context.

**Why**: "B (60)" is opaque. "B (60): MA 0/25, Vol 15/25, Conf 15/25, VWAP 10/25, RR 5/5" tells you exactly where the setup is weak.

**Files to modify**:
| File | Change |
|------|--------|
| `alerting/notifier.py` | Add score factor breakdown to Telegram message |
| `analytics/trade_coach.py` | Include score_factors in today's alerts context |

**Data source**: `AlertSignal.score_factors` dict — already computed, just not displayed.

**Effort**: ~20 lines. **Risk**: Zero — display only.

---

### Feature 3: Multi-Timeframe Synthesis Tab
**What**: New tab in AI Intelligence Hub that combines daily + weekly analysis into one Claude call. Detects alignment or conflict between timeframes.

**Why**: The META example showed daily bearish below all MAs. If weekly shows BASE_FORMING, that's a conflict worth flagging. If weekly also bearish, conviction to avoid is much higher.

**Files to modify**:
| File | Change |
|------|--------|
| `pages/11_AI_Coach.py` | Add "MTF Synthesis" tab with combined daily+weekly context → Claude call |
| `analytics/intel_hub.py` | Add `synthesize_timeframes()` helper that assembles daily+weekly context |

**Effort**: ~80 lines. **Risk**: Zero — new tab, read-only.

---

## Phase 2: AI Feedback Loop (medium risk, adds new data)

### Feature 4: Outcome-Linked Trade Review
**What**: When a real trade closes (target hit or stop out), auto-generate an AI post-trade analysis. Store it alongside the trade record.

**Why**: Currently AI generates a narrative at entry but never sees the outcome. This closes the loop: "Entry was based on MA bounce at SMA50. Price held SMA50 for 2 bars then broke down. The daily trend was bearish — this was a counter-trend trade. Decision quality: good risk management, but setup was fighting the trend."

**Flow**:
```
close_real_trade() → trigger AI review
  → send: entry signal, score, narrative, outcome, P&L, holding period, market conditions
  → receive: structured review (decision quality, what worked, what didn't, lesson)
  → store in real_trades.ai_review column
```

**Files to modify**:
| File | Change |
|------|--------|
| `db.py` | Add `ai_review TEXT` column to `real_trades` table (migration) |
| `analytics/trade_review.py` | **NEW** — `generate_trade_review()` function |
| `alerting/real_trade_store.py` | Call `generate_trade_review()` after `close_real_trade()` |
| `pages/8_Real_Trades.py` | Display AI review in trade detail view |

**Effort**: ~120 lines. **Risk**: Low — writes to new column only, doesn't change close logic.

---

### Feature 5: Personalized Coach Tuning
**What**: Enrich the Coach system prompt with behavioral patterns: which rules the user takes vs skips, win rates on took vs skipped, common mistakes (early exits, holding losers too long), and personalized recommendations.

**Why**: `decision_quality` data exists but the Coach barely references it. "You skip 70% of inside day breakouts, but they win 65% of the time" is actionable coaching.

**Data needed** (all exists):
- `get_decision_quality()` → took_wr vs skipped_wr
- `get_trading_journal()` → per-trade took/skipped with outcomes
- `get_acked_trade_win_rates()` → user-specific win rates

**Files to modify**:
| File | Change |
|------|--------|
| `analytics/trade_coach.py` | Expand behavioral analysis section in `assemble_context()`: add took-vs-skipped breakdown by rule type, common patterns (avg hold time, early exit rate), personalized tip |

**Effort**: ~60 lines. **Risk**: Zero — prompt enrichment only.

---

## Phase 3: AI in the Alert Pipeline (higher risk, touches business logic)

### Feature 6: AI Conviction Filter
**What**: After `evaluate_rules()` produces candidate signals, send each to Claude for a conviction score (0-100). Signals below threshold get suppressed or demoted. Signals above threshold get boosted.

**Why**: This is the biggest accuracy improvement. The LLM sees context the rules can't encode: "This is a B-score MA bounce, but daily chart shows MA compression about to resolve higher, and this rule type has 68% win rate in current regime — conviction: HIGH."

**Flow**:
```
evaluate_rules() → candidate signals
  → for each signal: build context (OHLCV, MAs, volume, SPY regime, daily/weekly trend, rule win rate)
  → Claude call → returns {conviction: 0-100, reasoning: str}
  → if conviction < 40: suppress signal
  → if conviction > 80: boost score by 10
  → attach conviction + reasoning to AlertSignal
  → proceed to dedup → notify
```

**Files to modify**:
| File | Change |
|------|--------|
| `alert_config.py` | Add `AI_CONVICTION_ENABLED`, `AI_CONVICTION_SUPPRESS_THRESHOLD`, `AI_CONVICTION_BOOST_THRESHOLD` |
| `analytics/ai_conviction.py` | **NEW** — `score_conviction()` function, prompt template, structured output parsing |
| `analytics/intraday_rules.py` | After scoring loop, call conviction filter (gated by feature flag) |
| `alerting/notifier.py` | Display conviction score + reasoning in alert message |
| `db.py` | Add `ai_conviction INTEGER`, `ai_reasoning TEXT` columns to alerts table |

**Effort**: ~150 lines. **Risk**: MEDIUM — touches the alert pipeline. Feature-flagged so can be toggled off instantly.

**Cost**: ~$0.15-0.30/day (Haiku for most signals, Sonnet for A-grade signals).

**Latency**: Claude Haiku responds in <1s. Alert fires immediately, conviction score appended async (update DB + edit Telegram message after AI response).

---

### Feature 6b: Pattern Classification (extension of conviction filter)
**What**: Send the last 20 daily candles as structured text to Claude. Classify the pattern (bull flag, ascending triangle, distribution, double bottom, etc.) and provide key levels.

**Why**: Enriches the daily setup detection beyond rule-based patterns. "PULLBACK_TO_MA" is mechanical — "pullback to SMA50 within a bull flag on the daily, 3rd touch of rising trendline" is much more actionable.

**Files to modify**:
| File | Change |
|------|--------|
| `analytics/intel_hub.py` | Add `classify_daily_pattern()` function |
| `pages/11_AI_Coach.py` | Display pattern classification in Daily View tab |

**Effort**: ~60 lines. **Risk**: Low — enrichment only, no business logic changes.

---

## Implementation Order

```
Phase 1 (safe, immediate value):
  1. Win-Rate-Aware Coach     → 30 min
  2. Score Factor Transparency → 20 min
  3. MTF Synthesis Tab         → 1 hour

Phase 2 (feedback loop):
  4. Outcome-Linked Review     → 1.5 hours
  5. Personalized Coach        → 45 min

Phase 3 (pipeline enhancement):
  6. AI Conviction Filter      → 2 hours
  6b. Pattern Classification   → 45 min
```

## What Does NOT Change
- `analytics/intraday_rules.py` — Alert trigger conditions unchanged (conviction filter is additive, not modifying)
- `monitor.py` / `worker.py` — Poll loop unchanged
- `alerting/alert_store.py` — Dedup/cooldown logic unchanged
- Existing scoring (v1/v2) — Preserved, conviction is a separate layer

## Cost Estimate
- Phase 1: $0/month (uses existing Claude calls or adds minimal tokens to existing prompts)
- Phase 2: ~$1-2/month (one Claude call per closed trade, ~3-5/day)
- Phase 3: ~$5-8/month (conviction scoring on ~15 signals/day)
