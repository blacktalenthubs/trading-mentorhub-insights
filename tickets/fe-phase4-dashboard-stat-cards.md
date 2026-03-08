# FE-P4: Dashboard & Stat Cards

**Priority:** P1 — High (primary landing page after login)
**Phase:** 4 of 10
**Depends on:** FE-P1 (Design System Foundation), FE-P2 (App Shell)

---

## Problem Statement

The dashboard is functional but flat. Stat cards are identical plain gray boxes with no visual differentiation. Quick links are basic card blocks. The alert feed is a simple list with no visual drama. There's no sense of "command center" or real-time market awareness.

**Impact:** The dashboard is the home base — users see it every session. It should feel like a trading command center, not a data dump.

---

## Acceptance Criteria

- [ ] Stat cards have visual hierarchy (primary metrics larger, secondary compact)
- [ ] Stat cards use subtle gradients or border accents matching their semantic color
- [ ] Positive/negative values have clear color treatment (green up, red down)
- [ ] Quick links have icons, hover elevation, and subtle border accent
- [ ] Alert feed items have left color bar (BUY=green, SELL=red)
- [ ] "NEW ALERT" toast has entrance animation and auto-dismiss
- [ ] Section headers have visual weight ("Today's Alerts" with underline or icon)
- [ ] Empty state for alerts is engaging (illustration or styled message)
- [ ] Market session indicator (pre-market / open / after-hours / closed) is prominent
- [ ] Optional: mini sparkline or trend indicator on stat cards

---

## Implementation Details

### Stat Card Redesign
- Primary stats (Signals, Active): larger card, accent border-left
- Secondary stats: compact row, monospace numbers
- Trend indicators: small up/down arrow with % change

### Alert Feed Redesign
- Left accent bar (4px) colored by direction
- Timestamp formatting (relative: "2m ago")
- Symbol as bold anchor, alert type as subtle badge
- Price levels in monospace font

### Files to Modify
| File | Change |
|------|--------|
| `web/src/pages/DashboardPage.tsx` | Full redesign with new components |
| `web/src/components/LoadingSkeleton.tsx` | Branded skeleton matching new card shapes |

### Files to Add
| File | Purpose |
|------|---------|
| `web/src/components/ui/StatCard.tsx` | Reusable stat card with variants |
| `web/src/components/ui/AlertItem.tsx` | Styled alert feed item |

---

## Out of Scope
- Portfolio P&L widget (future feature)
- Customizable dashboard layout (future feature)
