# Spec 13 — Tier Enforcement & Trial System

## Problem Statement

**What:** Users register as Free and get unlimited access to everything. No trial expiration, no feature gating, no usage limits. Premium tier is half-implemented (billing maps it but `require_pro` blocks premium users). Free users see all alerts, all history, unlimited AI coach queries.

**Why:** Without enforcement, there's no reason to upgrade. Users need to *taste* the value during a short trial, then hit limits that make the upgrade decision obvious. This is the #1 revenue blocker.

**What success looks like:**
- Free users get 3-day Pro trial, then hit clear limits with upgrade CTAs
- Pro/Premium users get differentiated experiences
- Every locked feature shows what they're missing (visible but locked)
- Usage tracking enforced server-side (can't bypass via API)

---

## Current State (Broken)

### What Exists
| Component | Status | Issue |
|-----------|--------|-------|
| `Subscription` model | ✅ Has `tier`, `status`, `current_period_end` | No `trial_ends_at` field |
| `get_user_tier()` | ✅ Checks subscription | Returns "free" if missing |
| `require_pro()` | ❌ Checks `!= "pro"` | **Blocks premium users too** |
| Watchlist limit | ✅ Free = 5 | Works, but should be 3 |
| AI Coach | ❌ `require_pro` only | No daily query limit |
| Alert history | ❌ No tier check | Free sees everything |
| Monitor polling | ✅ Pro-only | Free gets no alerts (correct) |
| Usage tracking | ✅ DB table exists | `get_daily_usage()` / `increment_daily_usage()` exist but unused in V2 |
| Billing (Square) | ✅ Subscribe/cancel/webhook | Maps pro + premium correctly |
| Frontend User type | ❌ Uses "elite" | Should be "premium" |

### Critical Bug
```python
# api/app/dependencies.py line 54
if get_user_tier(user) != "pro":  # ← BLOCKS premium users!
    raise HTTPException(403, "Pro subscription required")
```

---

## Tier Definitions

### Feature Matrix

| Feature | Free (post-trial) | Pro $29/mo | Premium $79/mo |
|---------|-------------------|------------|----------------|
| **Watchlist symbols** | 3 | 10 | 25 |
| **AI Coach queries** | 2/day | 20/day | Unlimited |
| **Alerts in app** | Last 3 (rest blurred) | Full session | Full session |
| **Alert history** | Today only | 30 days | Full history |
| **Telegram alerts** | ❌ (visible, locked) | ✅ Real-time | ✅ Real-time |
| **Chart Replay** | 1/day | Unlimited | Unlimited |
| **Pre-trade Checklist** | 👁 Visible, locked | ✅ Interactive | ✅ Interactive |
| **Daily EOD Review** | 👁 Visible, locked | ✅ Telegram | ✅ Telegram |
| **Weekly Review** | 👁 Visible, locked | ❌ | ✅ Telegram |
| **Pre-market Brief** | 👁 Visible, locked | ✅ Telegram | ✅ Telegram |
| **Performance Analytics** | 👁 Visible, locked | ✅ Full | ✅ Full |
| **Signal Library** | ✅ Public | ✅ Public | ✅ Public |
| **Paper Trading** | 👁 Visible, locked | 👁 Visible, locked | ✅ Full |
| **Backtesting** | 👁 Visible, locked | 👁 Visible, locked | ✅ Full |

### Trial System
- **Duration:** 3 days from registration
- **Trial tier:** Pro-level access (full alerts, AI coach, analytics)
- **Expiration:** `trial_ends_at` field on Subscription
- **Post-trial:** Downgraded to Free limits automatically
- **Nudges:**
  - Day 1: "Welcome! You have 3 days of Pro access"
  - Day 2: "Trial ends tomorrow — here's what you'll lose"
  - Day 3 (expired): Limits active, upgrade CTA on every locked feature

### Tier Hierarchy
```
free (0) < pro (1) < premium (2) < admin (99)
```

---

## Solution Architecture

```
┌──────────────┐       ┌──────────────────┐       ┌──────────────┐
│ React App    │──────▶│ FastAPI Backend   │──────▶│ Postgres DB  │
│              │       │                  │       │              │
│ tier in auth │       │ TierGate middleware│      │ subscriptions│
│ store        │       │ usage_limits tbl  │       │ usage_limits │
│              │       │ trial expiry check│       │              │
│ <UpgradeCTA/>│       │                  │       │              │
└──────────────┘       └──────────────────┘       └──────────────┘
```

### Data Flow — Feature Access Check
```
Request → get_current_user() → get_user_tier()
                                    │
                          ┌─────────▼──────────┐
                          │ Is trial active?    │
                          │ YES → return "pro"  │
                          │ NO  → return DB tier│
                          └─────────┬──────────┘
                                    │
                          ┌─────────▼──────────┐
                          │ require_tier("pro") │
                          │ tier >= required?   │
                          │ YES → proceed       │
                          │ NO  → 403 + upgrade │
                          └────────────────────┘
```

### Data Flow — Usage-Limited Feature (AI Coach)
```
Request → get_current_user() → get_user_tier()
                                    │
                          ┌─────────▼──────────┐
                          │ Get daily usage     │
                          │ count for feature   │
                          └─────────┬──────────┘
                                    │
                          ┌─────────▼──────────┐
                          │ count < tier_limit? │
                          │ YES → proceed,      │
                          │       increment     │
                          │ NO  → 429 + upgrade │
                          └────────────────────┘
```

---

## Implementation Plan

### Files to Modify

| File | Change |
|------|--------|
| `api/app/models/user.py` | Add `trial_ends_at` to Subscription |
| `api/app/dependencies.py` | Fix `require_pro` → `require_tier()`, add trial logic, add `check_usage_limit()` |
| `api/app/config.py` | Add `TIER_LIMITS` constants dict |
| `api/app/routers/intel.py` | Add usage counting to AI coach, tier gates on endpoints |
| `api/app/routers/alerts.py` | Add tier-based history limits |
| `api/app/routers/auth.py` | Set `trial_ends_at` on registration |
| `api/app/routers/billing.py` | Return trial info in status |
| `api/app/routers/watchlist.py` | Update limit from 5 → tier-based |
| `api/app/background/monitor.py` | Include premium users (not just pro) |
| `web/src/types/index.ts` | Fix User type: "elite" → "premium" |
| `web/src/stores/auth.ts` | Add trial state |
| `web/src/components/UpgradeCTA.tsx` | **NEW** — reusable upgrade prompt component |
| `web/src/components/TierGate.tsx` | **NEW** — wrapper that shows lock overlay for insufficient tier |
| `web/src/pages/DashboardPage.tsx` | Gate alert history, show blurred alerts |
| `web/src/pages/BillingPage.tsx` | Show trial countdown, fix tier names |

### Files to Add

| File | Purpose |
|------|---------|
| `api/app/tier.py` | Tier constants, limit definitions, helper functions |
| `web/src/components/UpgradeCTA.tsx` | Upgrade prompt with feature teaser |
| `web/src/components/TierGate.tsx` | Lock overlay wrapper |
| `web/src/hooks/useTier.ts` | Hook for tier checks + usage remaining |

---

## Step-by-Step Implementation

### Phase 1 — Backend Foundation (Critical Path)

#### Step 1: Tier Constants (`api/app/tier.py`)
```python
"""Tier definitions and feature limits — single source of truth."""

from enum import IntEnum

class Tier(IntEnum):
    FREE = 0
    PRO = 1
    PREMIUM = 2
    ADMIN = 99

TIER_MAP = {"free": Tier.FREE, "pro": Tier.PRO, "premium": Tier.PREMIUM, "admin": Tier.ADMIN}

# Limits per tier — None = unlimited
TIER_LIMITS = {
    "free": {
        "watchlist_max": 3,
        "ai_queries_per_day": 2,
        "alert_history_days": 0,      # today only
        "visible_alerts": 3,          # rest blurred
        "chart_replay_per_day": 1,
        "telegram_alerts": False,
        "premarket_brief": False,
        "eod_review": False,
        "weekly_review": False,
        "performance_analytics": False,
        "pre_trade_check": False,
        "paper_trading": False,
        "backtesting": False,
    },
    "pro": {
        "watchlist_max": 10,
        "ai_queries_per_day": 20,
        "alert_history_days": 30,
        "visible_alerts": None,       # unlimited
        "chart_replay_per_day": None,
        "telegram_alerts": True,
        "premarket_brief": True,
        "eod_review": True,
        "weekly_review": False,
        "performance_analytics": True,
        "pre_trade_check": True,
        "paper_trading": False,
        "backtesting": False,
    },
    "premium": {
        "watchlist_max": 25,
        "ai_queries_per_day": None,   # unlimited
        "alert_history_days": None,   # full history
        "visible_alerts": None,
        "chart_replay_per_day": None,
        "telegram_alerts": True,
        "premarket_brief": True,
        "eod_review": True,
        "weekly_review": True,
        "performance_analytics": True,
        "pre_trade_check": True,
        "paper_trading": True,
        "backtesting": True,
    },
}

TRIAL_DURATION_DAYS = 3

def get_limits(tier: str) -> dict:
    """Return limits dict for a tier string."""
    return TIER_LIMITS.get(tier, TIER_LIMITS["free"])

def tier_rank(tier: str) -> int:
    """Return numeric rank for comparison."""
    return TIER_MAP.get(tier, Tier.FREE)

def has_access(user_tier: str, required_tier: str) -> bool:
    """Check if user_tier >= required_tier."""
    return tier_rank(user_tier) >= tier_rank(required_tier)
```

#### Step 2: Fix Dependencies (`api/app/dependencies.py`)
```python
# Replace require_pro with flexible require_tier

def get_user_tier(user: User) -> str:
    """Return effective tier — checks trial expiry."""
    if not user.subscription:
        return "free"
    sub = user.subscription
    # Trial check: if trial_ends_at exists and hasn't expired, grant pro
    if sub.tier == "free" and sub.trial_ends_at:
        from datetime import datetime, timezone
        if datetime.now(timezone.utc) < sub.trial_ends_at:
            return "pro"  # trial is active
    if sub.status == "active":
        return sub.tier
    return "free"

def require_tier(minimum: str):
    """Dependency factory — require user tier >= minimum."""
    async def _check(user: User = Depends(get_current_user)) -> User:
        from api.app.tier import has_access
        user_tier = get_user_tier(user)
        if not has_access(user_tier, minimum):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "upgrade_required",
                    "required_tier": minimum,
                    "current_tier": user_tier,
                    "message": f"{minimum.title()} subscription required",
                },
            )
        return user
    return _check

# Convenience aliases
require_pro = require_tier("pro")
require_premium = require_tier("premium")
```

#### Step 3: Usage Limit Checker
```python
# In api/app/dependencies.py or api/app/tier.py

async def check_usage_limit(user: User, feature: str, db: Session) -> int:
    """Check and increment daily usage. Raises 429 if over limit."""
    from api.app.tier import get_limits
    tier = get_user_tier(user)
    limits = get_limits(tier)
    max_uses = limits.get(f"{feature}_per_day")
    
    if max_uses is None:
        return -1  # unlimited
    
    # Count today's usage
    today = date.today().isoformat()
    row = db.execute(
        text("SELECT usage_count FROM usage_limits WHERE user_id=:uid AND feature=:f AND usage_date=:d"),
        {"uid": user.id, "f": feature, "d": today}
    ).fetchone()
    
    current = row[0] if row else 0
    remaining = max_uses - current
    
    if remaining <= 0:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "usage_limit_reached",
                "feature": feature,
                "limit": max_uses,
                "tier": tier,
                "message": f"Daily limit reached ({max_uses}/{feature}). Upgrade for more.",
            },
        )
    
    # Increment
    db.execute(text("""
        INSERT INTO usage_limits (user_id, feature, usage_date, usage_count)
        VALUES (:uid, :f, :d, 1)
        ON CONFLICT (user_id, feature, usage_date) DO UPDATE SET usage_count = usage_count + 1
    """), {"uid": user.id, "f": feature, "d": today})
    db.commit()
    
    return remaining - 1
```

#### Step 4: Add `trial_ends_at` to Subscription Model
```python
# api/app/models/user.py — add to Subscription
trial_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
```

#### Step 5: Set Trial on Registration
```python
# api/app/routers/auth.py — in register endpoint
from datetime import timedelta, timezone
trial_ends = datetime.now(timezone.utc) + timedelta(days=3)
subscription = Subscription(user_id=user.id, tier="free", status="active", trial_ends_at=trial_ends)
```

#### Step 6: AI Coach Usage Enforcement
```python
# api/app/routers/intel.py — in /coach endpoint
# Remove require_pro dependency, replace with:
@router.post("/coach")
async def coach(req: CoachRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    remaining = await check_usage_limit(user, "ai_queries", db)
    # ... existing coach logic ...
    # Include remaining in response headers
    response.headers["X-Usage-Remaining"] = str(remaining)
```

#### Step 7: Alert History Tier Gating
```python
# api/app/routers/alerts.py — in /history endpoint
from api.app.tier import get_limits
tier = get_user_tier(user)
limits = get_limits(tier)
history_days = limits["alert_history_days"]
if history_days is not None:
    cutoff = datetime.utcnow() - timedelta(days=history_days)
    query = query.where(Alert.created_at >= cutoff)
# Also limit visible count for free
visible = limits["visible_alerts"]
```

#### Step 8: Fix Monitor to Include Premium
```python
# api/app/background/monitor.py — change tier filter
pro_users = db.execute(
    select(User.id).join(Subscription).where(
        Subscription.tier.in_(["pro", "premium"]),
        Subscription.status == "active",
    )
).scalars().all()
```

---

### Phase 2 — Frontend Enforcement

#### Step 9: TierGate Component
```tsx
// web/src/components/TierGate.tsx
interface TierGateProps {
  require: "pro" | "premium";
  children: React.ReactNode;
  featureName: string;
}

export function TierGate({ require, children, featureName }: TierGateProps) {
  const tier = useAuth(s => s.user?.tier ?? "free");
  const hasAccess = tierRank(tier) >= tierRank(require);
  
  if (hasAccess) return <>{children}</>;
  
  return (
    <div className="relative">
      <div className="blur-sm pointer-events-none opacity-50">{children}</div>
      <UpgradeCTA feature={featureName} requiredTier={require} />
    </div>
  );
}
```

#### Step 10: UpgradeCTA Component
```tsx
// web/src/components/UpgradeCTA.tsx
export function UpgradeCTA({ feature, requiredTier }: { feature: string; requiredTier: string }) {
  return (
    <div className="absolute inset-0 flex items-center justify-center bg-black/60 rounded-lg">
      <div className="text-center p-6">
        <LockIcon className="mx-auto mb-2 text-amber-400" />
        <p className="text-white font-semibold">{feature}</p>
        <p className="text-gray-300 text-sm mb-3">
          Available on {requiredTier.charAt(0).toUpperCase() + requiredTier.slice(1)}
        </p>
        <Link to="/billing" className="bg-amber-500 text-black px-4 py-2 rounded font-semibold">
          Upgrade Now
        </Link>
      </div>
    </div>
  );
}
```

#### Step 11: Usage Hook
```tsx
// web/src/hooks/useTier.ts
export function useTier() {
  const user = useAuth(s => s.user);
  const tier = user?.tier ?? "free";
  
  return {
    tier,
    isPro: tierRank(tier) >= tierRank("pro"),
    isPremium: tierRank(tier) >= tierRank("premium"),
    isTrial: user?.trial_active ?? false,
    trialDaysLeft: user?.trial_days_left ?? 0,
  };
}
```

#### Step 12: Wrap Features with TierGate
```tsx
// Dashboard — blur alerts beyond 3 for free
{alerts.map((alert, i) => (
  <TierGate require="pro" featureName="Full Alert Feed" key={alert.id}
    bypass={i < 3}>
    <AlertRow alert={alert} />
  </TierGate>
))}

// Performance page
<TierGate require="pro" featureName="Performance Analytics">
  <PerformanceDashboard />
</TierGate>

// Paper Trading
<TierGate require="premium" featureName="Paper Trading">
  <PaperTradingPanel />
</TierGate>
```

---

### Phase 3 — Trial UX

#### Step 13: Trial Banner
```tsx
// Show at top of app when trial active
{isTrial && (
  <div className="bg-amber-500/20 border border-amber-500 text-amber-200 px-4 py-2 text-center text-sm">
    Pro trial — {trialDaysLeft} day{trialDaysLeft !== 1 ? 's' : ''} left
    <Link to="/billing" className="ml-2 underline font-semibold">Upgrade now</Link>
  </div>
)}
```

#### Step 14: Auth `/me` Response — Include Trial Info
```python
# api/app/routers/auth.py — GET /me
return {
    "id": user.id,
    "email": user.email,
    "display_name": user.display_name,
    "tier": get_user_tier(user),  # effective tier (pro during trial)
    "raw_tier": user.subscription.tier if user.subscription else "free",
    "trial_active": is_trial_active(user),
    "trial_days_left": trial_days_remaining(user),
}
```

#### Step 15: Billing Page — Trial Countdown
```
┌──────────────────────────────────────┐
│  Your Pro trial ends in 2 days       │
│                                      │
│  Keep everything you've unlocked:    │
│  ✓ 12 alerts received               │
│  ✓ 4 AI coach queries answered       │
│  ✓ Real-time Telegram delivery       │
│                                      │
│  [Upgrade to Pro — $29/mo]           │
└──────────────────────────────────────┘
```

---

## API Response Standards

### 403 — Tier Insufficient
```json
{
  "error": "upgrade_required",
  "required_tier": "pro",
  "current_tier": "free",
  "message": "Pro subscription required"
}
```

### 429 — Usage Limit Hit
```json
{
  "error": "usage_limit_reached",
  "feature": "ai_queries",
  "limit": 2,
  "used": 2,
  "remaining": 0,
  "tier": "free",
  "message": "Daily limit reached (2 AI queries). Upgrade for more."
}
```

### Response Headers (on limited features)
```
X-Usage-Remaining: 1
X-Usage-Limit: 2
X-Tier: free
X-Trial-Active: true
X-Trial-Days-Left: 2
```

---

## E2E Validation

### Test 1: New User Registration
1. Register new account
2. Verify `trial_ends_at` = now + 3 days
3. Verify effective tier = "pro" (trial active)
4. Verify full access to AI coach, alerts, analytics
5. Verify trial banner shows "3 days left"

### Test 2: Trial Expiry
1. Set `trial_ends_at` to past date (via DB)
2. Refresh page / call `/me`
3. Verify effective tier = "free"
4. Verify AI coach → 2 queries, then 429
5. Verify alerts blurred after 3
6. Verify locked features show upgrade CTA

### Test 3: Free → Pro Upgrade
1. Start as expired-trial free user
2. Subscribe via Square
3. Verify tier = "pro" immediately
4. Verify all Pro features unlocked
5. Verify usage limits lifted

### Test 4: Premium Features
1. Subscribe as premium
2. Verify paper trading + backtesting accessible
3. Verify weekly review enabled
4. Downgrade to pro → verify premium features locked

### Test 5: Usage Counting
1. As free user (post-trial), send 2 AI coach queries → succeed
2. Send 3rd query → 429 with upgrade message
3. As pro user, send 20 queries → succeed, 21st → 429
4. Next day → counter resets

---

## Out of Scope
- **Stripe integration** — we use Square only
- **Annual billing** — monthly only for now
- **Referral/promo codes** — future feature
- **Grandfathering existing users** — all current users get fresh trial (they're early adopters)
- **Usage analytics dashboard** — admin can see via DB queries for now
- **Email reminders** — trial expiry Telegram only for now

---

## Migration Plan for Existing Users

All 5 real users (from admin panel) need trial setup:
1. **bolof (Pro)** — already paying, no change
2. **Debo (adejumo.debo)** — set `trial_ends_at` = now + 3 days (fresh start)
3. **Debo (debobbt)** — set `trial_ends_at` = now + 3 days
4. **Olan Matthew** — set `trial_ends_at` = now + 3 days
5. **Olusegun** — set `trial_ends_at` = now + 3 days

Migration SQL:
```sql
-- Add trial_ends_at column
ALTER TABLE subscriptions ADD COLUMN trial_ends_at TIMESTAMP;

-- Give existing free users a 3-day trial from now
UPDATE subscriptions
SET trial_ends_at = NOW() + INTERVAL '3 days'
WHERE tier = 'free' AND status = 'active';

-- Pro users don't need trial
-- No change for tier='pro'
```
