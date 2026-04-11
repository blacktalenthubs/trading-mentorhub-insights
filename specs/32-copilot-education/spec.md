# Feature Specification: AI CoPilot — Trading Education Platform

**Status**: Draft
**Created**: 2026-04-11
**Author**: Claude (via /speckit.specify)
**Priority**: High — education builds user confidence → retention → revenue

## The Shift

**Old CoPilot**: "Analyze this chart → get a trade plan" (duplicate of Coach)
**New CoPilot**: "Learn WHY this is a trade → build confidence to act on your own"

The Coach tells you WHAT to do. The CoPilot teaches you WHY.

## Problem

Beginners see an AI scan alert: "LONG ETH $2230 — PDL bounce." They ask:
- What's a PDL bounce?
- Why is this level important?
- How do I know the bounce is real?
- Where exactly do I put my stop and why?
- What does the volume tell me?
- How does this look on the daily chart?

The Coach gives an answer. The CoPilot should **teach the pattern** so next time they recognize it themselves.

## Core Value Proposition

> "Don't just follow signals. Understand them."

Every CoPilot analysis teaches the user:
1. **What pattern is this?** — Name it, explain it simply
2. **Why does it work?** — The logic behind support/resistance
3. **How to confirm it** — Volume, bar structure, timeframe alignment
4. **Where the trade fails** — What invalidates the setup
5. **Practice recognizing it** — "Here are 3 recent examples of this pattern"

## Page Redesign

### Current Layout
```
┌──────────────────────────────────────────┐
│ [Symbol picker] [Timeframe] [Analyze]    │
│ ┌─────────────────┐ ┌──────────────────┐ │
│ │  Chart           │ │ Trade Plan       │ │
│ │  (candlestick)  │ │ LONG/SHORT/WAIT  │ │
│ │                 │ │ Entry/Stop/T1/T2 │ │
│ │                 │ │ R:R, Confluence   │ │
│ └─────────────────┘ └──────────────────┘ │
│ Analysis History                         │
└──────────────────────────────────────────┘
```

### New Layout — Education-First
```
┌──────────────────────────────────────────────────┐
│ [Symbol picker] [Timeframe] [Analyze]             │
│                                                   │
│ ┌─────────────────────────────────────┐           │
│ │           Chart with Annotations    │           │
│ │  ← "PDL support here"              │           │
│ │  ← "Volume spike = buyers"         │           │
│ │  ← "Entry at this level"           │           │
│ └─────────────────────────────────────┘           │
│                                                   │
│ ┌─────────────┐ ┌───────────────────────────────┐ │
│ │ Trade Plan  │ │ LEARN: PDL Bounce             │ │
│ │ LONG $2230  │ │                               │ │
│ │ Stop $2220  │ │ What: Price tests yesterday's │ │
│ │ T1 $2246    │ │ low and holds above it.       │ │
│ │             │ │                               │ │
│ │ Conviction: │ │ Why it works: Institutional   │ │
│ │ HIGH        │ │ buyers defend PDL because...  │ │
│ │             │ │                               │ │
│ │ [Took It]   │ │ Confirmation: Look for...     │ │
│ │ [Skip]      │ │ - Volume increase at level    │ │
│ │             │ │ - 2-3 bars closing above      │ │
│ │             │ │ - RSI turning up from low     │ │
│ │             │ │                               │ │
│ │             │ │ When it fails: If price       │ │
│ │             │ │ closes below PDL → exit.      │ │
│ │             │ │                               │ │
│ │             │ │ [See 3 recent examples →]     │ │
│ └─────────────┘ └───────────────────────────────┘ │
│                                                   │
│ ┌───────────────────────────────────────────────┐ │
│ │ YOUR PATTERN STATS                            │ │
│ │ PDL Bounce: 8 times seen, 6 won (75% WR)     │ │
│ │ You took 4, skipped 4. Took WR: 100%          │ │
│ │ Avg gain: +0.4% | Avg hold: 45 min            │ │
│ └───────────────────────────────────────────────┘ │
│                                                   │
│ Pattern Library: [PDL Bounce] [VWAP Hold]         │
│ [MA Bounce] [Session Low] [PDH Breakout] [more]   │
└──────────────────────────────────────────────────┘
```

## Educational Content per Pattern

### Pattern: PDL Bounce

```
📚 LEARN: Prior Day Low (PDL) Bounce

WHAT IS IT?
Yesterday's lowest price ($2230.01) acts as a support level today.
When price pulls back to this level and holds above it, buyers 
are defending it — creating a buying opportunity.

WHY DOES IT WORK?
• Institutional traders place large orders at yesterday's key levels
• Algorithms are programmed to buy at PDL
• Many traders have stop losses just below PDL
• When price holds above PDL, it confirms demand is stronger than supply

HOW TO CONFIRM THE BOUNCE:
✓ Price touches or wicks below PDL then closes above → strong signal
✓ Volume increases at the level → buyers stepping in
✓ 2-3 consecutive bars close above PDL → hold confirmed
✓ RSI turning up from oversold zone → momentum shifting
✗ Price closes below PDL on strong volume → setup failed, exit

WHERE TO ENTER:
• Entry: at or near PDL level ($2230)
• Stop: below session low or PDL ($2220)
• Target 1: VWAP ($2245) — first overhead resistance
• Target 2: PDH ($2253) — yesterday's high

RISK MANAGEMENT:
• Risk: $10 (entry to stop)
• Reward: $15 (entry to T1)  
• R:R = 1:1.5 — acceptable for high-probability setup
• Position size: risk 1% of account per trade

YOUR TRACK RECORD WITH THIS PATTERN:
• Seen: 8 times in last 30 days
• Won: 6 (75% win rate)
• You took: 4 trades, all won (100%)
• Average gain: +0.4% per trade
• This is your STRONGEST pattern — keep taking it
```

### Pattern: VWAP Hold

```
📚 LEARN: VWAP Hold (Pullback to VWAP Support)

WHAT IS IT?
VWAP (Volume Weighted Average Price) is the average price weighted 
by volume — where the most trading happened today. When price is 
above VWAP and pulls back to it, the pullback often finds support.

WHY DOES IT WORK?
• VWAP is where institutional traders benchmark their executions
• When price is above VWAP, the average buyer is profitable
• A pullback to VWAP is a "buy the dip" for the existing trend
• Below VWAP = average buyer is losing → trend weakens

HOW TO CONFIRM:
✓ Price was above VWAP earlier (established uptrend)
✓ Price pulls back to touch VWAP
✓ Last 2-3 bars close above VWAP (hold confirmed)
✓ Volume on pullback is LOWER than volume on rally (healthy)
✗ Price breaks below VWAP on high volume → thesis broken
...
```

## Pattern Library (Full List)

| Pattern | Category | Difficulty | Description |
|---------|----------|-----------|-------------|
| PDL Bounce | Support | Beginner | Price holds yesterday's low |
| PDL Reclaim | Support | Beginner | Price dips below PDL, recovers |
| VWAP Hold | Support | Beginner | Pullback to VWAP, holds |
| VWAP Reclaim | Reversal | Intermediate | Crosses above VWAP from below |
| Session Low Bounce | Support | Beginner | Today's low holds on retest |
| Double Bottom | Support | Beginner | Two tests of same low |
| MA Bounce (50/100/200) | Support | Intermediate | Price bounces off moving average |
| PDH Breakout | Breakout | Intermediate | Price breaks above yesterday's high |
| PDH Rejection | Resistance | Beginner | Price fails at yesterday's high |
| Session High Double Top | Resistance | Intermediate | Two tests of session high, fails |
| VWAP Loss | Reversal | Beginner | Price drops below VWAP |
| Inside Day Breakout | Breakout | Advanced | Compression → expansion |
| Fib Retracement | Support | Advanced | Bounce at 50% or 61.8% fib level |
| Gap and Go | Momentum | Advanced | Gap up + holds above VWAP |

## AI Prompt for Education

```
You are a trading educator. A {level} trader is looking at {symbol}.
The AI scan identified a {setup_type} setup.

Explain this pattern in 4 sections:

WHAT IS IT: 2 sentences — name the pattern and describe what happened 
on the chart in plain language.

WHY IT WORKS: 3 bullet points — the market logic behind why this 
level matters (institutional orders, algorithms, supply/demand).

HOW TO CONFIRM: 4 checkmarks — what the trader should verify before 
entering (volume, bar closes, RSI, timeframe alignment).
1 X-mark — what would invalidate the setup.

RISK MANAGEMENT: Entry, stop (structural), T1, T2, R:R ratio.

Use the actual prices from the data. Speak to a {level} trader —
beginner = simple language, intermediate = can handle MA/RSI concepts,
advanced = discuss confluence and multi-timeframe.

MAXIMUM 150 WORDS. Plain text, no markdown.
```

## User Experience Flows

### Flow 1: Beginner Sees AI Scan Alert
```
1. AI Scan sends: "LONG ETH $2230 — PDL Bounce"
2. User thinks: "What's a PDL bounce?"
3. Opens CoPilot page → selects ETH → clicks Analyze
4. Sees: Trade Plan (left) + Education Panel (right)
5. Reads: "PDL Bounce — price tests yesterday's low and holds..."
6. Understands WHY this is a trade
7. Goes back to Telegram → clicks "Took It" with confidence
```

### Flow 2: User Wants to Learn a Pattern
```
1. Opens CoPilot page → Pattern Library section
2. Clicks "VWAP Hold"
3. Sees: explanation + 3 recent examples with charts
4. Understands the pattern conceptually
5. Next time AI Scan fires "VWAP HOLD" → recognizes it immediately
```

### Flow 3: User Reviews Their Pattern Performance
```
1. Opens CoPilot page → "Your Pattern Stats"
2. Sees: PDL Bounce 75% WR, VWAP Hold 60% WR
3. Realizes: "My edge is PDL bounces — focus there"
4. Confidence increases on PDL bounce alerts
```

## Technical Implementation

### Backend
- New prompt in `chart_analyzer.py` — education-focused (WHAT/WHY/CONFIRM/RISK)
- New endpoint: `GET /api/v1/intel/pattern-education/{pattern_type}` — returns static + dynamic content
- Reuse existing win rate data from `intel_hub.py` for per-pattern stats
- Reuse existing replay system for "recent examples"

### Frontend (AICoPilotPage.tsx)
- Split right panel: Trade Plan (top) + Education (bottom)
- Pattern Library grid at bottom of page
- "Your Pattern Stats" section with personal win rates
- Link from AI Scan alerts to CoPilot education for that pattern

### Content
- 14 pattern explanations (static content, AI-enhanced with real prices)
- Each pattern: WHAT/WHY/CONFIRM/RISK sections
- Difficulty tags: Beginner / Intermediate / Advanced
- "See examples" links to replay for that pattern type

## What CoPilot IS NOT (Anymore)

- NOT another "analyze this chart" tool (Coach does that)
- NOT another signal generator (AI Scan does that)
- NOT a generic AI chat (Coach does that)

CoPilot = **EDUCATION**. Understand patterns, build confidence, trade better.

## Success Metrics

- [ ] Every AI scan alert type has a CoPilot education page
- [ ] Users can navigate from AI scan alert → CoPilot pattern education
- [ ] Per-pattern win rates shown (personal + platform)
- [ ] Pattern Library with all 14 patterns documented
- [ ] Beginner users report understanding setups after CoPilot use
- [ ] Time on CoPilot page > 2 min average (reading, not bouncing)

## Scope

### Phase 1 (MVP)
- Rename/rebrand CoPilot page header to "Learn Trading Patterns"
- Add education panel next to trade plan (WHAT/WHY/CONFIRM/RISK)
- Pattern Library grid at bottom
- Link from AI Scan tab → CoPilot for that pattern

### Phase 2
- Per-pattern personal stats (win rate, taken/skipped)
- Recent examples with replay links
- Difficulty progression (beginner → intermediate → advanced)

### Phase 3
- Interactive quizzes ("Is this a PDL bounce? Yes/No")
- Pattern recognition practice (show chart, identify setup)
- Weekly education digest (Telegram: "This week you learned 3 patterns")

### Out of Scope
- Video content / tutorials
- Certification / badges
- Community / forums
- Paper trading integration with education
