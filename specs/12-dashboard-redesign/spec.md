# Feature Specification: Dashboard Redesign

**Status**: Ready for Implementation
**Created**: 2026-04-05
**Priority**: High — core user experience

---

## Problems with Current Dashboard

1. **Active Positions empty** — Telegram Took doesn't create real trades (V2 bot creates via V1 code, not V2 API)
2. **Watchlist Radar is useless** — duplicate of Trading page watchlist, takes prime real estate
3. **Today's Activity is flat** — 23 alerts in a grid, hard to review
4. **No per-pattern grouping** — can't see which patterns are winning/losing today
5. **No useful metrics** in the right panel

---

## New Dashboard Layout

```
┌──────────────────────────────────────────────────────────────┐
│ Header: Market Status | Session Stats | Open Trading        │
├──────────────────────────────┬───────────────────────────────┤
│                              │                               │
│  Active Positions (8 cols)   │  Session Intelligence (4 col) │
│  - Open trades with P&L     │  - Today's Win Rate            │
│  - Close button              │  - Took/Skipped/Open count    │
│                              │  - Best Pattern Today          │
│                              │  - P&L Today                  │
│                              │  - Account Risk Level          │
│                              │  - Quick Actions               │
├──────────────────────────────┴───────────────────────────────┤
│                                                              │
│  Today's Activity — Grouped by Symbol, Collapsible           │
│                                                              │
│  ▼ ETH-USD (14 alerts) — 3 took, 2 stopped, 9 info         │
│    ├─ ▼ session_low_double_bottom (3 alerts)                │
│    │    [alert] [alert] [alert]  [▶ Replay]                 │
│    ├─ ▼ ema_rejection_short (2 alerts)                      │
│    │    [alert] [alert]                                      │
│    └─ ▼ hourly_resistance_rejection (4 alerts)              │
│         [alert] [alert] [alert] [alert]                      │
│                                                              │
│  ▶ BTC-USD (9 alerts) — 2 took, 1 stopped, 6 info          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Changes Required

### 1. Replace Watchlist Radar → Session Intelligence Panel

| Metric | What it shows |
|--------|--------------|
| Today's Win Rate | Won / (Won + Lost) from today's outcomes |
| Took/Skipped | How many alerts you acted on vs passed |
| Best Pattern | Alert type with highest WR today |
| Session P&L | Sum of closed trade P&L today |
| Risk Level | How many open positions + exposure |
| Quick Actions | "Send Test Alert" / "Open Scanner" / "AI Coach" |

### 2. Fix Active Positions

**Root cause:** Telegram bot's `_handle_ack` creates trades via V1 `real_trade_store.py` which writes to the OLD DB path. The V2 API reads from Postgres via SQLAlchemy.

**Fix:** Make `_handle_ack` in `telegram_bot.py` create trades via the V2 API endpoint (`POST /real-trades/open`) instead of V1 store, OR make it write directly to Postgres via `db.get_db()`.

### 3. Group Today's Activity

**Level 1:** Group by symbol (ETH-USD, BTC-USD)
**Level 2:** Group by pattern within symbol (double_bottom, ema_rejection, etc.)
**Each group header shows:** symbol, alert count, took/skipped/open counts
**Collapsible:** Click symbol to expand/collapse
**Replay button:** On each pattern group, not each individual alert

### 4. Improve Alert Cards Within Groups

Each alert card should be minimal within a group:
```
03:51 PM  SHORT  hourly resistance rejection  TOOK  [▶]
03:42 PM  SELL   pdh rejection                       
03:39 PM  BUY    multi day double bottom      SKIPPED
```

Not the current full card — just a row within the group context.

---

## Implementation Priority

1. Fix Active Positions (Telegram ack → V2 trade) — CRITICAL
2. Replace Watchlist Radar with Session Intelligence — HIGH
3. Collapsible symbol groups with pattern sub-groups — HIGH
4. Compact alert rows within groups — MEDIUM

---

## Acceptance Criteria

- [ ] Telegram "Took It" creates a visible position in Active Positions
- [ ] Right panel shows useful session intelligence (WR, P&L, counts)
- [ ] Activity grouped by symbol with expand/collapse
- [ ] Pattern sub-groups within each symbol
- [ ] Replay button accessible per pattern group
- [ ] Positions show live P&L and Close button
