# Plan: FE-P1 Design System Foundation

## Problem Statement
The React frontend has no design system — system fonts, raw Tailwind colors, Unicode icons, and duplicated component patterns. Every page looks like a developer prototype. This phase establishes the visual DNA (fonts, colors, tokens, icons, base components) that all subsequent phases build upon.

## Solution Architecture

```
┌──────────────────────────────────────────────────┐
│                   index.html                      │
│        (Google Fonts preload + preconnect)        │
└──────────────┬───────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────┐
│                   index.css                       │
│  @theme { fonts, colors, radii, shadows }        │
│  @layer base { body, headings, mono }            │
│  @layer utilities { .badge-*, .btn-*, .card }    │
└──────────────┬───────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────┐
│              Component Layer                      │
│  icons/index.tsx  →  SVG icon wrappers           │
│  ui/Badge.tsx     →  Semantic badge variants      │
│  ui/Button.tsx    →  Primary/secondary/ghost      │
│  ui/Card.tsx      →  Consistent card wrapper      │
└──────────────────────────────────────────────────┘
```

### Data Flow
No data flow changes. This is purely a visual/styling layer. All existing API hooks, stores, and routing remain untouched.

## Codebase Analysis

### Existing Patterns to Follow
- Tailwind v4 CSS-first approach (`@theme` directive, not JS config)
- Component files in `src/components/`
- TypeScript strict mode, named exports
- Inline Tailwind classes (preserve this pattern, don't switch to CSS modules)

### Gaps Identified
- No font loading in `index.html`
- Only 4 CSS variables defined
- No reusable UI components (badge, button, card)
- No icon system
- No monospace font for numbers/prices

## Implementation Approach

### Files to Modify

| File | Change |
|------|--------|
| `web/index.html` | Add Google Fonts preconnect + preload links |
| `web/src/index.css` | Extended `@theme` with full design tokens, utility classes |
| `web/src/components/AppLayout.tsx` | Swap Unicode icons → Lucide React icons |
| `web/src/pages/DashboardPage.tsx` | Swap Unicode icons in QUICK_LINKS |
| `web/package.json` | Add `lucide-react` dependency |

### Files to Add

| File | Purpose |
|------|---------|
| `web/src/components/ui/Badge.tsx` | Reusable badge (BUY/SELL/Watch/grade/tier/pattern) |
| `web/src/components/ui/Button.tsx` | Primary, secondary, ghost, danger button variants |
| `web/src/components/ui/Card.tsx` | Consistent card wrapper with optional header |

### Step-by-Step

**Step 1: Install lucide-react**
```bash
cd web && npm install lucide-react
```

**Step 2: Load fonts in `index.html`**
- Add preconnect to `fonts.googleapis.com` and `fonts.gstatic.com`
- Load **DM Sans** (400, 500, 600, 700) for headings
- Load **Plus Jakarta Sans** (400, 500, 600) for body
- Load **JetBrains Mono** (400, 500) for numbers/prices

**Step 3: Extend `index.css` with design tokens**
Using Tailwind v4 `@theme` directive:

```css
@theme {
  /* Fonts */
  --font-display: "DM Sans", sans-serif;
  --font-body: "Plus Jakarta Sans", sans-serif;
  --font-mono: "JetBrains Mono", monospace;

  /* Surfaces (dark theme depth system) */
  --color-surface-0: #06080c;    /* deepest background */
  --color-surface-1: #0c1018;    /* page background */
  --color-surface-2: #131926;    /* cards */
  --color-surface-3: #1a2236;    /* elevated/hover */
  --color-surface-4: #222d44;    /* active states */

  /* Borders */
  --color-border-subtle: #1a2236;
  --color-border-default: #222d44;
  --color-border-strong: #2e3b54;

  /* Text */
  --color-text-primary: #e8ecf4;
  --color-text-secondary: #94a3b8;
  --color-text-muted: #64748b;
  --color-text-faint: #475569;

  /* Accent (brand blue) */
  --color-accent: #3b82f6;
  --color-accent-hover: #2563eb;
  --color-accent-muted: #1e3a5f;

  /* Semantic */
  --color-bullish: #22c55e;
  --color-bullish-muted: #14532d;
  --color-bearish: #ef4444;
  --color-bearish-muted: #450a0a;
  --color-warning: #f59e0b;
  --color-warning-muted: #451a03;
  --color-info: #3b82f6;
  --color-info-muted: #172554;

  /* Radii */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
  --radius-xl: 20px;

  /* Shadows */
  --shadow-card: 0 1px 3px rgba(0,0,0,0.3), 0 1px 2px rgba(0,0,0,0.2);
  --shadow-elevated: 0 4px 12px rgba(0,0,0,0.4), 0 2px 4px rgba(0,0,0,0.3);
}
```

**Step 4: Base styles in `index.css`**
- Body: `font-body`, `surface-1` background, `text-primary` color
- Headings: `font-display`
- Mono elements: `.font-mono` → `font-mono` for price/number displays

**Step 5: Create `ui/Badge.tsx`**
Variants: `bullish`, `bearish`, `warning`, `info`, `neutral`, `pro`, `grade-a`, `grade-b`, `grade-c`

**Step 6: Create `ui/Button.tsx`**
Variants: `primary` (accent fill), `secondary` (outline), `ghost` (text), `danger` (red)
Sizes: `sm`, `md`, `lg`
States: loading (spinner), disabled

**Step 7: Create `ui/Card.tsx`**
Props: `title?`, `subtitle?`, `padding?`, `elevated?`
Consistent: `surface-2` bg, `border-subtle` border, `radius-md`, `shadow-card`

**Step 8: Swap icons in AppLayout.tsx**
Replace Unicode chars with Lucide icons:
- `⌂` → `<LayoutDashboard />`
- `◎` → `<Crosshair />`
- `▤` → `<CandlestickChart />` (or `<BarChart3 />`)
- `⇄` → `<ArrowLeftRight />`
- `★` → `<Trophy />`
- `▦` → `<History />`
- `↑` → `<Upload />`
- `◈` → `<Gem />`
- `↻` → `<RotateCcw />`

**Step 9: Swap icons in DashboardPage.tsx**
Replace QUICK_LINKS Unicode icons with matching Lucide icons.

## Test Plan

### Visual Verification (no unit tests — this is CSS/visual)
- [ ] Fonts render correctly (DM Sans headings, Plus Jakarta body, JetBrains Mono numbers)
- [ ] Color tokens applied to body background and text
- [ ] Badge component renders all variants with correct colors
- [ ] Button component renders all variants and states
- [ ] Card component renders with consistent styling
- [ ] Lucide icons render in sidebar nav at correct size
- [ ] Lucide icons render in dashboard quick links
- [ ] No visual regressions on existing pages
- [ ] Mobile responsive layout still works

### E2E Validation
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ 1. npm start │────▶│ 2. Navigate  │────▶│ 3. Verify    │
│ dev server   │     │ all pages    │     │ visual output│
└──────────────┘     └──────────────┘     └──────────────┘
```

1. `cd web && npm run dev`
2. Open browser, navigate to login → dashboard → scanner → all pages
3. Verify: fonts loaded (check Network tab), icons render, colors applied
4. Check mobile viewport (< 768px) for responsive integrity
5. Check Chrome DevTools console for any CSS/font errors

## Out of Scope
- Page-specific redesigns (Phases 2-7)
- Animation system (Phase 8)
- Form validation (Phase 6)
- New pages (Phase 10)

## Risks
- **Font loading latency:** Mitigated by `display=swap` and preconnect
- **Tailwind v4 @theme compatibility:** Tailwind v4 uses CSS-native approach, `@theme` is the correct way to extend tokens
- **Lucide bundle size:** Tree-shaking keeps only imported icons (~1KB each)
