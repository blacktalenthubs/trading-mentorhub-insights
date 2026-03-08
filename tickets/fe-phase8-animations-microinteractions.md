# FE-P8: Animations & Micro-interactions

**Priority:** P2 — Medium (polish layer)
**Phase:** 8 of 10
**Depends on:** FE-P1 through P5 (core UI must be in place first)

---

## Problem Statement

The app has zero motion design. Only `transition-colors` is used. No page transitions, no entrance animations, no hover micro-interactions, no scroll-triggered reveals. The app feels static and lifeless.

**Impact:** Motion is the difference between "functional" and "premium". Well-crafted animations convey quality and guide attention.

---

## Acceptance Criteria

- [ ] Page transitions: subtle fade + slide on route change
- [ ] Staggered card entrance: stat cards, signal cards appear with cascade delay
- [ ] Sidebar nav items: smooth hover state with background slide
- [ ] Button interactions: subtle scale on press, ripple or glow on click
- [ ] Alert toast: slide-in from top with auto-dismiss fade
- [ ] Signal card expand: smooth height animation with content fade-in
- [ ] Skeleton loading: shimmer animation on loading placeholders
- [ ] Badge/number updates: brief color flash when value changes
- [ ] Scroll-triggered: elements fade in as they enter viewport
- [ ] Market status: pulse animation on "OPEN" indicator

---

## Implementation Details

### Approach
- CSS-only where possible (`@keyframes`, `transition`, `animation`)
- Consider `framer-motion` or CSS `@starting-style` for complex orchestration
- Use `prefers-reduced-motion` media query for accessibility

### Key Animations
| Element | Animation | Duration |
|---------|-----------|----------|
| Page enter | fadeIn + translateY(8px) | 200ms |
| Card cascade | staggered fadeIn | 50ms delay per item |
| Sidebar hover | background slide-right | 150ms |
| Button press | scale(0.98) | 100ms |
| Alert toast | slideDown + fadeIn | 300ms |
| Signal expand | height auto + fadeIn | 250ms |
| Skeleton shimmer | gradient slide | 1.5s infinite |

### Files to Modify
| File | Change |
|------|--------|
| `web/src/index.css` | Animation keyframes, utility classes |
| `web/src/components/AppLayout.tsx` | Nav hover animations |
| `web/src/components/SignalCard.tsx` | Expand animation |
| `web/src/components/LoadingSkeleton.tsx` | Shimmer effect |
| `web/src/pages/DashboardPage.tsx` | Staggered entrance, alert toast |
| All pages | Page entrance animation wrapper |

---

## Out of Scope
- Complex physics-based animations
- Page transition with shared element morphing
- 3D transforms or parallax
