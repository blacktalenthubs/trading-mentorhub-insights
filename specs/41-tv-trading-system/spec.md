# Spec 41 — TradingView MCP-Driven Trading System

**Status**: Phase 1 complete (live), Phase 2 in progress (automation)
**Created**: 2026-04-26
**Owner**: User (mentorhub) + Claude

## Problem statement

Replace TradeSignal's Python rule engine with TradingView-native signal detection. Reduce all-day chart monitoring through automation, alert routing, and confluence-based decision filters.

The user's `rules.json` describes a level-based, multi-timeframe trading system (EMAs 8/21/50/100/200, SMAs 50/100/200, PDH/PDL, sweeps, volume profile, daily-bias filter). Building this in TradingView gives:

- Real-time visual signals (TV's native chart engine)
- Per-symbol independence (no shared poll loop bottleneck)
- Native alert delivery (TV → webhook → Telegram via existing infra)
- Reduced "stare at chart" time as confluence + auto-routing mature

## Architecture

```
┌──────────────────────┐                ┌─────────────────────────────┐
│ TradingView Desktop  │   webhook      │ FastAPI on Railway          │
│ (CDP enabled)        │  ────POST────▶ │ /tv/webhook                 │
│                      │   JSON         │  • schema validation        │
│ Indicators:          │                │  • bias compute (no gate)   │
│  • PDH/PDL           │                │  • dedup (level + window)   │
│  • Daily MA Bounce   │                │  • persist Alert row        │
│  • Daily EMA Bias    │                │  • notify_user → Telegram   │
│                      │                └─────────────────────────────┘
│ Alerts:              │
│  • "Any alert()      │                ┌─────────────────────────────┐
│     function call"   │                │ User's Telegram             │
│  • per symbol        │                └─────────────────────────────┘
└──────────────────────┘
```

## Current state (Phase 1 — DONE)

### Indicators built and committed

| Script | Purpose | State |
|---|---|---|
| `pine_scripts/prior_day_levels.pine` | 6 trigger conditions (BREAK+/RECLAIM/REJECT/BREAK-/SWEEP+/SWEEP-) on PDH and PDL with ATR-based stops, live alerts via `freq_once_per_bar` | Live on SPY 1H, ETHUSD 1H |
| `pine_scripts/daily_ema_bias.pine` | 0–7 confluence scorecard from 8/21/50/100/200 EMA stack + price vs 8 EMA / 50 SMA / 200 SMA. Visual badge per chart. | Committed; user pastes per `MONDAY_CHECKLIST.md` |
| `pine_scripts/daily_ma_bounce.pine` | 8 daily MAs (5 EMAs + 3 SMAs) with bounce/rejection detection. Visual-only V1 (no `alert()` calls yet). Uses `lookahead_on` for live values. | Live on multiple charts |

### Webhook + delivery

- Webhook URL: `https://worker-production-f56f.up.railway.app/tv/webhook`
- Schema: `TVWebhookPayload` in `api/app/routers/tv_webhook.py`
- HTF bias gate **removed** for TV signals (commit `3bda96b`) — TV is independent source, scanner-side gates don't apply
- Telegram delivery: per-user via `notify_user()` (commit `4f60d1d`)
- Test ID 33196: synthetic ETH SWEEP+ delivered successfully (validated end-to-end)

### Live TV alerts

| Symbol | Alert | Trigger | Webhook | Status |
|---|---|---|---|---|
| SPY 1H | "Any alert() function call" on Prior Day Levels | Once Per Bar | ✅ | Active |
| ETHUSD 1H | Same | Once Per Bar | ✅ | Active |

### Critical fixes shipped tonight

1. **ATR-based stops/targets** (commit `3bda96b`) — was `risk = close - pdh` which produced $0.01 risk on first-tick crossings, now `pdh ± atr14*0.3` for meaningful R:R
2. **HTF gate removal** (commit `3bda96b`) — counter-trend SHORTs now deliver to Telegram (would have caught the ETH pdh_rejection that was silenced earlier)
3. **lookahead_on for daily MAs** — was returning yesterday's stale values on intraday charts, now updates live
4. **Distinct colors per rule** + larger labels — visual disambiguation
5. **Sweep window 3 → 5 bars** — catches equity reversals that take longer than crypto

## Decisions made

| Decision | Rationale |
|---|---|
| Use `freq_once_per_bar` (live) instead of `freq_once_per_bar_close` | Day trading needs entry signal at level break, not 30-60 min later. Trade-off: 10–15% phantom-fire risk on bars that reverse. |
| HTF bias gate disabled for TV signals | Architectural — TV is an independent signal source from the legacy scanner. Mixing gates conflates two systems. |
| `lookahead_on` without `[1]` | Live charting needs current developing daily MA values, not yesterday's frozen close. |
| Daily MAs (not intraday MAs) | Stable horizontal-ish levels work like PDH/PDL. Intraday MAs would be noisy. |
| Visual-only for Daily MA Bounce V1 | Observation week before wiring alerts. Prevents Telegram spam during tuning. |
| Reuse existing `/tv/webhook` (not build new infra) | Already production-tested with HTF, dedup, per-user routing. Saved ~2 days of work. |

## Phase 2 — automation (NEXT, prioritized)

### P0: Confluence indicator

**Why**: User identified visually that PDH/PDL signals + Daily MA bounces *on same bar* = A+ setups. Currently they have to look at two indicators and mentally cross-reference. A composite indicator makes the high-conviction trade visually obvious (single bright marker = trade).

**Scope**:
- New Pine script `pine_scripts/confluence_signals.pine`
- Recomputes both PDH/PDL conditions and MA bounce conditions
- Fires ONLY when both align on same bar (within tolerance)
- Output: large diamond/star marker with full trade plan in webhook payload
- Rule names: `confluence_long`, `confluence_short`

**Effort**: ~45 min

### P1: Bulk TV alert creation across watchlist

**Why**: User has 8-symbol CORE watchlist (SPY, QQQ, NVDA, MSFT, META, AMD, TSLA, MSTR) + rotation watchlist (~17 more). Manual alert creation per symbol takes 30+ sec each. Need to scale to all symbols + future indicators.

**Scope**:
- Script that drives TV alert dialog via MCP (`ui_mouse_click`, `ui_evaluate`)
- Reads watchlist from `rules.json`
- For each symbol: switch chart → open alert dialog → fill condition + webhook + message → submit
- Idempotent: skip symbols that already have a matching alert (check `alert_list`)
- Reusable for future indicators by parameterizing the indicator name

**Effort**: 1–2 hours (UI automation has shown brittleness; might need fallback to JS-paste recipe)

### P2: Wick-sweep detection

**Why**: User identified a real gap — when price wicks below PDL and recovers within the same bar (single-bar sweep), the current logic misses it because both `pdl_break` and `pdl_reclaim` require closes on opposite sides of PDL. The MSFT example: wick to $413, close $415, never broke. Pure liquidity grab — highest-conviction reversal.

**Scope**:
- Add `pdl_wick_sweep` and `pdh_wick_sweep` to PDH/PDL Pine script
- Conditions: `low <= pdl AND close > pdl AND close > open AND low < pdl - mintick` (and inverse for SHORT)
- Visual: distinct marker from SWEEP+ composite (e.g., star vs diamond)
- New rule names in webhook payload

**Effort**: ~30 min

### P3: Smart bias-tagged alert delivery

**Why**: Gate is fully removed (Phase 1), but counter-trend signals still arrive in Telegram with no warning. User would benefit from `[ALIGNED]` or `[COUNTER]` prefix in message so they can filter at-a-glance without losing the signal entirely.

**Scope**:
- Modify `_dispatch_signal` in `tv_webhook.py` to inject bias-alignment tag into message
- Notifier formats `[ALIGNED]` (4H + 1H bias agree with signal direction) or `[COUNTER]` (one or both disagree)
- No filtering — all signals deliver, but visually distinguishable

**Effort**: ~30 min

### P4: Pre-market scanner digest

**Why**: User wants to reduce monitoring time. A 7:30 AM ET digest could pre-identify "today's compression candidates" — symbols showing the patterns from `rules.json` (price above 8 EMA, near PDH/PDL, low volatility setup) so user doesn't need to chart-scan all morning.

**Scope**:
- Python service (or scheduled Railway worker) running at 7:30 AM ET
- For each watchlist symbol: fetch yesterday's close, compute MA stack, compute distance to PDH/PDL, compute compression metric
- Score and rank
- Send Telegram digest: top 4 candidates with one-line setup descriptions
- Prevents "open chart, scan, decide" routine — replaces with curated list

**Effort**: 2–3 hours

### Backlog / nice-to-have

- **Telegram message format polish** (Bug 9 from earlier audit): Show "Suggested limit at level" guidance for Model B trades
- **Volume profile pillar** (originally Pillar 4): POC/VAH/VAL alongside PDH/PDL. Most useful on indices.
- **Alert template export/import**: Save TV alert config as JSON for fast onboarding to new symbols
- **Multi-account alert routing**: Per-symbol routing to different Telegram channels (CORE → primary, rotation → secondary)

## Open questions

| Question | Why it matters | When to decide |
|---|---|---|
| Should the confluence indicator wait for bar close, or fire live? | Live = early entry but phantom risk on rejection bars. Bar close = late but confirmed. | When building P0 |
| Where should the wick-sweep buffer live (Pine input vs hardcoded)? | Tunability vs simplicity | Building P2 |
| Should Daily MA Bounce add `alert()` calls in V2? | Observation week (this week) determines which MAs are tradeable vs noisy | After 1 week of live data |
| Should the HTF bias gate come back as a *configurable* filter (per-user opt-in)? | Some users may want gating; current full removal is a hard line | After Phase 2 stabilizes |
| Pre-market scanner: pure Python (separate service) or extend the existing FastAPI worker? | Deployment + maintenance complexity | When building P4 |

## Key insights captured during build

These came up tonight and should inform future work:

1. **Daily MAs viewed on intraday are stable, not noisy** — the user's intuition was correct. Intraday MAs (e.g., 1H 8 EMA on 1H chart) ARE noisy; daily MAs displayed on a 1H chart behave like extra PDH/PDL levels. This drove the design of `daily_ma_bounce.pine`.

2. **Confluence is the trade signal** — single-indicator triangles are noise; same-bar overlap of PDH/PDL signal + MA bounce is A+ setup. This justifies P0 confluence indicator.

3. **Compression near a level precedes resolution** — Wyckoff "spring" pattern. User identified this on multiple charts. Could become a P5 "compression detector" eventually.

4. **Wick sweeps are missed by close-based detection** — most common sweep variant on liquid intraday assets gets ignored by current PDH/PDL rules. P2 fixes this.

5. **TV's "Any alert() function call" lives in the operator dropdown** — not the indicator dropdown. Easy to miss. Important for any UI automation work.

6. **`request.security` with `lookahead_off` returns stale values intraday** — must use `lookahead_on` (without `[1]`) for live daily-MA-on-intraday display. `lookahead_off` only matters for backtesting.

## File reference

| Path | Purpose |
|---|---|
| `pine_scripts/prior_day_levels.pine` | PDH/PDL detector (live) |
| `pine_scripts/daily_ma_bounce.pine` | 8 daily MAs visual (live) |
| `pine_scripts/daily_ema_bias.pine` | Bias scorecard (paste tomorrow) |
| `pine_scripts/MONDAY_CHECKLIST.md` | Morning setup procedure |
| `api/app/routers/tv_webhook.py` | Webhook receiver + dispatcher |
| `alerting/notifier.py` | Telegram delivery (existing) |
| `rules.json` | User's trading rules + scorecard (drives the framework) |

## Recent commits (this branch + main)

- `c6b9da0` Merge feat/rule-base-phase5c-sma-ladder: PDH/PDL Pine + sweep composites + ATR stops + remove HTF gate from TV webhook
- `3bda96b` fix(tv): ATR-based stops + remove HTF gate from TV webhook
- `5914e9d` docs(pine): Monday morning checklist for PDH/PDL system deployment
- `774f5ee` feat(pine): PDH/PDL signals + sweep composites + daily EMA bias scorecard
- `70bb774` feat(pine): daily MA bounce/rejection indicator (V1, visual-only)

## Working session pattern

Tonight's iteration was: build → observe on real charts → user identifies issue → fix → reobserve. This worked exceptionally well because chart observation surfaces issues that pure logic review misses (e.g., wick-sweep blind spot, lookahead bug, confluence pattern).

For Phase 2 work: keep the same pattern. Build small, observe, iterate.
