# Trading Platform UX Research (Apr 2026)

## Key Findings from Competitor Analysis

### Layout Patterns
- **Webull**: 3-column (watchlist 15%, chart 60%, order/L2 25%). All panels drag-resizable. Zero-latency watchlist→chart linking.
- **TradingView**: Chart-first (80-90%). Left icon rail (48px) expands to panels on click. Bottom panel collapsible.
- **Thinkorswim**: Multi-panel workspace system. Named layouts. Power-user focused.
- **Robinhood**: Single-column card-based. Chart 60% height. Buy/sell always visible.

### Recommended Color Palette (Dark)
```
Background:   #0D1117 (base) → #161B22 (surface) → #1C2128 (elevated)
Border:       #30363D (subtle, never bright)
Text:         #E6EDF3 (primary) → #8B949E (secondary) → #484F58 (tertiary)
Bullish:      #3FB68B (soft green, not #00FF00)
Bearish:      #FF6388 (soft red, not #FF0000)
Warning:      #F0B90B (amber)
Accent:       #58A6FF (blue for CTAs)
```

### Critical UX Principles for Trading
1. **Speed** — Zero latency between watchlist click and chart update
2. **Information density without clutter** — lots of data, clear hierarchy
3. **Context-sensitive panels** — right info appears automatically
4. **Keyboard-first** — power users never touch mouse for common actions
5. **Muted colors with purpose** — color means something (up/down/alert), never decorative

### Recommended Layout for TradeCoPilot V2
```
┌─────────────────────────────────────────────────────┐
│ Top Bar: Logo | Search (⌘K) | Market Status | 🔔    │
├────────┬────────────────────────────────┬───────────┤
│ Left   │     Chart (65-70%)             │  Right    │
│ Rail   │                                │  Panel    │
│ 48px   │     Tabs: Chart | Signals |    │  280px    │
│ icons  │     Scanner | AI Coach         │  Tabbed:  │
│        │                                │  AI/Flow/ │
│        ├────────────────────────────────┤  Levels   │
│        │ Bottom: Setup info + levels    │           │
└────────┴────────────────────────────────┴───────────┘
```

### Implementation Notes
- Use `react-resizable-panels` for drag-resize
- CandlestickChart (lightweight-charts) with canvas rendering
- Persist layout to localStorage/DB
- Flash price changes with 300ms fade animation
- Skeleton screens, never spinners
- Mobile: bottom tab bar, chart full-width, swipe to change symbols
