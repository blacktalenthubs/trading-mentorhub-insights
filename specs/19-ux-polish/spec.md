# Feature Specification: UI/UX Polish — Initial User Feedback

**Status**: In Progress
**Created**: 2026-04-07
**Updated**: 2026-04-07
**Author**: AI-assisted
**Priority**: High — directly impacts trial-to-paid conversion

## Overview

Polish the TradeCoPilot UI based on initial user feedback and competitive analysis of Robinhood, Webull, and TradingView. Focus areas: theme readability, chart controls organization, navigation, auth flows, and layout improvements.

## Current State (Post Overnight Build)

Features already shipped that address some feedback:
- **Score sorting** — watchlist sortable by Score/A-Z toggle (DONE)
- **Score badges** — numeric tradeability scores (0-100) with color coding (DONE)
- **TOP badge** — highest-scored symbol highlighted (DONE)
- **Sector Rotation strip** — compact horizontal bar above chart (DONE)
- **Options Flow panel** — collapsible on right side (DONE)
- **Sidebar** — already icon-based on left with tooltips (PARTIALLY DONE)

## Remaining Problems

From the current UI screenshot:
1. **MA toggles still scattered** — EMA 50, EMA 100, EMA 200, SMA 20, SMA 50, SMA 100, SMA 200, VWAP spread across two rows at the top of the chart. Cluttered, takes vertical space.
2. **Dark theme readability** — secondary text still hard to read, backgrounds too dark in some areas
3. **Sidebar needs full collapse** — currently shows icons but doesn't collapse to save space. No expand/collapse toggle.
4. **Day Trades/Swing Trades hidden** — only accessible via the Trades page tab. Should be in sidebar or easily accessible from Trading page.
5. **No forgot password** — still missing
6. **No email verification** — still missing
7. **Right panel crowded** — AI Coach + Options Flow + Signal Feed stacked vertically, hard to navigate

## Design Research Summary

**Competitive analysis** (Robinhood, Webull, TradingView):
- Background colors: Robinhood #1E2124, TradingView #131722 (never pure black)
- MA controls: Webull uses checkbox panel via "Indicators" button; TradingView uses indicator search modal
- Timeframe: compact pills, grouped intraday vs daily
- Sidebar: TradingView icon rail (48px) with flyout panels on click
- Watchlist: column header sorting with arrow indicators (Webull)

## Functional Requirements

### FR-1: Theme Improvements (Readability)
- Update surface-0 background from current to TradingView-inspired #131722 (navy-tinted dark)
- Increase contrast for text-muted and text-faint to meet WCAG AA (4.5:1)
- Soften borders — use more subtle dividers between sections
- Ensure bullish green and bearish red are readable on new background
- Acceptance: All body text passes WCAG AA contrast check

### FR-2: MA/Indicator Container
- Replace the two scattered rows of MA buttons with a single "Indicators" popover/dropdown
- Button labeled "Indicators" or chart icon on the chart toolbar
- Popover shows checkboxes grouped:
  - **EMAs**: 5, 20, 50, 100, 200
  - **SMAs**: 20, 50, 100, 200
  - **Other**: VWAP, Levels, Wicks
- Active indicators show as small colored dots or pills next to the button
- Current: ~15 buttons across 2 rows → Target: 1 button + popover
- Acceptance: All indicators accessible from one button, chart toolbar is one clean row

### FR-3: Timeframe Selector Cleanup
- Compact single row: 1m | 5m | 15m | 30m | 1H | 4H | D | W | M
- Smaller text, tighter padding
- Active timeframe: accent fill
- Group separator between intraday (1m-4H) and position (D-M)
- Acceptance: Fits on one line without wrapping on 1280px screens

### FR-4: Collapsible Sidebar
- Add expand/collapse toggle at bottom of sidebar
- Collapsed: icon rail (48px) with tooltip on hover showing label
- Expanded: current width with icon + text labels
- Auto-collapse on screens < 1280px
- Persist state in localStorage
- Show active page indicator (highlight/accent bar on current page icon)
- Acceptance: Toggle works, state persists, tooltips show on hover when collapsed

### FR-5: Trades Accessibility
- Add "Trades" to sidebar as a dedicated nav item (not hidden behind a tab)
- Show badge with open positions count (e.g., "3" badge on Trades icon)
- Clicking opens Trades page directly (Day Trades tab by default)
- On Trading page: add a floating "Open Positions" mini-panel showing active trade count + P&L summary
- Acceptance: Users can reach trades in 1 click from any page

### FR-6: Right Panel Organization
- Make right panel sections collapsible with clear headers:
  - **AI Coach** (collapsible, starts expanded)
  - **Options Flow** (collapsible, starts collapsed)
  - **Signal Feed** (collapsible, starts expanded)
- Each section header: icon + label + count badge + collapse arrow
- Remember collapsed state per session
- Acceptance: Each section independently collapsible, states persist

### FR-7: Forgot Password Flow
- "Forgot password?" link on login page
- Enter email → receive reset link (valid 1 hour)
- Click link → set new password page
- Success message → redirect to login
- Acceptance: User can reset password without admin help

### FR-8: Email Verification
- New users receive verification email after registration
- Unverified banner: "Verify your email to unlock all features" (non-blocking)
- Click link in email → account verified, banner removed
- Acceptance: Email sent within 30 seconds of registration

## User Scenarios

### Scenario 1: Trader on 13" Laptop
**Actor**: Pro user on a small screen
**Steps**:
1. Sidebar auto-collapses to icon rail
2. Opens "Indicators" popover → toggles EMA 20 and 200
3. Chart shows clean with just 2 MAs, no toolbar clutter
4. Collapses Options Flow panel → more room for Signal Feed
**Expected Outcome**: Maximum chart space, all features accessible

### Scenario 2: New User First Impression
**Actor**: Trial user from ad campaign
**Steps**:
1. Lands on Trading page — clean dark theme, readable text
2. Sees organized toolbar — one "Indicators" button, compact timeframes
3. Right panel: AI Coach ready, Signal Feed with live alerts
4. Sidebar clearly shows: Trading, Trades (3 open), Settings
**Expected Outcome**: Professional first impression, no visual overwhelm

### Scenario 3: Locked Out User
**Actor**: User who forgot password
**Steps**:
1. Clicks "Forgot password?" on login
2. Enters email, receives reset link
3. Sets new password, logs in
**Expected Outcome**: Self-service in under 2 minutes

## Success Criteria

- [ ] MA/indicator toolbar reduced from 15+ buttons to 1 button + popover
- [ ] Theme passes WCAG AA contrast for all body text
- [ ] Sidebar collapses to < 60px with working tooltips
- [ ] Trades accessible in 1 click from any page
- [ ] Right panel sections independently collapsible
- [ ] Password reset flow under 2 minutes
- [ ] 5 users report improved readability (qualitative)

## Edge Cases

- Ultra-wide monitor — sidebar expanded, right panel gets more width
- Color blind users — green/red supplemented with ▲/▼ icons
- Password reset email in spam — clear sender name, subject line
- All right panel sections collapsed — show "expand" hint

## Assumptions

- Theme changes via Tailwind CSS custom properties
- Sidebar collapse is frontend-only
- SMTP configured (already sending notifications)
- Password reset uses same token pattern as Telegram link tokens

## Scope

### In Scope
- Theme color update (readability)
- MA/indicator container (popover)
- Timeframe cleanup
- Collapsible sidebar with icon rail
- Trades nav visibility
- Right panel collapsible sections
- Forgot password
- Email verification (non-blocking)

### Out of Scope
- Light theme / theme toggle (future)
- Custom chart colors
- Drag-to-reorder watchlist
- Mobile layout (covered in iOS spec)

## Clarifications

_Added during `/speckit.clarify` sessions_
