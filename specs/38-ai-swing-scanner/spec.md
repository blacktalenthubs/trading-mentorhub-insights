# Spec 38 — AI Swing Scanner

**Status:** Draft
**Created:** 2026-04-13
**Related:** Spec 34 (AI day scans), Spec 35 (auto paper trading), Spec 36 (user alert prefs)

---

## Problem

The AI day scanner (spec 34) operates on 5-minute bars with a ~same-session horizon. It misses a different, equally valuable signal class: **multi-day swing setups** driven by daily/weekly levels and RSI extremes. Users asking "is AAPL a buy here?" on a 200MA test + RSI 28 daily get nothing from the day scanner — that's not its timeframe.

Rule engine had partial swing coverage (MA touch rules) but we deprecated it. We need an **AI swing scanner** that mirrors the day scanner's architecture but operates on daily/weekly data.

---

## Goals

1. Fire LONG/SHORT swing alerts at durable key levels: 100/200 daily MA, weekly 20/50 MA, prior-month high/low, 52w extremes, RSI oversold/overbought.
2. Independent pipeline — own scanner, own prompt, own cadence (2x/day), own alert_type, own tier limits, own public track record.
3. Reuse the **conviction ladder** philosophy from day scanner (spec 37 prompt change): at a key level, prefer firing LOW over WAIT.
4. Reuse `AIAutoTrade` + `/track-record` public audit infrastructure — tag with `timeframe='swing'`.

---

## Non-Goals

- Not replacing the day scanner — both run in parallel.
- Not real-time intraday monitoring — swing alerts are eval'd on daily close for fills/exits.
- Not options / LEAPs signals (future spec).
- Not backtesting historical performance (Phase 4, separate spec).

---

## Architecture

```
┌─────────────────┐   2x/day    ┌──────────────────────┐
│ APScheduler     │─────────────▶│ ai_swing_scan cycle  │
│ cron 13:30 UTC  │              │ (pre-mkt + post-close)│
│ cron 20:30 UTC  │              └──────────┬───────────┘
└─────────────────┘                         │
                                            ▼
                             ┌──────────────────────────┐
                             │ For each big-cap symbol:  │
                             │ 1. Fetch daily + weekly   │
                             │ 2. Compute MAs, RSI, pivots│
                             │ 3. Ask Claude Haiku       │
                             │ 4. Parse → LONG/SHORT/WAIT│
                             └──────────┬───────────────┘
                                        │
                   ┌────────────────────┼────────────────────┐
                   ▼                    ▼                    ▼
           ┌──────────────┐   ┌──────────────┐    ┌──────────────┐
           │ alerts table │   │ ai_auto_trades│   │ Telegram push│
           │ (type:       │   │ (timeframe:   │    │ (per-user    │
           │  ai_swing_*) │   │  'swing')     │    │  preferences)│
           └──────────────┘   └──────────────┘    └──────────────┘

Exit eval: EOD job (cron 20:45 UTC) — close swing auto-trades on
  - T1/T2 hit on daily close
  - Stop hit on daily close
  - Time stop: 10 trading days elapsed
```

---

## Data Flow

### Per-symbol input to AI (swing context)

| Field | Example | Notes |
|---|---|---|
| last 60 daily bars | OHLCV | primary structure |
| last 26 weekly bars | OHLCV | weekly trend |
| daily RSI14 | 28.3 | oversold trigger |
| weekly RSI14 | 42.1 | trend confirmation |
| daily 20/50/100/200 MA | array | key levels |
| daily 20/50/100/200 EMA | array | key levels |
| weekly 20/50 MA | array | weekly S/R |
| prior month high/low | 2 floats | monthly pivot |
| 52-week high/low | 2 floats | extreme pivots |
| distance from each MA | % | proximity scoring |

### Trigger universe (levels that warrant firing)

| Trigger | Condition |
|---|---|
| 200MA test | price within 2% of 200 daily MA/EMA |
| 100MA test | price within 1.5% of 100 daily MA/EMA |
| Weekly support | price within 3% of weekly 20 or 50 MA |
| Monthly pivot | price within 2% of prior-month high/low |
| RSI oversold | daily RSI14 < 30 |
| RSI overbought | daily RSI14 > 70 *and* near resistance |
| 52w low bounce | price within 5% of 52w low |
| 52w high rejection | price within 3% of 52w high |

---

## Conviction Ladder (swing)

Same philosophy as day scanner — fire at levels, scale conviction:

**LONG:**
- HIGH — at level + bullish candle (hammer/engulfing) on daily + RSI aligned
- MEDIUM — at level + RSI aligned, no confirming candle yet
- LOW — at level, no structure yet / flat candle

**SHORT:**
- HIGH — at resistance + bearish candle + RSI > 65
- MEDIUM — at resistance + RSI > 55
- LOW — at resistance, just arriving

**WAIT** only when price is mid-range (no level within trigger distance).

---

## Prompt Template (draft)

```
You are a swing trade analyst. Read the daily + weekly chart data below.
Is there a multi-day swing trade right now?

PHILOSOPHY: At a durable key level (200MA, 100MA, weekly MA, monthly pivot,
RSI extreme), prefer firing LONG/SHORT with conviction scaled to confirmation
strength over WAIT. Swing trades live 3-10 days; user decides if they take it.
The stop is trivial when entry is at structure.

KEY LEVELS THAT WARRANT FIRING:
- 200 Daily MA test (within 2%)
- 100 Daily MA test (within 1.5%)
- Weekly 20/50 MA (within 3%)
- Prior-month high/low (within 2%)
- 52-week low (within 5%) or 52-week high (within 3%)
- Daily RSI < 30 (oversold LONG) or > 70 at resistance (overbought SHORT)

LONG CONVICTION LADDER:
- HIGH: at level + bullish daily candle (hammer/engulfing) + RSI < 40
- MEDIUM: at level + RSI < 50, no confirming candle
- LOW: at level, just touching, no structure yet

SHORT CONVICTION LADDER:
- HIGH: at resistance + bearish daily candle + RSI > 65
- MEDIUM: at resistance + RSI > 55
- LOW: at resistance, just arriving

WAIT is only for price mid-range (>3% from every level, no RSI extreme).

OUTPUT (plain text):
SETUP: [e.g. 200MA bounce + RSI 28, 52w low reversal, weekly MA test]
Direction: LONG / SHORT / WAIT
Entry: $price (the level, not current)
Stop: $price (below key support for LONG; above for SHORT — use ~3-5% for swings)
T1: $price (next resistance above / support below — typically 5-10%)
T2: $price (second target — typically 10-20%)
Conviction: HIGH / MEDIUM / LOW
Timeframe: days (e.g. "3-7 days", "1-2 weeks")
Reason: 1 sentence — state level + RSI + candle structure

RULES:
- Be decisive. At a durable level, prefer LONG/SHORT LOW over WAIT.
- Entry = key level, not current price.
- MAXIMUM 70 WORDS.
```

---

## Universe (Phase 1 starter)

```python
SWING_UNIVERSE = [
    # Indexes
    "SPY", "QQQ", "IWM",
    # Mega-caps
    "AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMZN",
    # High-beta
    "AMD", "TSLA", "PLTR", "AVGO", "NFLX", "COIN",
]
```

15 symbols × 2 scans/day × ~$0.01/call ≈ **$0.30/day** Anthropic spend.

Future: user-configurable swing watchlist (Phase 2).

---

## Schema Changes

### `alerts` table
- New `alert_type` values: `ai_swing_long`, `ai_swing_short`
- No new columns — reuse existing `entry`, `stop`, `target_1`, `target_2`, `confidence`, `reason`

### `ai_auto_trades` table
- New column: `timeframe VARCHAR(20) DEFAULT 'day'` — values: `'day'` | `'swing'`
- New column: `time_stop_date DATE NULL` — swing trades auto-close after 10 trading days
- Migration via `migration_flags` one-shot in `main.py`

### `user_alert_preferences` (spec 36 settings)
- Reuse existing `min_conviction`, `alert_directions`
- New boolean: `swing_alerts_enabled` (default `true`)

### `tier_config`
- New key: `ai_swing_alerts_per_day` — free=1, pro=5, premium=unlimited

---

## Scheduler Jobs

| Job | Cron | Purpose |
|---|---|---|
| `_ai_swing_scan` (pre-mkt) | `13:30 UTC` (9:30 ET) | Scan universe + fire alerts before open |
| `_ai_swing_scan` (post-close) | `20:30 UTC` (16:30 ET) | Scan universe + fire alerts after close |
| `_ai_swing_exit_eval` | `20:45 UTC` | On daily close: T1/T2/stop/time-stop check for open swing trades |

Day-scan jobs (spec 34) keep running on 5-min interval — independent.

---

## Files to Add / Modify

| File | Change |
|---|---|
| `analytics/ai_swing_scanner.py` | **NEW** — scanner + prompt + parsing |
| `analytics/swing_data.py` | **NEW** — daily/weekly data fetch + RSI/MA calc |
| `api/app/models/auto_trade.py` | Add `timeframe`, `time_stop_date` columns |
| `api/app/models/user.py` | Add `swing_alerts_enabled` |
| `api/app/main.py` | Register 3 new APScheduler jobs + migration |
| `api/app/tier.py` | Add `ai_swing_alerts_per_day` per tier |
| `api/app/routers/auto_trades.py` | Split stats by timeframe; new `/swing-signals` endpoint |
| `web/src/pages/TrackRecordPage.tsx` | Add "Swing signals" section |
| `web/src/pages/SettingsPage.tsx` | Add swing toggle |

---

## Phased Delivery

### Phase 1 — Scanner + alerts (1 day)
- Build `ai_swing_scanner.py` with prompt, parsing, alert insert
- Wire scheduler jobs (pre-mkt + post-close)
- Telegram delivery gated by `swing_alerts_enabled` + tier limit
- No auto-trade yet

### Phase 2 — Swing auto-paper-trade (1 day)
- `AIAutoTrade` insert with `timeframe='swing'`, `time_stop_date=+10 days`
- EOD exit eval job: daily close vs T1/T2/stop/time-stop
- Separate Telegram "swing exit" messages

### Phase 3 — Public track record + settings UI (half day)
- `/track-record` split: "Day trades" / "Swing trades" tabs
- Separate stats: swing win rate, avg hold, avg R
- Settings toggle for swing alerts

### Phase 4 — Future (not in this spec)
- User-configurable swing watchlist
- Backtest harness on last 2 years
- Weekly digest email of swing setups

---

## Test Plan

### Unit tests
- `test_swing_prompt_build` — prompt contains all levels, RSI, MAs
- `test_swing_trigger_universe` — distance-% calcs for each level type
- `test_swing_parse_long` / `test_swing_parse_short` / `test_swing_parse_wait`
- `test_swing_time_stop` — 10-trading-day close logic

### Integration tests
- `test_swing_scan_end_to_end` — mock Anthropic, assert alert + auto-trade rows
- `test_swing_tier_rate_limit` — free user hits cap after 1 alert
- `test_swing_exit_eval_t1_hit` — daily bar closes above T1 → auto-close

### E2E manual
1. Railway: set `ALPACA_DISABLED=true`, deploy
2. Trigger scan manually: `POST /admin/trigger-swing-scan`
3. Confirm alerts appear for big caps currently at 200MA (SPY, QQQ likely candidates on pullback days)
4. Verify Telegram delivery respects `swing_alerts_enabled`
5. Next day: verify `/track-record` swing tab populated

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Daily AI scans cost too much | Cap at 15 symbols, 2x/day — $0.30/day ceiling; add env `SWING_SCAN_ENABLED` flag |
| Swing alerts bury day alerts | Separate Telegram tag/emoji; user can toggle off |
| Time-stop too aggressive / lax | Start with 10 trading days; review after 30 days |
| Overlap with day alerts on same symbol | Distinct `alert_type` prevents dedup collision; public page shows both |
| Yahoo daily data stale during market hours | Pre-market scan uses prior close (intentional); post-close scan uses today's close |

---

## Success Metrics (30 days after launch)

- ≥ 3 swing alerts/day fired on average
- Swing win rate ≥ 55% (measured at T1 or time-stop, whichever first)
- Avg R-multiple ≥ 1.0
- User opt-out rate on swing alerts < 20%
- Anthropic spend < $15/month

---

## Out of Scope

- Options / LEAP strategies — future spec
- Intraday re-evaluation of swing stops — EOD only
- User-custom swing watchlist — Phase 4
- Automated position sizing for swings — user decides from alert
- Integration with real brokerage — paper only (spec 35 territory)
