# FE-P1: Design System Foundation

**Priority:** P0 — Critical (blocks all other frontend work)
**Phase:** 1 of 10
**Estimated Scope:** ~8 files modified, ~3 new files

---

## Problem Statement

The frontend uses Tailwind defaults (system sans-serif, raw gray palette, no icon system). Every page looks like a generic developer prototype. There is no brand identity, no typographic hierarchy, and colors are scattered as inline Tailwind classes with no cohesive system.

**Impact:** Without a design foundation, every subsequent page improvement will be ad-hoc and inconsistent. This ticket establishes the visual DNA that cascades across all pages.

---

## Acceptance Criteria

- [ ] Custom display + body font pairing loaded via Google Fonts
- [ ] Extended CSS variable system for colors (surfaces, borders, accents, semantic)
- [ ] Consistent border-radius, shadow, and spacing tokens
- [ ] SVG icon component system replacing all Unicode icons (`◎ ▤ ⇄ ★`)
- [ ] Base component styles: buttons (primary, secondary, ghost), inputs, badges, cards
- [ ] Dark theme with depth (not flat gray-on-gray)

---

## Implementation Details

### Typography
- **Display font:** A distinctive sans-serif for headings (e.g., DM Sans, Outfit, Satoshi, Sora)
- **Body font:** High-readability for data-dense UI (e.g., IBM Plex Sans, General Sans, Plus Jakarta Sans)
- **Mono font:** For prices/numbers (e.g., JetBrains Mono, IBM Plex Mono, Space Mono)
- Load via `<link>` in `index.html` or `@import` in CSS

### Color System (CSS Variables)
```css
:root {
  /* Surfaces */
  --surface-0: /* deepest bg */;
  --surface-1: /* cards */;
  --surface-2: /* elevated cards/modals */;
  --surface-3: /* hover states */;

  /* Borders */
  --border-subtle: ;
  --border-default: ;

  /* Text */
  --text-primary: ;
  --text-secondary: ;
  --text-muted: ;

  /* Semantic */
  --accent: ;
  --bullish: ;
  --bearish: ;
  --warning: ;
  --info: ;

  /* Gradients */
  --gradient-accent: ;
  --gradient-surface: ;
}
```

### Icon System
- Create `src/components/icons/` with SVG components
- Cover all nav items: Dashboard, Scanner, Charts, Trades, Scorecard, History, Import, Paper Trading, Backtest
- Plus utility icons: chevron, close, menu, refresh, search, alert, check, x

### Base Component Tokens
- Card: consistent `border-radius`, `background`, `border`, `shadow`
- Button variants: primary (accent fill), secondary (outline), ghost (text-only)
- Input: consistent focus ring, border, background
- Badge: BUY/SELL/WATCH with proper contrast

### Files to Modify
| File | Change |
|------|--------|
| `web/index.html` | Add font preload links |
| `web/src/index.css` | Extended CSS variables, base styles, font-face |
| `web/src/components/AppLayout.tsx` | Replace Unicode icons with SVG components |
| `web/src/pages/DashboardPage.tsx` | Use new card/badge tokens |
| `web/src/pages/ScannerPage.tsx` | Use new card tokens |
| `web/src/components/SignalCard.tsx` | Use new badge/color tokens |

### Files to Add
| File | Purpose |
|------|---------|
| `web/src/components/icons/index.tsx` | SVG icon components |
| `web/src/components/ui/Badge.tsx` | Reusable badge component |
| `web/src/components/ui/Button.tsx` | Reusable button component |

---

## Out of Scope
- Page-specific redesigns (handled in Phase 2-7)
- Animation system (Phase 8)
- New pages (Phase 10)
