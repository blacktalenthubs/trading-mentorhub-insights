# Feature Specification: Tier Gating — AI Features & Upgrade Flow

**Status**: Draft
**Created**: 2026-04-11
**Author**: Claude (via /speckit.specify)
**Priority**: Critical — free users consume AI resources with no revenue

## Problem

Free users get unlimited access to:
- AI scan alerts (every 5 min, Claude API calls)
- Telegram AI commands (/spy, /eth — Claude API calls)
- AI Coach queries (partially gated but easily bypassed)
- All Telegram alerts (no gate)

This costs money (Claude API) and gives no incentive to upgrade.

## Current Tier System

Infrastructure exists (`api/app/tier.py`, `api/app/dependencies.py`):
- `TIER_LIMITS` dict defines limits per tier
- `check_usage_limit()` tracks daily usage in `usage_limits` table
- `get_user_tier()` resolves user → tier
- Frontend handles 429 responses with upgrade button

### Current Limits (tier.py)

| Feature | Free | Pro | Premium |
|---------|------|-----|---------|
| watchlist_max | 3 | 10 | 25 |
| ai_queries_per_day | 2 | 20 | None |
| alert_history_days | 0 (today) | 30 | None |
| visible_alerts | 3 | None | None |
| chart_replay_per_day | 1 | None | None |
| telegram_alerts | False | True | True |
| premarket_brief | False | True | True |
| eod_review | False | True | True |
| performance_analytics | False | True | True |
| paper_trading | False | False | True |
| backtesting | False | False | True |

### What's NOT Gated (Should Be)

| Feature | Current | Should Be |
|---------|---------|-----------|
| AI scan alerts (Telegram) | Unlimited all tiers | Free: 3/day, Pro: unlimited |
| Telegram /spy commands | Unlimited | Free: 3/day, Pro: 50/day |
| AI scan feed (dashboard) | All visible | Free: last 3, rest blurred |
| AI Coach (V2 web) | 429 but inconsistent | Enforce consistently |

## Proposed Tier Limits

```python
TIER_LIMITS = {
    "free": {
        "watchlist_max": 5,
        "ai_queries_per_day": 3,           # AI Coach + Telegram commands combined
        "ai_scan_alerts_per_day": 3,       # NEW: AI scan LONG/RESISTANCE to Telegram
        "telegram_commands_per_day": 3,    # NEW: /spy, /eth, /btc commands
        "alert_history_days": 0,
        "visible_alerts": 5,
        "chart_replay_per_day": 1,
        "telegram_alerts": True,           # CHANGED: let free see alerts (they upgrade for more)
        "premarket_brief": False,
        "eod_review": False,
        "weekly_review": False,
        "performance_analytics": False,
        "paper_trading": False,
        "backtesting": False,
    },
    "pro": {
        "watchlist_max": 10,
        "ai_queries_per_day": 50,
        "ai_scan_alerts_per_day": None,    # Unlimited
        "telegram_commands_per_day": 50,
        "alert_history_days": 30,
        "visible_alerts": None,
        "chart_replay_per_day": None,
        "telegram_alerts": True,
        "premarket_brief": True,
        "eod_review": True,
        "weekly_review": False,
        "performance_analytics": True,
        "paper_trading": False,
        "backtesting": False,
    },
    "premium": {
        "watchlist_max": 25,
        "ai_queries_per_day": None,        # Unlimited
        "ai_scan_alerts_per_day": None,
        "telegram_commands_per_day": None,
        "alert_history_days": None,
        "visible_alerts": None,
        "chart_replay_per_day": None,
        "telegram_alerts": True,
        "premarket_brief": True,
        "eod_review": True,
        "weekly_review": True,
        "performance_analytics": True,
        "paper_trading": True,
        "backtesting": True,
    },
}
```

## User Interaction Flows

### Flow 1: Free User Hits AI Scan Alert Limit

```
[AI Scan fires LONG ETH — user's 4th alert today]

Telegram message:
  "📊 Daily AI scan limit reached (3/3).
   Upgrade to Pro for unlimited AI alerts.
   → tradesignalwithai.com/billing"

Dashboard (AI Scan tab):
  Shows first 3 AI scan alerts normally.
  4th+ alerts show blurred with lock icon:
  "🔒 Upgrade to see more AI scans → [Upgrade Plan]"
```

### Flow 2: Free User Types /spy in Telegram

```
First 3 commands: normal response (AI analysis)

4th command:
  "📊 Daily command limit reached (3/3).
   Upgrade to Pro for 50 commands/day.
   
   [Upgrade Plan → tradesignalwithai.com/billing]"
```

### Flow 3: Free User Opens AI Coach on Web

```
First 3 queries: normal response

4th query:
  Coach chat shows:
  "Daily limit reached (3 queries).
   [Upgrade Plan →]"
  
  Button links to /billing page.
```

### Flow 4: Free User Views AI Scan Tab

```
Tab shows:
  ┌─────────────────────────────┐
  │ ETH-USD  AI LONG  $2230    │ ← visible
  │ BTC-USD  AI LONG  $72564   │ ← visible  
  │ ETH-USD  WAIT    $2249    │ ← visible
  ├─────────────────────────────┤
  │ 🔒 4 more AI scans today   │
  │    Upgrade for full access  │
  │    [Upgrade Plan →]         │
  └─────────────────────────────┘
```

### Flow 5: Pro User — No Limits

```
All AI features work without interruption.
No limit messages. No blurred content.
Usage counter shown subtly: "47 AI queries remaining today"
```

## Implementation Points

### 1. AI Scan Alerts — Telegram Delivery Gate

**File**: `analytics/ai_day_scanner.py`
**Where**: Before `_send_telegram_to()` call
**Logic**:
```python
# Check if user has remaining AI scan alerts
from api.app.tier import get_limits
from db import get_user_tier, check_usage_limit

tier = get_user_tier(user_id)
limits = get_limits(tier)
max_scans = limits.get("ai_scan_alerts_per_day")

if max_scans is not None:
    remaining = check_and_increment("ai_scan_alert", user_id, max_scans)
    if remaining <= 0:
        # Send upgrade message instead of alert
        _send_telegram_to(
            "📊 Daily AI scan limit reached.\n"
            "Upgrade to Pro for unlimited alerts.\n"
            "→ tradesignalwithai.com/billing",
            user.telegram_chat_id
        )
        continue  # skip this alert
```

**Note**: Alert still records to DB (for analytics). Only Telegram delivery is gated.

### 2. Telegram Commands — Rate Limit

**File**: `scripts/telegram_bot.py`
**Where**: In `ai_symbol_command()` handler
**Logic**:
```python
# Check usage before calling Claude
tier = get_user_tier(user_id)
limits = get_limits(tier)
max_commands = limits.get("telegram_commands_per_day")

if max_commands is not None:
    remaining = check_and_increment("telegram_command", user_id, max_commands)
    if remaining <= 0:
        await update.message.reply_text(
            f"📊 Daily command limit reached ({max_commands}/{max_commands}).\n"
            f"Upgrade to Pro for {get_limits('pro')['telegram_commands_per_day']}/day.\n"
            f"→ tradesignalwithai.com/billing"
        )
        return
```

### 3. AI Coach — Already Gated (Verify)

**File**: `api/app/routers/intel.py`
**Where**: Coach endpoint already calls `check_usage_limit()`
**Verify**: Ensure V2 TradingPage coach hook handles 429 with upgrade button (already done).

### 4. AI Scan Tab — Blur Extra Alerts

**File**: `web/src/pages/TradingPageV2.tsx`
**Where**: `AIScanFeedTab` component
**Logic**:
```tsx
const tier = useUserTier();
const limit = tier === "free" ? 5 : null;

{aiAlerts.map((a, i) => {
  if (limit && i >= limit) {
    return (
      <div key={a.id} className="blur-sm opacity-50 relative">
        {/* blurred alert */}
        <div className="absolute inset-0 flex items-center justify-center">
          <Link to="/billing" className="bg-accent text-white px-3 py-1 rounded">
            Upgrade to see more
          </Link>
        </div>
      </div>
    );
  }
  return <NormalAlertCard alert={a} />;
})}
```

### 5. Upgrade Navigation — All Paths Lead to /billing

| Touchpoint | Message | CTA |
|-----------|---------|-----|
| AI scan Telegram limit | "Daily limit reached" | "→ tradesignalwithai.com/billing" |
| Telegram command limit | "3/3 commands used" | "→ tradesignalwithai.com/billing" |
| AI Coach web limit | "Daily limit reached" | [Upgrade Plan →] button to /billing |
| AI Scan tab blur | "Upgrade to see more" | [Upgrade Plan →] button to /billing |
| Signal Feed blur | "3 alerts visible" | [See all → Upgrade] link to /billing |
| Replay limit | "1 replay/day on free" | [Unlock replays →] to /billing |
| Top banner | "Free plan — limited features" | [See plans] link to /billing |

**Every limit message includes a direct path to /billing.** No dead ends.

### 6. Billing Page — Already Built

Square integration working. Pro $49/mo, Premium $99/mo. Card form loads.
User sees current tier, can upgrade/downgrade.

## Usage Tracking

All limits tracked in `usage_limits` table:

```sql
CREATE TABLE usage_limits (
    user_id INTEGER,
    feature VARCHAR(50),      -- 'ai_queries', 'telegram_command', 'ai_scan_alert', 'chart_replay'
    usage_date VARCHAR(10),   -- '2026-04-11'
    usage_count INTEGER,
    PRIMARY KEY (user_id, feature, usage_date)
);
```

Already exists. Just need to add new feature keys: `telegram_command`, `ai_scan_alert`.

## Free Tier Value — What They Get

Free isn't useless — it's a taste:
- 5 symbols on watchlist
- 3 AI Coach queries/day (enough to try it)
- 3 AI scan alerts/day (see the system work)
- 3 Telegram commands/day (/spy, /eth, /btc)
- 1 chart replay/day
- Today's alerts (5 visible)
- Full access to trading page + charts

**The upgrade moment**: When they hit a limit during market hours and want more. The AI scan catches a setup, they've used their 3 — "Upgrade to Pro for unlimited."

## Testing Checklist

- [ ] Free user gets exactly 3 AI scan alerts, then upgrade message on 4th
- [ ] Free user gets exactly 3 Telegram commands, then upgrade message on 4th
- [ ] Free user AI Coach shows upgrade after 3 queries (2 in current config → change to 3)
- [ ] Pro user gets no limits on AI features
- [ ] Premium user gets no limits on anything
- [ ] Upgrade message links to /billing
- [ ] /billing page loads, card form works, subscription creates
- [ ] After upgrade, limits immediately increase (no logout needed)
- [ ] AI scan tab blurs alerts beyond limit for free users
- [ ] Usage counter resets at midnight

## Scope

### In Scope
- Add `ai_scan_alerts_per_day` and `telegram_commands_per_day` to TIER_LIMITS
- Gate AI scan Telegram delivery for free users
- Gate Telegram /spy commands for free users
- Blur extra AI scans in dashboard for free users
- Upgrade messages at every limit with link to /billing
- Update free tier: watchlist 3→5, ai_queries 2→3, telegram_alerts True

### Out of Scope
- Changing pricing ($49/$99)
- Adding new tiers
- Metered billing (pay per query)
- API key access for developers
- Changing Pro/Premium limits
