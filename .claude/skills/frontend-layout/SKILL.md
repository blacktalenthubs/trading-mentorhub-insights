---
name: frontend-layout
description: How to structure pages in the BusyTradersDesk web app so they look like a professional platform — full-width, sidebar-aware, list+detail panels, dense information design. Use whenever building or redesigning a page in web/src/pages, or when a page "looks centered / empty / amateur".
---

# Frontend Layout — build pages like a real platform

The app's #1 recurring UI mistake: pages built as a **narrow centered column**
(`mx-auto max-w-2xl`) that float in a sea of dark canvas. On desktop that reads as
amateur. Professional platforms (Bloomberg, TradingView, Linear, the user's "Guac"
reference) do the opposite: a persistent sidebar, content that **uses the width**, and
context laid out in **structured regions** (a list on one side, detail on the other),
with real density and alignment.

Read this before touching any page in `web/src/pages`.

## The frame you're inside

`AppLayout` already renders the left nav sidebar and wraps every route in:

```
<div className="min-h-0 flex-1 overflow-hidden"><Outlet /></div>
```

So the page gets a **definite-height, overflow-hidden** box. That means:

- The page **owns its own scrolling** — a plain `<div className="mx-auto max-w-2xl py-5">`
  will CLIP when it grows taller than the viewport (there's no scroll on the parent).
- Build the page as `h-full flex flex-col`, then give the scrolling region
  `flex-1 min-h-0 overflow-y-auto`. Header/toolbars are `shrink-0`.

## Decide the layout by what the page is

- **A worklist / dashboard / scanner** (many rows the user picks from, then acts on one):
  use a **two-pane list + detail** on desktop. This is the default for anything
  "browse then drill in". See `PremiumDeskPage.tsx` — the reference implementation.
- **A single record / form / report**: a readable centered column is fine, but make it
  `max-w-3xl`/`max-w-4xl` (not `max-w-2xl`), left-align content, and still `h-full
  overflow-y-auto` so it scrolls instead of clipping.
- **A true document** (long prose): centered `max-w-2xl`–`prose` is correct. Rare here.

Never default to the narrow centered column for an app screen. Use the width.

## The two-pane pattern (copy this)

```tsx
<div className="flex h-full flex-col bg-surface-0">
  <header className="shrink-0 space-y-3 border-b border-border-subtle px-4 py-3 lg:px-6">
    {/* title + subtitle + right-aligned actions; compact stat pills + segmented filter */}
  </header>
  <div className="flex min-h-0 flex-1">
    <div className="min-w-0 flex-1 overflow-y-auto">{/* dense table / list */}</div>
    <div className="hidden w-[384px] shrink-0 overflow-y-auto border-l border-border-subtle bg-surface-0 lg:block">
      {/* detail / context panel for the selected row */}
    </div>
  </div>
</div>
```

- Selection lives in page state; clicking a row updates the panel on `lg+`.
- On mobile the panel is `hidden lg:block`; a row instead navigates to a `/:id` detail
  route that renders the **same** panel component (`variant="page"`). Extract the panel
  into `web/src/components/` so both surfaces share it — see `PremiumTradePanel.tsx`.
- Route order matters: put static child routes (`/x/positions`) BEFORE param routes
  (`/x/:id`) in `App.tsx`.

## Tables & information design

- Real `<table>` with a `sticky top-0` header inside the scroll region. Left-align text,
  **right-align every number**, `font-mono` + `tabular-nums` for figures so columns line up.
- Group rows with a full-width separator row (a `<tr><td colSpan=…>` band), not gaps.
- Encode state in form: a tier/severity **color stripe** (`shadow-[inset_3px_0_0_var(--color-…)]`),
  a colored pill, an RSI cell that turns red when hot / green when oversold. Scannable at a glance.
- Selected row: `bg-accent-subtle` + the stripe. Hover: `hover:bg-surface-1`.

## Tokens — never hardcode colors

Use the app's CSS-variable design tokens (defined in `web/src/index.css`, work in light+dark):

- Surfaces: `bg-surface-0` (base) → `surface-1` `surface-2` `surface-3` `surface-4` (raised).
- Text: `text-text-primary` `text-secondary` `text-muted` `text-faint` (decreasing emphasis).
- Lines: `border-border-subtle` `border-default` `border-strong`.
- Accent (interactive): `bg-accent` `text-accent` `accent-hover` `accent-subtle`.
- Semantic: `bullish`/`bullish-text` (green), `bearish`/`bearish-text` (red),
  `warning`/`warning-text` (amber) + their `-subtle` fills. Keep semantic color separate
  from the accent — green/amber/red mean good/watch/bad, blue means "interactive".
- Tailwind arbitrary values can reference the vars: `var(--color-bullish-text)`.

## Density & alignment checklist

- Left-align headings and content; only truly centered things (a lone empty-state) center.
- Consistent padding on repeated elements (cards, cells) — same edges top to bottom.
- A recurring element sits in the same place in each row/card.
- Toolbars are tight rows of small controls, not giant centered blocks.
- Numbers: `font-mono tabular-nums`, right-aligned in columns.
- Wide content (tables) scrolls inside its own `overflow-x-auto` container; the page body
  never scrolls sideways.

## Process

For a non-trivial screen, **prototype the structure first** as a standalone HTML artifact
(full-frame, real data, the two-pane layout) and get the user's read before implementing
in React — the user has asked for this. Then implement with the tokens/patterns above and
run `npm run build` (not just `tsc --noEmit`) before merging — CI uses the strict build.

Reference implementation to copy from: `web/src/pages/PremiumDeskPage.tsx` +
`web/src/components/PremiumTradePanel.tsx` (list + shared detail panel, full-height,
tokenized, responsive).
