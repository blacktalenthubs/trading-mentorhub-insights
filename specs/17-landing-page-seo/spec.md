# Feature Specification: Landing Page Value Proposition & SEO Update

**Status**: Draft
**Created**: 2026-04-07
**Author**: AI-assisted

## Overview

Update the TradeCoPilot landing page to accurately reflect the platform's current feature set (11 AI services, 5 intelligence features, options flow, sector rotation, smart watchlist) and improve search engine visibility. The current landing page was written before many features existed and undersells the product.

## Problem Statement

The landing page was last updated weeks ago. Since then, the platform has added:
- 11 AI-powered services (coach, narrator, pre-market brief, EOD review, weekly review, etc.)
- Options Flow Scanner, Sector Rotation, Catalyst Calendar
- Smart Watchlist Ranking with tradeability scores
- Trade Performance Breakdown (pattern/time/symbol analytics)
- Swing trade system with expandable entry/exit reasons
- Structured AI coaching (day trade + swing trade entries)

None of these appear on the landing page. Visitors see a generic "AI trading alerts" pitch when the product is actually a comprehensive AI trading copilot. This hurts conversion and SEO.

**SEO gaps**: No structured data, thin keyword coverage, missing long-tail terms traders search for ("best AI trading alerts", "swing trade scanner", "options flow alerts", "sector rotation tracker").

## Functional Requirements

### FR-1: Updated Hero Section
- Headline communicates the full value: AI copilot that analyzes charts, sends alerts, coaches trades, and tracks performance
- Sub-headline includes key differentiators: 11 AI services, real-time alerts, structured trade plans
- Live stats from the platform: total alerts fired, win rate, active users (pulled from public API)
- Acceptance: New visitor understands the full product in under 5 seconds

### FR-2: Feature Showcase Sections
- Dedicated sections for each major capability:
  1. **Real-Time Alerts** — BUY/SELL signals with entry/stop/targets, delivered to Telegram
  2. **AI Trade Coach** — structured day trade + swing trade analysis with specific levels
  3. **Options Flow Scanner** — unusual activity detection, volume/OI analysis
  4. **Sector Rotation** — live sector ETF momentum tracking
  5. **Smart Watchlist** — tradeability scoring, auto-ranking
  6. **Swing Trade System** — EOD scans, expandable entry/exit reasons
  7. **Performance Analytics** — win rate by pattern, time, symbol
  8. **Catalyst Calendar** — earnings/events warnings
  9. **AI Coaching Suite** — pre-market brief, EOD review, weekly edge report
  10. **Chart Replay** — educational trade replays for content creation
- Each section: headline, 2-sentence description, visual/screenshot mockup
- Acceptance: Every major feature is represented with a clear value statement

### FR-3: Updated Pricing Section
- Pro ($49/mo): Emphasize 11 AI services, unlimited alerts, Telegram DMs, performance analytics
- Premium ($99/mo): Add options flow, paper trading, backtesting, weekly coaching
- Feature comparison table updated with all new features
- 3-day free trial prominently displayed
- Acceptance: Pricing reflects actual current features, comparison table has 15+ rows

### FR-4: Social Proof & Trust Signals
- Live platform stats: total signals tracked, win rate, active traders
- Comparison table: TradeCoPilot vs TradingView vs Trade Ideas vs Discord groups
- Updated with new comparison rows: AI coaching, chart replay, options flow, sector rotation
- Acceptance: At least 3 trust signals visible above the fold

### FR-5: SEO Meta Tags & Structured Data
- Primary keyword targets: "AI trading alerts", "AI trade coach", "options flow scanner", "swing trade alerts", "sector rotation tracker"
- Updated meta title, description, and Open Graph tags
- Structured data markup for: SoftwareApplication, FAQPage, Product (with pricing)
- Canonical URL set to https://www.tradingwithai.ai
- Acceptance: Pages pass Google Rich Results test for at least 2 structured data types

### FR-6: Updated FAQ Section
- Minimum 10 questions covering: what is TradeCoPilot, how alerts work, what AI services are included, pricing, free trial, Telegram setup, options flow, swing trades, performance tracking, getting started
- Questions written as natural search queries (long-tail SEO)
- Acceptance: FAQ section contains 10+ questions with clear answers

### FR-7: Call-to-Action Optimization
- Primary CTA: "Start Free Trial" (above fold, after features, after pricing)
- Secondary CTA: "See Live Signals" (links to public track record)
- Telegram demo section showing actual alert format
- Acceptance: At least 3 CTA placements on the page, each contextually relevant

## Non-Functional Requirements

### Performance
- Landing page loads in under 2 seconds (Lighthouse score 90+)
- No layout shift during loading (CLS < 0.1)
- Images optimized and lazy-loaded below the fold

### SEO
- Page passes Core Web Vitals thresholds
- All images have descriptive alt text
- Heading hierarchy is correct (single H1, logical H2/H3 structure)
- Internal links to key pages (pricing, features, login)

## User Scenarios

### Scenario 1: Organic Search Visitor
**Actor**: Trader searching "best AI trading alerts"
**Trigger**: Clicks Google result for tradingwithai.ai
**Steps**:
1. Lands on hero section — sees "AI Trading Copilot" headline with live stats
2. Scrolls to features — sees alerts, AI coach, options flow, swing trades
3. Sees comparison table — understands differentiation vs TradingView
4. Clicks "Start Free Trial"
5. Redirected to registration
**Expected Outcome**: Visitor understands the product and starts trial within 60 seconds

### Scenario 2: Referral Visitor
**Actor**: Trader who received a referral link from existing user
**Trigger**: Clicks referral link, lands on landing page
**Steps**:
1. Sees hero with live win rate and signal count
2. Scrolls to Telegram demo — sees actual alert format
3. Checks pricing — sees 3-day free trial
4. Signs up with referral code applied
**Expected Outcome**: Referred user starts trial, both users get reward

### Scenario 3: Returning Visitor (Comparison Shopper)
**Actor**: Trader comparing TradeCoPilot to Trade Ideas or Discord groups
**Trigger**: Returns to landing page after initial visit
**Steps**:
1. Scrolls directly to comparison table
2. Sees feature-by-feature breakdown
3. Reads FAQ for specific questions
4. Decides to start trial
**Expected Outcome**: Comparison table and FAQ answer remaining objections

## Success Criteria

- [ ] Organic search traffic increases by 50% within 60 days of update
- [ ] Landing page bounce rate decreases by 20%
- [ ] Free trial signup conversion rate increases from current baseline by 25%
- [ ] Page loads in under 2 seconds on mobile (3G connection)
- [ ] Google indexes at least 2 rich results (FAQ, SoftwareApplication)
- [ ] All 10+ major features are represented on the landing page
- [ ] Comparison table includes at least 15 feature rows

## Edge Cases

- Stats API is down — show hardcoded recent stats with "as of [date]" label
- Visitor on slow connection — progressive loading with skeleton states
- Mobile viewport — all sections stack cleanly, CTAs remain accessible
- Visitor with ad blocker — page functions fully without external tracking scripts

## Assumptions

- Live stats (total alerts, win rate) are available from the existing public track record API
- Screenshots/mockups of features will be created from actual platform UI
- The landing page remains a single-page design (no separate feature pages yet)
- SEO improvements target English-speaking US traders initially

## Constraints

- Must maintain current branding (TradeCoPilot, dark theme, accent colors)
- Cannot make claims about guaranteed returns or specific profit percentages
- Must include disclaimer: "Not financial advice. Past performance does not guarantee future results."
- Landing page must work without JavaScript for basic content (SEO crawlability)

## Scope

### In Scope
- Hero section rewrite
- Feature showcase sections (all 10+ features)
- Pricing update with full feature comparison
- SEO meta tags and structured data
- FAQ expansion to 10+ questions
- CTA optimization
- Comparison table update

### Out of Scope
- Separate feature detail pages (future initiative)
- Blog/content marketing pages
- Localization/multi-language support
- Video production (use static screenshots for now)
- A/B testing infrastructure (manual testing first)

## Clarifications

_Added during `/speckit.clarify` sessions_
