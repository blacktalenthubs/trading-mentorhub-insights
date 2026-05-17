# Component Map — Spec 50 (Phase 1 Design)

**Purpose**: Maps each visual section of the landing to its React component, layout strategy, and the icons/Tailwind utilities involved. Lets the rewriter focus on copy + structure without re-deciding the surface design.

---

## Section-by-section render contract

### LandingNav

- Container: `<nav class="fixed top-0 ... z-50 bg-surface-0/80 backdrop-blur-lg border-b border-border-subtle/50">`
- Height: `h-16`, max-width `max-w-6xl`, `mx-auto`, padding `px-6`
- Layout: `flex items-center justify-between`
- Left: BrandMark (icon + wordmark), inline
- Center (desktop ≥ md): `flex items-center gap-8 text-sm text-text-muted` — links: Pattern Library, Track Record
- Center (mobile < md): hidden; replaced by hamburger trigger
- Right: AuthLinks — Sign in (text link) + Get started (primary button)
- Mobile menu: native `<details>` with `<summary>` (accessible no-JS dropdown); slides under the nav

### Hero

- Container: `<section class="min-h-[calc(100vh-4rem)] flex items-center pt-24 pb-16 px-6">`
- Inner: `max-w-4xl mx-auto text-center`
- Eyebrow (`<p>`): `inline-flex items-center gap-2 text-xs uppercase tracking-wider text-accent`
- Headline (`<h1>`): `text-4xl sm:text-5xl md:text-6xl font-bold leading-tight text-text-primary mb-6`
- Sub-headline (`<p>`): `text-lg sm:text-xl text-text-muted max-w-2xl mx-auto mb-10`
- HeroStat container: `mb-10` — render branches per [hero-stat-fallback.md](./hero-stat-fallback.md)
- PrimaryCTA: `inline-flex items-center gap-2 bg-accent hover:bg-accent-hover px-8 py-4 rounded-lg text-white font-semibold transition-colors`
- SecondaryCTA: text link, `text-accent hover:text-accent-hover text-sm mt-4 inline-block`

### WhatYouGet

- Container: `<section class="py-24 px-6 bg-surface-1 border-y border-border-subtle">`
- Inner: `max-w-6xl mx-auto`
- Section header block: eyebrow + h2 + lead, centered, mb-16
- Grid: `grid grid-cols-1 md:grid-cols-2 gap-6` — 4 cards
- Card: `bg-surface-0 border border-border-subtle rounded-2xl p-8 flex flex-col gap-4 hover:border-border-default transition-colors`
- Status pill (top-right of each card): `<span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border">` — green for LIVE, accent-subtle for COMING SOON
- Icon container: `w-12 h-12 rounded-xl bg-accent-subtle text-accent flex items-center justify-center`
- Headline: `text-xl font-bold text-text-primary`
- Body: `text-text-muted leading-relaxed`
- CTA link: `mt-auto inline-flex items-center gap-1.5 text-accent hover:text-accent-hover text-sm font-medium`

### ProofSection

- Container: `<section class="py-24 px-6">`
- Inner: `max-w-6xl mx-auto`
- Section header: eyebrow + h2 + lead, centered, mb-16
- Stat grid: `grid grid-cols-1 sm:grid-cols-3 gap-6 max-w-4xl mx-auto`
- Stat card: `bg-surface-1 border border-border-subtle rounded-xl p-8 text-center`
- Stat value: `text-5xl font-bold text-accent mb-2` (or use fallback rendering per hero-stat-fallback contract)
- Stat label: `text-text-muted text-sm`
- ProofCTA: centered, `mt-12`

### FinalCTA

- Container: `<section class="py-24 px-6 bg-surface-1 border-t border-border-subtle">`
- Inner: `max-w-3xl mx-auto text-center`
- Headline (`<h2>`): `text-3xl sm:text-4xl font-bold text-text-primary mb-4`
- Body: `text-text-muted text-lg mb-8`
- PrimaryCTA: same as hero

### Footer

- Container: `<footer class="py-12 px-6 border-t border-border-subtle">`
- Inner: `max-w-6xl mx-auto`
- Layout: `flex flex-col md:flex-row items-start md:items-center justify-between gap-6`
- Left: brand + year
- Right: links inline, `flex gap-6 text-sm text-text-muted`
- Bottom: tagline, full-width, `text-xs text-text-faint text-center mt-8`

---

## Icon assignments (lucide-react)

| Where | Icon |
|-------|------|
| BrandMark | `Crosshair` (existing) |
| Hero — secondary CTA arrow | `ArrowRight` |
| WhatYouGet — Telegram | `MessageCircle` |
| WhatYouGet — EOD Recap | `FileText` |
| WhatYouGet — Chart Critique | `Eye` |
| WhatYouGet — Pattern Edu Live | `BookOpen` |
| Coming-soon pill icon | `Clock` |
| Live pill icon | `Check` |
| Mobile menu | `Menu` (closed) / `X` (open) |
| Proof CTA arrow | `ArrowRight` |

All icons sized `h-4 w-4` inline, `h-6 w-6` for the deliverable card icons.

---

## Color usage discipline

- `bg-surface-0` — page background, hero card backgrounds
- `bg-surface-1` — alternating section backgrounds (WhatYouGet, FinalCTA)
- `bg-surface-2 / 3` — currently unused on landing; reserve for hover/focus states on cards
- `text-text-primary` — headlines + stat values
- `text-text-muted` — body copy, sub-headlines
- `text-text-faint` — footer tagline, ultra-quiet metadata
- `text-accent` (blue) — CTA buttons, links, stat values, icon containers
- `text-bullish-text` (green) — LIVE status pill
- `border-border-subtle` — card borders, section dividers
- `border-border-default` — hover state on cards

No gradients on Tier-1 surfaces (no neon glow). Restrained.

---

## Accessibility notes (FR-207)

- Every `<button>` and `<a>` is focusable and has visible focus ring (Tailwind `focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface-0`).
- All icons used decoratively have `aria-hidden="true"`.
- `<h1>` once, `<h2>` per major section, no skipped levels.
- Stat values have an `aria-label` that spells out the number when it could read as just "62%": `aria-label="62 percent win rate"`.
- Mobile menu uses native `<details>` for accessible no-JS toggle.
- Reduced motion: `motion-reduce:animate-none` on the loading pulse.

---

## Mobile breakpoints

- Tailwind defaults: `sm` 640px, `md` 768px, `lg` 1024px, `xl` 1280px
- Below 360px: best-effort (not a target)
- 360–639px: stack everything, mobile menu, single-column deliverable grid
- 640–767px: still mostly mobile layout, larger type
- 768px+: desktop nav, 2-col deliverable grid
- 1024px+: max-width 6xl applies

---

## What the rewriter MUST NOT do

- No new files in `web/src/components/` (keep landing self-contained)
- No new design tokens in `index.css`
- No new icon imports beyond the ~10 listed above
- No third-party library additions
- No CSS-in-JS or styled-components (Tailwind only, per project convention)
- No SVG fonts or web-font imports (DM Sans / Plus Jakarta Sans / JetBrains Mono are already loaded)
