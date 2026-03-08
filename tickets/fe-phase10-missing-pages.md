# FE-P10: Missing Pages (Settings, Swing Trades, AI Coach)

**Priority:** P2 — Medium (feature completeness)
**Phase:** 10 of 10
**Depends on:** FE-P1 (Design System), FE-P6 (Tables/Forms)

---

## Problem Statement

Three Streamlit pages have not been ported to the React SPA: Settings, Swing Trades, and AI Coach. Users must fall back to the Streamlit UI for these features, breaking the experience.

**Impact:** Blocks full migration from Streamlit to React. Users can't manage settings or access AI features from the modern UI.

---

## Acceptance Criteria

### Settings Page
- [ ] User profile section (display name, email — read-only or editable)
- [ ] Tier display with upgrade CTA (if Free)
- [ ] Notification preferences (alert types, channels)
- [ ] Portfolio size setting (for position sizing calculations)
- [ ] Scanner preferences (default timeframe, risk percentage)
- [ ] Theme preferences (future: light/dark toggle)
- [ ] API key management (if applicable)

### Swing Trades Page
- [ ] Open swing positions table with: symbol, entry date/price, current price, P&L, holding days
- [ ] Close swing trade form with exit price + notes
- [ ] Swing trade history table
- [ ] Summary stats (avg hold time, win rate, avg R:R)
- [ ] Visual P&L indicator per position (green/red)

### AI Coach Page
- [ ] Trade journal entry selector (date picker or trade list)
- [ ] AI-generated narrative display (markdown rendered)
- [ ] Generate button with loading state
- [ ] History of past AI reviews
- [ ] Coaching insights cards (patterns, recommendations)

---

## Implementation Details

### API Endpoints Required
Reference existing Streamlit pages for API contract:
- Settings: `/api/v1/settings` (GET/PUT)
- Swing Trades: reuse `/api/v1/trades` with `trade_type=swing` filter
- AI Coach: `/api/v1/ai/coach` (POST to generate, GET for history)

### Files to Add
| File | Purpose |
|------|---------|
| `web/src/pages/SettingsPage.tsx` | User settings form |
| `web/src/pages/SwingTradesPage.tsx` | Swing trade management |
| `web/src/pages/AICoachPage.tsx` | AI narrative generation |

### Files to Modify
| File | Change |
|------|--------|
| `web/src/App.tsx` | Add new routes |
| `web/src/components/AppLayout.tsx` | Add nav items for new pages |
| `web/src/api/hooks.ts` | Add query hooks for new endpoints |
| `web/src/types/index.ts` | Add type definitions |

---

## Out of Scope
- AI model training/fine-tuning
- Real-time AI streaming responses
- Settings sync across devices
