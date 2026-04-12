# Platform Rebrand — AI Trading Education & Intelligence Platform

**Status**: Ready for Implementation
**Updated**: 2026-04-11
**Priority**: High — landing page must reflect actual product value for SEO and paid ads

## The Shift

The platform evolved from rule-based alerts (78 rules) to an **AI-first trading education platform**. The AI scan now outperforms the rule engine — it catches setups rules miss, knows your active positions, and tells you when NOT to trade. The landing page must reflect this reality.

**Old positioning**: "Your chart analyst that never sleeps" — passive, tool-focused
**New positioning**: "AI-powered trading strategies — learn, scan, trade, review" — active, education-focused

## Platform Identity: 5 AI Pillars

The platform delivers value through 5 distinct AI capabilities. Each is a marketing pillar, SEO target, and feature showcase.

```
                    AI TRADING INTELLIGENCE PLATFORM

  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │ AI COACH │  │AI COPILOT│  │ AI SCAN  │  │  TRADE   │  │ PATTERN  │
  │          │  │          │  │          │  │  REVIEW  │  │ LIBRARY  │
  │ Live     │  │ Deep     │  │ Auto     │  │          │  │          │
  │ trading  │  │ chart    │  │ entry/   │  │ Replay   │  │ 14       │
  │ guidance │  │ analysis │  │ exit     │  │ validate │  │ setups   │
  │ any      │  │ multi-TF │  │ every    │  │ every    │  │ taught   │
  │ question │  │ trade    │  │ 5 min    │  │ trade    │  │ with     │
  │ any time │  │ plans    │  │ watchlist│  │ visually │  │ examples │
  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘
```

### Pillar 1: AI Coach — Live Trading Guidance
**SEO targets**: "AI trading coach", "AI trade analysis", "should I buy ETH"
**What it does**: Real-time conversational AI that reads any chart and gives structured trade guidance. Entry, stop, target — every time. Knows your open positions, win rates, and market regime.

Live capabilities:
- Reads 5-min + hourly OHLCV bars in real time
- Computes VWAP from session bars (no hallucination)
- Sees your active positions (won't tell you to buy what you already hold)
- Provides structured output: CHART READ + ACTION (direction, entry, stop, T1, T2)
- Aware of historical win rates per pattern per symbol
- Available via web chat AND Telegram commands (/spy, /eth, /btc, etc.)

**Key differentiator**: Not generic ChatGPT market commentary. Sees YOUR chart, YOUR positions, YOUR win rates. Gives a specific trade plan, not opinions.

### Pillar 2: AI CoPilot — Deep Chart Analysis & Education
**SEO targets**: "AI chart analysis", "AI trade plan", "multi-timeframe analysis"
**What it does**: Structured multi-timeframe chart analysis with full trade plans. Confluence scoring (0-10), playbook pattern matching, and educational explanations.

Live capabilities:
- Multi-timeframe analysis (5m → 1H → Daily → Weekly)
- Confluence score (0-10) based on volume, MAs, RSI, trend alignment
- Matches against 14 playbook patterns (PDL bounce, VWAP hold, MA bounce, etc.)
- Trade plan output: SETUP, DIRECTION, ENTRY, STOP, T1, T2, CONFIDENCE, KEY_LEVELS
- Pattern education: WHAT IS IT, WHY IT WORKS, HOW TO CONFIRM, RISK MANAGEMENT
- Analysis history — review past AI analyses and their outcomes

**Key differentiator**: Not just "buy/sell" — teaches you WHY the setup works. Over time you internalize the patterns and develop your own edge.

### Pillar 3: AI Scan — Automated Entry/Exit Detection
**SEO targets**: "AI trading signals", "automated trade alerts", "AI entry detection"
**What it does**: Scans your entire watchlist every 5 minutes using Claude AI. Identifies entries at key levels, warns at resistance, and tells you when to WAIT.

Live capabilities:
- Scans every 5 minutes during market hours (24/7 for crypto)
- Detects: PDL bounce, VWAP hold/reclaim, MA bounce, double bottom, PDH breakout, session low hold
- Resistance warnings: "approaching PDH, tighten stop or take profits"
- WAIT signals: "no setup confirmed, stay out" (unique — no other platform does this)
- Position awareness: knows your active trades, won't send duplicate LONGs
- Direction-change notifications: only alerts when the signal changes (LONG → WAIT → RESISTANCE)
- Telegram delivery with inline Took/Skip/Exit buttons
- Coinbase data for crypto (reliable daily candles, not dropped bars)

**Key differentiator**: AI says WAIT when there's no trade. That's the edge — less noise, better entries. You get 3-5 quality setups per day, not 100 alerts to sort through.

### Pillar 4: Trade Review — Validate Every Trade
**SEO targets**: "trade replay", "trade journal AI", "trading performance review"
**What it does**: Dedicated page for replaying any alert candle-by-candle. Cinematic animation showing setup → entry → price action → outcome.

Live capabilities:
- Full-screen animated replay of any alert (entry, stop, target lines on chart)
- Cinematic phases: SETUP → APPROACH → ENTRY → MOVE → TARGET → RESULT
- Filter by source (AI Scan vs Rules), action (Took/Skipped), date
- Date navigation across last 30 days of trading sessions
- Shareable replay links (/replay/:alertId — public, no login required)
- Speed controls (1x, 2x, 5x)
- Auto-generated after market close (4:40 PM ET)

**Key differentiator**: Visual proof. Every trade becomes content you can share. Show your edge — or learn from losses. No other platform auto-generates cinematic replays.

### Pillar 5: Pattern Library — Trading Education
**SEO targets**: "trading patterns", "how to trade PDL bounce", "VWAP trading strategy"
**What it does**: 14 trading patterns taught with difficulty ratings, interactive deep-dives, and live performance data.

Live capabilities:
- 14 patterns: PDL Bounce, PDL Reclaim, VWAP Hold, VWAP Reclaim, Double Bottom, MA Bounce, PDH Breakout, PDH Rejection, Double Top, VWAP Loss, Inside Day, Fib Bounce, Gap & Go, EMA Rejection
- Difficulty levels: Beginner, Intermediate, Advanced
- Click any pattern → deep-dive education: What Is It, How to Identify, Why It Works, When It Fails, Common Mistakes, Pro Tips
- Live win rate data per pattern from production alerts
- Categories: Support, Resistance, Breakout, Reversal, Momentum
- Public access at /learn (SEO-friendly, no login required)

**Key differentiator**: Education tied to real trading data. You don't just learn PDL bounce theory — you see its 81% win rate from your own signals.

## Current Landing Page Audit

### Features Marketed That DON'T EXIST (Must Remove)

| Marketed Feature | Status | Action |
|---|---|---|
| Options Flow Scanner | Not built | REMOVE from features + pricing |
| Sector Rotation Tracker | Not built | REMOVE from features + pricing |
| Catalyst Calendar | Not built | REMOVE from features + pricing |
| Backtesting engine (Premium) | Not built | REMOVE from pricing |
| Paper trading simulator (Premium) | Partially built | REMOVE until complete |

### Features That ARE LIVE But NOT Marketed (Must Add)

| Live Feature | Why It Matters |
|---|---|
| AI Scan (every 5 min, 14 patterns) | Core differentiator — this IS the product |
| AI position awareness | Knows your trades, won't duplicate alerts |
| WAIT signals | Only platform that tells you NOT to trade |
| Pattern Library (14 patterns, education) | SEO goldmine, educational positioning |
| Trade Review page (dedicated replay hub) | Validates every trade visually |
| Telegram commands (/spy /eth /btc) | Instant AI analysis from phone |
| 24/7 crypto with Coinbase data | Unique — most platforms equity-only |
| Direction-change notifications | Smart noise reduction |
| Computed VWAP in Coach | Accurate data, not hallucinated |
| Pre-market brief + Game plan | Daily AI trading preparation |
| EOD Review + Weekly coaching | AI-driven improvement loop |
| Confluence scoring (0-10) | Quantified trade quality |
| Multi-timeframe analysis | Professional-grade context |

### Copy That's WRONG (Must Fix)

| Current Copy | Fix |
|---|---|
| "Scans every 3 min" | Now 5 min |
| "AI Coach (2 queries/day)" for Free | Now 3/day |
| Hero: "Your chart analyst that never sleeps" | Passive — rewrite to active AI positioning |
| "Smart Watchlist Ranking (0-100)" | Oversold — simplify claim |

## New Landing Page Structure

### Section 1: Hero
```
AI-POWERED TRADING STRATEGIES
THAT FIND THE TRADE FOR YOU.

Your AI trading analyst scans the market every 5 minutes,
identifies entries at key levels, and delivers complete trade
plans — entry, stop, target, conviction.

You decide. You learn. You get better.

[Start Free — 3 Day Pro Trial]  [See Live Track Record]
```

Background: Dark, animated chart with AI scan overlay highlighting a support bounce entry.

Stats bar below: [Win Rate: XX%] [Signals Tracked: XXX] [Patterns: 14] [24/7 Crypto]

### Section 2: The 5 AI Pillars (Visual Cards)

Each pillar gets a card with icon, headline, 3-bullet description, and a screenshot/animation.

**Card 1: AI Coach**
```
YOUR AI TRADING ANALYST — ON DEMAND

Ask any question about any chart. Get a structured trade plan
in seconds — not generic commentary.

- "Should I buy ETH here?" → Entry $2245, Stop $2233, T1 $2275
- Knows your open positions — won't tell you to buy what you hold
- Available on web + Telegram (/spy, /eth, /btc commands)
```

**Card 2: AI CoPilot**
```
DEEP CHART ANALYSIS WITH EDUCATION

Multi-timeframe analysis with confluence scoring.
Learn WHY patterns work — not just WHERE to enter.

- Analyzes 5m → 1H → Daily → Weekly for full context
- Confluence score (0-10) quantifies trade quality
- Pattern education: what, why, confirm, risk management
```

**Card 3: AI Scan**
```
AUTOMATED ENTRY/EXIT DETECTION — EVERY 5 MINUTES

AI monitors your watchlist and fires when price hits
a key level. When there's no trade, it says WAIT.

- 14 patterns: PDL bounce, VWAP hold, MA bounce, breakouts
- WAIT signals: AI tells you when NOT to trade (unique)
- Position-aware: won't duplicate entries you've already taken
```

**Card 4: Trade Review**
```
REPLAY & VALIDATE EVERY TRADE

Cinematic animated replay of every alert — entry to outcome.
Share your wins. Learn from your losses.

- Full-screen replay with entry/stop/target lines
- Filter by AI vs Rules, Took vs Skipped, date
- Shareable links — build your public track record
```

**Card 5: Pattern Library**
```
14 TRADING PATTERNS — TAUGHT WITH REAL DATA

Learn support bounces, breakouts, reversals with
difficulty ratings and live win rate data.

- Beginner to Advanced patterns
- Click any pattern → deep education: what, why, how, risk
- Win rates from real production data — not theory
```

### Section 3: How It Works (3 Steps)
```
1. SET YOUR WATCHLIST
   SPY, AAPL, ETH, BTC — up to 25 symbols.
   AI monitors all of them. 24/7 for crypto.

2. AI SCANS EVERY 5 MINUTES
   When price hits a key level, AI identifies the setup
   and sends a complete plan: Entry. Stop. Target. Conviction.
   When there's no trade, it says WAIT. No noise.

3. DECIDE, TRACK, IMPROVE
   Took It → track P&L automatically
   Skip → see if you were right to pass
   Review → replay every trade, learn patterns, build edge
```

### Section 4: AI vs Manual Trading (Comparison)
```
                    MANUAL           AI PLATFORM
Watching charts     Hours/day        AI scans every 5 min
Missing setups      Constantly       Catches setups 24/7
Entry timing        Emotional        At the structural level
Stop placement      Arbitrary %      Below support structure
Alert noise         100/day          3-5 quality setups
Position tracking   Spreadsheet      Auto from Took/Skip
Education           YouTube + trial  AI explains every trade
Track record        "Trust me"       Public, auditable
```

### Section 5: Live Track Record (Real Data)
```
LAST 90 DAYS — LIVE DATA — VERIFIED

[Win Rate]  [Total Signals]  [Wins]  [Losses]

Pulled from /api/v1/intel/public-track-record
```

### Section 6: Daily AI Workflow
```
THE AI TRADING DAY

  09:05 AM  │  AI Game Plan — top 3 focus symbols + edge
  09:15 AM  │  Pre-Market Brief — market outlook + key levels
  09:30 AM  │  AI Scan starts — every 5 min through close
  ALL DAY   │  AI Coach available — ask about any chart
  ALL DAY   │  Telegram alerts — Took / Skip / Exit
  04:30 PM  │  EOD cleanup — close stale entries
  04:35 PM  │  AI EOD Review — what worked, what didn't
  04:40 PM  │  Trade Replay — auto-generated for every trade
  FRIDAY    │  Weekly Edge Report — patterns, performance, coaching

24/7 for crypto — AI never stops monitoring BTC, ETH
```

### Section 7: Pricing (Corrected)

```
FREE                    PRO ($49/mo)              PREMIUM ($99/mo)
─────────               ──────────                ────────────────
5 symbols               10 symbols                25 symbols
AI Coach: 3/day         AI Coach: 50/day          AI Coach: unlimited
AI Scan: 3 alerts       AI Scan: unlimited        AI Scan: unlimited
Telegram: 3 cmds/day    Telegram: 50/day          Telegram: unlimited
Today's alerts          30-day history            Full history
1 replay/day            Unlimited replay          Unlimited replay
Pattern Library         Pattern Library           Pattern Library
                        Pre-market Brief          Pre-market Brief
                        EOD Review                EOD Review
                        Performance Analytics     Performance Analytics
                                                  Weekly Edge Report
```

### Section 8: Social Proof / Trust
```
RADICAL TRANSPARENCY — WE SHOW EVERYTHING

Public track record. Per-pattern win rates. Even the losses.
Most signal services can't survive this level of honesty. We can.

[Win Rate]  [Win/Loss]  [Total Signals]
```

### Section 9: Signal Library Preview
```
LEARN TRADING PATTERNS — FREE

14 setups taught with real data:
PDL Bounce (Beginner) • VWAP Reclaim (Intermediate) •
Inside Day Breakout (Advanced) • and 11 more

[Explore Pattern Library →]
```

### Section 10: FAQ
```
Q: Is this a signal service?
A: No. We provide AI-powered analysis and education. Entry, stop,
   target, reasoning — you decide whether to trade. We teach you
   to find your own setups over time.

Q: How is this different from ChatGPT?
A: Our AI is trained on a specific trading playbook (14 patterns),
   sees real-time OHLCV bars, computes VWAP from live data, knows
   your open positions, and gives structured trade plans.

Q: What markets do you cover?
A: US equities (SPY, AAPL, TSLA, NVDA, etc.) + crypto (ETH, BTC)
   with 24/7 coverage for crypto using Coinbase data.

Q: Does the AI guarantee profits?
A: No. Trading has risk. Our track record is public — see exactly
   what works and what doesn't. We help you find better entries
   and learn from every trade.

Q: What is a WAIT signal?
A: When AI scans your watchlist and finds no valid setup, it says
   WAIT. This is a feature — saving you from bad entries in choppy
   markets. Less noise = better signal quality.

Q: Can I try before paying?
A: Yes. Free tier forever (5 symbols, 3 AI queries/day). New accounts
   get 3 days of full Pro access.
```

### Section 11: Final CTA
```
STOP STARING AT CHARTS.
LET AI FIND YOUR ENTRIES.

Join traders who get AI-powered trade plans delivered to their
phone — with the coaching to get better every trade.

[Start Free — 3 Day Pro Trial]
```

## SEO Strategy

### Primary Keywords (Landing Page)
- "AI trading platform"
- "AI trading signals"
- "AI day trading alerts"
- "AI trading coach"
- "automated trading alerts"

### Long-tail Keywords (Pattern Library / Learn Pages)
- "how to trade PDL bounce"
- "VWAP reclaim trading strategy"
- "double bottom day trading"
- "MA bounce entry rules"
- "PDH breakout strategy"
- "inside day breakout trading"

### Content Strategy
- Each of the 14 patterns = a dedicated SEO-optimized page at /learn/patterns/:id
- Each learning category = SEO page at /learn/:categoryId
- Blog potential: "AI caught this ETH setup that rules missed" (with replay embed)

## Technical Requirements

### Live Data Widgets (Landing Page)
- Track record: `/api/v1/intel/public-track-record` (already built)
- Market status: `/api/v1/market/status` (already built)

### Public Pages (No Auth)
- Landing page: / (already public)
- Pattern Library: /learn (already public)
- Trade Replay: /replay/:alertId (already public)
- Track Record: needs new public page or landing page widget

### Performance
- Page load < 2 seconds
- Mobile-first responsive
- Dark theme (matches product)

## What to BUILD for the Landing Page

| Item | Effort | Priority |
|---|---|---|
| Rewrite hero + all copy per this spec | Medium | P0 |
| Remove 5 unbuilt features from page | Low | P0 |
| Add 5 AI pillar cards | Medium | P0 |
| Fix pricing table (remove unbuilt, add AI Scan) | Low | P0 |
| Add "Daily AI Workflow" timeline section | Low | P1 |
| Add "AI vs Manual" comparison table | Low | P1 |
| Embed auto-playing trade replay | Medium | P1 |
| Add Pattern Library preview section | Low | P1 |
| Update meta tags for SEO | Low | P1 |

## What NOT to Build

- No new features — just market what's already live
- No Options Flow, Sector Rotation, Catalyst Calendar
- No new logo/brand identity
- No blog system (Phase 2)
- No A/B testing framework (Phase 2)

## Success Metrics

- [ ] Zero unbuilt features marketed on landing page
- [ ] All 5 AI pillars prominently featured
- [ ] Live track record widget visible above the fold
- [ ] Pricing table matches actual tier limits
- [ ] Pattern Library linked from landing page
- [ ] Page loads in < 2 seconds
- [ ] Mobile responsive (test on iPhone)
- [ ] Meta description includes "AI trading" keywords
