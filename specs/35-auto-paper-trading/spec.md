# Feature Specification: AI Auto-Executed Paper Trades

**Status**: Draft
**Created**: 2026-04-12
**Author**: Claude (speckit)
**Priority**: High — strongest proof-of-product for marketing and conversion

## Overview

Every AI LONG / SHORT signal auto-executes into a public paper trading account. The AI's stops and targets manage the position — no human intervention. This creates a **live, auditable track record** of the AI trading its own calls in real time.

For marketing: "Here's the AI's paper account. It's up X% this month. You can watch every trade."

For conversion: Skeptics see the system work with no cherry-picking, no survivorship bias, no guru hand-waving.

## Problem Statement

### What's broken with the current proof story

The platform has two existing signals-of-trust:
- **Public track record** — aggregate win rate from alerts that users marked "Took"
- **Trade replay** — individual alert replays with outcomes

Both have gaps:

1. **Self-reported takes are biased.** Users tend to skip losing setups in hindsight (not clicking Skip), so "took" alerts skew winner-heavy.
2. **Track record depends on users pressing buttons.** Quiet-day signals go unrecorded.
3. **No continuous P&L story.** We show win rate, not "the AI account is up 4.2% this month."
4. **No social-media-ready equity curve.** Can't tweet "AI closed +12% in Q2" because we don't track it systemically.

### The fix

A **system paper account** (let's call it "AI Auto-Pilot") that:

- Auto-opens a paper trade on every actionable AI signal (LONG / SHORT / eventually EXIT advisories)
- Uses the AI's own entry, stop, target
- Monitors price and auto-closes when stop or target hits
- Accrues a public equity curve + per-trade P&L
- Shown on a new `/track-record` page (already partially public) with per-pattern, per-symbol, per-day breakdowns

This is NOT the user's personal paper trading (existing `PaperTrade` table is user-scoped). This is a **system-level account** — one per symbol universe — that runs continuously as the public performance record.

## Goals

1. **Credibility**: Public, auditable, tamper-proof AI performance data
2. **Marketing fuel**: Shareable equity curve, screenshots, weekly P&L posts
3. **Product honesty**: Show losses with the same prominence as wins — forced by automation
4. **Self-audit**: See exactly where the AI excels and fails, without user-selection bias

## Non-Goals

- **Not broker integration** — no real money, no order routing
- **Not replacing user paper trading** (existing feature stays, user-scoped)
- **Not a signal service replica** — users still see their own alerts and decide
- **Not per-user AI paper accounts** — this is one system account for public record

## Proposed Design

### Data model

New table `ai_auto_trades` (or reuse `paper_trades` with a sentinel `user_id`):

```sql
CREATE TABLE ai_auto_trades (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER REFERENCES alerts(id),  -- source signal
    symbol VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,  -- BUY or SHORT
    setup_type VARCHAR(100),         -- e.g. "PDL bounce"
    conviction VARCHAR(20),          -- HIGH / MEDIUM / LOW

    -- Entry
    entry_price REAL NOT NULL,
    opened_at TIMESTAMP DEFAULT NOW(),
    session_date VARCHAR(10) NOT NULL,

    -- Risk plan (from AI)
    stop_price REAL,
    target_1_price REAL,
    target_2_price REAL,

    -- Position sizing (fixed rules, see below)
    shares REAL NOT NULL,
    notional_at_entry REAL NOT NULL,

    -- Exit
    status VARCHAR(20) NOT NULL DEFAULT 'open',
      -- 'open' | 'closed_t1' | 'closed_t2' | 'closed_stop' | 'closed_eod' | 'closed_manual'
    exit_price REAL,
    closed_at TIMESTAMP,
    exit_reason VARCHAR(50),

    -- P&L
    pnl_dollars REAL,
    pnl_percent REAL,
    r_multiple REAL,  -- (exit - entry) / (entry - stop); negative if stop hit

    -- Meta
    market VARCHAR(20),  -- 'equity' or 'crypto'
    notes TEXT
);

CREATE INDEX idx_ai_auto_trades_symbol ON ai_auto_trades(symbol);
CREATE INDEX idx_ai_auto_trades_status ON ai_auto_trades(status);
CREATE INDEX idx_ai_auto_trades_session ON ai_auto_trades(session_date);
```

### Auto-entry flow

Triggered inside `day_scan_cycle` after any actionable signal (LONG or SHORT) is recorded:

```
For each new AI LONG / SHORT signal:
  1. Check dedup — one open ai_auto_trade per (symbol, direction) at a time
  2. Apply fixed position sizing (below)
  3. INSERT ai_auto_trade with status='open', entry/stop/targets from AI
  4. Log to worker
```

### Auto-exit flow

New scheduled job every 1 minute during market hours:

```
For each open ai_auto_trade:
  1. Fetch latest price for symbol (reuse /market/prices cache)
  2. LONG logic:
     - If price >= target_2 → close @ target_2, status='closed_t2'
     - Elif price >= target_1 → close @ target_1, status='closed_t1' (full exit for v1)
     - Elif price <= stop → close @ stop_price, status='closed_stop'
  3. SHORT logic: inverted
  4. Equity / crypto EOD handling:
     - Equity trades close at 4:00 PM ET if still open, status='closed_eod', exit_price=last close
     - Crypto trades stay open overnight (24/7 market)
  5. Compute pnl_dollars, pnl_percent, r_multiple
  6. UPDATE ai_auto_trade
```

### Position sizing rules (fixed, transparent)

Every trade uses the same sizing so P&L is comparable across signals:

```python
NOTIONAL_PER_TRADE = 10_000  # $10k per signal
shares = NOTIONAL_PER_TRADE / entry_price
```

Document this openly in the marketing page: "Every signal = $10k notional. No discretionary sizing."

### Public metrics (for landing + `/track-record`)

Compute and cache (5-min TTL):

- **Lifetime**: total trades, closed trades, win rate, total P&L $ and %
- **Last 30 days**: signals, wins, losses, P&L, best trade, worst trade
- **Per pattern**: PDL bounce 82% (11/13), VWAP reclaim 67% (4/6)…
- **Per symbol**: ETH-USD 73%, NVDA 65%…
- **Per direction**: LONGs 72% / SHORTs 58%
- **Equity curve**: daily cumulative P&L, starting at $0
- **Open positions**: list of currently-open auto trades with unrealized P&L

### New API endpoints

```
GET  /api/v1/auto-trades/stats                # Aggregate metrics
GET  /api/v1/auto-trades/recent?limit=50      # Recent closed
GET  /api/v1/auto-trades/open                 # Currently open
GET  /api/v1/auto-trades/equity-curve?days=30 # Daily cumulative series
GET  /api/v1/auto-trades/by-pattern           # Breakdown
GET  /api/v1/auto-trades/by-symbol            # Breakdown
GET  /api/v1/auto-trades/{id}                 # Single trade detail + replay link
```

All endpoints **public** (no auth) — this is the marketing asset.

### Frontend changes

#### Landing page
- Replace / augment current "Live track record" widget with:
  - Total P&L % (large, hero)
  - Last 30-day win rate
  - Currently open positions badge ("3 open now, check back at 4 PM")
  - Mini equity curve sparkline
  - CTA: "See every trade →" → `/track-record`

#### New public page: `/track-record`
- Full equity curve (30d / 90d / YTD toggle)
- Sortable table of all closed trades with: date, symbol, direction, setup, entry, exit, P&L %, replay link
- Per-pattern / per-symbol tabs
- Open positions panel at top
- Share buttons: "Tweet this track record" (pre-filled with current stats)

#### In-app (logged in users)
- Small widget on Dashboard: "AI Auto-Pilot: +X.Y% today / +Z% last 30d" (drives premium upgrade)
- Link to `/track-record`

### Marketing hooks (ties to Spec 33)

Weekly auto-generated post:
```
AI Auto-Pilot — Week of [DATE]:
P&L: +[X]%
Wins: [Y]  Losses: [Z]
Best: [SYMBOL] +[A]%
Worst: [SYMBOL] -[B]%

Every trade: tradingwithai.ai/track-record

#tradecopilot #tradingwithai #aitrade #trackrecord
```

Daily recap (EOD at 4:05 PM ET):
```
AI Auto-Pilot today:
[N] trades · [W] wins · [L] losses
Net: [+/-X]%

Equity curve: [link]

#tradecopilot #aitrade
```

## User Scenarios

### Scenario 1: Skeptic checks the track record
**Actor**: Day trader, skeptical of AI claims, saw a tweet
**Flow**:
1. Clicks `tradingwithai.ai/track-record`
2. Sees 127 closed trades, +8.4% cumulative, 68% win rate
3. Scrolls list, sees a -2.1% loss detailed with replay
4. Clicks replay → watches stop get hit exactly where AI placed it
5. Concludes: "This is real, and they don't hide losses."
6. Signs up for trial

### Scenario 2: Marketing asset on Twitter
**Actor**: Founder posting Friday
**Flow**:
1. Opens `/track-record`, screenshots equity curve
2. Click "Tweet this" → pre-filled with week's stats + link
3. Posts → followers click → traffic spike → signups

### Scenario 3: Self-audit of AI performance
**Actor**: You (admin)
**Flow**:
1. Open `/track-record` → filter by pattern
2. Notice "Inside Day Breakout" is 2/7 (29% win rate)
3. Investigate in logs → AI is firing on false breakouts
4. Tune the SHORT confirmation rules in the prompt
5. Tracking shows improvement over next 2 weeks

## Functional Requirements

### FR-1: Auto-entry on AI signals
- [ ] On every `ai_day_long` or `ai_day_short` alert recorded, auto-insert matching `ai_auto_trade`
- [ ] Dedup: one open auto trade per (symbol, direction) — skip if already open
- [ ] Fixed sizing: $10k notional per trade (configurable constant)
- [ ] If entry/stop/targets missing, skip auto trade and log warning
- Acceptance: LONG alert fires → auto trade created within 1 sec → verifiable in DB

### FR-2: Auto-exit engine
- [ ] New scheduler job `auto_trade_monitor` runs every 1 min during market hours (24/7 for crypto symbols)
- [ ] For each open auto trade, fetches current price and checks T1 / T2 / stop
- [ ] Closes with proper status, records exit price and P&L
- [ ] EOD cleanup: equities close at 4:00 PM ET if still open (`status='closed_eod'`)
- Acceptance: LONG with T1=$2,218 → price touches $2,218 → auto trade closes within 60 sec with correct P&L

### FR-3: Public stats API
- [ ] All `/api/v1/auto-trades/*` endpoints return 200 without auth
- [ ] Response cached 5 min (Redis or in-memory) to keep landing page fast
- [ ] Stats include: total P&L, win rate, per-pattern, per-symbol, equity curve
- Acceptance: GET `/api/v1/auto-trades/stats` returns JSON with non-zero metrics after first 10 trades

### FR-4: Track record page
- [ ] Public route `/track-record` (no login required)
- [ ] Hero: cumulative P&L + win rate + open positions count
- [ ] Equity curve chart (Recharts or similar)
- [ ] Sortable trade table with replay links
- [ ] Tabs: All / By Pattern / By Symbol
- [ ] "Share on Twitter" buttons with pre-filled text
- Acceptance: Page loads in <3s with live data; passes smoke tests

### FR-5: Landing page widget upgrade
- [ ] Replace current win-rate widget with live auto-trade stats
- [ ] Sparkline of 30-day equity curve
- [ ] CTA to `/track-record`
- Acceptance: Landing shows "+X.Y%" live number, matches `/track-record` hero

### FR-6: Daily recap automation
- [ ] At 4:05 PM ET on weekdays, publish daily summary to a log / webhook / Twitter queue
- [ ] Friday 5:00 PM ET: weekly summary with wins, losses, best pattern
- [ ] Content available for social scheduling (manual Twitter for now; automated later)
- Acceptance: Daily summary content generated and retrievable via admin endpoint

### FR-7: Admin controls
- [ ] `/admin/auto-trades` page to force-close a trade (in case of bad data)
- [ ] `/admin/auto-trades/rebuild-stats` to recompute aggregate cache
- [ ] Audit log entry for any manual intervention (visible on `/track-record` — honesty)
- Acceptance: Admin can close any open trade; forced closes show a "manually closed" badge on public view

## Edge Cases

- **Signal fires with no stop / target**: skip auto-entry, log warning (rare but possible if AI output parsing fails)
- **Crypto + weekend gap**: crypto trades may hit stop at 2 AM Sunday. Handle normally — that's the point of 24/7 coverage.
- **Equity overnight holds**: close at 4:00 PM ET with that day's close price. Don't hold overnight (too complex + not a day trade).
- **Multiple signals same bar**: first one creates the trade, subsequent dedup'd. Next signal for that symbol/direction accepted once the previous closes.
- **Price feed hiccup**: if fetch fails, skip this cycle, try again next minute. Don't force-close on data gap.
- **Alert updated / retracted**: out of scope. AI signals are fire-and-forget.
- **Very volatile bar**: if both stop and target touched in same 1-min window, use "stop first" rule (conservative — protects downside narrative).
- **Fee / slippage modeling**: out of scope for v1. P&L is raw — clearly documented.

## Out of Scope (v1)

- Real broker integration
- Partial exits (scale out at T1, trail rest)
- Position sizing based on volatility or conviction
- Multiple concurrent positions on same symbol
- User-scoped AI auto-trading (separate feature, future)
- Backtesting on historical alerts
- Fee / slippage simulation

## Risks & Mitigation

| Risk | Mitigation |
|---|---|
| AI has a bad streak right after launch → bad optics | Seed with 2 weeks of paper trading BEFORE going fully public. Publish when we have a healthy sample. |
| Whipsaw causes stop-then-target same trade | Stop-first rule; documented on methodology page |
| Price feed outages = phantom stops | Graceful retry, no force-close on gap; audit log |
| Users confuse system account with real money / theirs | Clear "AI Auto-Pilot (simulated)" labels everywhere |
| Public data reveals setup weaknesses competitors copy | Acceptable — the AI + education is the moat, not the patterns (those are public anyway) |
| Regulatory — "track record" claims | Disclaimer: "Simulated trades. Past performance doesn't guarantee future results. Not an offer or solicitation." Present on `/track-record` |

## Compliance & Disclaimers

Every public-facing track record page must show:
```
AI Auto-Pilot is a simulated trading account.
Every trade executes the AI's own signals at the moment they fire,
using fixed $10,000 notional sizing with no fees or slippage applied.
Past performance does not guarantee future results.
This is educational analysis, not financial advice.
```

## Success Criteria

- [ ] After 30 days live: ≥ 50 closed trades in the system
- [ ] Win rate within ± 5% of user-reported win rate (sanity check — AI is consistent whether humans take signals or not)
- [ ] `/track-record` page generates ≥ 20% of landing page clicks
- [ ] Weekly Twitter post with track record screenshot drives measurable signup spike
- [ ] Zero manual admin interventions in steady state (system is self-healing)

## Implementation Phases

### Phase 1 — Data model + auto-entry (2-3 days)
- Add `ai_auto_trades` table + migrations
- Hook into `day_scan_cycle` to auto-create paper trade on LONG/SHORT signal
- Manual SQL dashboard to verify trades are being created correctly
- **No public exposure yet** — running in shadow mode

### Phase 2 — Auto-exit engine (2-3 days)
- Price monitor scheduler every 1 min
- T1 / T2 / stop detection with logging
- EOD cleanup for equities
- **Still shadow mode** — letting trades complete to validate P&L math

### Phase 3 — Public API + track record page (3-5 days)
- `/api/v1/auto-trades/*` endpoints
- `/track-record` public page with equity curve + trade list
- Landing page widget update
- Launch publicly once data set is healthy (2 weeks of shadow data)

### Phase 4 — Social marketing wiring (Phase 2, Spec 33)
- Daily / weekly auto-generated content
- Share buttons with pre-filled tweets
- Weekly recap format standardized

## Related

- `api/app/models/paper_trade.py` — existing user-scoped paper trading (don't confuse)
- `analytics/ai_day_scanner.py` — source of signals
- `api/app/routers/intel.py` (`/public-track-record`) — existing public endpoint, will merge with new stats
- `specs/33-social-media-launch/twitter-playbook.md` — content hooks using this data
- `web/src/pages/LandingPage.tsx` — widget update target
