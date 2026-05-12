# Feature Specification: Platform Rebrand v2 — Core Positioning + Visual Identity

**Status**: Draft — Scope tightened 2026-05-12 (3-spec split)
**Created**: 2026-05-07
**Last Updated**: 2026-05-12
**Author**: mentorhubnetworks@gmail.com
**Supersedes (in part)**: `specs/28-platform-rebrand` (2026-04-11).
**Companion specs**:
- `specs/48-education-module` — lesson framework, AI tutor inside lessons, Foundations track content
- `specs/49-trading-layer-surface` — strategies catalog, sample alerts archive, methodology page, system stats, legal-safe results framing

## Overview

The product has outgrown the "AI alert service" identity. What started as a rule-based alert tool now delivers a **complete trading methodology** — a TradingView-native detection layer, an AI triage agent that adds sector/index confluence to every alert, an EOD review surface, and a 4-indicator Pine suite that powers the alert stream. Alongside that system, the user has accumulated a teachable framework that needs an on-ramp for new visitors.

**This spec (47) covers**: the rebrand of marketing-site presentation — hero, navigation, pricing, brand identity, migration — and the cross-link tissue between the existing app surfaces and the new positioning.

**Spec 48 covers**: the new Education product surface (lessons, AI tutor, Foundations track content).

**Spec 49 covers**: the trading-strategies and results-presentation surface (methodology page, system stats, strategies catalog, legal-safe framing, EOD/Pine indicator marketing surface).

The 3 specs ship together at cutover but are managed as independent work streams.

## Positioning (Locked 2026-05-12)

The platform is positioned as **"AI Trading & Education with Results to Show"**:

- **Education**: We teach a structured framework (EMA system, structural levels, multi-TF confluence, risk management) through lessons + AI tutor (spec 48).
- **Trading strategies with results**: We show what the system has detected — anonymized alert archive, pattern-frequency stats, AI verdict breakdowns. **Descriptive, not predictive. Educational, not advisory** (spec 49).
- **Live signals**: The existing alert stream remains the spine of the Pro tier, now framed as one output of a larger methodology.

The brand name and domain are retained — `tradingwithai.ai` stays. No SEO migration; visual identity refresh suffices.

The platform is presented as a methodology + tool + education stack, not as a "signals service that prints money." Legal/regulatory safety is non-negotiable: see spec 49 FR-9 (Disclaimer & Compliance Surface) for the hard rules.

## Problem Statement

**Who is affected**: Prospective users hitting the marketing site, existing free-tier users evaluating an upgrade, and the operator (single-person team) who needs the platform to convert and retain at higher rates than an "alerts service" can.

**Current pain points**:

- Front-end positioning leads with alert-tool language and feature lists. It doesn't communicate the methodology + AI triage layer + education stack.
- Visitors with no trading background bounce because alerts assume context they don't have.
- The methodology is the durable moat; the rebrand makes it visible and sellable.
- The brand visual identity was chosen for an earlier product. It under-sells the current scope and limits pricing power.

## Functional Requirements (Rebrand Core Only)

### FR-1: New Positioning & Hero Narrative
- The home page hero must communicate three things in plain language: (a) the platform teaches a trading framework, (b) the platform surfaces real-time pattern detections using that same framework, (c) every detection is AI-vetted with sector/volume/flow context before delivery.
- The phrase "AI alerts" must no longer be the lead. The lead is the **method** + the **outcome**: "Learn the framework. See it in action. Trade with vetted signals."
- The hero must contain two equally-weighted CTAs: **Start Learning** (→ spec 48 Learn landing) and **See Live Signals** (→ spec 49 strategies + recent signals).
- A first-time visitor (no trading background) must identify within 10 seconds: who this is for, what they get, and what to do next.
- **Acceptance**: A 5-second test with 10 unfamiliar users returns ≥70% who can state both the educational and trading-detection value props after viewing only the hero.

### FR-2: Two-Path Front Door
- The home page presents two primary CTAs leading to dedicated landing experiences: **Learn** (spec 48) and **Trade** (spec 49).
- A returning user reaches their default surface (Trading dashboard or Learning hub) in one click from any marketing page.
- **Acceptance**: Both paths convert to either a free-account creation or a trial start. Analytics can attribute which path a paying subscriber originated from.

### FR-3: Information Architecture & Navigation
- Primary nav (logged-in): **Trading**, **EOD Report**, **Learn**, **Strategies**, **Watchlist**, **Premarket**, **Trades**, **Account**.
- Primary nav (logged-out marketing): **Home**, **Learn**, **Strategies & Results**, **How It Works**, **Pricing**.
- "Alerts" is no longer a top-level nav concept — it lives under Trading.
- **Acceptance**: A tree-test returns ≥80% success on tasks: "find a lesson on EMAs", "find recent live signals", "find the EOD report", "upgrade your plan".

### FR-4: Tier Matrix Presentation
- Pricing page presents 3 tiers with one-sentence audience descriptions:
  - **Free** — preview the platform (5 watchlist symbols, 1 lesson preview, today's alerts blurred for non-actionable detail).
  - **Pro** — daily traders + active learners (unlimited Telegram alerts, full EOD Report, all Foundations lessons, AI Tutor 50 queries/day, Pine indicator source code access).
  - **Premium** — power users + serious learners (everything in Pro + paper trading + backtesting + weekly review + unlimited AI tutor + 50-symbol watchlist).
- Education is **bundled in Pro** — no standalone "Learn" tier.
- Each tier's value is explainable in one sentence to a non-technical visitor.
- **Acceptance**: A visitor on Pricing correctly selects the tier matching their stated goal in ≥85% of card-sort tests.

### FR-5: Brand Identity Refresh
- Refreshed visual identity: palette, typography, hero imagery, tone of voice. Signals "AI trading platform with an education layer" rather than "alerts service".
- Wordmark and tagline convey the dual nature (teach + signal + results) without being buzzword-heavy.
- Applied consistently across: marketing site, in-app dashboard headers, Telegram message footers, email templates.
- **Domain retained**: `tradingwithai.ai`. No domain migration.
- **Acceptance**: A side-by-side comparison test with 10 prospective users returns ≥70% preference for the refreshed identity on "looks like a serious trading platform I'd pay for".

### FR-6: Migration Without Disruption
- Existing subscribers retain entitlements through cutover.
- Existing URLs (signals page, dashboard, telegram links) redirect to new homes without breaking bookmarks or alert-message deep links.
- One-time subscriber notification (in-app banner + Telegram message) in plain language: "We've expanded — same alerts you love, now with the framework that powers them."
- **Acceptance**: Subscriber churn in the 30 days following cutover is no worse than the trailing 30-day baseline; zero broken links from historical Telegram alerts.

### FR-7: Disclaimer Integration (Cross-cuts with spec 49 FR-9)
- Every marketing and product page renders a persistent footer disclaimer: "Educational content. Not investment advice. Past pattern detection does not guarantee future outcomes. Trade at your own risk."
- A `/disclaimer` page is linked from every footer with the full risk text.
- **Acceptance**: Every page renders the short disclaimer; full text is one click away from any footer.

## Non-Functional Requirements

### Performance
- Marketing pages (home, learn landing, trade landing, pricing) render meaningful content within 2 seconds on a typical mobile connection.

### Reliability
- The rebrand rollout does not introduce regressions in the existing live-signal delivery pipeline.
- A rollback path exists: if the new front-end has a critical bug, the operator reverts within 30 minutes via `git revert` of the rebrand commits + redeploy.

### Accessibility
- All marketing pages meet WCAG 2.1 AA for color contrast, keyboard navigation, and screen-reader labels.

## User Scenarios

### Scenario 1: Curious Newcomer
**Trigger**: Lands on home page from ad/organic.
1. Reads hero — recognizes the dual value prop.
2. Clicks "Start Learning" → Learn landing (spec 48).
3. Reads first lesson (free preview); creates a free account to continue.
4. After 2 lessons, sees "See it live" widget → strategies / recent signals page (spec 49).
5. Upgrades to Pro within their first week.

### Scenario 2: Active Trader Evaluating
**Trigger**: Lands on home page from a comparison review.
1. Scans hero; recognizes framework language (EMAs, structural levels, AI triage).
2. Clicks "See Live Signals" → strategies catalog + recent signals archive (spec 49).
3. Reviews methodology page; reviews pricing.
4. Starts a Pro trial.

### Scenario 3: Existing Subscriber Post-Cutover
**Trigger**: Opens dashboard URL the morning after cutover.
1. Lands on (or is redirected to) the new dashboard with a one-time "what's new" banner.
2. Alerts, watchlist, EOD Report all intact.
3. Notices new "Learn" and "Strategies" nav entries — clicks in out of curiosity.
4. Continues their normal trading day without disruption.

### Scenario 4: Pricing-Page Decision
**Trigger**: Arrives at Pricing via Learn landing.
1. Sees 3 tiers (Free / Pro / Premium) with one-sentence audience descriptions.
2. Picks Pro (since it's the bundled tier with both Telegram alerts AND lessons).

## Success Criteria

- Within 90 days of cutover, ≥30% of new free-account creations originate from the Learn path (vs. the prior alerts-only funnel).
- Within 90 days, paid-conversion rate for new sign-ups improves by ≥25% over the trailing 90-day baseline.
- Within 30 days, monthly subscriber churn is no worse than the trailing 90-day baseline.
- A first-time visitor states both value props (education + trading detection) after viewing only the hero in ≥70% of qualitative tests.
- The refreshed visual identity preferred over current in ≥70% of side-by-side prospective-user comparisons.
- Zero broken links from historical Telegram alerts after cutover.

## Edge Cases

- **Logged-out visitor following a Telegram deep link to a lesson**: lesson preview + sign-up prompt.
- **Existing subscriber on a legacy grandfathered price**: tier matrix does not silently re-price; explicit consent required for any change.
- **Mobile screen**: dual-CTA hero and tier matrix legible without horizontal scroll on iPhone SE width.
- **An anonymized link in a historical Telegram alert points to a route we've renamed**: redirect maintained for 12 months minimum.

## Assumptions

- The existing live-signal pipeline (TradingView webhook → triage agent → Telegram) remains the canonical alert delivery path. This spec changes packaging and presentation, not signal logic.
- The brand name change preserves the existing domain.
- A single operator owns delivery; scope is bounded by single-person capacity.

## Constraints

- **Continuity of revenue**: No service interruption or surprise re-pricing during cutover.
- **Single operator capacity**: Scope achievable without hiring.
- **Compliance posture**: Marketing copy stays educational + observational. See spec 49 FR-9 for the hard wording rules.

## Scope

### In Scope (this spec, v2 cutover)
- Front-end rebrand of marketing pages: home, pricing, footer, meta.
- Information architecture changes (nav restructure).
- Visual identity refresh: palette, typography, hero copy.
- Tier matrix presentation (3 tiers).
- Migration: legacy URL redirects, one-time subscriber notification, rollback procedure.
- Persistent disclaimer footer + `/disclaimer` page.

### Out of Scope (handled by companion specs)
- Education lesson content + framework (spec 48)
- Strategies catalog / recent signals page / methodology page / system stats (spec 49)
- Backend changes to alert logic, Pine indicators, triage agent, or Telegram message format. **Hard line: this is a presentation rebrand, not a logic rebuild.**

## Clarifications

### Resolved 2026-05-12
- **C1: Brand-name strategy**: Keep `tradingwithai.ai`. Visual identity refresh, no domain change.
- **C2: Education pricing model**: Bundled in Pro tier. No standalone "Learn" price.
- **C3: Education depth at cutover**: 5-lesson Foundations skeleton (delegated to spec 48 FR-7).
- **C4: Positioning emphasis (added 2026-05-12 per user direction)**: Focus on "education + trading strategies with results to show users". Results are framed as **descriptive system behavior** (pattern frequency, alert metadata, AI verdict breakdowns) **NOT as personalized P&L or win-rate claims**. Legal-safe framing per spec 49 FR-9.
