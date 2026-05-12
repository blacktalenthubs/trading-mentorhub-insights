# Feature Specification: Education Module — Lesson Framework + Foundations Track

**Status**: Draft
**Created**: 2026-05-12
**Author**: mentorhubnetworks@gmail.com
**Related**: Split out of `47-platform-rebrand-v2` for scope management.

## Overview

This spec describes the **Education product surface** of the platform — the lesson framework, AI tutor, and content delivery layer that complements the live alert stream. Spec 47 (Rebrand Core) creates the marketing path to this surface; this spec defines what the surface itself contains and how lessons render, link to alerts, and provide AI-assisted learning.

The user's trading methodology already exists in commit messages, Pine code, and the operator's head. This spec turns that methodology into a curriculum that converts visitors into paying subscribers and retains them by teaching the *why* behind every alert.

## Problem Statement

**Who is affected**:
- Prospective customers with limited trading background who land on the marketing site
- Existing free-tier users who don't understand the alerts well enough to act on them
- Paid subscribers in low-volatility weeks who have no in-app activity to engage with

**Pain points**:
- The alert stream alone has no on-ramp for non-traders. A visitor sees "PDH break LONG NVDA $217.60" and bounces.
- The platform has no productized way to monetize the trading *methodology* itself, separate from the live signal stream. Methodology is the moat; alerts alone are commoditized.
- Subscribers churn during quiet markets because there's nothing else to engage with.

**Success looks like**: A new visitor can complete a Foundations track, identify the EMA framework state and a PDH/PDL setup on a blind chart, and feel confident reading any live alert from the platform.

## Functional Requirements

### FR-1: Lesson Data Model
- Each lesson is a persistent content unit with: title, slug, track, ordinal, prerequisite_lesson_ids, linked_pattern_keys, sample_alert_ids, body (Markdown), estimated_minutes, difficulty.
- Tracks group lessons in ordered sequences: Foundations (cutover), Levels, EMA Framework, Confluence, Risk (post-cutover expansion).
- Lessons are versioned — edits don't invalidate completion records.
- **Acceptance**: Adding a new lesson via a content commit appears live in the Learn UI within 5 minutes (next deploy).

### FR-2: Lesson Rendering
- Lessons render as a single scrollable page with: heading, table-of-contents, body (Markdown supporting code, blockquotes, images, callouts), annotated chart embeds, "see this live" links to historical alerts, and an AI tutor input box pinned to the bottom.
- Mobile-first: lessons must read cleanly on iPhone SE width (320px) with no horizontal scroll.
- **Acceptance**: A first-time visitor can complete a 10-minute lesson on a phone without zooming, without scrolling sideways, with all chart annotations readable.

### FR-3: Annotated Chart Examples
- Each lesson can reference one or more historical alert IDs. The renderer pulls the alert's symbol + entry/stop/target levels + setup context and renders an annotated mini-chart inline.
- Charts use the same Long/Short Position trade-box rendering as HIGH-conviction Telegram alerts (via chart-img.com).
- If a referenced alert has been deleted or anonymized, the chart degrades gracefully to a static placeholder ("This example chart is no longer available").
- **Acceptance**: A lesson on PDH breaks shows ≥3 real alert examples from the platform's archive with rendered charts in <2s each.

### FR-4: AI Tutor Inside Lessons
- A learner can ask the AI tutor questions inside any lesson context. The tutor has access to: the lesson body, the lesson's pattern definition, the user's progress so far, and (optionally) the most recent live alert for that pattern.
- The tutor responds in plain English, references the relevant lesson section, and offers to elaborate.
- Tutor responses are rate-limited per tier: Free tier 3/day, Pro 50/day, Premium unlimited (matches existing `ai_queries_per_day` limits from `api/app/tier.py`).
- **Acceptance**: A learner asks "what's the difference between EMA8 and SMA8?" and receives a contextually-correct answer that references the lesson's EMA framework section.

### FR-5: Learner Progress
- The system tracks per-user per-lesson: started_at, last_viewed_at, completed_at, time_spent_seconds.
- Progress is shown as a track-level percentage on the Learn landing.
- Lessons completed in the last 7 days are highlighted on the dashboard.
- A learner can mark a lesson as "favorited" for re-review.
- **Acceptance**: A user closes a half-read lesson, returns next day, and the lesson opens at their last scroll position with a "continue where you left off" hint.

### FR-6: Cross-Linking to Live Alerts
- Each lesson exposes the pattern_keys it teaches (e.g., `staged_pdh_break`, `ma_bounce_long_v3_ema21`).
- When a live alert fires for a pattern, the Telegram message includes a "Why this fires → [Lesson Name]" deep link (URL with `?source=tg&alert_id=NNN`).
- When the lesson loads from a Telegram deep link, the top of the lesson shows: "This lesson explains the alert you just received on $SYM."
- The lesson body includes a live widget: "Last fired today at HH:MM for $SYM" pulling from the most recent matching alert.
- **Acceptance**: A Telegram alert for `staged_pdh_break` deep-links to the PDH Break lesson; the lesson shows the originating alert's chart at the top.

### FR-7: Foundations Track (Cutover Content)
The 5-lesson Foundations track must ship at cutover. Topics:

1. **Chart Literacy 101** — what a candle is, time vs. price axes, volume bars, why we use 5m/15m/1h timeframes.
2. **The EMA Framework Intro** — the 8/21/50/100/200 EMAs, why this set, what each represents in trader psychology.
3. **Prior Day Levels (PDH/PDL) Basics** — yesterday's high and low as today's structural memory; how alerts fire when they're broken or defended.
4. **Reading a Structured Alert** — anatomy of a Telegram message from this platform; what each line means; how to act on a HIGH verdict.
5. **Risk + Position Sizing** — the R-multiple framework; why entry-stop distance defines your share count; when to take T1 vs T2 vs trail.

Each lesson ≤10 minutes reading time, ≥2 annotated chart examples from the alert archive, ≥1 AI-tutor prompt suggestion.

**Acceptance**: A user with no prior trading background completes the Foundations track and, on a blind chart screenshot, correctly identifies (a) the current EMA framework state (which EMAs are above/below price) and (b) where the prior-day high/low would be, ≥80% of the time.

### FR-8: Free-Tier Preview
- The first lesson (Chart Literacy 101) is fully readable for anonymous + free-tier visitors.
- The remaining 4 Foundations lessons show a preview (first section) + sign-in/upgrade prompt for the rest.
- The AI tutor is gated to paid tiers (Pro+) — free tier sees a "sign in to ask the tutor" prompt.
- **Acceptance**: An anonymous visitor can read Chart Literacy 101 end-to-end without any sign-up wall.

## Non-Functional Requirements

### Performance
- Lesson page reaches first interaction within 3 seconds on mid-tier mobile connections.
- AI tutor response time p50 < 4 seconds, p95 < 10 seconds.

### Reliability
- Lesson rendering doesn't depend on the alert API — if alert backend is down, lessons still render (chart embeds degrade gracefully).
- AI tutor uses the same model + auth setup as the existing AI Coach — no new integration.

### Content Quality
- Each lesson is reviewed for trading-advice safety language. Lessons teach pattern recognition, not personalized recommendations.
- Charts are real historical signals — no fabricated examples.

## Key Entities

| Entity | Description | Key Fields |
|--------|-------------|------------|
| Lesson | Markdown-bodied lesson content with metadata | id, slug, title, track_id, ordinal, prerequisite_ids, pattern_keys, sample_alert_ids, body_markdown, estimated_minutes, difficulty |
| Track | Ordered sequence of lessons | id, name, ordered_lesson_ids, completion_criteria |
| LessonProgress | Per-user per-lesson progress | user_id, lesson_id, started_at, last_viewed_at, completed_at, time_spent_seconds, favorited |
| LessonTutorChat | AI tutor conversation thread per (user, lesson) | id, user_id, lesson_id, messages_json, created_at |

## Out of Scope (for cutover)

- Video lesson production
- Live cohort / instructor-led classes
- Quizzes with grading
- Lesson localization (English only)
- Discussion forums / comments on lessons
- Lesson recommendations engine ("you might like…")
- Custom user-generated lessons / community uploads

## Success Criteria

- Within 60 days of cutover, ≥40% of paid subscribers have viewed at least one lesson.
- Within 60 days of cutover, ≥20% have completed the Foundations track.
- Within 90 days of cutover, ≥30% of new free-account creations originate from the Education / Learn path.
- ≥20% of subscribers who receive a Telegram alert click through to the explainer lesson at least once per month.
