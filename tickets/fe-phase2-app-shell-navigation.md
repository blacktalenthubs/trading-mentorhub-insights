# FE-P2: App Shell & Navigation

**Priority:** P0 — Critical (first thing users see every session)
**Phase:** 2 of 10
**Depends on:** FE-P1 (Design System Foundation)

---

## Problem Statement

The sidebar and app shell are functional but visually plain. Unicode icons render inconsistently across platforms. The sidebar has no visual hierarchy, no active state polish, and no branded presence. The mobile header is bare minimum. There's no top header bar on desktop showing context (current page, market status, user).

**Impact:** The shell is the permanent frame around every page — polishing it elevates the entire app instantly.

---

## Acceptance Criteria

- [ ] Sidebar uses SVG icons from Phase 1 icon system
- [ ] Active nav item has clear visual indicator (left accent bar, background highlight)
- [ ] Sidebar header has branded logo/wordmark with subtle gradient or accent
- [ ] Market status badge is more prominent with pulse animation when market is open
- [ ] Desktop top bar showing: page title breadcrumb, market status, user avatar/initials
- [ ] Sidebar sections (Core / Pro) have visual separation with section headers
- [ ] User footer section is polished (avatar initials, tier badge, logout)
- [ ] Sidebar has subtle background treatment (gradient, noise, or texture)
- [ ] Mobile hamburger menu has smooth slide + backdrop animation
- [ ] Sidebar collapse/expand on desktop (icon-only mode)

---

## Implementation Details

### Files to Modify
| File | Change |
|------|--------|
| `web/src/components/AppLayout.tsx` | Complete visual overhaul of sidebar + header |
| `web/src/index.css` | Add sidebar-specific CSS (active bar, animations) |

### Key Design Decisions
- Active item: left 3px accent bar + elevated background
- Logo: "TradeSignal" wordmark with accent-colored icon/glyph
- Market pulse: CSS `@keyframes` pulse on green dot when market is open
- Desktop header: sticky top bar with page context
- Collapsible sidebar: `w-16` icon-only mode with tooltip labels

---

## Out of Scope
- Page content changes (other phases)
- Mobile bottom tab bar (future consideration)
