# Sub-spec G — Shared Marketing Components & Tokens

Part of the Landing Redesign master spec. **Build first** — A–F depend on it.

## Goal
The reusable building blocks so every section is consistent and fast to assemble, with no new
visual language.

## What it provides
- **Section primitives:** `<Section>` (padding, top-border), `Eyebrow` (mono uppercase label),
  section heading style (DM Sans, gradient-accent option).
- **Cards:** feature card (icon tile + title + body), pill (pattern chip), stat chip.
- **CTAs:** primary (bullish glow), secondary (surface), app-store badge component.
- **Hero components:** badge with pulse dot, the alert-card + AI-read mock pair.
- **Tokens:** confirm existing set covers it (surface-0..4, accent, bullish/bearish, purple,
  warning, text-*). Add only if a gap appears — document any new token.

## Requirements
- **G1** Reuse existing tokens/fonts (DM Sans / Plus Jakarta / JetBrains Mono); introduce no new
  palette.
- **G2** Components are responsive (mobile-first) and theme-aware (dark default, light supported).
- **G3** App-store badges are self-contained (inline SVG/data-URI) so the marketing page has no
  external asset dependency.
- **G4** No horizontal overflow at 375px; wide elements scroll within their own container.

## Acceptance
- A–F can be assembled entirely from these primitives without ad-hoc styling.
- `tsc -b` clean; renders identically dark/light.

## Reuse / build notes
- Extend `components/ui/*` (Badge/Button/Card) + a small `components/marketing/*` set.
- Landing stays a composition of section functions in `LandingPage.tsx` (current pattern).

## Effort: S
