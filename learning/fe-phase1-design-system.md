# Learning: FE-P1 Design System Foundation

## Current State Inventory

### Fonts
- **React:** No custom fonts loaded. System sans-serif via Tailwind default.
- **Streamlit:** Inter (300-700) via Google Fonts import in `ui_theme.py`
- **Gap:** Complete font mismatch between React and Streamlit UIs

### Color System (4 CSS vars only)
```css
--color-primary: #2563eb
--color-success: #16a34a
--color-danger: #dc2626
--color-warning: #d97706
```
All other colors are raw Tailwind classes (`bg-gray-900`, `text-green-400`, etc.) — no semantic tokens.

### Tailwind Config
- Using Tailwind v4 with zero customization (no `tailwind.config.ts`)
- Tailwind v4 uses CSS-first config via `@theme` directive in CSS — no JS config needed
- All styling is inline Tailwind classes

### Icons (11 Unicode chars)
| Icon | Char | Where |
|------|------|-------|
| `⌂` | House | Dashboard nav |
| `◎` | Circle target | Scanner nav |
| `▤` | Grid lines | Charts nav |
| `⇄` | Swap arrows | Trades nav |
| `★` | Star | Scorecard nav |
| `▦` | Grid blocks | History nav |
| `↑` | Up arrow | Import nav |
| `◈` | Diamond | Paper Trading nav |
| `↻` | Reload | Backtest nav |
| `▲▼` | Triangles | Expand/collapse |

### Semantic Color Patterns Already In Use
- **BUY/Bullish:** `bg-green-900 text-green-300` / `text-green-400`
- **SELL/Bearish:** `bg-red-900 text-red-300` / `text-red-400`
- **Watch/Warning:** `bg-yellow-900 text-yellow-300`
- **Info/Primary:** `bg-blue-900 text-blue-300` / `text-blue-400`
- **Inside pattern:** `bg-purple-900 text-purple-300`
- **Outside pattern:** `bg-orange-900 text-orange-300`
- **Surfaces:** `bg-gray-950` (page) → `bg-gray-900` (card) → `bg-gray-800` (hover)
- **Borders:** `border-gray-800` (primary), `border-gray-700` (secondary)
- **Text hierarchy:** `text-white` → `text-gray-300` → `text-gray-400` → `text-gray-500`

### Chart Colors (hardcoded hex in CandlestickChart.tsx)
- Up: `#22c55e`, Down: `#ef4444`
- Entry: `#22c55e`, Stop: `#ef4444`, Target: `#3b82f6`
- Support: `#f59e0b`, Grid: `#1f2937`, BG: `#0a0a0a`

### Component Patterns Worth Preserving
- `rounded-lg bg-gray-900 p-4` — universal card pattern
- `text-xs text-gray-500 uppercase tracking-wider` — section headers
- `bg-{color}-900 text-{color}-300` — badge pattern (consistent dark-on-light within hue)
- `hover:bg-gray-800/50 transition-colors` — interactive hover

---

## Design Decisions

### Font Selection Rationale
- **Display:** Need something with character but still professional for a trading app. Not Inter (too generic, overused). Looking at: **DM Sans** (geometric, clean, great for headings), **Outfit** (modern geometric), **Plus Jakarta Sans** (distinctive humanist).
- **Body/Data:** Need high readability for dense data tables and numbers. **IBM Plex Sans** or **Plus Jakarta Sans** — both render well at small sizes.
- **Mono:** Need proper tabular number alignment for prices. **JetBrains Mono** (excellent number readability) or **IBM Plex Mono**.

### Color Strategy
- Keep the existing semantic mappings (green=bullish, red=bearish) — these are universal in trading
- Add depth to surfaces (current 3-tier gray system is flat)
- Add accent color for branding (the blue is fine but needs more presence)
- Create proper token names so colors are referenced semantically

### Icon Library Choice
- **Lucide React** — modern fork of Feather icons, tree-shakeable, 1000+ icons, MIT license
- Lightweight (each icon ~1KB), consistent 24x24 grid
- Better than heroicons (fewer icons) or react-icons (bloated bundle)
- Can be installed without touching existing components until ready to swap
