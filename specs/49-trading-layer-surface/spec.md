# Feature Specification: Trading Strategies & Results Surface

**Status**: Draft
**Created**: 2026-05-12
**Author**: mentorhubnetworks@gmail.com
**Related**: Split out of `47-platform-rebrand-v2`. Pairs with `48-education-module` (which teaches the methodology; this spec presents the methodology + its measurable outputs).

## Overview

This spec describes the **trading-strategies and results surface** of the rebranded platform. It complements the Education module (spec 48) by showing prospective and existing users:

1. **What strategies** the platform encodes (Scott Redler EMA framework, structural-level trading, multi-TF pivot alignment, sector-confluence routing).
2. **What the system saw** historically — anonymized alert archive, pattern-frequency stats, alert-quality metrics. **Not personalized P&L. Not win-rate claims.**
3. **How the AI triage layer adds value** beyond raw TradingView alerts (sector context, verdict reasoning, noise filtering).
4. **How the EOD report + Pine indicators** are tools users get on top of alerts.

The product is positioned as **a methodology platform + a real-time pattern detector + a learning system**, not as a "signals service that prints money." That positioning is intentional: it's both more durable (methodology is the moat) and substantially safer from a legal/regulatory perspective (educational + observational, not advisory).

## Legal & Positioning Constraints (Hard Rules)

This spec is bounded by what we can claim without crossing into investment-advisory territory:

- **No win-rate stats** ("our alerts win 65% of the time")
- **No P&L numbers** ("subscribers made $X")
- **No personalized recommendations** ("you should buy NVDA")
- **No predictions** ("NVDA will hit $250 by Friday")
- **No backtest "proof"** marketed as trading proof (backtests are illustrative, not predictive)

What we CAN claim and surface:

- **Pattern frequency**: "The system detected 90 actionable setups across our 50-symbol watchlist yesterday"
- **Alert metadata**: "Every alert is tagged with sector confluence, volume confirmation, and a verdict reason"
- **Methodology description**: "The system encodes the Scott Redler EMA framework" — citing publicly available trading methodology
- **System behavior**: "The AI triage layer filters NOTICE-direction alerts and caps repeat MA bounces at 2/day"
- **User testimonials**: ONLY if structured as opinions, never as performance claims, and with explicit disclosure
- **Educational case studies**: "Here's a chart from May 11 where the system fired a 1h/4h pivot break — let's read what happened next" — descriptive, not predictive

Every marketing page MUST include a disclaimer footer: "Educational content. Not investment advice. Past pattern detection does not guarantee future outcomes. Trade at your own risk."

## Functional Requirements

### FR-1: Strategies Catalog Page
- A new `/strategies` page lists each detection rule the platform supports, organized into 4 buckets matching the 4 Pine indicators:
  1. **Moving Average Bounce / Rejection** (8 daily MAs)
  2. **Prior-Day Levels + VWAP** (PDH break, PDL reclaim, PDH rejection, VWAP reclaim, etc.)
  3. **Weekly + Monthly Structural Levels** (PWH/PWL/PMH/PML — referenced by alerts, no separate alerts)
  4. **Multi-Timeframe Pivot Alignment** (1h+4h pivot break, reclaim, reject)
- Each rule shows: name, plain-English description, the chart pattern it looks for, when it fires, what makes it high-conviction vs. just informational.
- Each rule links to: the lesson that explains it (FR cross-link with spec 48), and a sample alert from the archive.
- **Acceptance**: A visitor on `/strategies` can identify the 4 indicator categories and pick one to drill into without confusion.

### FR-2: Sample Alerts Archive (Anonymized)
- A `/recent-signals` (or similar) public page shows the most recent ~30 actionable alerts from the platform.
- Each row: time, symbol, rule name, direction, entry/stop/T1/T2 (just the structure data — no P&L outcome).
- A "view detail" expands to show the AI triage verdict + reason + sector context (same as the Telegram message format).
- This page is **observational** — it shows what the system detected, not what to do.
- A disclaimer is shown above the table: "Past detections. Educational examples. Not investment advice."
- **Acceptance**: A logged-out visitor can browse 30 past alerts with full structural data + AI verdict and understand what each one represents.

### FR-3: AI Triage Explainer Page
- A dedicated `/how-it-works` (or `/triage`) page explains the AI triage layer at a non-technical level:
  - Step 1: Pine indicator on TradingView fires a raw signal
  - Step 2: Backend ingests via webhook, stores in DB
  - Step 3: AI triage agent checks: sector peers, index alignment, CVD, volume, historical cluster
  - Step 4: Verdict assigned (HIGH / NORMAL / MUTE) + plain-English reason
  - Step 5: Telegram delivery with the bold reason header + full structure
- Shown via diagram + plain English narrative.
- The page includes a sample Telegram message (rendered like the actual format) so visitors see the contracted output.
- **Acceptance**: A visitor can describe what the AI triage does in one sentence after reading the page.

### FR-4: System Behavior Stats (Not Performance Stats)
A `/stats` (or embedded in `/how-it-works`) page shows **descriptive** numbers about the system, NOT win/loss outcomes:

- Total alerts detected this month (across the watchlist)
- Breakdown by rule type (PDH break: X%, MA bounce: Y%, etc.)
- Breakdown by AI verdict (HIGH: X%, NORMAL: Y%, MUTE: Z%, NOTICE_MUTED: Q%)
- Average sector confluence per HIGH alert
- Average R:R math per actionable alert (just the math — not the realized R)
- "Most active symbols by alert count" — descriptive, not directional

All stats refresh nightly. All stats include the disclaimer: "Pattern-detection counts. Not trade outcomes."

**Acceptance**: A visitor can see "the system detects ~80 setups per day across our watchlist, and the AI flags ~30% as HIGH-conviction after sector/volume checks" — descriptive, not predictive.

### FR-5: Methodology Page (The "Why" of the System)
A `/methodology` page describes the trading framework the platform encodes:

- **The EMA framework** — Scott Redler's 8/21/50/100/200 setup. Cited as publicly published methodology with link.
- **Prior-day structural levels** — PDH/PDL as session memory; why the previous day's high and low matter for today's price action.
- **SPY-gated long bias** — why shorts on individual equities are suppressed when SPY is TRENDING.
- **Multi-TF confluence** — why 1h+4h pivot alignment is a higher-conviction signal class than a single TF.
- **Volume + CVD as confirmation** — what these tell you about a setup's conviction.

Each section ≤300 words, with a chart illustration and a link to the deeper Foundations lesson.

**Acceptance**: A reader leaves the page able to describe the methodology in 2-3 sentences.

### FR-6: EOD Report — Marketing Surface
- The Trade landing page must mention the EOD Report as a Pro-tier inclusion with a screenshot.
- Description: "Every alert from every session, sortable by any field. Filter by rule type, symbol, or volume. Copy to Sheets for offline analysis."
- A logged-in Pro+ user reaches the EOD Report directly from the sidebar (already shipped — commit `763cb1b`).
- **Acceptance**: A visitor on the Trade landing can describe what the EOD report shows without seeing it.

### FR-7: Pine Indicator Suite — Marketing Surface
- The Trade landing page must mention the 4 Pine indicators as a Pro-tier inclusion.
- Description: "Copy these 4 TradingView Pine indicators into your own TV, and the same setups that fire our alerts paint on your charts."
- A logged-in Pro+ user can access the Pine source code via a `/indicators` route that displays each pine's source with a "Copy to clipboard" button.
- **Acceptance**: A Pro subscriber can copy the `ma-ema-daily` pine source from the dashboard and paste it into TV in <2 minutes.

### FR-8: Tier-Cap UX Fix (Cross-cutting with Spec 47)
- When a non-admin user hits the watchlist symbol cap, the existing structured 403 response (`{ error: "upgrade_required", current_tier, limit, message }` from `api/app/routers/watchlist.py`) must be rendered as a friendly in-context modal, not raw "403 Forbidden".
- The modal shows: current tier, current cap, what upgrading would unlock, and a CTA to Pricing.
- **Acceptance**: A user at the 10-symbol Pro cap sees a clean modal naming Pro + 10-symbol limit + "Upgrade to Premium (50 symbols)" CTA when they try to add the 11th symbol.

### FR-9: Disclaimer & Compliance Surface
- A persistent footer on all marketing + product pages contains: "Educational content. Not investment advice. Past pattern detection does not guarantee future outcomes. Trade at your own risk."
- Telegram message footer (one line, after the trade-action buttons): "Educational alert. Not a recommendation."
- A `/disclaimer` page links from every footer with the full risk-disclosure text (boilerplate).
- **Acceptance**: Every page renders the short disclaimer in the footer; the `/disclaimer` page is reachable from every footer.

## Non-Functional Requirements

### Performance
- Stats pages (`/stats`, `/how-it-works`) render aggregated numbers from a cached daily computation — no live SQL on page load.
- `/recent-signals` paginates at 30 rows, lazy-loads the rest on scroll.

### Reliability
- Stats computation is a nightly cron — if the cron fails, the page shows yesterday's numbers with a "stats refreshed at X" timestamp. Never shows a hard error.
- If the historical alert archive grows beyond a threshold, the `/recent-signals` table queries only the most recent 90 days (older data archived for the EOD Report but not browsed publicly).

### Legal
- No marketing copy may use the words: "guarantee", "profit", "winning", "make money", "beat the market", "outperform", or "win rate" in proximity to platform claims. (Operators of education content can audit by running a regex check.)
- All testimonials require explicit user consent + a "results may vary" attribution.

## Out of Scope

- Personalized recommendations engine ("you should look at NVDA today")
- Public leaderboard of subscribers' trades
- Real-time portfolio tracker (separate spec — Real Trades page already exists)
- Affiliate / referral marketing
- Discord / community surface

## Success Criteria

- The `/methodology` and `/how-it-works` pages are in the top 5 marketing pages by view count within 60 days of cutover.
- The `/recent-signals` page is reached by ≥40% of new visitors before sign-up (validates that "show me what it detects" is a key conversion path).
- Zero compliance escalations / takedown requests in the 90 days following cutover.
- The tier-cap upgrade modal converts ≥10% of cap-hit events into Pricing page visits.

## Open Questions

- Should `/recent-signals` be public (logged-out visitors can browse) or gated to free-account holders? Pro: public gives marketing fuel; Con: full alert archive visibility might give competitors a roadmap. **Default**: public for the most recent 7 days, gated for older.
- Are there state-level financial-services registration requirements triggered by the language we use? **Action**: legal review before cutover. Bias is toward conservative wording until cleared.
