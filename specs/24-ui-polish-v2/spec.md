# Feature Specification: UI Polish Pass 2 — Visual Refinements

**Status**: Draft
**Created**: 2026-04-08
**Author**: AI-assisted
**Priority**: High — directly impacts user trust and professional perception

## Overview

Second round of UI polish for the TradeCoPilot Trading page based on live production screenshot review. The first polish pass (spec 19) addressed major structural issues (indicator popover, sidebar collapse, theme toggle, forgot password). This pass targets smaller but visible issues: misleading signal colors, clipped text, low-contrast annotations, alignment inconsistencies, and the SSL certificate warning that undermines trust on first visit.

## Current State

The Trading page is functional with all major features shipped. However, several visual details reduce the professional feel that trading tools demand:

- Signal Feed uses green for "Skipped" actions (implies positive when it should be neutral)
- Chart annotation bar at the bottom is low-contrast italic text, hard to read at a glance
- Sector rotation strip has very small text for sector names and percentages
- Watchlist columns are not perfectly aligned across rows
- Timestamp labels in Signal Feed are partially clipped
- The site shows "Not Secure" in the browser bar — immediate trust killer for a financial product
- Bottom chart status bar (Screenshot button, Entry/Stop indicators) is cramped and partially cut off

## Functional Requirements

### FR-1: Signal Feed — Fix "Skipped" Button Color

The "Skipped" action button in the Signal Feed currently appears in green, which implies a positive/confirmed action. Skipping an alert is a neutral/dismissive action.

- "Skipped" button should use a muted neutral color (gray) instead of green
- "Entered" or "Taken" actions should remain green (positive confirmation)
- "Stopped Out" or "Loss" actions should use the existing red
- Acceptance: Skipped buttons are visually distinct from positive action buttons; no green used for skip/dismiss actions

### FR-2: Signal Feed — Fix Clipped Timestamps

Alert timestamps (e.g., "02:46 AM", "12:33 AM") are partially overlapping with the red dot status indicators on the left edge of each signal card.

- Timestamps should be fully visible without overlapping any other element
- Maintain compact layout but ensure adequate spacing between the time, status dot, and card content
- Acceptance: All timestamp text is fully readable with no visual overlap

### FR-3: Chart Annotation Bar — Improve Readability

The bottom annotation bar showing support levels and trade context (e.g., "Support: $673.54 (50 MA) AT SUPPORT · bullish · normal · Closed bullish — look for pullback...") uses low-contrast italic text that is difficult to read quickly.

- Increase text contrast to meet WCAG AA (4.5:1 minimum)
- Use regular weight instead of italic for the primary data (support price, condition)
- The narrative portion ("look for pullback to prior day low for long entry") may remain italic to distinguish opinion from data
- Acceptance: Support level and condition labels are legible in under 1 second; passes WCAG AA contrast check

### FR-4: Sector Rotation Strip — Increase Readability

The sector strip ("Industrials +3.8%", "Materials +3.3%", etc.) is functional but the text is very small and hard to read, especially the percentage values.

- Increase font size for sector percentages (the primary data users scan for)
- Ensure sector names remain readable at the current strip height
- On smaller screens, allow horizontal scroll rather than shrinking text further
- Acceptance: Sector names and percentages are readable without leaning toward the screen on a standard laptop (13-15" at arm's length)

### FR-5: Watchlist — Column Alignment & Grammar

Prices, percentage changes, and score badges are not perfectly aligned across watchlist rows. The header shows "1 setups" instead of "1 setup".

- Align price column to right edge consistently across all rows
- Align score badges to the same horizontal position
- Fix pluralization: "1 setup" (singular), "2 setups" (plural)
- Acceptance: Columns appear visually aligned when scanning vertically; grammar is correct for all count values

### FR-6: SSL Certificate — Enable HTTPS

The browser shows "Not Secure" warning on tradingwithai.ai. For a financial product handling user credentials and trading data, this is a critical trust issue.

- Enable SSL/TLS on the production domain
- All pages served over HTTPS
- HTTP requests redirect to HTTPS (301 redirect)
- Acceptance: Browser shows lock icon (or no warning) on all pages; no mixed content warnings

### FR-7: Bottom Chart Bar — Fix Cutoff

The bottom bar containing the "Screenshot" button and Entry/Stop status indicators is cramped and partially cut off at the viewport bottom.

- Ensure the bottom bar is fully visible without scrolling
- Adequate padding between the chart annotation text and the bottom bar controls
- Entry/Stop status indicators should be fully visible with their labels
- Acceptance: All bottom bar elements are fully visible on a 768px minimum viewport height

## User Scenarios

### Scenario 1: New User Evaluating the Platform (Trial from Ad)

**Actor**: Prospective trader visiting from a paid ad
**Steps**:
1. Lands on tradingwithai.ai/trading — notices "Not Secure" in URL bar
2. Sees Signal Feed with alerts — "Skipped" button in green confuses them (did someone take this trade?)
3. Tries to read sector strip — squints at small percentages
4. Looks at chart annotation — can barely read the italic support level text
**Expected Outcome**: After fixes, the user sees a secure site, clearly understands which signals were taken vs skipped, can read sector data and chart annotations effortlessly

### Scenario 2: Active Trader Scanning Signals During Market Hours

**Actor**: Pro user monitoring multiple symbols
**Steps**:
1. Glances at Signal Feed — immediately distinguishes taken (green) from skipped (gray) alerts
2. Reads timestamps on each signal without any clipping
3. Checks sector strip — quickly reads which sectors are leading/lagging
4. Reads chart annotation bar — instantly sees support level and condition
**Expected Outcome**: All critical information readable at scanning speed (under 1 second per element)

### Scenario 3: User on 13" Laptop

**Actor**: Trader on a smaller screen
**Steps**:
1. Chart bottom bar is fully visible without scrolling
2. Sector strip scrolls horizontally if needed rather than shrinking to unreadable size
3. Watchlist columns are aligned even with varying price lengths ($231 vs $2177)
**Expected Outcome**: No content clipped or cut off on standard laptop viewports

## Success Criteria

- [ ] "Skipped" buttons use neutral gray color, distinct from positive green actions
- [ ] All Signal Feed timestamps fully visible with no overlap
- [ ] Chart annotation text passes WCAG AA contrast ratio (4.5:1)
- [ ] Sector strip text readable at arm's length on 13" screen
- [ ] Watchlist price and score columns visually aligned across all rows
- [ ] Browser shows secure connection (lock icon) on all pages
- [ ] Bottom chart bar fully visible on 768px viewport height
- [ ] Grammar correct: "1 setup" singular, "N setups" plural

## Edge Cases

- Extremely long symbol names (ETH-USD, BTC-USD) in watchlist — ensure no column shift
- 11 sectors in strip on narrow screen — horizontal scroll activates cleanly
- Chart annotation text with very long narrative — truncate with ellipsis or wrap gracefully
- Mixed content (HTTP images/scripts) blocking HTTPS — audit all asset URLs
- Signal Feed with 50+ alerts — timestamp alignment holds in scrolled state

## Assumptions

- SSL can be configured through Railway or the domain registrar (Cloudflare, Namecheap, etc.)
- Current chart annotation text color values are in the theme's CSS custom properties
- Signal Feed "Skipped" button color is defined in the component, not inherited from a global style
- The bottom bar cutoff is a CSS issue (padding/margin), not a fundamental layout problem

## Scope

### In Scope
- Signal Feed button colors and timestamp spacing
- Chart annotation bar contrast and font style
- Sector strip text sizing
- Watchlist column alignment and grammar fix
- SSL certificate setup
- Bottom bar visibility fix

### Out of Scope
- Signal Feed redesign or new features
- Sector strip interaction changes (click to filter, etc.)
- Watchlist drag-to-reorder
- Mobile/responsive layout overhaul
- Chart widget customization (TradingView embed)
