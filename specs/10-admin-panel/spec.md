# Feature Specification: Admin Panel

**Status**: Spec Complete
**Created**: 2026-04-05
**Priority**: Medium — needed before marketing push

---

## Overview

Admin dashboard for monitoring users, subscriptions, alerts, and platform health. Accessible only to admin users.

---

## Pages

### 1. User Management (`/admin/users`)
- Table: email, display name, tier, status, Telegram linked, watchlist count, alert count, signup date
- Search/filter by email, tier
- Click user → detail view with their watchlist, recent alerts, trade history
- Actions: upgrade/downgrade tier, reset password, disable account

### 2. Platform Stats (`/admin`)
- Cards: total users, pro users, free users, Telegram linked
- Charts: signups over time (daily), alerts per day, active users (who logged in last 7 days)
- Revenue: MRR (monthly recurring revenue) from Square subscriptions

### 3. Alert Monitor (`/admin/alerts`)
- Live view of recent alerts across all users
- Filter by symbol, alert type, direction
- Alert volume chart (per hour, per day)
- Monitor health: last poll time, poll duration, error count

### 4. Analytics (`/admin/analytics`)
- Traffic: page views, unique visitors (requires Google Analytics or Plausible)
- Conversion funnel: landing page → register → onboarding → first alert → subscription
- Retention: DAU/WAU/MAU, alert engagement rate (took/skip ratio)

---

## API Endpoints (Already Built)

| Endpoint | What |
|----------|------|
| `GET /admin/users` | List all users with stats |
| `GET /admin/stats` | Platform-wide counts |

## API Endpoints (Needed)

| Endpoint | What |
|----------|------|
| `GET /admin/users/:id` | Single user detail |
| `PATCH /admin/users/:id` | Update tier, status |
| `GET /admin/alerts/recent` | Recent alerts across all users |
| `GET /admin/alerts/volume` | Alert count by hour/day |
| `GET /admin/health` | Monitor status, last poll, errors |

---

## Analytics Integration

### Option A: Plausible (Privacy-First)
- Self-hosted or cloud ($9/mo)
- No cookies, GDPR-compliant
- Simple script tag in index.html
- Dashboard at plausible.io

### Option B: Google Analytics 4
- Free
- Full funnel tracking
- More complex setup
- Requires cookie consent banner

### Recommendation: Start with Plausible — simple, privacy-first, and gives you the basics (page views, referrers, countries). Add GA4 later if you need deeper funnel analysis.

---

## Implementation Priority

```
Phase 1 (now): Admin API endpoints (DONE)
Phase 2 (next week): Simple admin React page with user table
Phase 3 (later): Charts, analytics integration, alert monitor
```

---

## Acceptance Criteria

- [ ] Admin can see all registered users with tier and engagement stats
- [ ] Admin can upgrade/downgrade user tiers
- [ ] Admin can see platform-wide stats (users, alerts, revenue)
- [ ] Traffic analytics integrated (Plausible or GA4)
- [ ] Admin panel accessible only to admin emails
