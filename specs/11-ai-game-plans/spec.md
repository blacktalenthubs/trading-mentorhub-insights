# Feature Specification: 3 AI Game Plans for User Value

**Status**: Ready for Review
**Created**: 2026-04-05

---

## Vision

Three AI-powered features that create undeniable value — each one is a reason users stay subscribed and tell their friends.

---

## Game Plan 1: AI Daily Battle Plan (Pre-Market)

### What
Every morning at 9:15 AM ET, each Pro user receives a personalized AI-generated game plan for their specific watchlist. Not a generic market recap — a specific if/then playbook for every symbol they watch.

### Format (Telegram + Dashboard)
```
🌅 YOUR BATTLE PLAN — Monday April 7

SPY OUTLOOK: Bearish regime, testing 200MA at 655. If holds → bounce to 660.
If breaks → flush to 645. Wait for direction before adding equity longs.

YOUR PLAYS:

NVDA $177 — INSIDE DAY yesterday. Breakout above 178.50 → LONG, 
  stop 176.80, target 183. Breakdown below 174 → avoid, wait for 170 MA200.

ETH-USD $2040 — Double bottom at 2024 HOLDING. Already long from 2024.
  MANAGE: Move stop to 2030 if it clears 2045 resistance.
  EXIT: Below 2020 = thesis broken.

SPY — DO NOT TRADE until 200MA resolves. Watch 655 hold or break.

AVOID TODAY: PLTR (no setup), META (extended, no pullback to buy)

RISK BUDGET: You've been taking 3-4 trades/day. Today focus on ONE 
high-conviction play. Quality > quantity.
```

### Why Users Love It
- Starts every day with a plan instead of scrambling at the open
- Personalized to THEIR watchlist and open positions
- Teaches them to think in if/then scenarios
- The "AVOID" section prevents bad trades (saves money)

### Implementation
- Enhanced `send_ai_premarket_brief()` already exists
- Need to add: per-user watchlist context, open positions, recent P&L
- Use Claude Sonnet for depth
- Deliver via Telegram + show on Dashboard

---

## Game Plan 2: AI Trade Replay Analyst

### What
After every completed trade (T1 hit or stop loss), the AI generates a replay analysis that teaches the user what happened and why. Combined with the chart replay feature, this creates a visual + narrative learning experience.

### Format (Dashboard + Signal Library)
```
📊 TRADE REPLAY: ETH-USD PDL Reclaim

ENTRY: $2,024.45 at 5:37 AM — Double bottom zone tested 3x, 
bounce confirmed with wick reclaim + 1.3x volume.

WHAT HAPPENED:
▶ [Chart replay plays here — candle by candle]
- Price bounced off 2024 zone ✅
- Rallied to 2044 resistance (broken support) ⚠️
- Got rejected at 50MA — first test, expected
- Pulled back to 2033, held above entry
- Second push through 2044... [still playing]

OUTCOME: T1 hit at $2,065.23 (+$40.78, +2.0%)

WHAT YOU CAN LEARN:
1. Double bottoms with 3+ touches are high-conviction support
2. First test of broken support (now resistance) often rejects — 
   but the second attempt usually breaks through
3. The 50MA that was support for days doesn't flip to resistance 
   instantly — it takes 2-3 rejections to confirm

WIN RATE FOR THIS PATTERN: 65% (33 trades, last 90 days)
YOUR WIN RATE: 80% (4/5 trades on this pattern)
```

### Why Users Love It
- They SEE their trade play out — visual learning
- AI explains cause and effect (not just "T1 hit")
- Builds pattern recognition over time
- Creates shareable content ("Watch how I caught the ETH double bottom")
- Signal Library examples become REAL trade stories, not hypotheticals

### Implementation
- Chart replay component exists (`ChartReplay.tsx`)
- Need to add: AI narration overlay, outcome explanation, pattern lesson
- New endpoint: `GET /api/v1/intel/trade-replay/:alert_id` — combines replay data + AI analysis
- Store completed replay analyses for the Signal Library examples

---

## Game Plan 3: AI Edge Tracker (Weekly Intelligence Brief)

### What
Every Friday, the AI analyzes the user's entire trading week and produces an "Edge Report" — not just wins/losses, but behavioral patterns that reveal their trading edge (or lack of it).

### Format (Telegram + Email + Dashboard)
```
📈 YOUR EDGE REPORT — Week of April 7-11

EDGE SCORE: 7.2/10 (up from 6.8 last week)

YOUR PROVEN EDGE:
• PDL reclaim trades: 4/4 wins this week (100%) — this IS your edge
• You take bounces early (within 5 min of alert) — faster than 80% of users
• Your average winner is 2.1x your average loser — excellent discipline

YOUR LEAKS:
• You took 2 breakout trades that both failed — breakouts in CHOPPY 
  regime have 45% WR. Skip breakouts when SPY is range-bound.
• You held ETH through resistance instead of taking partial at T1.
  T1 hit at 2065 but you exited at 2052 (left $13/share on table).

WHAT CHANGED THIS WEEK:
• You started using the pre-trade checklist — your win rate improved 
  from 65% to 78% since you started checking regime before entry
• You reduced position count from 4 to 2 simultaneous — fewer but 
  better trades

NEXT WEEK FOCUS:
1. Keep taking PDL reclaims — it's working, don't fix what isn't broken
2. Skip breakout alerts when SPY regime is CHOPPY
3. Practice taking partial profits at T1 — set a rule: sell 50% at T1

PATTERN SPOTLIGHT: Prior Day Low Reclaim
[Link to Signal Library page with your actual trade as the example]
```

### Why Users Love It
- They discover their actual edge (not what YouTube told them)
- Behavioral insights they can't see themselves
- Tracks improvement over time (Edge Score)
- The "LEAKS" section is worth the subscription alone — saves money
- Creates accountability without being judgmental

### Implementation
- Weekly review exists (`analytics/weekly_review.py`)
- Need to enhance with: Edge Score calculation, behavioral pattern detection, week-over-week comparison
- New data: track time-to-action (how fast user takes alert), partial profit behavior, regime-filtered win rate
- Store weekly Edge Score for trend tracking
- Email delivery (in addition to Telegram)

---

## How These 3 Features Work Together

```
MORNING:
  AI Battle Plan → "Here's YOUR game plan for today"
     ↓
DURING MARKET:
  Alerts fire → AI Coach teaches → User takes/skips
     ↓
AFTER EACH TRADE:
  AI Trade Replay → "Here's what happened and what you can learn"
     ↓
END OF WEEK:
  AI Edge Tracker → "Here's your edge, your leaks, and how to improve"
```

Each feature feeds into the next:
- Battle Plan teaches **preparation**
- Coach + Alerts teach **execution**
- Trade Replay teaches **pattern recognition**
- Edge Tracker teaches **self-awareness**

**The result:** Users get measurably better at trading over time. That's the subscription moat — they stay because they're improving.

---

## Monetization Impact

| Feature | Free Tier | Pro Tier | Premium Tier |
|---------|-----------|----------|-------------|
| Daily Battle Plan | SPY only | Full watchlist | Full + sector analysis |
| Trade Replay | 1/week | Unlimited | Unlimited + video export |
| Edge Tracker | Basic score | Full report | Full + email + coaching call |

---

## Implementation Priority

```
Week 1: Enhance Daily Battle Plan (mostly built, needs per-user context)
Week 2: Trade Replay Analyst (chart replay exists, needs AI narration)
Week 3: Edge Tracker (weekly review exists, needs behavioral analysis)
```

---

## Success Metrics

- **Battle Plan**: >50% of Pro users read it daily (measured by Telegram read rate)
- **Trade Replay**: Users watch >3 replays/week (measured by API calls)
- **Edge Tracker**: Edge Score improves for >60% of users over 4 weeks
- **Retention**: Pro churn drops below 5%/month within 60 days of launch
