# Feature Specification: AI Scan — Exit Signals, SHORT Entries, Daily MA Context

**Status**: Draft
**Created**: 2026-04-12
**Author**: Claude (speckit)
**Priority**: High — closes the loop on AI scan value proposition

## Overview

AI scan currently handles **entries at support** very well. Three gaps remain:

1. **No exit management** for open LONGs — AI tells you where to enter, but doesn't track the thesis breaking or T1 approaching
2. **No daily MA context** — 50/100/200 daily MAs are primary support/resistance for swing-scale structure; AI doesn't reference them
3. **No SHORT entries** — AI says RESISTANCE as a warning, but doesn't fire SHORT entries when rejection structure is confirmed

These are the last pieces to make AI scan a complete "entry + exit" signal service.

## Problem Statement

### Problem 1: AI forgets about you after the entry
When you take a LONG at $2186, AI scan keeps checking for NEW setups but doesn't tell you:
- "T1 approaching — consider trimming"
- "Price broke below your stop zone — exit if not stopped out"
- "Volume collapsing on hold — thesis weakening"
- "Price rejecting at T1 twice — take profits"

Users have to manage exits manually using their own judgment or the Coach on demand. The scanner could do this automatically since it already sees the price action.

### Problem 2: Daily MAs are invisible to AI
Daily 20/50/100/200 MAs are the highest-probability support/resistance levels on intraday charts. AI gets PDH, PDL, session levels, monthly EMAs — but daily MAs aren't surfaced. Result: AI misses "price bouncing off 50 daily MA" as a LONG setup, or "price rejecting at 200 daily MA" as a SHORT setup.

### Problem 3: SHORT entries treated as notices
Today's flow:
- Price rejects at PDH → AI fires `RESISTANCE ETH $2290` (notice)
- Message: "tighten stop / take profits / watch for rejection"
- No entry/stop/target for someone wanting to SHORT

Real day traders short rejections. The same structural logic that makes a LONG at support valid (higher low + volume) makes a SHORT at resistance valid (lower high + volume). AI has the data, just needs permission to call it.

## Goals

1. **Exit management** — AI tracks open positions and sends "manage your position" alerts at key moments
2. **Daily MA context** — Fetch + pass 20/50/100/200 daily MAs into the scan prompt
3. **SHORT entries** — Upgrade RESISTANCE from notice to full trade plan (entry/stop/T1/T2) when structure confirms

## Non-Goals

- Not changing the 5-pillar platform positioning
- Not adding options signals
- Not scanning additional symbols (stays on user watchlist)
- Not per-user tuning (all users get same scan output; delivery filters stay)

## Current State (as of commit `c54a3a7`)

### AI Scan flow
```
Every scan cycle:
  For each symbol in watchlist:
    Fetch 5m bars, 1h bars, prior day data
    Build prompt with: PDH/PDL, monthly EMAs, session levels, VWAP, bars
    Ask Claude Haiku: LONG / RESISTANCE / WAIT
    If LONG: record alert, deliver Telegram with Took/Skip/Exit buttons
    If RESISTANCE: record notice, deliver Telegram (no buttons, text action)
    If WAIT: record notice (DB), Telegram only if direction changed + cooldown
```

### Position awareness (done)
- Per-user filter: skip LONG delivery if user already holds open LONG
- RESISTANCE alerts still deliver to holders (exit signal)

## Proposed Changes

### Change 1: Add Daily MA Context to Prompt

**Where**: `analytics/ai_day_scanner.py::build_day_trade_prompt`

Daily MAs come from `fetch_prior_day()` which already returns `ma20`, `ma50`, `ma100`, `ma200` but these are currently unlabeled as "daily". Also add `ema20` daily if missing.

**Prompt addition** (under existing [KEY LEVELS] section):
```
[DAILY MAs — strong multi-day support/resistance]
20 Daily MA: $X (trend ref)
50 Daily MA: $X (medium-term)
100 Daily MA: $X (intermediate support)
200 Daily MA: $X (long-term pivot)

If price is within 0.3% of any daily MA, that's the dominant level —
use it as the LONG entry (bounce) or SHORT entry (rejection) context.
```

**Data source**: `fetch_prior_day()` already provides these. Just label them clearly and include in prompt.

### Change 2: SHORT Entries as First-Class Direction

**Where**: `analytics/ai_day_scanner.py`

Upgrade the AI output enum from `LONG / RESISTANCE / WAIT` to `LONG / SHORT / RESISTANCE / WAIT`.

- **LONG** — entry at support with higher low + volume (as today)
- **SHORT** — new — entry at resistance with lower high + volume, explicit entry/stop/T1/T2
- **RESISTANCE** — downgrade to "approaching, no confirmed rejection" (notice only, for holders of LONGs)
- **WAIT** — no setup

**Prompt additions**:
```
SHORT CONFIRMATION RULES (mirror of LONG rules):
- Require LOWER HIGH structure: last bar's high must be BELOW the prior swing high.
- Require VOLUME > 1.0x average on the rejection bar, OR 2+ bars holding below the level.
- First touch of resistance with no lower high → WAIT (not SHORT).
- Price just pinned at resistance with flat structure → WAIT.
- Only fire SHORT when reversal STRUCTURE is confirmed, not on hope.

SHORT output uses same format as LONG but inverted:
Direction: SHORT
Entry: $price (the resistance level)
Stop: $price (above the resistance — where thesis breaks)
T1: $price (next support below)
T2: $price (second support)
```

**Delivery behavior**:
- SHORT alerts recorded as `alert_type = "ai_day_short"` (new type)
- Telegram message with Took/Skip/Exit buttons (same as LONG)
- Per-user filter: skip SHORT delivery if user already holds open SHORT (RealTrade.direction='SELL', status='open')
- RESISTANCE remains a text notice only (no buttons)

**Level dedup**: extend `_day_fired` set to include direction: `(symbol, "SHORT", level_bucket)` separate from `(symbol, "LONG", level_bucket)`.

### Change 3: Exit Management for Open Positions

**New concept**: Position-tracking scan runs alongside entry scan, per open RealTrade.

**Where**: new function `scan_open_positions(api_key)` in `analytics/ai_day_scanner.py`

**Flow**:
```
Every scan cycle (after entry scan):
  Fetch all open RealTrades (users watching symbol also in scan)
  For each open trade:
    Fetch latest bars for that symbol
    Build exit-focused prompt with: entry, stop, T1, T2, current bars
    Ask Claude Haiku:
      EXIT_NOW  → thesis broken, price below stop zone
      TAKE_PROFITS → approaching T1, tight volume
      HOLD → structure intact, no action
    If EXIT_NOW: send Telegram to that user only
      "AI EXIT — ETH-USD at $X. Reason: [1 sentence]"
      Button: "Exit Trade" (same as existing exit flow)
    If TAKE_PROFITS: send Telegram
      "AI ALERT — ETH-USD approaching T1 $X. Consider trimming."
      No button (user decides)
    If HOLD: no notification
```

**Rate limits**:
- Same `ai_scan_alerts_per_day` counter applies (free = 7/day includes exits)
- Dedup: don't repeat same exit advice for same position within 30 min cooldown
- Only fires once per reason per position (`EXIT_NOW` fires at most twice: warning + actual breach)

**Prompt structure** (separate from entry prompt):
```
You are managing an open position. Read the position data and current chart,
decide if the user should act.

POSITION:
Direction: LONG
Entry: $2186.37 (30 min ago)
Stop: $2175.89
T1: $2192.55
T2: $2205.47

CURRENT CHART:
[5-min bars, last 20]
Current price: $X
VWAP: $X
Volume trend: X

OUTPUT:
Status: EXIT_NOW / TAKE_PROFITS / HOLD
Reason: 1 sentence
Action: [specific — "exit at market", "trim 50% here", "keep holding, stop $X still valid"]

RULES:
- EXIT_NOW if:
  - Price broke below stop zone (within 0.2% of stop or lower)
  - Higher low structure broken (new lower low formed)
  - Volume collapsed and price flat at entry (thesis dying)
- TAKE_PROFITS if:
  - Price within 0.5% of T1
  - Rejection candle (long upper wick) at T1 zone
  - Volume spike on approach to T1
- HOLD otherwise (default — don't harass the user)
- Be conservative — only act on clear signals
```

## User Scenarios

### Scenario 1: Daily MA Bounce LONG
**Actor**: Day trader watching SPY
**Trigger**: SPY pulls back to 50 daily MA at $672
**AI flow**:
1. Scanner sees SPY $672.10, 50 daily MA at $672.00
2. Prompt includes `[DAILY MAs]` section
3. AI identifies: "SPY bouncing at 50 daily MA with higher low + volume"
4. Fires LONG at $672, stop $670.50 (below MA + structure), T1 $676 (prior hourly high)
**Expected**: User gets a LONG alert specifically citing daily MA bounce — higher conviction than session-level alerts

### Scenario 2: PDH Rejection SHORT
**Actor**: Day trader, ETH rejecting at PDH $2,330
**Trigger**: ETH rallies to PDH, prints a lower high on the retest
**AI flow**:
1. Scanner sees ETH at $2,327, PDH at $2,330
2. Current bar high $2,328 < prior swing high $2,332 → lower high confirmed
3. Volume 1.3x average on rejection bar
4. AI fires SHORT at $2,327, stop $2,335 (above PDH + structure), T1 $2,300 (VWAP), T2 $2,275 (session low)
**Expected**: User gets a full SHORT trade plan with Took/Skip/Exit buttons. Can take the short.

### Scenario 3: Exit Signal on Weakening Long
**Actor**: User holds open LONG on ETH from earlier scan
**Trigger**: 20 min after entry, ETH drifts back toward stop, volume dies
**AI flow**:
1. Position-scan runs on open RealTrade
2. Prompt: entry $2186, stop $2175, current $2178, volume collapsed
3. AI returns: `EXIT_NOW — volume dead, price drifting to stop, thesis weakening`
4. Telegram to that user only: "AI EXIT — ETH at $2178. Thesis weak, consider closing. [Exit Trade]"
**Expected**: User exits with small loss instead of getting stopped for full loss

### Scenario 4: Take Profits at T1
**Actor**: User holds open LONG on NVDA, price approaching T1 from below
**Trigger**: Scan cycle sees NVDA within 0.3% of T1, rejection wick forms
**AI flow**:
1. Position-scan prompt detects: price at $129.60, T1 at $130.00
2. Long upper wick on latest 5m bar — rejection at T1
3. AI returns: `TAKE_PROFITS — T1 rejection forming, trim here`
4. Telegram: "AI ALERT — NVDA at T1 with rejection. Consider trimming 50%."
**Expected**: User takes profits before price rolls over

## Functional Requirements

### FR-1: Daily MA Context in Entry Prompt
- [ ] `build_day_trade_prompt` includes `[DAILY MAs]` section with 20/50/100/200 values
- [ ] Prompt explicitly directs AI to prefer daily MA as entry level when price is within 0.3%
- [ ] `fetch_prior_day` confirmed to return `ma20`, `ma50`, `ma100`, `ma200` for both equities and crypto
- Acceptance: Unit test verifies prompt includes daily MA section with correct labels

### FR-2: SHORT Entries
- [ ] AI output enum extended: `LONG / SHORT / RESISTANCE / WAIT`
- [ ] Prompt includes SHORT confirmation rules (mirror of LONG)
- [ ] `parse_day_trade_response` handles SHORT direction
- [ ] New alert_type `ai_day_short` in scanner
- [ ] SHORT alerts recorded with direction="SHORT" and Telegram Took/Skip/Exit buttons
- [ ] Per-user position filter: skip SHORT delivery if user holds open SHORT RealTrade
- [ ] Level dedup: `(symbol, "SHORT", level_bucket)` distinct from LONG bucket
- [ ] RESISTANCE downgraded to notice-only (no entry/stop/target, text action)
- Acceptance: Unit tests for parse_day_trade_response with SHORT, and per-user filter symmetry

### FR-3: Exit Management Scan
- [ ] New function `scan_open_positions(api_key)` in `ai_day_scanner.py`
- [ ] Runs after entry scan each cycle
- [ ] Fetches open RealTrades across all users, groups by symbol to minimize AI calls
- [ ] One AI call per unique (symbol, position_direction) — generic exit read, not per-user
- [ ] Per-user delivery: fire exit alert to each holder of that position
- [ ] Output: `EXIT_NOW / TAKE_PROFITS / HOLD`
- [ ] New alert_type `ai_exit_signal` in scanner
- [ ] Telegram message format: reason + "Exit Trade" button (calls existing exit flow)
- [ ] Cooldown: don't repeat same status for same position within 30 min
- Acceptance: Unit tests for prompt generation, output parsing, cooldown logic

### FR-4: Rate Limit & Attribution
- [ ] Exit alerts count toward `ai_scan_alerts_per_day` (free tier = 7/day total across entries + exits)
- [ ] SHORT alerts count toward `ai_scan_alerts_per_day`
- [ ] Exit limit reached → same one-time daily notification as entry cap
- Acceptance: Usage count increments on exit/short delivery just like LONG delivery

### FR-5: Dashboard UI (web)
- [ ] Trade Review page: SHORT alerts show with red direction badge
- [ ] Trade Review filter: "Entry (LONG/SHORT)" vs "Exit" filter
- [ ] Dashboard Active Positions: add "AI signal" column showing latest signal (HOLD / EXIT_NOW / TAKE_PROFITS)
- Acceptance: SHORT alerts render correctly, exit signals visible in UI

## Open Questions

- Should exit signals run at a different cadence (e.g., every 2 min) than entry scan (every 5 min)?
  Faster exits = catch thesis breaks sooner, but more AI cost per user with open positions
- Should SHORT be gated by tier (e.g., free tier LONG-only)?
  Arg for: shorts are riskier, paying users get fuller tool
  Arg against: complexity, alienates free users from realistic market
  Recommendation: start with SHORT available to all, gate only if abuse
- Should EXIT_NOW auto-close the trade (optional "auto-exit" toggle per user)?
  No for launch — always human in the loop. Revisit after 90 days of data

## Out of Scope

- Swing trade exits (separate from day trade)
- Options position management
- Stop trailing (adjusting stop as price moves favorable)
- Multi-leg exit strategy (e.g., trim 1/3 at T1, 1/3 at T2, trail rest)
- Auto-exit execution (broker integration)

## Testing

- Unit tests for daily MA prompt injection
- Unit tests for SHORT direction parsing
- Unit tests for exit prompt + output parsing
- Integration test: full scan cycle with mock open positions + mock Claude responses
- E2E manual test: take a LONG, watch for exit signals during drawdown

## Implementation Phases

### Phase 1 — Daily MAs (Quick Win)
Small prompt change, immediate impact. No new alert types.
Acceptance: Next scan cycle references daily MAs, LONG conviction improves on MA bounces.

### Phase 2 — SHORT Entries
Larger change but well-defined. Mirrors LONG code paths.
Acceptance: First SHORT signal fires in production; Telegram delivery correct.

### Phase 3 — Exit Management
Most complex — new scan loop, new prompt, new alert type, per-user delivery logic.
Acceptance: Exit signals fire on open positions; users report value in the alerts.

## Related

- `analytics/ai_day_scanner.py` — core scanner
- `api/app/models/paper_trade.py` — RealTrade model (direction, status)
- `tickets/ai-scan-rate-limit-persistence.md` — rate limit counters (needed before Phase 3 for mid-day deploys)
- `tickets/deprecate-rule-based-alerting.md` — rule engine retirement (this spec is what replaces it)
- Spec 28 — Platform rebrand (AI-first positioning)
