# FE-P7: Charts Page Polish

**Priority:** P2 — Medium
**Phase:** 7 of 10
**Depends on:** FE-P1 (Design System Foundation)

---

## Problem Statement

The Charts page uses `lightweight-charts` for candlestick rendering which works well, but the surrounding UI (symbol selector, period toggles, level management) is basic. There's no crosshair data display, no volume overlay controls, no drawing tools or annotations.

**Impact:** Charts are a core workflow — traders spend significant time here. Polish elevates the professional feel.

---

## Acceptance Criteria

- [ ] Symbol selector is a searchable dropdown (not plain text input)
- [ ] Period toggles are pill-shaped buttons with active state
- [ ] Chart container has proper border/shadow matching design system
- [ ] Crosshair tooltip shows OHLCV data
- [ ] Volume bars shown below price chart (toggleable)
- [ ] Level lines have labels inline on chart (not just price lines)
- [ ] Level management panel is polished (add/edit/delete with color picker)
- [ ] Chart toolbar: zoom controls, reset view, fullscreen toggle
- [ ] Loading state shows chart-shaped skeleton
- [ ] Responsive: chart fills available width, min-height on mobile

---

## Implementation Details

### Files to Modify
| File | Change |
|------|--------|
| `web/src/pages/ChartsPage.tsx` | Toolbar, symbol search, period pills |
| `web/src/components/CandlestickChart.tsx` | Crosshair tooltip, volume overlay, controls |

---

## Out of Scope
- Drawing tools (trendlines, fibonacci)
- Multi-chart layout
- Indicator overlays (RSI, MACD)
