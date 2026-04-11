# Feature Specification: AI-Driven Trading Platform — Marketing Strategy & Landing Page

**Status**: Draft
**Created**: 2026-04-11
**Author**: Claude (speckit)

## Overview

Reposition TradeCoPilot as an **AI-driven trading intelligence platform** that eliminates trading stress and teaches users to trade efficiently. This spec defines the platform's core marketing values, identifies new AI initiatives to add market value, audits the current landing page, and provides a roadmap for messaging that converts visitors into paying subscribers.

## Problem Statement

The current landing page markets 12 features, but 3 are not yet built (Options Flow, Sector Rotation, Catalyst Calendar). The messaging positions the platform as an "alert service" — a crowded, commoditized category where users compare on price. The actual competitive advantage is **AI that thinks like a trading analyst**: it doesn't just ping you when a price crosses a line — it evaluates the full context and delivers a trade plan.

**Current positioning weakness**: "Your chart analyst that never sleeps" is passive. It describes what the AI does (watch charts) but not the USER outcome (make better trades with less stress).

**What competitors say**: TradingView = "Chart your way." Trade Ideas = "AI-powered stock scanner." Benzinga = "Actionable news." All focus on the tool. None focus on the trader's emotional journey — the stress, the FOMO, the chart fatigue, the missed setups.

**Opportunity**: Position TradeCoPilot as the platform that **removes trading stress** by giving you an AI analyst on your team. You stop watching charts. You stop second-guessing. You get a plan, decide, and learn from results.

## Current Landing Page Audit

### What's Working

| Element | Status | Notes |
|---------|--------|-------|
| Live track record widget | Strong | 77% win rate, auditable — unique differentiator |
| Telegram example alert | Strong | Shows exact output users will get |
| 3-step "How it works" | Clear | Set watchlist → Get plans → Take or skip |
| Pricing comparison table | Good | Shows value vs competitors |
| Signal Library (/learn) | Good | Educational, builds SEO |
| Dark theme / trading aesthetic | Good | Matches target audience expectations |

### What Needs to Change

| Element | Issue | Fix |
|---------|-------|-----|
| Hero headline | Passive ("never sleeps") | Active: what the USER gets, not what AI does |
| Feature list | 3 unbuilt features marketed | Remove Options Flow, Sector Rotation, Catalyst Calendar |
| AI positioning | AI mentioned but not central | Make "AI" the lead word in every value prop |
| No video/demo | Text-only pitch | Add 60-second demo video or animated trade replay embed |
| No testimonials | "Placeholder" notes in code | Collect 3-5 real user quotes |
| Crypto coverage undersold | Barely mentioned | Highlight 24/7 AI monitoring as unique edge |
| WAIT signals not mentioned | Unique: AI tells you when NOT to trade | Major differentiator — add to feature list |
| Win rate by pattern hidden | On /learn but not landing page | Surface top 3 patterns with win rates on homepage |

## Core Marketing Values (Platform Identity)

### Value 1: "AI Finds the Trade. You Decide."
The AI continuously scans your watchlist and delivers complete trade plans — entry, stop, targets, conviction level. You're not glued to charts. You receive a notification, evaluate it, and decide. The stress of watching every tick is replaced by a structured decision point.

### Value 2: "Every Alert Teaches You"
Unlike signal services that say "Buy AAPL now," every TradeCoPilot alert explains WHY the setup exists: what level is being tested, what the confirmation looks like, and where the risk is. Over time, users internalize these patterns and develop their own edge.

### Value 3: "Transparent Track Record — Even When It's Ugly"
The platform publishes real win rates per pattern. Users see which setups work and which don't. No cherry-picking. No hiding losses. This builds trust and helps users calibrate confidence.

### Value 4: "Your AI Trading Analyst — Not a Signal Service"
Signal services give you fish. TradeCoPilot teaches you to fish while an AI catches fish for you. The AI Coach answers your chart questions. The Pre-market Brief gives you a game plan. The Weekly Review identifies your edge. It's a continuous learning loop.

### Value 5: "24/7 Coverage, Zero Chart Fatigue"
AI monitors equities during market hours and crypto around the clock. When a key level is tested at 2 AM, you get a Telegram notification with a full plan. No more setting price alerts and wondering what to do when they fire.

## New AI Initiatives to Add Market Value

### Initiative 1: AI Trade Confidence Score (visible per alert)
Show users a clear 1-5 star rating per alert based on: win rate for this pattern (historical), regime alignment, volume confirmation, multi-timeframe confluence. Users see stars, not just "HIGH/MEDIUM/LOW."

- Market value: Users trust alerts with visual confidence indicators
- Differentiator: No competitor shows historical pattern-specific win rates per alert

### Initiative 2: AI "What Would You Do?" Education Mode
For free-tier users, show the chart scenario WITHOUT the trade plan. Ask "What would you do?" Then reveal the AI's analysis. Gamified learning that teaches pattern recognition while driving upgrade conversion.

- Market value: Viral education feature, shareable on social
- Differentiator: Turns the platform into an interactive trading school

### Initiative 3: AI Weekly Edge Report (personalized)
Already built but undersold. Package the weekly review as a "Personal Trading Edge Report" — your win rate, best patterns, behavioral tendencies, and 1 specific thing to change next week. Make it shareable (anonymized) on social media.

- Market value: Users share their Edge Score, creating organic marketing
- Differentiator: No competitor provides personalized coaching with data-backed recommendations

### Initiative 4: AI "Market Mood" Dashboard
Real-time dashboard showing: SPY regime (trending/choppy/pullback), sector heat map, breadth indicators, and AI's overall market stance (aggressive/cautious/defensive). Users check this before trading.

- Market value: Institutional-grade market overview for retail traders
- Differentiator: Context for every trade, not just individual stock alerts

### Initiative 5: AI Pattern Recognition Overlay
When users view a chart, AI identifies and labels visible patterns: double bottom forming, ascending triangle, MA squeeze. Visual education directly on the chart they're reading.

- Market value: Teaches pattern recognition in real-time
- Differentiator: TradingView has user-drawn patterns; TradeCoPilot auto-detects

### Initiative 6: AI Trade Simulator (Paper Trading with AI Coaching)
Free-tier paper trading where the AI coaches you through each trade decision: "Good entry — price was at PDL with hold confirmation. Where would you set your stop?" Interactive, zero-risk learning.

- Market value: Reduces barrier to entry for beginners
- Differentiator: Paper trading + coaching is rare; most platforms offer one or the other

### Initiative 7: AI Alerts on Autopilot (Set-and-Forget Mode)
Users configure: "Only alert me on HIGH conviction setups where my historical win rate > 60%." The AI filters everything else out. Perfect for busy professionals who check their phone twice a day.

- Market value: Addresses #1 user complaint — too many alerts
- Differentiator: Personalized filtering based on each user's own track record

## Functional Requirements

### FR-1: Landing Page Messaging Overhaul
- Replace hero headline with outcome-focused messaging: what the USER gets, not what the AI does
- Remove all references to unbuilt features (Options Flow, Sector Rotation, Catalyst Calendar)
- Add "AI" as lead word in every feature description
- Add embedded trade replay animation or 60-second demo video
- Surface top 3 patterns with live win rates directly on homepage
- Highlight 24/7 crypto coverage as a prominent feature
- Add "WAIT signals" as a feature: "AI tells you when NOT to trade — saving you from bad entries"
- Acceptance: Landing page only references features that are live in production; every feature description starts with AI context

### FR-2: Core Values Integration
- Create a "Why TradeCoPilot?" section with the 5 core values defined above
- Each value has: headline, 2-sentence description, visual icon or metric
- Values are ordered by user impact: stress reduction, education, transparency, coaching, coverage
- Acceptance: Section is visible above the fold or immediately after hero on landing page

### FR-3: Social Proof Enhancement
- Replace placeholder testimonial section with real user quotes (minimum 3)
- Add "As seen in" section if any press/blog coverage exists
- Feature the live track record widget more prominently (move above pricing)
- Add a "Pattern of the Week" rotating feature showing a recent winning alert with full context
- Acceptance: At least 3 real testimonials displayed; track record widget visible without scrolling past hero

### FR-4: Competitive Differentiation Section
- Replace generic comparison table with focused "Why traders switch" section
- Highlight 3 unique capabilities competitors cannot match:
  1. Per-pattern win rate transparency (no competitor publishes this)
  2. AI WAIT signals (only platform that tells you when NOT to trade)
  3. Personalized edge scoring (weekly report showing YOUR patterns, not generic advice)
- Acceptance: Competitive section includes only verifiable claims about capabilities that are live

### FR-5: SEO & Content Strategy for AI Positioning
- Update page title, meta description, and keywords to lead with "AI trading"
- Target keywords: "AI trading alerts," "AI day trading," "AI swing trading," "automated trading signals"
- Every Signal Library page (/learn) includes structured FAQ schema
- Blog/content calendar: 2 posts per week focused on AI trading education
- Acceptance: Primary keyword "AI trading alerts" appears in title, H1, and first paragraph; structured data validates

### FR-6: Conversion Path Optimization
- Add a "See AI in Action" interactive demo (free, no signup required)
- Show a real recent alert with Took/Skip scenario and actual outcome
- Free tier users see 3 blurred alerts per day with CTA: "Upgrade to see full trade plans"
- Trial CTA emphasizes low risk: "3 days free, cancel anytime, no credit card to start"
- Acceptance: New visitor can see a real AI alert example without creating an account

### FR-7: AI Evidence Board (Public Proof Page)
- A public, no-login-required page (`/proof` or `/evidence`) showing recent trades with full evidence chain
- Each evidence card includes:
  - **The alert**: What AI detected (setup type, entry, stop, T1, T2, conviction)
  - **The chart replay**: Embedded animated replay showing price action from alert fire to outcome
  - **AI analysis**: 2-3 sentence explanation of why the setup was valid and what happened
  - **The outcome**: T1 hit / T2 hit / Stopped / Open — with exact prices and P&L in R-multiples
  - **Timestamp**: When the alert fired, when the outcome was resolved
- Page shows the last 10-20 resolved trades (won or lost — transparency)
- Trades are auto-populated from the existing alert + outcome tracking system
- Filterable by: symbol, setup type, outcome (win/loss/all), date range
- Each evidence card is shareable (unique URL) for social media posting
- Losses are shown with the same detail as wins — builds trust through honesty
- Acceptance: Public page shows at least 10 resolved trades with replay + AI analysis + verified outcome; page loads without login

## User Scenarios

### Scenario 1: New Visitor Evaluates the Platform
**Actor**: Retail trader seeing TradeCoPilot for the first time (from Google search "AI trading alerts")
**Trigger**: Lands on homepage
**Steps**:
1. Reads hero headline — understands platform reduces trading stress via AI
2. Sees live track record — 77% win rate builds credibility
3. Views example alert — understands exact output they'll receive
4. Reads 5 core values — understands educational + intelligence positioning
5. Checks pricing — sees Pro at $49/month, compares to Trade Ideas at $228
6. Clicks "Start Free Trial" — begins 3-day Pro trial
**Expected Outcome**: Visitor understands value prop in under 60 seconds and starts trial

### Scenario 2: Free User Converts to Pro
**Actor**: Free-tier user who has been using platform for 2 weeks
**Trigger**: Sees 3 blurred alerts in dashboard with "Upgrade to see full plan"
**Steps**:
1. User has experienced AI Coach (2 queries/day) and found it valuable
2. Sees blurred alert for a symbol they're watching — FOMO trigger
3. Reads "Your PDL bounce win rate is 73% — this pattern just fired" (personalized nudge)
4. Clicks upgrade, enters payment, gets instant Pro access
**Expected Outcome**: User converts based on personalized data showing their own edge

### Scenario 3: Trader Shares Edge Report
**Actor**: Pro subscriber after 30 days of trading
**Trigger**: Friday weekly edge report delivered via Telegram
**Steps**:
1. User receives: "Edge Score: 7.2/10 — Your proven edge: PDL reclaims (78% win rate)"
2. User screenshots and shares on Twitter/X
3. Friend sees the post, visits tradingwithai.ai
4. Friend starts free trial
**Expected Outcome**: Organic viral loop through shareable performance data

### Scenario 4: Skeptic Checks the Evidence Board
**Actor**: Trader skeptical of AI trading claims, finds platform via Twitter
**Trigger**: Clicks link to `/proof` page
**Steps**:
1. Sees grid of recent trades — some green (wins), some red (losses)
2. Clicks on a winning ETH-USD PDL bounce trade
3. Watches embedded chart replay: sees price touch PDL, hold 3 bars, bounce to T1
4. Reads AI analysis: "PDL hold confirmed with 3-bar close above $2,176. Volume supported the bounce."
5. Sees outcome: T1 hit at $2,210. P&L: +1.5R
6. Notices losses are shown too — platform isn't hiding failures
7. Clicks "Start Free Trial" — convinced by verifiable evidence
**Expected Outcome**: Skeptic converts because evidence is visual, specific, and honest (shows losses too)

## Success Criteria

- [ ] Landing page bounce rate decreases by 20% within 30 days of relaunch
- [ ] Free trial signup rate increases by 30% within 60 days
- [ ] Free-to-Pro conversion rate increases by 15% within 90 days
- [ ] Organic search traffic for "AI trading alerts" increases by 50% within 60 days
- [ ] At least 3 real user testimonials collected and displayed within 30 days
- [ ] Zero unbuilt features marketed on the landing page
- [ ] Landing page loads in under 3 seconds
- [ ] Time-to-value for new visitors (understanding the platform) is under 60 seconds

## Edge Cases

- **No track record data yet**: Show platform-wide demo data with disclaimer "Based on platform signals, not individual results"
- **User has no trading history**: Edge reports show platform averages with note "Your personal data appears after 10+ trades"
- **Competitor changes pricing**: Comparison table uses ranges ("$150-250/mo") instead of exact prices
- **Testimonial user cancels**: Keep testimonial if consented; replace if they request removal
- **SEO keyword cannibalization**: Ensure landing page targets "AI trading alerts" while /learn targets specific patterns

## Assumptions

- The current 77% win rate is sustainable and auditable for marketing claims
- Users find AI-generated trade plans more valuable than raw price alerts
- Telegram remains the primary notification channel (mobile-first audience)
- Pro at $49/month is competitive against Trade Ideas ($228), Benzinga Pro ($117), and similar
- Education-first positioning differentiates from pure signal services
- Users will share Edge Reports on social media if made easy (shareable link or image)

## Constraints

- All marketing claims must reference features that are live in production — no "coming soon" positioning
- Win rate claims must be verifiable via the public track record endpoint
- "Not financial advice" disclaimer must appear on landing page and in all marketing
- Budget for paid acquisition is not defined in this spec — organic and content-led growth first
- No guarantees of profitability in any marketing copy — focus on education and decision support

## Scope

### In Scope
- Landing page messaging overhaul (headline, features, values, social proof)
- Core marketing values definition (5 pillars)
- New AI initiative identification (7 initiatives ranked by market value)
- Competitive positioning refresh
- SEO keyword strategy for AI trading
- Conversion path optimization
- Content strategy framework

### Out of Scope
- Implementing new AI features (separate specs per initiative)
- Paid advertising campaigns (requires budget approval)
- Mobile app development (Telegram is the mobile channel)
- Redesigning the entire web application UI
- Pricing changes (current tiers stay for now)
- International/multilingual support

## AI Initiative Priority Matrix

| Initiative | Market Value | Build Effort | Priority |
|-----------|-------------|-------------|----------|
| AI Trade Confidence Score (stars) | High | Low | Phase 1 |
| AI Alerts on Autopilot (filter mode) | High | Medium | Phase 1 |
| AI Weekly Edge Report (shareable) | High | Low (mostly built) | Phase 1 |
| AI "What Would You Do?" education | High | Medium | Phase 2 |
| AI Market Mood Dashboard | Medium | Medium | Phase 2 |
| AI Pattern Recognition Overlay | Medium | High | Phase 3 |
| AI Trade Simulator with Coaching | Medium | High | Phase 3 |

## Suggested Landing Page Structure (Revised)

1. **Hero**: Outcome-focused headline + live market status + example alert
2. **Social Proof Bar**: "77% win rate across 600+ signals" + 3 user quotes
3. **Core Values**: 5 pillars (stress-free, educational, transparent, coaching, 24/7)
4. **Feature Showcase**: 8 live features with AI lead-in (remove 3 unbuilt)
5. **How It Works**: Set watchlist → Get AI plans → Decide → Learn
6. **AI Evidence Board**: Recent trades with replay + AI analysis + outcome (link to /proof)
7. **Live Track Record**: Per-pattern win rates with interactive filter
8. **Why Switch**: 3 unique differentiators (transparency, WAIT signals, evidence board)
8. **Pricing**: 3 tiers with Pro highlighted, trial CTA
9. **Signal Library Preview**: Top 3 patterns with live stats
10. **FAQ**: 10 questions addressing objections
11. **Final CTA**: "Start your 3-day free trial"

## Clarifications

### Session 2026-04-11
- Q: What kind of evidence-based proof would be most convincing? → A: AI Evidence Board — public page showing recent trades with chart replay animation + AI analysis + entry/exit prices + actual outcome. Shows wins AND losses. Shareable cards for social proof. No login required.
