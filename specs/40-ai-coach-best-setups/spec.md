# Spec 40 — AI Coach: Best Setups of the Day

**Status:** Draft (specify phase)
**Created:** 2026-04-15
**Related:** Spec 39 (AI signal logic), Spec 34 (day scanner), Spec 36 (user prefs)

---

## 1. Problem

Users wake up, markets open in 20 minutes, and they have 10-15 symbols on their watchlist. Without help they have to manually look at each chart, identify key levels, and decide which setups are worth watching today. By the time they finish, half the moves have already happened.

The existing AI Coach answers questions ("what do you think about NVDA?"), but doesn't proactively surface the best opportunities across the whole watchlist. It's a reactive chat, not a morning planning tool.

## 2. Goal

Let the user ask the AI Coach one question — *"What are the best setups in my watchlist today?"* — and get a ranked, actionable list within 5-10 seconds.

Each setup shows:
- Symbol + direction (LONG / SHORT)
- The specific key level being traded (PDL reclaim, 200MA bounce, weekly high breakout, etc.)
- Entry / Stop / T1 / T2
- **Risk-to-reward ratio** (R:R — the primary ranking signal)
- AI conviction (HIGH / MEDIUM / LOW)
- 1-sentence "why this, why now"

Ordered by R:R descending so the best-edge setups surface first.

## 3. User Story

> As a busy trader with a 9-5, I open TradeCoPilot at 9:15 AM. I click "AI Coach" → ask "*Best setups today?*" (or tap a preset button). Within 10 seconds I see 3-5 ranked setups across my watchlist. I pick the one I want, set my orders, go to work.

## 4. Non-Goals

- Not a replacement for the day scanner (which fires real-time during market hours)
- Not a full backtest or historical analysis
- Not placing trades automatically
- Not a general-purpose coach ("how should I feel about my trades?") — that's the existing chat
- Not a swing-trade digest (Spec 38 covers that separately)
- Not pre-market rank (that's the existing game plan email — different product)

## 5. Triggers

User can invoke this mode three ways:

1. **Preset button** in the AI Coach sidebar: `[ Best Setups Today ]`
2. **Natural language** detection in chat: "best setups", "what should I trade", "ranked watchlist", "top picks today"
3. **API endpoint** (for future push notifications / Telegram bot command `/picks`)

## 6. Ranking: Risk-to-Reward is Primary

**R:R = (T1 - entry) / (entry - stop)** for LONG
**R:R = (entry - T1) / (stop - entry)** for SHORT

Setups sorted by R:R descending. Tiebreaker: conviction.

**Minimum bar to make the list**: R:R ≥ 1.5. Below that the trade isn't worth the risk regardless of conviction.

## 7. AI Decides Setups From Data

Input: per symbol, full level + price context (see §11).
Output: AI returns setups it identifies, in its own words — no predefined
"setup type" menu. AI describes each setup with a free-text label
("50 EMA reclaim", "weekly high breakout + RSI strength", "session low
double-bottom", etc.).

This matches how the day scanner works today (Spec 39 principles) — we give
AI the data and trust it to reason about what's tradeable. Pre-listing
"valid setups" would cap AI's judgement to our imagination.

### Code-side validation (applied to AI output)

After AI returns its picks, code enforces:

- **R:R ≥ 1.5** — compute from AI's entry/stop/T1; reject lower
- **SPY-only SHORT** — non-SPY SHORTs become informational RESISTANCE, not
  a tradeable entry on the ranked list
- **Directional sanity** — LONG requires stop < entry < T1; SHORT mirror;
  reject if geometry broken
- **Staleness** — reject if current price already past 50% of entry → T1
  distance (progress-to-target check, same as day scanner)

Rejected setups are logged (for debugging) but don't surface to the user.

## 8. Output Schema

### API response shape

```json
{
  "generated_at": "2026-04-15T09:15:00-04:00",
  "watchlist_size": 12,
  "setups_found": 4,
  "picks": [
    {
      "rank": 1,
      "symbol": "AAPL",
      "direction": "LONG",
      "setup_type": "200 Daily MA bounce",
      "entry": 258.30,
      "stop": 256.50,
      "t1": 263.00,
      "t2": 267.00,
      "risk_per_share": 1.80,
      "reward_per_share": 4.70,
      "rr_ratio": 2.61,
      "conviction": "MEDIUM",
      "confluence": ["200MA", "prior swing low", "oversold RSI 32"],
      "why_now": "Price tagged 200 Daily MA at $258.30 with RSI 32 oversold; multi-level support cluster.",
      "current_price": 258.45,
      "distance_to_entry_pct": 0.06
    }
  ],
  "skipped": [
    {"symbol": "TSLA", "reason": "no clear setup — mid-range, no structural level"},
    {"symbol": "PLTR", "reason": "R:R 1.2 — below 1.5 minimum"}
  ]
}
```

### UI (AI Coach panel)

```
Best Setups Today — Apr 15, 9:15 AM

① AAPL   LONG   200MA bounce            R:R 2.6   MEDIUM
   Entry $258.30  Stop $256.50  T1 $263.00  T2 $267.00
   Why now: Price tagged 200 Daily MA with RSI 32 oversold; multi-level
   support cluster (200MA + prior swing low + RSI).
   [ Replay similar setups ]  [ Add to trade plan ]

② SPY    LONG   VWAP reclaim            R:R 2.1   HIGH
   …

③ NVDA   LONG   Weekly high reclaim     R:R 1.8   LOW
   …

Skipped (3):
• TSLA — no clear setup
• PLTR — R:R 1.2 below minimum
• AMD  — no structural level nearby

↻ Refresh   |   Last updated 14 seconds ago
```

## 9. Architecture

```
User clicks "Best Setups Today"
    ↓
Frontend → GET /api/v1/ai/best-setups
    ↓
Backend:
  1. Load user's watchlist symbols (from DB)
  2. For each symbol, fetch:
     - Current price (Alpaca)
     - Prior-day levels (MAs, PDH/PDL, weekly/monthly) — fetch_prior_day()
     - 5-min recent bars
  3. Build ONE consolidated Claude Sonnet call with all symbols + levels
     (batch prompt: "Rank the best setup for today across these symbols")
  4. Parse structured response (JSON)
  5. Compute R:R per setup, filter R:R < 1.5
  6. Sort by R:R desc
  7. Return JSON
    ↓
Frontend renders ranked list
```

**Key insight**: one AI call for the whole watchlist, not N calls. Sonnet can compare symbols in a single pass, which also improves ranking (it's seeing all options at once).

**Cost**: ~5000 input tokens (levels for 15 symbols) + ~1500 output tokens per request = ~$0.04/call. Cached 15 min to absorb repeated clicks.

## 10. Prompt Design (draft)

```
You are a swing/day trade analyst ranking the best setups across a user's watchlist
for the upcoming session.

For each symbol below, evaluate whether there is a tradeable setup RIGHT NOW at a
durable key level. Return ONLY the top setups — no filler, no "maybe watch".

You have FULL discretion on what qualifies as a setup. Read the data per symbol
(MAs, PDH/PDL, weekly/monthly levels, VWAP, RSI, recent bars) and identify
the best tradeable setup right now — if any.

Label your setup in your own words. Examples of strong setups: durable key
level being tested, multi-level confluence, RSI extreme at support/resistance,
reclaim of just-broken level (flipped support/resistance), clean higher-low
structure at support.

Do NOT fire a setup if price is mid-range with no structural level nearby.

CONVICTION:
- HIGH: multi-level confluence + structure confirming
- MEDIUM: at level + one confirmation
- LOW: at level, no structure yet

RISK:REWARD is the primary ranking metric. Only include setups where:
  (T1 - entry) / (entry - stop) >= 1.5 for LONG
  (entry - T1) / (stop - entry) >= 1.5 for SHORT

OUTPUT — return a JSON array, one object per qualifying setup:
[
  {
    "symbol": "...",
    "direction": "LONG" | "SHORT",
    "setup_type": "<name>",
    "entry": <number>,
    "stop": <number>,
    "t1": <number>,
    "t2": <number>,
    "conviction": "HIGH" | "MEDIUM" | "LOW",
    "confluence": ["<level1>", "<level2>", ...],
    "why_now": "<1 sentence>"
  }
]

Order by R:R descending. Skip symbols with no qualifying setup.

[WATCHLIST DATA]
<for each symbol: current price + all level data from fetch_prior_day>
```

## 11. Data Inputs per Symbol

Reuses existing helpers (no new data fetching needed):

| Field | Source | Helper |
|---|---|---|
| Current price | Alpaca latest bar | `_fetch_alpaca_bars` / `_fetch_alpaca_crypto_bars` |
| PDH/PDL/Prior Close | Yesterday's daily bar | `fetch_prior_day` |
| Daily MA 20/50/100/200 | computed in prior_day | `fetch_prior_day` |
| Daily EMA 20/50/100/200 | computed in prior_day | `fetch_prior_day` |
| Weekly high/low | computed in prior_day | `fetch_prior_day` |
| Monthly high/low | computed in prior_day | `fetch_prior_day` |
| RSI14 (daily) | computed in prior_day | `fetch_prior_day` |
| Last 10 × 5-min bars (intraday context) | Alpaca | `fetch_intraday` / `fetch_intraday_crypto` |

## 12. Caching Strategy

- Response cached **15 minutes** per user's watchlist snapshot (hash of sorted symbols)
- Invalidate immediately when user adds/removes symbols
- Cache key: `best_setups:{user_id}:{watchlist_hash}`
- Underlying data (prior_day, bars) already cached per-symbol — no extra cache complexity

## 13. Tier Limits

| Tier | Best Setups calls per day |
|---|---|
| Free | 1 (morning taste) |
| Pro | 20 |
| Premium | unlimited |

Repeated clicks within 15-min cache window don't count.

## 14. Success Metrics (30 days after launch)

- **Usage**: % of users clicking "Best Setups" in first 30 min after market open
- **Conversion**: % of picks that were "Took" within the session
- **Hit rate**: % of picks where T1 was reached
- **Retention lift**: 7-day return rate of users who used Best Setups vs. those who didn't
- **Cost**: Anthropic spend per day attributable to this feature

Target: ≥ 50% daily activation among Pro users, ≥ 50% T1 hit rate on top-3 ranked picks.

## 15. Phased Delivery

### Phase 1 — Backend endpoint (1 day)
- `/api/v1/ai/best-setups` endpoint with Sonnet batch call
- R:R filter + sort
- In-memory cache (15 min)
- Unit tests for R:R math, JSON parsing, tier gating

### Phase 2 — Chat integration (half day)
- Detect "best setups" / "top picks" natural language in AI Coach chat
- Route to the same endpoint, render result inline as chat response
- Preset button `[ Best Setups Today ]` prominent in coach panel

### Phase 3 — Dedicated UI (1 day)
- Standalone "Best Setups" widget on Dashboard (morning section)
- Collapsible cards, one per pick
- `[ Take ]` button wires into existing alerts.took flow
- `[ Replay ]` shows similar historical setups if any

### Phase 4 — Enhancements (future, not in this spec)
- Telegram `/picks` command
- Push notification 15 min before market open with top 3
- Daily win-rate tracking on picks
- Personalized ranking (user's historical preference: volatility, asset class, etc.)

## 16. Test Plan

### Unit tests
- R:R computation for LONG + SHORT + edge cases (entry==stop, t1<entry for LONG bug)
- JSON parser handles malformed Sonnet output gracefully
- Cache key stability across watchlist reorders
- Tier gate blocks free user after 1 call/day

### Integration tests
- Mock Anthropic, verify endpoint returns ranked picks
- Watchlist with 0 symbols → empty setups, clear message
- Watchlist with all-bad-RR → all skipped with reasons
- Crypto + equity mixed watchlist handled

### E2E manual
1. User logs in, has AAPL/SPY/NVDA/PLTR/ETH-USD on watchlist
2. Opens AI Coach → clicks "Best Setups Today"
3. Sees 2-4 picks ranked by R:R within 10 sec
4. Picks top one → "Take" → alerts.took flow fires → appears on dashboard
5. Refreshes within 15 min → cached response, no new AI call
6. Adds a symbol → cache invalidated, next call re-scans

## 17. Rollback

- Feature-flag env: `BEST_SETUPS_ENABLED=true`
- If Sonnet quality is poor or cost explodes: flip flag off, feature hides from UI
- DB-backed tier counter — no stale state on rollback

## 18. Risks

| Risk | Mitigation |
|---|---|
| Sonnet hallucinates levels not in data | Validate returned entry/stop/T1 against the level list we passed; reject if fabricated |
| Free tier abuses 1-call/day limit by creating multiple accounts | Existing rate limit per user + IP-based throttle if needed |
| Watchlist of 50+ symbols blows token budget | Hard cap at 25 symbols per call, surface message "Trim watchlist for best results" |
| Morning spike slams Anthropic API | Pre-warm cache at 9:25 AM ET for active users' watchlists (cron job) |

## 19. Out of Scope

- Automatic order placement
- Personalized filters (asset class, volatility preference, etc.) — Phase 4
- Historical performance ranking — Phase 4
- Multi-timeframe setups (intraday + swing in same output) — two separate endpoints
- Options setups — future spec

## 20. Files Touched

**Backend (add):**
- `analytics/ai_best_setups.py` — scan logic, prompt builder, R:R filter
- `api/app/routers/ai_coach.py` — add `/best-setups` endpoint
- `api/app/tier.py` — add `best_setups_per_day` limit

**Frontend (add):**
- `web/src/components/BestSetupsCard.tsx` — rendering component
- `web/src/pages/TradingPageV2.tsx` — preset button in AI Coach tab
- `web/src/pages/DashboardPage.tsx` — Phase 3 widget

**Tests:**
- `tests/test_ai_best_setups.py` — unit + integration
- `web/src/components/BestSetupsCard.test.tsx` — rendering

## 21. Approvals

- [ ] Spec reviewed by user
- [ ] R:R threshold of 1.5 confirmed
- [ ] Tier caps (1/20/unlimited) confirmed
- [ ] Cache TTL of 15 min confirmed
- [ ] Phased delivery order (backend → chat → widget) approved
- [ ] Ready to `/speckit.plan`
