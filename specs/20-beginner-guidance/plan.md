# Implementation Plan: Beginner Trader Guidance System

**Spec**: [spec.md](spec.md)
**Branch**: 20-beginner-guidance
**Created**: 2026-04-07

## Technical Context

| Item | Value |
|------|-------|
| Language | Python 3.9+ (backend), TypeScript (frontend) |
| Framework | FastAPI (API), React + Tailwind (frontend) |
| Database | SQLite (local) / Postgres (production) |
| Notifications | Telegram Bot API (per-user DMs) |
| AI | Anthropic API (Haiku/Sonnet) |
| Deployment | Railway (auto-deploy on push to main) |

### Dependencies
- No new dependencies needed
- Beginner descriptions are static content (no new API)
- AI coach persona is a prompt modification (no model change)
- Glossary tooltips are pure frontend (React state + CSS)

### Integration Points
- `analytics/trade_coach.py` — AI coach prompt modification for beginner persona
- `alerting/notifier.py` — Telegram message formatting for beginner descriptions
- `api/app/models/user.py` — Add `beginner_mode` column
- `web/src/` — Frontend components for tooltips, tour, mode toggle

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| Protect Business Logic | PASS | No changes to alert rules, signal engine, or monitor. Only presentation layer. |
| Test-Driven Development | PASS | Tests for beginner descriptions mapping, coach prompt, user preference API |
| Local First | PASS | All changes testable locally — frontend + API |
| Database Compatibility | PASS | Single column addition: `beginner_mode BOOLEAN DEFAULT 1` — works on both |
| Alert Quality | PASS | Alert signals unchanged — only display text changes |
| Single Notification Channel | PASS | Telegram messages enhanced with beginner text, channel unchanged |

## Solution Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    User (beginner_mode=true)              │
└────────────────────────┬─────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    ┌────▼────┐    ┌─────▼─────┐   ┌─────▼─────┐
    │ Signal  │    │ AI Coach  │   │ Telegram  │
    │ Feed    │    │ Chat      │   │ DM        │
    └────┬────┘    └─────┬─────┘   └─────┬─────┘
         │               │               │
    ┌────▼────┐    ┌─────▼─────┐   ┌─────▼─────┐
    │Beginner │    │ Beginner  │   │ Beginner  │
    │Desc Map │    │ Prompt    │   │ Formatter │
    │(static) │    │(dynamic)  │   │(static)   │
    └─────────┘    └───────────┘   └───────────┘
```

### Data Flow
1. Alert fires → monitor records in DB (unchanged)
2. Frontend renders alert → checks `user.beginner_mode`
3. If beginner: shows plain-English description from static map + glossary tooltips
4. AI coach: if beginner, prepends beginner persona instructions to system prompt
5. Telegram: if beginner, appends plain-English line to alert message

### Files to Modify

| File | Change | Risk |
|------|--------|------|
| `api/app/models/user.py` | Add `beginner_mode` column | Low |
| `api/app/routers/settings.py` | Add beginner mode toggle endpoint | Low |
| `api/app/schemas/auth.py` | Add `beginner_mode` to user response | Low |
| `analytics/trade_coach.py` | Add beginner persona to prompt | Low |
| `alerting/notifier.py` | Add beginner descriptions to Telegram | Low |
| `web/src/pages/TradingPage.tsx` | Glossary tooltips, "What should I do?" button | Med |
| `web/src/pages/RealTradesPage.tsx` | Learning moments on closed trades | Low |
| `web/src/components/ai/ChatWindow.tsx` | Coach beginner context | Low |

### Files to Add

| File | Purpose |
|------|---------|
| `api/app/data/beginner_glossary.py` | Static glossary: 25+ terms with definitions |
| `api/app/data/alert_descriptions.py` | Plain-English descriptions for all 30+ alert types |
| `web/src/components/GlossaryTooltip.tsx` | Reusable tooltip component for trading terms |
| `web/src/components/GuidedTour.tsx` | 4-step onboarding overlay for new users |
| `web/src/components/WhatShouldIDo.tsx` | Quick action button + AI response panel |

## Implementation Approach

### Phase 1: Data Layer + API
1. Add `beginner_mode` column to `api/app/models/user.py` (default True)
2. Add migration in `api/app/main.py` lifespan (ALTER TABLE ADD COLUMN)
3. Add `PUT /api/v1/settings/beginner-mode` endpoint in `settings.py`
4. Add `beginner_mode` to auth response schema
5. Create `api/app/data/beginner_glossary.py` — 25+ terms
6. Create `api/app/data/alert_descriptions.py` — 30+ alert types
7. Add `GET /api/v1/settings/glossary` endpoint (returns glossary terms)

### Phase 2: AI Coach Beginner Persona
1. Modify `analytics/trade_coach.py` `format_system_prompt()`:
   - Accept `beginner_mode` parameter
   - If True, prepend beginner persona instructions
   - Instructions: use analogies, explain terms inline, add "WHY this matters"
2. Modify `api/app/routers/intel.py` coach endpoint:
   - Pass `beginner_mode` from user context to `format_system_prompt()`
3. Add "What should I do?" endpoint in `intel.py`:
   - Uses Smart Watchlist top symbol + AI coach with beginner prompt

### Phase 3: Frontend — Signal Feed + Tooltips
1. Create `GlossaryTooltip.tsx` — hover/tap tooltip component
2. Modify Signal Feed in `TradingPage.tsx`:
   - If `beginner_mode`: show plain-English description first, technical below
   - Wrap trading terms in `<GlossaryTooltip>`
3. Add score labels (Strong/Decent/Risky/Low) alongside numeric scores
4. Add "What should I do?" button to Trading page

### Phase 4: Guided Tour + Learning Moments
1. Create `GuidedTour.tsx` — 4-step overlay with highlights
2. Trigger on first login when `beginner_mode=true`
3. Add learning moment cards to `RealTradesPage.tsx` for closed trades
4. Store `tour_completed` in localStorage

### Phase 5: Telegram Beginner Format
1. Modify `alerting/notifier.py` `_format_sms_body()`:
   - Check user's beginner_mode preference
   - If True, append plain-English description below technical alert
2. Pass `beginner_mode` through notification prefs dict

## Test Plan

### Unit Tests
- [ ] `test_beginner_glossary.py` — all 25+ terms have definitions, no empty values
- [ ] `test_alert_descriptions.py` — all alert types have beginner descriptions
- [ ] `test_coach_beginner_prompt.py` — beginner prompt includes persona instructions
- [ ] `test_score_labels.py` — score ranges map to correct labels

### Integration Tests
- [ ] `test_settings_beginner_mode.py` — toggle on/off persists across requests
- [ ] `test_coach_beginner_response.py` — coach response in beginner mode uses simple language

### E2E Validation
1. **Setup**: Register new user (beginner_mode defaults ON)
2. **Action**: View Signal Feed, open AI coach, check Telegram alert
3. **Verify**: Plain-English descriptions visible, coach uses simple language, Telegram includes beginner text
4. **Cleanup**: Toggle beginner_mode OFF, verify technical view returns

## Out of Scope
- Video tutorials (content initiative, not code)
- Gamification (achievements, streaks)
- Paper trading beginner mode (already exists for Premium)
- Light theme (separate spec #19)

## Research Notes

_No research needed — this feature uses existing infrastructure (static content, prompt modification, React components). No new dependencies or technologies._
