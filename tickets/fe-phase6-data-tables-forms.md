# FE-P6: Data Tables & Forms

**Priority:** P1 — High (usability blocker for real usage)
**Phase:** 6 of 10
**Depends on:** FE-P1 (Design System Foundation)

---

## Problem Statement

Tables across the app (History, Real Trades, Paper Trading) have no pagination, sorting, or filtering. With real usage, these tables will have hundreds of rows and become unusable. Forms (trade open, import, backtest params) use manual `onChange` handlers with no validation or error states.

**Impact:** Directly blocks production usage — users can't work with large datasets or get feedback on invalid inputs.

---

## Acceptance Criteria

### Tables
- [ ] Reusable `DataTable` component with: column sorting, pagination, column-specific filtering
- [ ] Sticky header row on scroll
- [ ] Row hover highlight
- [ ] Responsive: horizontal scroll on mobile, or card layout below breakpoint
- [ ] Empty state for filtered results
- [ ] Row count and page indicator
- [ ] CSV export button integrated into table header

### Forms
- [ ] Reusable form input component with: label, error state, helper text
- [ ] Client-side validation using zod schemas
- [ ] Inline error messages (not just red text at top)
- [ ] Input focus ring matching design system accent
- [ ] Number inputs with proper formatting (currency, percentage)
- [ ] Select/dropdown with consistent styling
- [ ] Form submission loading state (button spinner)

---

## Implementation Details

### DataTable Component
- Props: `columns`, `data`, `sortable`, `paginate`, `pageSize`
- Internal state for sort direction, current page, filters
- Render: `<table>` with sticky header, paginated rows, footer controls

### Form Components
- `FormField` wrapper: label + input + error + helper
- Zod schema integration for validation on blur/submit
- Currency input: auto-format with `$` prefix

### Files to Modify
| File | Change |
|------|--------|
| `web/src/pages/HistoryPage.tsx` | Use DataTable component |
| `web/src/pages/RealTradesPage.tsx` | Use DataTable + FormField for trade open |
| `web/src/pages/PaperTradingPage.tsx` | Use DataTable for positions/history |
| `web/src/pages/BacktestPage.tsx` | Use FormField for parameters |
| `web/src/pages/ImportPage.tsx` | Polish upload form |

### Files to Add
| File | Purpose |
|------|---------|
| `web/src/components/ui/DataTable.tsx` | Reusable table with sort/page/filter |
| `web/src/components/ui/FormField.tsx` | Form input wrapper with validation |

### Dependencies to Add
| Package | Purpose |
|---------|---------|
| `zod` | Schema validation |

---

## Out of Scope
- Virtual scrolling for massive datasets (future optimization)
- Inline cell editing
- Drag-to-reorder columns
