# Proactive AI Scans — Spec 26

**Status**: Draft
**Created**: 2026-04-10
**Priority**: High — AI services are the biggest product value
**Depends on**: Spec 25 (AI actionable services), Spec 23 (alert engine)

## Problem

The AI Coach gives excellent actionable levels — but only when the user asks. By the time they open it and type a query, the move might be over. Meanwhile, the rule-based alert engine (78 rules) is complex, fragile, and keeps breaking.

## Proposal

Run automated AI scans alongside rule-based alerts. Both produce entries for the same watchlist symbols. Compare accuracy over time, then iterate.

**Not replacing rules** — running both in parallel to see which works best from the data.

## How It Works

```
Every 30 min during market hours:
  For each symbol on user's watchlist:
    1. Fetch latest OHLCV bars (5m + 1H)
    2. Fetch key levels (PDH, PDL, MAs, VWAP)
    3. Run AI analysis (same prompt as Coach, but automated)
    4. If AI identifies actionable entry → record as "ai_scan" alert
    5. Push to Signal Feed + optionally Telegram
```

### AI Scan Output (same as Coach)

```
CHART READ: SPY pulling back to 50MA support at $673.

ACTION:
Direction: LONG
Entry: $673.50 — 50MA support
Stop: $671.80 | T1: $677.08 | T2: $681.00
```

### Stored as Alert

```sql
INSERT INTO alerts (symbol, alert_type, direction, price, entry, stop, target_1, target_2, message, score)
VALUES ('SPY', 'ai_scan', 'BUY', 673.50, 673.50, 671.80, 677.08, 681.00,
        'AI: 50MA support bounce — pullback to $673', 80);
```

### Comparison with Rule-Based

Both systems produce alerts for the same symbols. After 1 week:

| Metric | Rule-Based Alerts | AI Scan Alerts |
|--------|------------------|----------------|
| Total fired | Count | Count |
| Accuracy (price at actual level) | % | % |
| Win rate (if Took) | % | % |
| False signals | Count | Count |
| Missed setups | Count | Count |

This data tells us which approach to invest in.

## Architecture

```
┌────────────────────┐     ┌────────────────────┐
│  Rule-Based Engine │     │  AI Scan Engine     │
│  (evaluate_rules)  │     │  (ai_scan_cycle)    │
│  78 rules          │     │  Coach prompt       │
│  Fires per bar     │     │  Fires every 30 min │
└────────┬───────────┘     └────────┬────────────┘
         │                          │
         └──────────┬───────────────┘
                    │
              ┌─────▼─────┐
              │  alerts DB │
              │  (unified) │
              └─────┬──────┘
                    │
         ┌──────────┼──────────┐
         │          │          │
    ┌────▼───┐ ┌───▼────┐ ┌──▼──────┐
    │Signal  │ │Telegram│ │Analytics│
    │Feed    │ │        │ │(compare)│
    └────────┘ └────────┘ └─────────┘
```

## Scan Frequency

| Market Phase | Frequency | Reason |
|-------------|-----------|--------|
| Pre-market (8:30-9:30 AM) | Once at 9:00 AM | Pre-market levels for the day |
| Opening range (9:30-10:00) | Every 15 min | Fast moves, need quick reads |
| Core session (10:00-3:00) | Every 30 min | Standard monitoring |
| Power hour (3:00-4:00) | Every 15 min | EOD setups |
| After hours | None | No action needed |

## Cost Estimate

| Component | Model | Calls/Day | Cost/Day |
|-----------|-------|-----------|----------|
| AI scan per symbol | Haiku | 10 symbols x 16 scans = 160 | ~$0.15 |
| With Sonnet (Pro users) | Sonnet | 160 | ~$1.50 |

At scale (100 users, 10 symbols each): $15-150/day depending on model tier.

## What AI Sees (Context per Scan)

Same context as Coach, but automated:
- Last 20 OHLCV bars (5m for intraday, 1H for swing)
- Key levels: PDH, PDL, MAs (20/50/100/200), VWAP
- Weekly high/low
- RSI14
- Current price vs all levels

**NOT included** (to keep it fast/cheap):
- User positions (AI scan is market-level, not user-level)
- Historical alerts
- Paper trading data

## Signal Feed Integration

AI scan alerts show in the same Signal Feed as rule-based alerts:

```
SPY  [AI SCAN]  LONG  10:30 AM
  Entry $673.50 — 50MA support
  Stop $671.80 | T1 $677.08

SPY  [BUY]  LONG  10:32 AM
  Entry $673.54 — MA bounce 50
  Stop $672.19 | T1 $677.08
```

Users see both side by side. Over time, they'll trust whichever is more accurate.

## Telegram Format

```
AI SCAN — SPY $673.50
Direction: LONG
Entry: $673.50 — 50MA support
Stop: $671.80 | T1: $677.08
```

Same clean format as current alerts. Tagged "AI SCAN" so users know the source.

## Implementation Phases

### Phase 1: Backend Scan Job (MVP)
- New scheduled job in worker: `ai_scan_cycle()` every 30 min
- For each user's watchlist symbols: fetch bars, build context, call Coach prompt
- Parse AI output → create alert record with `alert_type = "ai_scan"`
- Record to DB (same alerts table, new type)

### Phase 2: Signal Feed Display
- Show AI scan alerts in Signal Feed with "AI SCAN" badge
- Different color from rule-based alerts (purple vs green/orange)
- Same "Took It" / "Skip" buttons

### Phase 3: Telegram Delivery
- Send AI scan alerts to Telegram (opt-in per user)
- Clean format matching current alerts

### Phase 4: Comparison Dashboard
- Side-by-side: rule-based vs AI scan alerts per symbol per day
- Win rate, accuracy, false signal rate
- Data-driven decision on which to invest in

## What This Is NOT

- NOT replacing the alert engine — running alongside
- NOT real-time (every 30 min, not every 5 min bar)
- NOT per-user customized (same scan for all users watching same symbol)
- NOT expensive (Haiku for free tier, ~$0.15/day)

## Success Criteria

After 1 week of parallel operation:
- [ ] AI scan fires for every watchlist symbol on schedule
- [ ] Entries are at key levels (not current price)
- [ ] Comparison data available in dashboard
- [ ] Users can see both alert sources in Signal Feed
- [ ] Cost stays under $0.50/day for Haiku tier
