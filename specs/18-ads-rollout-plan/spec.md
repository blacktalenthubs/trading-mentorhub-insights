# Feature Specification: 1-Week Ad Campaign Rollout + Smoke Tests

**Status**: Draft
**Created**: 2026-04-07
**Author**: AI-assisted
**Target Launch**: Week of 2026-04-14 (Monday)

## Overview

Run a 1-week paid ad campaign to drive traffic to TradeCoPilot, measure conversion data, and validate product-market fit. Before spending ad dollars, run smoke tests to ensure the entire user journey works end-to-end: landing page → registration → trial → Telegram link → alerts → upgrade.

## Problem Statement

TradeCoPilot has 15 users (10 real, 5 test), 14 active trials, and $49 MRR. The platform is feature-rich (11 AI services, options flow, sector rotation, swing trades) but has zero paid acquisition data. Key unknowns:

1. **What does a user cost?** — No CPA (cost per acquisition) data
2. **Does the funnel convert?** — Registration → trial → paid subscription hasn't been tested at scale
3. **Which message resonates?** — Is it "AI alerts", "options flow", "trade coaching", or "structured trade plans"?
4. **Does the product retain?** — 3-day trial → will users upgrade or churn?

Running ads for 1 week with a small budget ($200-500) answers these questions with real data before scaling.

## Functional Requirements

### FR-1: Pre-Launch Smoke Tests (Before Ads Go Live)
Complete end-to-end testing of every step a new user takes:

**Test 1: Landing Page → Registration**
- Visit tradingwithai.ai from an incognito browser
- Verify page loads in under 3 seconds
- Click "Start Free Trial" → registration form loads
- Register with a new email
- Verify: account created, redirected to dashboard, trial banner shows "3 days left"
- Acceptance: 100% pass rate across Chrome, Safari, mobile Safari

**Test 2: Onboarding → Watchlist**
- New user adds 3 symbols to watchlist
- Verify symbols appear, live prices load within 15 seconds
- Verify AI coach responds when asked about a symbol
- Acceptance: Watchlist works, prices update, coach responds

**Test 3: Telegram Link**
- Go to Settings → Telegram Alerts
- Click "Open in Telegram & Tap Start"
- Verify bot responds with confirmation message
- Verify Settings page shows "Connected" status after refresh
- Acceptance: Telegram linked in under 30 seconds

**Test 4: Alert Delivery**
- Wait for next 3-min poll cycle (or trigger manually during market hours)
- Verify alert appears in Signal Feed on dashboard
- Verify alert arrives in Telegram DM (if market is open)
- Verify "Took It" / "Skip" buttons work in both web and Telegram
- Acceptance: Alert flows end-to-end from detection to notification

**Test 5: Trial Expiry → Upgrade**
- Verify the billing page shows correct pricing ($49 Pro, $99 Premium)
- Verify "Upgrade" button works (redirects to Square checkout)
- Verify payment completes and tier updates to Pro
- Verify upgraded user gets full Pro access (10 watchlist, unlimited alerts, Telegram)
- Acceptance: Payment flow completes without errors

**Test 6: Mobile Experience**
- Open tradingwithai.ai on iPhone Safari
- Complete registration, add watchlist, view chart
- Verify responsive layout — no horizontal scroll, CTAs accessible
- Acceptance: All core flows work on mobile viewport

### FR-2: Ad Campaign Setup
- Run ads on 2 platforms for comparison data
- Each ad links to the landing page with UTM tracking parameters
- Minimum 3 ad variations to test messaging:
  - Variation A: "AI Trading Alerts" angle (alerts + trade plans)
  - Variation B: "AI Trade Coach" angle (coaching + education)
  - Variation C: "Options Flow + Smart Signals" angle (intelligence tools)
- Acceptance: Ads are live on 2 platforms with UTM tracking, 3 variations each

### FR-3: UTM Tracking & Analytics
- Landing page captures UTM parameters (source, medium, campaign, content)
- Registration stores which ad/campaign the user came from
- Dashboard or admin view shows: visitors by source, registrations by source, trial starts by source
- Acceptance: Can determine which ad variation produced each registration

### FR-4: Daily Monitoring Checklist (During Ad Week)
- Check daily: ad spend, impressions, clicks, CTR, CPC
- Check daily: registrations, trial starts, Telegram links, first alert viewed
- Check daily: any errors in Railway logs (500s, failed registrations, Telegram issues)
- End of week: compile funnel data (impressions → clicks → registrations → trials → upgrades)
- Acceptance: Daily metrics tracked and compiled into end-of-week report

### FR-5: Conversion Tracking
- Track these funnel events:
  1. Landing page visit (by UTM source)
  2. Registration completed
  3. Watchlist symbol added (activation)
  4. Telegram linked (engagement)
  5. First alert viewed/acknowledged
  6. Upgrade to paid (conversion)
- Acceptance: Each funnel step is measurable and attributable to ad source

## User Scenarios

### Scenario 1: New User From Instagram Ad
**Actor**: Retail trader sees TradeCoPilot ad on Instagram
**Trigger**: Taps "Start Free Trial" on ad
**Steps**:
1. Lands on tradingwithai.ai?utm_source=instagram&utm_medium=paid&utm_campaign=week1&utm_content=ai_alerts
2. Reads hero, scrolls to features, clicks "Start Free Trial"
3. Registers with email/password
4. Adds SPY, NVDA, AAPL to watchlist
5. Links Telegram, receives first alert
6. Uses AI coach to analyze a chart
7. Trial expires after 3 days → sees upgrade prompt
8. Upgrades to Pro ($49)
**Expected Outcome**: Full funnel conversion tracked from ad click to paid subscription

### Scenario 2: New User Who Doesn't Convert
**Actor**: Curious trader from Twitter ad
**Trigger**: Clicks ad, registers, doesn't engage
**Steps**:
1. Registers but doesn't add watchlist symbols
2. Doesn't link Telegram
3. Trial expires, gets email/notification about upgrade
4. Stays on free tier
**Expected Outcome**: Drop-off point is identified (no watchlist = no activation)

### Scenario 3: Smoke Test Failure Blocks Launch
**Actor**: Internal team running smoke tests
**Trigger**: Test 3 (Telegram link) fails
**Steps**:
1. Smoke test reveals Telegram bot not responding
2. Team fixes the issue before ad launch
3. Re-runs all 6 smoke tests
4. All pass → ads go live
**Expected Outcome**: No ads run until all smoke tests pass

## Success Criteria

- [ ] All 6 smoke tests pass before ads go live
- [ ] At least 500 landing page visits during the week
- [ ] Registration conversion rate is measurable (target: >5% of visitors)
- [ ] At least 20 new trial signups during the week
- [ ] Cost per trial signup is under $15
- [ ] At least 1 paid conversion during the week (validates the funnel works)
- [ ] Can identify which ad variation (A/B/C) produced the most registrations
- [ ] Funnel drop-off points are identified (where users stop engaging)
- [ ] Zero critical errors during the ad week (no 500s, no broken flows)

## Edge Cases

- Ad platform rejects ads (financial services restrictions) — have backup copy that says "educational platform" instead of "trading signals"
- Surge of registrations overwhelms Railway — monitor CPU/memory, Railway Pro plan handles scaling
- Users register but never activate (no watchlist) — trigger activation email after 24 hours: "Add your first symbol to get started"
- Trial expires on weekend when market is closed — user never experienced alerts. Consider extending trial if user registered on Friday
- Square checkout fails — show fallback message with support email

## Assumptions

- Ad budget: $200-500 for the week (split across 2 platforms)
- Ad platforms: Instagram/Facebook (Meta Ads) and Twitter/X Ads — most accessible for financial education
- UTM tracking can be done via URL parameters without additional analytics infrastructure
- Registration already captures referral source (utm_source) — needs verification
- The landing page update (spec 17) is deployed before ads go live
- All smoke tests will be run manually (no automated test suite needed for this scope)
- Square checkout is functional for subscription payments

## Constraints

- Meta and Twitter have restrictions on financial services advertising — copy must emphasize "education" not "guaranteed returns"
- Cannot show specific profit claims in ads ("Make $500/day") — must use factual stats ("79% win rate across 600+ tracked signals")
- Budget is fixed — no ability to scale mid-week even if performance is good (that's for week 2)
- 3-day trial means users from Monday/Tuesday ads have the best chance of experiencing market hours alerts before trial expires

## Scope

### In Scope
- 6 smoke tests (manual, pre-launch)
- Ad campaign setup on 2 platforms
- 3 ad variations per platform
- UTM parameter tracking through registration
- Daily monitoring checklist
- End-of-week funnel analysis
- Any bug fixes discovered during smoke tests

### Out of Scope
- Automated test suite (manual testing is sufficient for this scale)
- Retargeting pixel setup (future optimization)
- Email drip campaigns for trial users (future)
- Landing page A/B testing (single version for now)
- Video ad creative (static images + copy only)
- Google Ads (more complex approval process — phase 2)

## Appendix: Pre-Launch Checklist

Run these the Friday before ads go live (2026-04-11):

- [ ] Smoke Test 1: Landing → Registration (Chrome, Safari, Mobile)
- [ ] Smoke Test 2: Onboarding → Watchlist + AI Coach
- [ ] Smoke Test 3: Telegram Link (fresh account)
- [ ] Smoke Test 4: Alert Delivery (during market hours)
- [ ] Smoke Test 5: Trial → Upgrade Payment
- [ ] Smoke Test 6: Mobile Experience
- [ ] Landing page spec-17 changes deployed
- [ ] UTM tracking verified (register with ?utm_source=test, check DB)
- [ ] Square checkout tested with real card
- [ ] Ad creative approved on Meta + Twitter
- [ ] Ad budget set ($200-500)
- [ ] Railway monitoring alerts configured
- [ ] All team members have admin access to ad platforms

## Appendix: Ad Copy Variations

**Variation A — AI Alerts Angle:**
"Stop staring at charts. TradeCoPilot sends complete trade plans to your phone — entry, stop, targets, AI analysis. 3-day free trial."

**Variation B — AI Coach Angle:**
"Your AI trading copilot. Ask about any chart, get day trade + swing trade levels. 11 AI services coaching you to better decisions. Free trial."

**Variation C — Intelligence Tools Angle:**
"Options flow scanner. Sector rotation tracker. Smart watchlist ranking. See what the market sees — before it moves. Try free for 3 days."

## Clarifications

_Added during `/speckit.clarify` sessions_

[NEEDS CLARIFICATION: What is the total ad budget for the week? $200 (conservative, ~50 signups data) vs $500 (enough for statistically meaningful conversion data). This directly impacts how much data you'll collect.]
