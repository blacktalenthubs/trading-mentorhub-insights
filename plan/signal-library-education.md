# Signal Library — Education-First Trading Patterns

> **Status:** Ready for review
> **Goal:** Free educational content that teaches chart structure, drives adoption, reduces churn

---

## Problem Statement

Traders subscribe to signal services that say "buy NVDA now" — but never learn WHY. When the service stops, they're back to square one. TradeCoPilot's edge is education through execution: every alert teaches a pattern. The Signal Library makes this explicit.

**Why it matters:**
- Free content drives SEO ("what is a prior day low reclaim" → Google → landing page)
- Free users learn patterns → want live alerts → upgrade to Pro
- Users who understand WHY stay longer (reduced churn)
- Radical transparency: show per-pattern win rates from our actual track record

---

## Solution Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Landing Page │────▶│ /learn      │────▶│ /learn/:id  │
│ "Learn"  nav │     │ Category    │     │ Pattern     │
│              │     │ Grid        │     │ Detail      │
└─────────────┘     └─────────────┘     └─────────────┘
                          │                    │
                    ┌─────▼──────┐      ┌──────▼──────┐
                    │ API:       │      │ API:        │
                    │ /learn/    │      │ /learn/:id  │
                    │ categories │      │ stats +     │
                    │ + stats    │      │ examples    │
                    └────────────┘      └─────────────┘
```

### Access: All tiers (public — no auth required for SEO)

---

## 8 Category Pages (96 alert types total)

| Category | # Types | Key Patterns | What It Teaches | Difficulty |
|----------|---------|-------------|-----------------|------------|
| **Entry Signals** | 41 | MA/EMA bounce (20/50/100/200), PDL reclaim, double bottom, fib bounce, VWAP reclaim, planned level touch | Support levels, MAs as dynamic S/R, how institutions defend levels | Beginner |
| **Breakout Signals** | 11 | PDH breakout, inside day breakout, consolidation breakout, ORB, gap & go | Volume confirmation, prior day levels, range expansion, momentum | Intermediate |
| **Short Signals** | 13 | EMA rejection, double top, hourly resistance rejection, VWAP loss, failed breakout | Resistance, failed breakouts, when bulls lose control | Intermediate |
| **Exit Alerts** | 7 | Target 1/2 hit, stop loss, auto stop, trailing stop | Position management, partial profits, risk discipline | Beginner |
| **Resistance Warnings** | 10 | PDH rejection, MA/EMA resistance, weekly/monthly high resistance | Knowing when NOT to buy — the #1 beginner mistake | Beginner |
| **Support Warnings** | 7 | Support breakdown, PDL/weekly/monthly low breaks | When structure fails, when to cut losses and step aside | Beginner |
| **Swing Trade** | 13 | Multi-day double bottom, RSI divergence, MACD crossover, bull flag, EMA crossover | Multi-timeframe analysis, patience, larger moves over days | Advanced |
| **Informational** | 7 | Inside day forming, consolidation notice, first hour summary, gap fill | Reading market context BEFORE signals fire | Beginner |

---

## Each Category Page Contains

### 1. Overview (static content)
- What is this pattern family?
- Why does it work? (market structure explanation)
- When does it fail? (invalidation conditions)
- Difficulty level (beginner / intermediate / advanced)

### 2. Live Stats (from DB — refreshed daily)
- Win rate (target hits / total completed)
- Average R:R
- Total signals fired (last 90 days)
- Best performing symbol for this pattern

### 3. Real Example (from alert history)
- Actual alert that fired with entry/stop/T1/T2
- What happened (target hit? stopped out?)
- Mini chart showing the setup (OHLCV + levels)

### 4. CTA
- "Want these alerts live? Start Free Trial"
- Link to register → sets up watchlist → alerts flow

---

## Implementation Plan

### Files to Add

| File | Purpose |
|------|---------|
| `web/src/pages/LearnPage.tsx` | Category grid (the /learn index page) |
| `web/src/pages/LearnDetailPage.tsx` | Individual category deep-dive |
| `api/app/routers/learn.py` | API endpoints for categories + stats + examples |
| `api/app/services/pattern_stats.py` | Compute per-category win rates from alerts table |

### Files to Modify

| File | Change |
|------|--------|
| `web/src/App.tsx` | Add /learn and /learn/:id routes (public, no auth) |
| `web/src/pages/LandingPage.tsx` | Add "Learn" link in nav |

### API Endpoints

**Existing (reuse):**
```
GET /api/v1/intel/alert-win-rates?days=90
  → Already returns per-alert-type and per-symbol win rates
  → Uses (symbol, session_date) grouping to match entries → outcomes
  → Located: api/app/routers/intel.py + analytics/intel_hub.py
```

**New:**
```
GET /api/v1/learn/categories
  → List all 8 categories with aggregated stats (rolls up win-rate endpoint data)
  → Response: [{ id, name, description, difficulty, pattern_count, win_rate, avg_rr, signal_count_90d }]
  → Public (no auth required)

GET /api/v1/learn/:category_id
  → Category detail: educational content + alert types + stats + real example
  → Response: { id, name, difficulty, overview, why_it_works, when_it_fails,
                alert_types: [...], stats: {...}, example: AlertResponse | null }
  → Public (no auth required)
```

### Data: Pattern Stats Service

```python
# api/app/services/pattern_stats.py

def get_category_stats(category_id: str, days: int = 90) -> dict:
    """Aggregate win rates from existing intel_hub.get_alert_win_rates().
    
    Groups alert-type-level stats by category using ALERT_TYPE_TO_CATEGORY mapping.
    Reuses the same (symbol, session_date) outcome matching logic.
    """
```

### Content: Static educational copy

```python
# api/app/data/learn_content.py

CATEGORY_CONTENT = {
    "entry_signals": {
        "overview": "Entry signals fire when price bounces off a support level...",
        "why_it_works": "Moving averages act as dynamic support because...",
        "when_it_fails": "In strong downtrends, bounces get sold into...",
        "pro_tips": ["Wait for volume confirmation", "Check SPY regime first"],
    },
    ...
}
```

### Content: Static educational copy per category

Stored as a Python dict or JSON file — not in DB. This is editorial content:
- Pattern explanation (2-3 paragraphs)
- How to read it on a chart
- When it fails
- Pro tips

---

## E2E Validation

1. Visit `/learn` as unauthenticated user → see 8 category cards with live win rates
2. Click a category → see full explanation + real example + stats
3. Click CTA → redirected to `/register`
4. Google can crawl `/learn` and `/learn/:category_id` (no auth wall)

---

## Out of Scope (V1)

- Interactive chart replay (future — requires historical OHLCV loading + animation)
- User-contributed examples or comments
- Video content
- Per-alert-type pages (V1 is per-category, V2 can go granular)
- Personalized "your win rate for this pattern" (requires auth, Pro feature)

---

## Test Plan

- [ ] `/learn` page renders 8 categories with stats
- [ ] `/learn/:id` page renders detail with example
- [ ] Stats are computed correctly from alerts table
- [ ] Pages are accessible without auth
- [ ] CTA links to register page
- [ ] Mobile responsive
