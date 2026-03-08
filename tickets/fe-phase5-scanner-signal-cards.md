# FE-P5: Scanner & Signal Cards

**Priority:** P1 — High (core product feature)
**Phase:** 5 of 10
**Depends on:** FE-P1 (Design System Foundation)

---

## Problem Statement

The scanner page is the core product feature but the signal cards are dense data dumps. The collapsed row crams symbol, action label, grade, pattern, price, and entry/stop/target into one line. The expanded view is a wall of label-value pairs. Users need to quickly scan, compare, and act — the current layout doesn't support fast visual scanning.

**Impact:** This is where users make trading decisions. Visual hierarchy directly affects decision quality.

---

## Acceptance Criteria

- [ ] Collapsed signal row has clear visual hierarchy (symbol dominant, grade/action as badges)
- [ ] Action label badges are more prominent with distinct shapes/colors
- [ ] Grade display uses a visual indicator (colored ring, letter grade with background)
- [ ] Expand/collapse has smooth animation (height transition)
- [ ] Expanded trade plan uses a structured layout (not just label-value grid)
- [ ] Entry/Stop/Target displayed as a visual price ladder or range bar
- [ ] Position sizing section is visually distinct (boxed, different background)
- [ ] MA context shown as visual indicators (above/below with colored dots)
- [ ] Chart section has proper loading state
- [ ] KPI summary bar at top has more visual weight
- [ ] Filter/sort controls for signal list (by grade, action, symbol)
- [ ] Watchlist editor is more polished (better add/remove UX)

---

## Implementation Details

### Signal Card Redesign
- Collapsed: 3-zone layout (symbol+badges | price | grade indicator)
- Expanded: 2-column with clear sections separated by headers
- Price ladder: visual bar showing stop → entry → T1 → T2 range
- Grade ring: circular indicator with color fill based on grade

### KPI Bar
- Horizontal bar with icon + number + label per metric
- Subtle background differentiation from page

### Files to Modify
| File | Change |
|------|--------|
| `web/src/components/SignalCard.tsx` | Visual redesign of collapsed + expanded states |
| `web/src/pages/ScannerPage.tsx` | KPI bar, filter controls, list layout |
| `web/src/components/WatchlistEditor.tsx` | Polish add/remove UX |

---

## Out of Scope
- Signal comparison mode (side-by-side)
- Alert setup from signal card
- AI-generated trade narratives (Phase 10 - AI Coach)
