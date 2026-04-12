# Feature Specification: Beginner Trader Guidance System

**Status**: Draft
**Created**: 2026-04-07
**Author**: AI-assisted
**Priority**: High — expands addressable market beyond experienced traders

## Overview

Make TradeCoPilot equally valuable for beginner traders who don't understand trading terminology. The platform currently assumes knowledge of terms like "EMA bounce," "PDL reclaim," "VWAP," "R:R ratio," and "session low double bottom." A new user who doesn't know these terms gets alerts they can't interpret, coaching they can't follow, and a dashboard full of acronyms. This feature adds contextual education, plain-English explanations, and guided experiences so beginners extract the same value as experienced traders.

## Problem Statement

TradeCoPilot's current user base is experienced traders who understand chart patterns and trading vocabulary. But the largest market opportunity is **beginner traders** — people who want to learn and trade but feel overwhelmed by:

1. **Alert jargon** — "MA bounce 20" / "PDL reclaim" / "session high double top" means nothing to a beginner
2. **Chart complexity** — EMAs, VWAP, support/resistance lines with no explanation of what they represent
3. **No learning path** — experienced traders know to check the chart, read the setup, decide. Beginners don't know where to start
4. **AI coach assumes expertise** — the coach says "pullback to 20EMA at $253" but doesn't explain what a pullback or EMA is

**Impact**: Beginners sign up, see a wall of unfamiliar terms, and churn during the 3-day trial. They never experience the value because they can't understand what they're looking at.

## Functional Requirements

### FR-1: Beginner Mode Toggle
- Users can toggle "Beginner Mode" on/off in Settings
- New users default to Beginner Mode ON (can turn off anytime)
- Beginner Mode changes how information is displayed — not what information is available
- No features are removed — everything is still accessible, just explained differently
- Acceptance: Toggle exists in Settings, persists across sessions, affects all pages

### FR-2: Plain-English Alert Descriptions
- Every alert type has a beginner-friendly description alongside the technical one
- Examples:
  - "MA bounce 20" → "Price dropped to a key average price line and bounced back up — a common buy signal"
  - "PDL reclaim" → "Price fell below yesterday's lowest point, then recovered above it — buyers stepping in"
  - "Session high double top" → "Price tried to break a high point twice and failed — sellers are in control"
  - "VWAP loss" → "Price dropped below the day's average trading price — momentum shifting down"
- In Beginner Mode, the plain-English description appears FIRST, technical term in small text below
- Acceptance: Every alert type in the system has a beginner description, visible in Signal Feed and Telegram

### FR-3: Glossary Tooltips
- Trading terms throughout the platform show a dotted underline in Beginner Mode
- Hovering (desktop) or tapping (mobile) shows a tooltip with a 1-sentence definition
- Key terms to cover: EMA, SMA, VWAP, PDL, PDH, Support, Resistance, RSI, R:R, Stop Loss, Target, Entry, Breakout, Breakdown, Bounce, Consolidation, Session, Prior Day, Conviction
- Tooltips are contextual — "RSI 30" tooltip says "RSI measures momentum. Below 30 = oversold, prices often bounce here"
- Acceptance: At least 25 trading terms have tooltips, visible on hover/tap in Beginner Mode

### FR-4: AI Coach Beginner Persona
- In Beginner Mode, the AI coach adjusts its language:
  - Avoids jargon or explains terms inline when first used
  - Uses analogies: "Think of the 200-day moving average like a floor — price tends to bounce off it"
  - Adds "WHY this matters" after each recommendation
  - Still gives specific prices and levels (actionable), but explains the reasoning in simple terms
- Example response in Beginner Mode:
  - "AAPL is sitting on a price floor at $251 (the 200-day average — a level big institutions watch). If it closes above this today, that's a sign buyers are defending it. Entry: $253, Stop: $249 (if it breaks below the floor, the trade is wrong)."
- Acceptance: Coach responses in Beginner Mode use no unexplained jargon

### FR-5: "What Should I Do?" Quick Action
- New prominent button on the Trading page: "What should I do right now?"
- Clicking it asks the AI coach for a simple, actionable summary:
  - Which symbol has the best setup right now (from Smart Watchlist)
  - Whether to buy, wait, or avoid
  - Specific entry price and stop, explained simply
  - Confidence level in plain English ("This setup has worked 8 out of 10 times historically")
- Acceptance: Button visible on Trading page, response appears within 3 seconds, uses beginner language

### FR-6: Guided First Trade Experience
- After registration, if Beginner Mode is on, show a guided overlay:
  1. "This is your watchlist — these are the stocks you're tracking" (highlight watchlist)
  2. "When the system spots a good setup, it appears here" (highlight Signal Feed)
  3. "Tap 'Took It' if you want to follow this trade, 'Skip' if not" (highlight action buttons)
  4. "Your AI coach can explain anything — just ask" (highlight coach input)
- 4-step guided tour, skippable, shown once per account
- Acceptance: Tour triggers on first login in Beginner Mode, completes in under 60 seconds

### FR-7: Alert Confidence in Plain English
- Replace score numbers (e.g., "Score 85") with human-readable labels in Beginner Mode:
  - Score 80-100 → "Strong setup — this pattern works most of the time"
  - Score 60-79 → "Decent setup — worth watching, use a tight stop"
  - Score 40-59 → "Risky — only take this if you see other confirmation"
  - Score 0-39 → "Low probability — more experienced traders only"
- The numeric score still shows in small text for reference
- Acceptance: Score labels visible in Signal Feed and alert cards in Beginner Mode

### FR-8: Learning Moments on Closed Trades
- When a trade hits its target or stop, show a "What happened?" card:
  - For winners: "This trade worked because price bounced off the $251 support level as expected. The stop at $249 was never hit. You made $4.30 per share."
  - For losers: "Price broke below the support level at $251 — this means buyers weren't strong enough. The stop at $249 protected you from a bigger loss."
- Uses the existing trade review AI but with beginner-friendly language
- Acceptance: Learning cards appear for closed trades in Beginner Mode

## User Scenarios

### Scenario 1: Complete Beginner's First Session
**Actor**: New user, never traded before, signed up from Instagram ad
**Trigger**: First login after registration
**Steps**:
1. Sees guided tour overlay — learns what watchlist, Signal Feed, and AI coach are
2. An alert fires: "NVDA — Price bounced off a key support level ($173). Buyers are stepping in."
3. Reads the plain-English description, sees "Strong setup" label
4. Taps "Took It" (guided tour showed this)
5. Opens AI coach, asks "Is this a good trade?"
6. Coach responds in simple language: "NVDA is at a price floor that big institutions watch..."
7. Price hits target — sees "What happened?" card explaining the win
**Expected Outcome**: Beginner completes a full trade cycle with understanding, not just mimicry

### Scenario 2: Beginner Uses "What Should I Do?"
**Actor**: Beginner during market hours, unsure what to look at
**Trigger**: Clicks "What should I do right now?"
**Steps**:
1. System checks Smart Watchlist for top-ranked symbol
2. Returns: "Right now, SPY at $655 is the best setup. It's testing a support level (a price where buyers usually step in). If you buy here with a stop at $653, you risk $2 to make $5. This pattern has worked 75% of the time."
3. User decides whether to act
**Expected Outcome**: Beginner gets clear, actionable guidance without needing to interpret charts

### Scenario 3: Experienced Trader Turns Off Beginner Mode
**Actor**: Experienced trader who finds Beginner Mode verbose
**Trigger**: Goes to Settings, toggles Beginner Mode off
**Steps**:
1. All tooltips, plain-English descriptions, and guided elements disappear
2. Platform returns to compact, jargon-heavy default
3. AI coach switches back to expert persona (concise, technical)
**Expected Outcome**: No impact on experienced user's workflow

## Key Entities

| Entity           | Description                              | Key Fields                                    |
| ---------------- | ---------------------------------------- | --------------------------------------------- |
| Alert Type       | Each type has a beginner description     | type_id, technical_name, beginner_description |
| User Preference  | Beginner mode toggle                     | user_id, beginner_mode (boolean)              |
| Glossary Term    | Trading term with simple definition      | term, definition, context_example             |
| Guided Tour Step | Onboarding step with highlight target    | step_number, title, description, target_element |

## Success Criteria

- [ ] Beginner users complete the guided tour in under 60 seconds
- [ ] 70% of beginner users take action on their first alert (Took or Skip, not ignored)
- [ ] Beginner user 3-day trial retention matches or exceeds experienced user retention
- [ ] AI coach responses in Beginner Mode contain zero unexplained jargon (verified by review of 20 responses)
- [ ] At least 25 trading terms have glossary tooltips
- [ ] Every alert type (30+) has a plain-English beginner description
- [ ] "What should I do?" generates a response within 3 seconds
- [ ] Beginner Mode toggle has zero impact on page load time

## Edge Cases

- Beginner receives a complex multi-signal confluence alert — simplify to the primary signal, note "multiple factors confirm this setup"
- Beginner asks AI coach a highly technical question — coach should still answer accurately, just in simpler language
- Beginner Mode user shares a screenshot — the plain-English text is visible, which is good for social sharing
- Alert fires in Telegram in Beginner Mode — Telegram message includes the beginner description too (not just web)
- Guided tour on mobile — ensure overlay doesn't cover critical UI elements on small screens

## Assumptions

- Beginner Mode is a frontend display preference — no separate data pipeline needed
- The AI coach persona switch is a prompt modification, not a separate model
- Glossary terms are static content (not AI-generated), maintained in a content file
- The platform's signal quality remains the same — Beginner Mode changes presentation, not analysis
- Beginner descriptions for all 30+ alert types can be written as static content

## Constraints

- Beginner Mode must not slow down the platform (no extra API calls for descriptions)
- Plain-English descriptions must still be accurate — oversimplification that misleads is worse than jargon
- "Not financial advice" disclaimer must remain visible in all modes
- Guided tour must be skippable and never shown again after completion

## Scope

### In Scope
- Beginner Mode toggle (Settings, defaults ON for new users)
- Plain-English alert descriptions for all alert types
- Glossary tooltips for 25+ trading terms
- AI coach beginner persona (prompt modification)
- "What should I do?" quick action button
- Guided first-trade tour (4 steps)
- Score-to-label translation
- Learning moments on closed trades

### Out of Scope
- Video tutorials or courses (future content initiative)
- Paper trading specifically for beginners (already exists for Premium)
- Gamification (achievements, streaks, levels)
- Community/social features (chat, forums)
- Multi-language support
- Separate beginner dashboard layout (same layout, different language)

## Clarifications

_Added during `/speckit.clarify` sessions_
