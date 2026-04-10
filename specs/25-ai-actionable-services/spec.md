# AI Actionable Services — Spec 25

**Status**: Draft
**Created**: 2026-04-09
**Priority**: High — AI is the core product differentiator
**Depends on**: Spec 23 (alert engine redesign — entries first)

## Core Principle

> Every AI output must help the user decide: **enter, exit, or wait**.

No fluff, no generic advice, no education without a price level attached. If the AI speaks, it must speak in terms of:
- **Entry**: price, stop, target, R:R
- **Exit**: hold, tighten stop, take profit, or close
- **Wait**: what level to watch, what triggers the trade

## Current State

| Service | Status | Actionable? | Gap |
|---------|--------|-------------|-----|
| AI Coach | Live | Partially — gives entries but format varies | Needs structured output enforcement |
| AI CoPilot | Live | Yes — structured entry/stop/target | Needs playbook sync with alert engine |
| AI Narrator | Disabled | No — education only | Needs re-enabling with entry-level context |
| Exit Coach | Live | Yes — rule-based stop/target mgmt | Needs AI upgrade for nuanced exits |
| Morning Brief | Basic | Partially | Needs specific levels per watchlist symbol |
| Weekly Review | Not built | N/A | Needs building |
| Pre-Trade Check | Not built | N/A | Needs building |

## Service Redesign

### S1: AI Coach — Structured Actionable Responses

**Current**: Free-form chat that sometimes gives levels, sometimes gives generic advice.

**Proposed**: Every Coach response MUST include a structured action block:

```
CHART READ: SPY broke above 50MA at 673, testing 100MA at 676.

ACTION:
  Direction: LONG
  Entry: 674.50 — pullback to VWAP support
  Stop: 672.80 (below 50MA)
  T1: 677.08 (PDH)
  T2: 681.00 (weekly resistance)
  R:R: 1:1.5
  Conviction: MEDIUM

  OR

  Direction: WAIT
  Watch: 676.39 (100MA) — need close above for breakout confirmation
  Invalidation: close below 673.54 (50MA)
```

**Changes needed**:
- Update system prompt to enforce ACTION block in every response
- Parse structured output on frontend — render as actionable card
- Coach must reference the SAME key levels the alert engine uses (PDH, PDL, MAs, VWAP)
- When user has open positions, Coach defaults to EXIT management:
  ```
  ACTION:
    Direction: HOLD
    Current P&L: +$1.50 (+0.2%)
    Move stop to: 676.00 (breakeven)
    Next target: 681.00 (weekly R)
    Exit if: close below 674.50
  ```

**Technical**:
- Add `action_block` parsing to frontend `ChatWindow.tsx`
- Update `format_system_prompt()` in `trade_coach.py` to require ACTION block
- Enable prompt caching (Anthropic cache_control) — context rarely changes mid-session
- Increase max_tokens from 768 to 1024 to accommodate structured output

### S2: AI CoPilot — Playbook Sync with Alert Engine

**Current**: CoPilot has its own 9-setup playbook defined in `chart_analyzer.py`. The alert engine has 78 rules in `intraday_rules.py`. They're independent.

**Proposed**: CoPilot's playbook MUST match the alert engine's key level rules:

| CoPilot Setup | Alert Engine Rule | Sync Status |
|--------------|-------------------|-------------|
| MA Bounce | ma_bounce_20/50/100/200 | Matched |
| PDL Reclaim | prior_day_low_reclaim | Matched |
| PDH Breakout | prior_day_high_breakout | Matched |
| Double Bottom | session_low_double_bottom | Matched |
| Inside Day Breakout | inside_day_breakout | Matched |
| EMA Reclaim | ema_reclaim_20/50/100/200 | Matched |
| Gap and Go | gap_and_go | Matched |
| Session Low Reversal | session_low_reversal | Matched |
| Consolidation Breakout | consol_breakout_long | Matched |
| **VWAP Reclaim** | **vwap_reclaim** | **MISSING from CoPilot** |
| **VWAP Bounce** | **vwap_bounce** | **MISSING from CoPilot** |
| **Fib Bounce** | **fib_retracement_bounce** | **MISSING from CoPilot** |
| **Weekly Support** | **weekly_level_touch** | **MISSING from CoPilot** |

**Changes needed**:
- Add VWAP reclaim, VWAP bounce, fib bounce, weekly support to CoPilot's playbook prompt
- CoPilot should output the SAME alert_type name the engine uses — so users see consistency
- When CoPilot identifies a setup, it should note if the alert engine also fired for it:
  ```
  SETUP: VWAP Reclaim (vwap_reclaim)
  ALERT ENGINE: Alert fired at 10:45 AM — score 85
  ```

### S3: AI Narrator — Re-enable with Actionable Thesis

**Current**: Disabled. When enabled, generates 3-5 sentences of education per alert.

**Proposed**: Re-enable with actionable focus. Every narrative must include:

```
THESIS: 20MA bounce at $177.50 after pullback from $182. Volume 1.8x
confirms buyers. SPY bullish regime supports longs.

KEY LEVELS:
  Entry: $177.50 (20MA)
  Invalidation: close below $174.50 (50MA)
  First target: $182.00 (prior swing high)

WHAT TO WATCH: If $177 fails to hold on retest, the 50MA at $174.50
is the next support. Volume must stay above average for the bounce
to have legs.
```

**Changes needed**:
- Set `CLAUDE_NARRATIVE_ENABLED = True` in alert_config
- Update prompt in `narrator.py` to include KEY LEVELS section
- Add invalidation level (the "what kills this trade" price)
- Include in Telegram message — currently narrative exists but isn't sent
- Fix confluence_score attribute bug (`_confluence_score` vs `confluence_score` in notifier.py)

### S4: Morning Brief — Daily Game Plan with Specific Levels

**Current**: Basic pre-market brief with general context.

**Proposed**: Structured game plan per watchlist symbol:

```
MORNING BRIEF — Thursday April 10, 2026

SPY ($679.87)
  Bias: Bullish — closed above 50MA (673) and 100MA (676)
  BUY: pullback to 676 (100MA support) → target 681 (weekly R)
  SHORT: rejection at 681 → target 677
  Key: must hold 673 (50MA) or bulls lose control

AAPL ($260.45)
  Bias: Neutral — inside day between 258-262
  BUY: breakout above 262 with volume → target 268
  SHORT: breakdown below 258 → target 254 (200MA)
  Key: wait for direction — inside day compression

ETH ($2,195)
  Bias: Bullish — reclaimed PDL at 2181, VWAP at 2190
  BUY: hold above 2190 (VWAP) → target 2238 (prior high)
  Key: 2181 (PDL) is the line — below = bearish
```

**Changes needed**:
- Enhance `analytics/premarket_brief.py` or create new `analytics/game_plan.py`
- For each watchlist symbol: fetch prior_day data, compute key levels, determine bias
- AI generates the game plan using key levels + prior day data
- Send via Telegram at 9:00 AM ET (before market open)
- Also display in web dashboard as "Today's Game Plan"

### S4-S7: DEFERRED — Not useful until entries/exits are perfected

Morning Brief, Position Advisor, Weekly Review, Pre-Trade Checklist are all deferred. The core problem users need solved is: **buy at the right time, sell at the right time**. Until S1-S3 reliably produce correct entries/exits at key levels, everything else is noise.

These can be revisited once:
1. Alert engine entries are proven accurate (spec 23 Phase 7+ live data)
2. AI Coach/CoPilot/Narrator consistently agree on key levels
3. Win rate data validates the system's edge

---

## DEFERRED SERVICES (for reference only)

### S5: Position Advisor — Real-Time Exit Management (DEFERRED)

**Current**: Rule-based exit_coach sends basic signals (T1 hit → tighten stop).

**Proposed**: AI-powered position management that considers context:

```
POSITION CHECK — NVDA LONG from $177.00

Current: $180.50 (+$3.50, +2.0%)
T1: $182.00 (0.8% away)
Stop: $176.00 (original) → SUGGEST: move to $178.50 (breakeven + buffer)

ANALYSIS: Price approaching hourly resistance at $181.20. Volume
declining on the push higher — momentum fading. SPY also at resistance.

ACTION:
  Hold for T1 ($182) — 0.8% away, worth the wait
  New stop: $178.50 (locks in +$1.50 profit)
  If rejected at $181.20: take 50% off, trail rest with $179 stop
```

**Changes needed**:
- Upgrade `alerting/exit_coach.py` to use AI for nuanced analysis
- Trigger: every 15 min for open positions (or on-demand from dashboard)
- Context: current price vs entry/stop/target, volume trend, nearby S/R, SPY regime
- Output: specific stop adjustment + hold/trim/exit recommendation
- Send to Telegram only on material changes (stop adjustment, exit recommendation)

### S6: Weekly Performance Review — Actionable Coaching

**Proposed**: Every Friday/Sunday, AI reviews the week:

```
WEEKLY REVIEW — April 7-11, 2026

RESULTS: 8 trades, 6 won, 2 lost (75% WR)
  P&L: +$890 on $10k sizing
  Best: AAPL 200MA bounce +$420 (1.7%)
  Worst: SPY double top short -$180 (stopped)

WHAT WORKED:
  Bounce trades at MA levels: 5/5 (100%) — your edge
  Entries near VWAP after reclaim: 2/2 (100%)

WHAT DIDN'T:
  SPY shorts: 0/1 — rejected at $677 but broke to $681
  Lesson: don't short at resistance when price structure is bullish

NEXT WEEK:
  Focus: MA bounce + VWAP reclaim setups (proven edge)
  Avoid: counter-trend shorts in bullish regime
  Watch: SPY 681 weekly resistance — breakout or rejection sets the tone
  Size: maintain current sizing, WR supports it
```

**Changes needed**:
- New scheduled job: Friday 5 PM ET or Sunday 6 PM ET
- Query: all alerts with user_action + outcomes for the week
- Group by: alert_type, direction, symbol, time_of_day
- AI generates review with specific forward-looking levels
- Send via Telegram + display in dashboard

### S7: Pre-Trade Checklist — Confidence Score Before Entry

**Proposed**: When user clicks "Took It" on an alert, run a quick AI check:

```
PRE-TRADE CHECK — NVDA MA Bounce 20 at $177.50

  Structure: 20MA support confirmed (bounced 2x today)
  Volume: 1.8x average — buyers stepping in
  Regime: SPY bullish, above VWAP
  Timing: 10:45 AM — prime session, good follow-through
  Sector: Semis +0.5% vs SPY — sector aligned
  R:R: 1:2.1 ($177.50 → $182 target, $174.50 stop)

CONVICTION: 8/10 — Strong setup, good timing, sector aligned.
Full size appropriate.
```

**Changes needed**:
- New endpoint: `POST /api/v1/intel/pre-trade-check`
- Input: alert_id (or symbol + entry + stop + target)
- AI runs checklist against current market context
- Return conviction score 1-10 with reasoning
- Frontend: show as modal before confirming "Took It"

## Technical Architecture

```
                    ┌─────────────────────┐
                    │  Context Assembly    │
                    │  (shared across all  │
                    │   AI services)       │
                    │                      │
                    │  - OHLCV bars        │
                    │  - Key levels (PDH,  │
                    │    PDL, MAs, VWAP)   │
                    │  - Open positions    │
                    │  - Win rates         │
                    │  - SPY regime        │
                    └──────────┬──────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
    ┌─────▼─────┐       ┌─────▼─────┐       ┌─────▼─────┐
    │ AI Coach  │       │ AI CoPilot│       │ AI Narrator│
    │ (chat)    │       │ (analysis)│       │ (per-alert)│
    └─────┬─────┘       └─────┬─────┘       └─────┬─────┘
          │                    │                    │
          │              ┌─────▼─────┐              │
          │              │ Morning   │              │
          │              │ Brief     │              │
          │              └─────┬─────┘              │
          │                    │                    │
    ┌─────▼─────┐       ┌─────▼─────┐       ┌─────▼─────┐
    │ Position  │       │ Pre-Trade │       │ Weekly    │
    │ Advisor   │       │ Checklist │       │ Review    │
    └─────┬─────┘       └─────┬─────┘       └─────┬─────┘
          │                    │                    │
          └────────────────────┼────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Delivery           │
                    │  - Telegram         │
                    │  - Web dashboard    │
                    │  - Email (weekly)   │
                    └─────────────────────┘
```

**Shared context module**: All AI services pull from the same context assembly — key levels, OHLCV, positions, regime. This ensures consistency: the Coach, CoPilot, Narrator, and Morning Brief all reference the SAME support/resistance levels.

## Prompt Caching Strategy

All services should use Anthropic prompt caching to reduce cost:

| Component | Cache Strategy | Savings |
|-----------|---------------|---------|
| System prompt + playbook | Cache per session (rarely changes) | ~90% of input tokens |
| Key levels + regime | Cache per 5-min cycle | ~60% of context |
| User history + win rates | Cache per session | ~80% of context |
| OHLCV bars | Don't cache (changes every bar) | 0% |

**Implementation**: Use `cache_control: {"type": "ephemeral"}` on the system message block. This is native to the Anthropic API — just needs adding to the API call.

## Priority & Phasing

**Focus: buy at the right time, sell at the right time. Nothing else matters yet.**

**Phase 1 — Now**:
- S3: Re-enable Narrator with actionable thesis (config + prompt update)
- S1: Coach structured ACTION block (prompt update + frontend card)
- Fix confluence_score bug in notifier.py

**Phase 2 — This week**:
- S2: CoPilot playbook sync (add VWAP/fib/weekly setups to match alert engine)
- Prompt caching implementation (cost reduction)

**Phase 3 — After entries are proven**:
- S4-S7: Morning Brief, Position Advisor, Weekly Review, Pre-Trade Check

## Success Metrics

| Metric | Target |
|--------|--------|
| Every AI response includes price levels | 100% |
| Coach responses with ACTION block | 100% |
| Narrator enabled for all BUY/SHORT alerts | 100% |
| Morning Brief sent before 9:15 AM | Daily |
| User engagement with AI features | Track click-through on Coach/CoPilot |
| Trade decisions aligned with AI recommendation | Track Took vs AI direction |

## Cost Model

| Service | Model | Frequency | Est. Cost/Day |
|---------|-------|-----------|---------------|
| Narrator (per alert) | Haiku | ~30 alerts | $0.03 |
| Coach (per query) | Haiku/Sonnet | ~20 queries | $0.10 |
| CoPilot (per analysis) | Haiku/Sonnet | ~10 analyses | $0.05 |
| Morning Brief | Sonnet | 1/day | $0.02 |
| Position Advisor | Haiku | ~10 checks/day | $0.02 |
| Weekly Review | Sonnet | 1/week | $0.02 |
| **Total** | | | **~$0.25/day per active user** |

At $29/mo subscription, AI costs are <1% of revenue.
