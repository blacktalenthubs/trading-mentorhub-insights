# FE-P9: Empty & Loading States

**Priority:** P2 — Medium
**Phase:** 9 of 10
**Depends on:** FE-P1 (Design System Foundation), FE-P8 (Animations)

---

## Problem Statement

Empty states are plain text ("No alerts fired today", "No signals. Add symbols..."). Loading states are generic skeleton grids. These dead-end moments are missed opportunities to guide users, reinforce branding, and reduce perceived wait time.

**Impact:** Empty and loading states are surprisingly frequent touchpoints — market hours, first-time users, slow network. Polishing them prevents the "broken" feeling.

---

## Acceptance Criteria

### Empty States
- [ ] Each empty state has: icon/illustration, headline, description, and CTA button
- [ ] Dashboard empty: "Market is quiet" with suggestion to add watchlist symbols
- [ ] Scanner empty: "No signals yet" with link to add symbols
- [ ] History empty: "No trades recorded" with link to import
- [ ] Alerts empty: "No alerts today" with market hours context
- [ ] Consistent empty state component across all pages

### Loading States
- [ ] Skeleton shapes match actual content layout (not generic grid)
- [ ] Shimmer animation on all skeletons
- [ ] Page-level loading: full content area skeleton
- [ ] Component-level loading: inline skeleton matching component shape
- [ ] Chart loading: chart-shaped placeholder with shimmer
- [ ] Table loading: row-shaped skeletons

---

## Implementation Details

### Files to Add
| File | Purpose |
|------|---------|
| `web/src/components/ui/EmptyState.tsx` | Reusable empty state (icon, title, desc, CTA) |

### Files to Modify
| File | Change |
|------|--------|
| `web/src/components/LoadingSkeleton.tsx` | Shape-specific skeletons, shimmer |
| `web/src/pages/DashboardPage.tsx` | Custom empty states |
| `web/src/pages/ScannerPage.tsx` | Custom empty state |
| `web/src/pages/HistoryPage.tsx` | Custom empty state |
| All pages | Replace text-only empty states |

---

## Out of Scope
- SVG illustrations (use CSS/icon compositions)
- Error state redesign (separate concern)
