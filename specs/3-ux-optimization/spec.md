# Feature Specification: UX Optimization Pass

**Status**: In Progress
**Created**: 2026-04-04
**Priority**: High — directly impacts user experience and adoption

---

## Overview

Comprehensive UX audit identified 25 issues across all pages. This spec tracks fixes from critical (blocking user actions) to polish (nice-to-have animations). Goal: production-grade UX before V2 cutover.

---

## Issues Fixed (2026-04-04)

| # | Issue | File | Status |
|---|-------|------|--------|
| F1 | Watchlist add/remove lag — no optimistic updates | hooks.ts | DONE |
| F2 | Active positions not populating after "Took" | alerts.py, hooks.ts | DONE |
| F3 | Chart zoom — shows all data, too zoomed out | CandlestickChart.tsx | DONE |
| F4 | Registration page ugly/inconsistent with login | RegisterPage.tsx | DONE |
| F5 | Alert ack (Took/Skip) has no instant UI feedback | hooks.ts | DONE |

---

## HIGH Priority — DONE (2026-04-04)

| # | Issue | File(s) | Status |
|---|-------|---------|--------|
| H1 | Onboarding Back button | OnboardingPage.tsx | DONE — Back buttons on steps 2 and 3 |
| H2 | Toast notifications | Toast.tsx, hooks.ts, App.tsx | DONE — Toast system + wired to watchlist add/remove |
| H3 | Empty states with CTAs | DashboardPage.tsx | DONE — "No signals" has explanation + two CTA buttons |
| H4 | Portfolio size configurable | SettingsPage.tsx, TradingPage.tsx | DONE — Position Sizing section in Settings, reads from localStorage |
| H5 | Chart loading skeleton | TradingPage.tsx | DONE — Animated bar skeleton while chart loads |
| H6 | Mobile nav safe area | AppLayout.tsx | DONE — pb-14 on main content for mobile bottom bar |

---

## MEDIUM Priority — DONE (2026-04-04)

| # | Issue | Status |
|---|-------|--------|
| M1 | Disabled buttons cursor-not-allowed | DONE — global CSS rule |
| M2 | Inline form validation (register) | DONE — password mismatch shows live as user types |
| M3 | LearnDetail retry on error | DONE — Retry + Back to Library buttons |
| M4 | EquityCurve theme colors | DONE — default green, transparent background |
| M5 | Telegram setup UX | DONE — clearer CTA "Open in Telegram & Tap Start", expiry warning |
| M6 | Payment error guidance | DONE — context-specific help (declined, expired, generic) |
| M7 | API failure states | DONE — alerts + scanner show error with retry |
| M8 | WatchlistBar UX | SKIPPED — legacy component, replaced by inline search on Trading page |
| M9 | Chart crosshair | DONE — mode: 1 enables interactive price tracking |

---

## LOW Priority — Polish

| # | Issue | File(s) | Description | Effort |
|---|-------|---------|-------------|--------|
| L1 | No keyboard nav in nav rail | AppLayout.tsx:55 | Tab key doesn't cycle through nav items | Medium |
| L2 | Color-only indicators (accessibility) | Multiple | Market status, grade badges use only color — needs icons/patterns for color-blind users | Medium |
| L3 | No micro-interactions | Multiple | No transitions on timeframe switch, no success animation on onboarding complete | Medium |
| L4 | Chart error boundary | CandlestickChart.tsx | Silent failures on bad data — should show error fallback UI | Small |
| L5 | Missing chart skeleton loader | CandlestickChart.tsx | Show shimmer while chart renders | Small |
| L6 | Inconsistent input styling | Multiple | Some inputs have focus:border-accent, others don't. Padding varies. | Small |
| L7 | Range slider unstyled | SettingsPage.tsx | Score filter slider uses browser default — should match dark theme | Small |
| L8 | No confetti/success on onboarding done | OnboardingPage.tsx | Step 4 "You're all set" is plain — could celebrate | Tiny |
| L9 | Onboarding progress not saved | OnboardingPage.tsx | If user closes browser mid-wizard, starts over | Medium |
| L10 | Resizable watchlist pane | TradingPage.tsx | User requested ability to adjust left panel width | Medium |

---

## Acceptance Criteria

### HIGH items done when:
- [ ] User can navigate back in onboarding wizard
- [ ] Visible toast/feedback on every mutation (add, remove, took, skip, save)
- [ ] Empty states have actionable CTAs
- [ ] User can set their own account size for position sizing
- [ ] Charts show skeleton while loading
- [ ] Mobile users don't have content hidden under nav bar

### MEDIUM items done when:
- [ ] Disabled buttons show not-allowed cursor
- [ ] Register form shows inline validation as user types
- [ ] Learn pages have retry buttons on error
- [ ] Equity curve uses theme colors
- [ ] Telegram setup flow is clear and linear
- [ ] Payment errors give actionable guidance
- [ ] API failures show error states (not blank)

### LOW items done when:
- [ ] Keyboard-navigable nav rail
- [ ] Color-blind friendly indicators
- [ ] Smooth transitions between states
- [ ] Chart has error boundary fallback

---

## Test Plan

### Manual E2E Tests
1. Register new user → verify styled form, inline validation, onboarding redirect
2. Onboarding: pick symbols → back → forward → connect Telegram → skip → prefs → done
3. Trading page: add symbol → instant appear. Remove → instant disappear. Error → rollback.
4. Dashboard: click "Took" on alert → position appears in Active Positions immediately
5. Chart: loads with zoomed-in view (last 80 bars), not all data
6. Mobile: nav bar doesn't overlap content on iPhone
7. Settings: save → visible toast. Telegram link → clear instructions.
8. Empty dashboard (new user): CTAs visible, not just "No data"

### Performance Checks
- Watchlist add/remove: <100ms visual update (optimistic)
- Chart render: <500ms from data load to visible candles
- Alert ack: <100ms visual state change
- Page transitions: no layout shift or flash
