# Implementation Plan: Landing & Internal Page Revamp (Spec 50)

**Branch**: `main` | **Date**: 2026-05-16 | **Spec**: [spec.md](./spec.md)
**Manifest**: [Spec 48 (V3 Revamp)](../48-v3-cleanup-and-paid-ai-revamp/spec.md)

## Summary

Spec 50 deletes the "5 AI pillars" landing pitch (which referenced the retired V1 AI scanner) and replaces it with the V2 positioning — one sentence, one live stat, four real deliverables, real proof. The route map work (FR-208) is mostly complete: Spec 49 already removed the 11 V1 React page imports + the `/trading-v1` route; this spec verifies the final shape and keeps the three legacy redirects. The new `LandingPage.tsx` is intentionally ~half the size of the current 934-line file because four pillars of marketing copy go away.

Technical approach: rewrite `web/src/pages/LandingPage.tsx` in place. No new components in `components/` — keep the page self-contained until the design proves itself, then extract. Reuse the existing Tailwind v4 design tokens (surface-0..4, text-primary..faint, accent blue). The track-record fetch hook is already there; we add FR-202b's graceful fallback (no `NaN%`, no empty slot). The "what you get" section ships with two live targets (Telegram screenshot, EOD recap deep link) and two "coming soon" affordances for spec 51 + spec 52 features, per FR-203.

## Technical Context

**Language/Version**: TypeScript 5.x, React 18, Vite 7
**Primary Dependencies**: React Router v6, TanStack Query, Tailwind v4 (CSS-first @theme), lucide-react icons
**Target Platform**: Modern Chromium browsers + iOS Capacitor build (existing)
**Project Type**: Web frontend (single-page React app under `web/`)
**Performance Goals**: First contentful paint ≤ 1.5s on cable (SC-202); hero stat renders within 3s even on slow API
**Constraints**: WCAG 2.2 AA (SC-204), mobile floor 360px (FR-206), 0 references to "AI scans the market"/"5 AI pillars"/`tradesignalwithai.com` (SC-203, SC-205)
**Scale/Scope**: Single page rewrite + light App.tsx verification. Touches one `.tsx` file primarily.

## Constitution Check

Substituting cross-cutting rules from Spec 48 as effective gates:

| Gate | Status |
|------|--------|
| No revival of "AI picks the trades" | ✅ This spec actively removes that framing |
| No new Streamlit dashboard | ✅ Pure React work |
| Tier model coordination | N/A — landing is pre-auth |
| Brand consistency with V2 (TradeCoPilot / tradingwithai.ai) | ✅ FR-211 enforces it |

**No FR amendments needed.** Pre-flight research is light because:
- `App.tsx` route map already matches FR-208 (Spec 49 cleanup did this work).
- `usePublicTrackRecord` hook already exists in `LandingPage.tsx` — just needs FR-202b fallback hardening.
- "Coming soon" affordances for specs 51/52 are explicitly allowed by FR-203.

The only soft risk: copy decisions ("what does the proof section actually say?"). Those are recorded in [contracts/copy-deck.md](./contracts/copy-deck.md) so they're reviewable before implementation lands.

## Project Structure

### Documentation (this feature)

```text
trade-analytics/specs/50-landing-revamp/
├── spec.md                       # (existed)
├── plan.md                       # this file
├── research.md                   # baseline + design rationale
├── data-model.md                 # repurposed: component breakdown
├── quickstart.md                 # implementation runbook
├── checklists/requirements.md    # (existed)
└── contracts/
    ├── copy-deck.md              # the exact words on the page (reviewable)
    ├── component-map.md          # the React component tree
    └── hero-stat-fallback.md     # FR-202b graceful fallback rules
```

### Source Code (what changes)

```text
trade-analytics/web/src/
├── pages/
│   └── LandingPage.tsx           # FULL REWRITE — 934 → ~400 LOC target
├── App.tsx                       # VERIFY — already matches FR-208 from Spec 49 work
└── index.css                     # NO CHANGE — design tokens already there
```

Out of scope: no edits to internal pages (Dashboard, Trading, etc.) beyond what App.tsx routing requires. Pricing page is out (Spec 11 / monetization is Interview Copilot's domain; trade-analytics monetization is a separate future spec).

## Complexity Tracking

| Concern | Resolution |
|---------|------------|
| Self-contained page vs. extracted components | Stay self-contained for v1. Extract `Hero`, `WhatYouGet`, `ProofSection` after the design is proven on the live landing |
| Live stat API may be slow / 0-data | FR-202b graceful fallback contract in `contracts/hero-stat-fallback.md` |
| Two of the four "what you get" items aren't shipped yet (Spec 51/52) | "Coming soon — join waitlist" badge per FR-203; waitlist email collection is operator-configurable, defaults to a `mailto:` link |
| Mobile floor 360px | Use `min-w-[320px]` and existing responsive utilities; no custom breakpoints |
| Brand consistency | Single source of truth: `TradeCoPilot` brand name, `tradingwithai.ai` URL; no `TradeSignal` references except as governed by Spec 49 FR-417's recorded decision |

## Phase 0: Research

**Status**: COMPLETE — see [research.md](./research.md). Key findings:

- Current `LandingPage.tsx` (934 LOC) marketed 5 AI pillars referencing the retired V1 AI scanner. Architecture: single self-contained component, no extracted sub-components, dark terminal aesthetic, uses existing design tokens.
- `App.tsx` route map already matches FR-208 (Spec 49 dropped the 11 V1 React page routes + the v1 TradingPage import). Three legacy redirects (`/scanner`, `/charts`, `/alerts` → `/trading`) are in place per FR-209.
- `usePublicTrackRecord` hook fetches `/api/v1/intel/public-track-record?days=90`; verified working from Spec 49 smoke test (returns `{period_days, total_signals, wins, losses, win_rate, by_alert_type}`). FR-202b's graceful fallback is partially missing (the `.catch(() => {})` silently fails; we'll add an explicit loading state).
- Design tokens defined in `web/src/index.css` (Tailwind v4 CSS-first @theme): surface-0..4, text-primary..faint, accent blue, bullish/bearish for green/red. Reuse, don't add.
- Lucide-react icons already a dependency.
- React Router v6 + TanStack Query: no new deps.

## Phase 1: Design & Contracts

**Outputs**:

1. **[data-model.md](./data-model.md)** — repurposed as "Component breakdown." Documents the LandingPage component tree (Nav, Hero, WhatYouGet, ProofSection, FinalCTA, Footer) with prop shapes.
2. **[contracts/copy-deck.md](./contracts/copy-deck.md)** — the exact words to ship. Reviewable before code lands.
3. **[contracts/component-map.md](./contracts/component-map.md)** — React-tree contract: what renders inside what, where the icons go, where the buttons go.
4. **[contracts/hero-stat-fallback.md](./contracts/hero-stat-fallback.md)** — the FR-202b contract: every code path for the hero stat ("loading", "no data", "API error", "happy path") with the exact rendered string.
5. **[quickstart.md](./quickstart.md)** — sequenced runbook.

**Agent context update**: skipped (same reason as Spec 49 plan; the trade-analytics CLAUDE.md was already rewritten and reference Spec 49 specifically).

## Phase 2: Task Planning Preview (NOT executed here)

`/speckit-tasks` would produce a sequence like:

- T1: Rewrite `LandingPage.tsx` against the copy deck + component map (single PR)
- T2: Verify `App.tsx` matches FR-208 + FR-209 (smoke check, no changes expected)
- T3: Manual accessibility scan (axe-core via browser extension, fix any AA criticals)
- T4: `npm run build` green + visual smoke at 1280px / 768px / 360px
- T5: 5-tester usability check for SC-201 (15-second comprehension) — manual, scheduled

Estimated: ~3 hours of focused implementation + ~1 hour of accessibility/responsive polish.

---

## Stop and report

Plan complete. Implementation can proceed against the contracts. No FR amendments needed; the only operator decision is the **waitlist email destination** for spec 51 + spec 52 "coming soon" CTAs (defaults to a `mailto:` link to a hard-coded inbox if not provided).
