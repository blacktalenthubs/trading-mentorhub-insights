# Feature Specification: Marketing & Educational Value

**Status**: Planning
**Created**: 2026-04-04

---

## Part 1: Marketing & Go-To-Market

### Landing Page Optimization

**Current state:** Landing page is live with hero, pricing, features, live track record (659 signals, 77% WR). But it's missing key conversion elements.

**Improvements needed:**

| # | Item | Impact |
|---|------|--------|
| M1 | **Social proof section** — testimonials, user count, "X traders joined this week" | High |
| M2 | **Live ticker** — real-time price feed across top of page (TradingView widget) | Medium |
| M3 | **Video demo** — 60-second explainer showing alert → Telegram → Took → Exit flow | High |
| M4 | **FAQ section** — "Is this financial advice?", "How fast are alerts?", "Can I cancel?" | Medium |
| M5 | **Comparison table** — TradeCoPilot vs TradingView vs Trade Ideas vs Discord groups | High |
| M6 | **Free trial CTA improvement** — show what free tier includes, reduce friction | Medium |
| M7 | **Mobile screenshots** — show Telegram alert flow on a phone mockup | High |

### SEO Strategy

**Signal Library as inbound funnel:**
- 8 category pages already indexed (entry, breakout, short, exit, etc.)
- Expand to 30+ per-alert-type pages ("What is a prior day low reclaim?")
- Target long-tail keywords: "stock alert app for day traders", "support bounce trading strategy"
- Each page ends with CTA → register

**Content calendar:**
- Daily: pre-market brief on Twitter/X (free, drives awareness)
- Weekly: "Alert of the Week" deep-dive with chart + outcome
- Monthly: performance scorecard (transparency builds trust)

### Launch Channels

| Channel | Strategy | Cost |
|---------|----------|------|
| Twitter/X | Daily pre-market briefs, alert screenshots, win rate transparency | Free |
| Reddit | r/daytrading, r/stockmarket — value posts, not spam | Free |
| YouTube | "How I caught the SPY double bottom" — real alerts, real charts | Free |
| Discord | Trading community with free tier access | Free |
| Google Ads | "stock alert app", "day trading alerts" | $500/mo |
| Trading forums | Elite Trader, Warrior Trading community posts | Free |

### Referral Program

```
Refer a friend → both get 1 month free Pro
Track via unique referral codes
Show referral count in dashboard
```

---

## Part 2: Educational Value

### Signal Library Expansion

**Current:** 8 category pages with overview, why it works, when it fails, pro tips, live stats.

**Phase 2 — Per-Rule Deep Dives (30+ pages):**

Each alert type gets its own page:
```
/learn/entry-signals/ma-bounce-20

What is a 20 EMA Bounce?
[Chart diagram showing the pattern]

How to identify it:
1. Price is in an uptrend (above 50MA)
2. Price pulls back to the 20EMA
3. A candle closes with lower wick touching the 20EMA
4. Next candle closes above the 20EMA (confirmation)

Real examples from our track record:
[3 actual alerts with charts showing entry → outcome]

Win rate: 87% (36 signals, last 90 days)
Average R:R: 2.1:1
Best time of day: 10:00-11:30 AM

Common mistakes:
- Buying the first touch without confirmation
- Not checking SPY regime (buying bounces in bearish market)
- Setting stop too tight (needs room below the MA)

Pro tips:
- The 20EMA bounce is strongest in the first 2 hours
- Volume should increase on the bounce candle
- If RSI is between 30-45, the bounce has higher probability
```

### Interactive Chart Replay

**What:** Users click a past alert and watch the chart play out in fast-forward:
- Entry marked on chart
- Price moves candle by candle
- T1 hit or stop hit shown
- Final P&L displayed

**Implementation:** Use Lightweight Charts with historical OHLCV, animated candle-by-candle rendering.

### Trading Education Modules

**Module 1: Reading Structure**
- What is support and resistance?
- How moving averages act as dynamic S/R
- Prior day high/low — why they matter
- VWAP — the institutional benchmark

**Module 2: Risk Management**
- Position sizing: account size × risk% = max loss per trade
- Stop placement: below the level that triggered the signal
- R:R ratio: why 1:2 minimum matters
- Daily risk budget: stop trading after X losses

**Module 3: Trade Execution**
- When to take an alert (Took It)
- When to skip (market context, regime, conviction)
- Partial profits at T1 vs holding for T2
- When to exit early (thesis invalidated)

**Module 4: Pattern Recognition**
- How to spot a double bottom
- How to read consolidation breakouts
- Failed breakout = short opportunity
- Inside day → explosive move coming

### Personalized Learning Path

Based on user's trading data:
```
Welcome, Victor!

Based on your first 2 weeks:
✅ You're great at bounce trades (82% WR)
⚠️ You struggle with breakouts (50% WR)
❌ You haven't tried short trades yet

Recommended next steps:
1. Read: "When to Skip a Breakout" (5 min read)
2. Watch your skipped breakout alerts this week
3. Try: Take one short signal next week (start small)
```

### Weekly Coaching Email

Every Sunday evening:
```
Subject: Your TradeCoPilot Weekly Coaching — April 7-11

Hi Victor,

This week you:
• Took 8 trades (6 won, 2 lost) — 75% WR
• Best pattern: PDL reclaim (3/3 wins)
• Total P&L: +$890

One thing to improve:
Your two losses were both breakout trades during CHOPPY regime.
The system flagged these as "CAUTION" — next time, check the 
regime badge before taking breakout alerts.

Next week's focus:
• Markets are approaching monthly options expiration
• Expect increased volatility Thursday/Friday
• Bounce setups may be more reliable than breakouts

Happy trading,
TradeCoPilot AI Coach
```

---

## Implementation Priority

### This Weekend:
1. **AI-1: Smart alert narratives** — enhance prompts (1-2 hours)
2. **AI-5: Morning brief** — enhance existing with per-symbol game plan (1-2 hours)
3. **Marketing: FAQ section** on landing page (30 min)
4. **Marketing: Comparison table** on landing page (30 min)

### Next Week:
5. **Per-rule Signal Library pages** (expand from 8 to 30+)
6. **AI-6: Weekly review email** (Friday delivery)
7. **AI-2: Personalized coaching** (needs data)
8. **Video demo** for landing page

### Later:
9. Interactive chart replay
10. Trading education modules
11. Referral program
12. Google Ads setup
