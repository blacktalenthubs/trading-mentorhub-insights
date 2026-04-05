# Feature Specification: AI Trading Services

**Status**: Planning
**Created**: 2026-04-04
**Priority**: High — core product differentiator for new traders

---

## Vision

> "Every interaction with TradeCoPilot makes you a better trader."

The AI doesn't trade for you — it teaches you to read structure, manage risk, and build discipline. Over time, users develop their own edge and the AI becomes a validation tool rather than a crutch.

---

## Current AI Capabilities (What Exists)

| Feature | Status | Quality |
|---------|--------|---------|
| AI Coach chat (ask about any chart) | Working | Good — uses Claude with OHLCV bars |
| Per-alert AI narrative | Working | Basic — "why this setup" in 1-2 sentences |
| Regime narrator (SPY shifts) | Working | Good — educational regime change alerts |
| Cluster narrator (confluence) | Working | Good — synthesizes multi-signal confluence |
| Track record with win rates | Working | Live data, per-category breakdown |

---

## Proposed AI Services (Priority Order)

### AI-1: Smart Alert Narratives (Enhance Existing)

**Current:** Brief 1-line message like "EMA 20 Bounce — price tested 20EMA and bounced with 1.8x volume"

**Proposed:** Structured 3-part narrative on every alert:
```
📊 SETUP: EMA 20 bounce at $177.50 — price pulled back from $182 
to test the 20-day moving average and found buyers. Volume 1.8x 
average confirms institutional interest.

⚡ WHY NOW: SPY in bullish regime (above VWAP all session). NVDA 
sector (semis) showing relative strength. Daily RSI at 42 — 
oversold enough for a bounce but not broken.

⚠️ RISK: If $174.50 breaks (stop), the 20MA failed as support — 
next level is 50MA at $168. This invalidates the bounce thesis.
```

**Implementation:** Enhance `generate_narrative()` in `alerting/narrator.py` to include:
- Setup context (what happened, why this level matters)
- Timing context (regime, sector, momentum indicators)  
- Risk context (what invalidates, next support/resistance)

**Effort:** Small — prompt engineering, no new code

---

### AI-2: Personalized Trading Coach (New)

**What:** After 2+ weeks of data, the AI analyzes the user's Took/Skip/Exit history and provides personalized coaching.

**Coaching insights:**
```
"Your MA bounce trades win 82% — this is your strongest pattern. 
Focus here."

"You skip breakout alerts 70% of the time, but they have 92% WR. 
You might be missing your best opportunities."

"You exit at T1 consistently, but 6 of your last 10 T1 hits 
continued to T2. Consider holding a runner."

"3 of your last 5 losses were in the last hour. Consider stopping 
trading after 3 PM."
```

**Implementation:**
- New endpoint: `GET /api/v1/intel/coaching-insights`
- Analyzes: user's took/skipped alerts + outcomes
- Groups by: pattern type, time of day, symbol, action
- AI generates personalized recommendations

**Data required:**
- `alerts.user_action` (took/skipped) 
- `alerts.alert_type` + session outcomes (T1/T2/stop)
- 14+ days of history for meaningful patterns

---

### AI-3: Pre-Trade Checklist (New)

**What:** Before a user takes a trade, AI runs a quick checklist:

```
✅ Structure: EMA 20 support confirmed (bounced twice today)
✅ Volume: 1.8x average — buyers stepping in
✅ Regime: SPY bullish, above VWAP
⚠️ Timing: 2:45 PM — late session, reduced follow-through
❌ Sector: Semis lagging SPY by -0.3% today
───
CONVICTION: 7/10 — Strong setup but late timing may limit upside.
Consider smaller position size.
```

**Implementation:**
- New endpoint: `POST /api/v1/intel/pre-trade-check`
- Accepts: symbol, direction, entry, stop, target
- Returns: checklist items with pass/fail + AI synthesis

---

### AI-4: Position Management Advisor (New)

**What:** For open positions, AI monitors and suggests:

```
NVDA — LONG from $177.00 (current $180.50, +$3.50)

📈 T1 ($182) is 0.8% away. Price momentum is strong.
Recommendation: Hold for T1. Move stop to breakeven ($177).

⚠️ Watch: Approaching hourly resistance at $181.20. If 
rejected here, consider taking partial profits.
```

**Implementation:**
- Runs on demand (user clicks "Check Position" in dashboard)
- Or scheduled check every 30 min for open positions
- Uses current OHLCV + entry/stop/target levels

---

### AI-5: Market Morning Brief (Enhance Existing)

**Current:** Pre-market brief exists but basic.

**Proposed:** AI-generated daily game plan:
```
🌅 MARKET BRIEF — Monday April 7, 2026

OVERNIGHT: Futures +0.3%. Asia mixed. Europe flat.
SPY setup: Testing 200MA from below ($655). Key level today.

YOUR WATCHLIST:
• NVDA — Inside day yesterday. Breakout above $178 or 
  breakdown below $174. Wait for direction.
• AAPL — At 50MA support ($254). Bounce setup if holds.
• ETH-USD — Range-bound $2050-$2080. Trade the boundaries.

TODAY'S BIAS: Cautiously bullish if SPY reclaims 200MA.
Focus on bounce setups at support levels.

KEY LEVELS TO WATCH:
• SPY 655 (200MA), 660 (PDH), 651 (PDL)
• NVDA 178 (inside day high), 174 (inside day low)
```

---

### AI-6: Weekly Performance Review (New)

**What:** Every Friday/Sunday, AI generates a comprehensive review:

```
📊 WEEKLY REVIEW — March 31 - April 4

PERFORMANCE:
• 12 alerts taken, 9 won, 3 lost (75% WR)
• Total P&L: +$1,280 (2.6% on $50k)
• Best trade: NVDA PDL reclaim +$420
• Worst trade: SPY breakout failed -$180

PATTERNS:
• Bounce trades: 6/7 won (86%) — your bread and butter
• Breakout trades: 2/4 won (50%) — consider tighter criteria
• Short trades: 1/1 won — small sample but profitable

COACHING:
Your timing improved this week — no losses in the last hour.
The two breakout losses were both in CHOPPY regime. Consider
skipping breakouts when SPY is range-bound.

NEXT WEEK: Focus on bounce setups. Reduce breakout sizing
until win rate improves.
```

---

## Implementation Priority

```
Weekend (spec + implement):
  AI-1: Smart narratives     ← prompt engineering, quick win
  AI-5: Morning brief        ← enhance existing, schedule already done

Next week:
  AI-2: Personalized coach   ← needs 2+ weeks of user data
  AI-6: Weekly review        ← Friday delivery

Later:
  AI-3: Pre-trade checklist  ← nice to have
  AI-4: Position advisor     ← complex, needs real-time monitoring
```

---

## Technical Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Alert Engine │────▶│ AI Narrator  │────▶│ Telegram     │
│ (rules)      │     │ (Claude)     │     │ (delivery)   │
└──────────────┘     └──────────────┘     └──────────────┘
                            │
                     ┌──────▼──────┐
                     │ Context     │
                     │ Assembly    │
                     │ (OHLCV +   │
                     │  regime +   │
                     │  history)   │
                     └─────────────┘
```

All AI services use:
- **Claude Haiku** for fast, cheap narratives (alerts, checklists)
- **Claude Sonnet** for deep analysis (coaching, weekly review)
- **OHLCV bars** as context (chart reading)
- **User history** for personalization (took/skipped/outcomes)

---

## Cost Estimation

| Service | Model | Calls/Day | Est. Cost/Day |
|---------|-------|-----------|---------------|
| Alert narratives | Haiku | ~50 | $0.05 |
| Morning brief | Sonnet | 1 | $0.02 |
| Coaching insights | Sonnet | 1/week | $0.01 |
| Weekly review | Sonnet | 1/week | $0.02 |
| Pre-trade check | Haiku | ~10 | $0.01 |
| **Total** | | | **~$0.10/day** |

At $29/mo subscription, AI costs are <1% of revenue per user.
