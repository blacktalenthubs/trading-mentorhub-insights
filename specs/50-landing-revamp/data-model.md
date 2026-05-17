# Component Breakdown — Spec 50 (Phase 1 Design)

**Purpose**: For a UI-revamp spec, the structural design output is the React component tree, not a data model. This file documents the component breakdown, prop shapes, and where each FR lands.

---

## Component tree

```
LandingPage (page-level component, default export)
├── LandingNav                      — sticky top nav
│   ├── BrandMark                   — TradeCoPilot wordmark + icon
│   ├── NavLinks (desktop)          — Pattern Library, Track Record
│   ├── MobileMenu (≤ md)           — <details> dropdown with same links
│   └── AuthLinks                   — Sign in, Get started
│
├── Hero                            — above-fold: positioning + stat + CTA
│   ├── PositioningHeadline         — single sentence (FR-201)
│   ├── HeroStat                    — live win-rate stat or fallback (FR-202, FR-202b)
│   └── PrimaryCTA                  — single button (FR-201, FR-202b safe)
│
├── WhatYouGet                      — 4 deliverables (FR-203)
│   ├── Deliverable: TelegramChannel       — live, links nowhere (Telegram is off-platform)
│   ├── Deliverable: EODRecap              — live, deep links to /public/eod-report
│   ├── Deliverable: ChartCritique         — coming soon (Spec 51)
│   └── Deliverable: PatternEducationLive  — coming soon (Spec 52)
│
├── ProofSection                    — live numbers (FR-204, FR-205)
│   ├── StatGrid                    — today's fired-alerts count + 90-day win/loss/rate
│   └── ProofCTA                    — "see the full record →" → /track-record
│
├── FinalCTA                        — closing sign-up push
│   └── PrimaryCTA (reused)
│
└── Footer                          — minimal: links, brand, year
```

---

## Prop shapes (lifted state lives at LandingPage level)

```ts
// The 3-state machine for the live hero stat (FR-202b safety contract)
type TrackRecordState =
  | { status: "loading" }
  | { status: "ok"; data: TrackRecord }
  | { status: "error" };

interface TrackRecord {
  period_days: number;
  total_signals: number;
  wins: number;
  losses: number;
  win_rate: number;          // 0..1, float (server returns 0.0 when no data — that's "ok" not "error")
  by_alert_type: Record<string, { wins: number; losses: number }>;
}
```

Hook:
```ts
function usePublicTrackRecord(days: number = 90): TrackRecordState
```

Subcomponent prop interfaces (inferred from tree):

```ts
interface HeroStatProps {
  state: TrackRecordState;
}

interface DeliverableProps {
  icon: LucideIcon;
  label: string;
  headline: string;
  body: string;
  status: "live" | "coming-soon";
  cta?: {
    label: string;
    href: string;              // internal or mailto for waitlist
    external?: boolean;        // for the Telegram link, future
  };
}

interface ProofSectionProps {
  state: TrackRecordState;
}
```

---

## Where each FR lands

| FR | Component | Notes |
|----|-----------|-------|
| **FR-201** Positioning sentence | `PositioningHeadline` inside `Hero` | One `<h1>`, semantic markup |
| **FR-202** Live 90-day stat | `HeroStat` inside `Hero` | Consumes `state` from `usePublicTrackRecord()` |
| **FR-202b** Graceful fallback | `HeroStat` → see [hero-stat-fallback.md](./contracts/hero-stat-fallback.md) | Three render branches, never `NaN%` |
| **FR-203** 4 deliverables | `WhatYouGet` → 4 × `Deliverable` | Two `status="live"`, two `status="coming-soon"` |
| **FR-204** Live proof | `ProofSection` → `StatGrid` | Numbers sourced from same `state` as hero |
| **FR-205** No placeholders | (test) — manual grep verifies no `lorem`, no fake testimonials, no unaffiliated logos in DOM | |
| **FR-206** Mobile 360px | All components use existing responsive utilities; `MobileMenu` for ≤ md viewports | |
| **FR-207** Accessibility | All `<button>` / `<a>` are semantic; alt text on images; ARIA roles where needed; reduced-motion respect | |
| **FR-208** Route map | `App.tsx` — already matches per research §2 | No changes |
| **FR-209** Legacy redirects | `App.tsx` — already in place | No changes |
| **FR-210** New paid routes slot in later | `App.tsx` — out of scope this spec | |
| **FR-211** Brand consistency | All copy + alt text uses TradeCoPilot / tradingwithai.ai | Audit by SC-205 |

---

## State management

- No global state needed. Component is self-contained.
- `useState` + `useEffect` for the API fetch (matches existing pattern, no TanStack Query for landing).
- Mobile menu open/close: local `useState` inside `LandingNav` (or `<details>` for accessible no-JS).
- No analytics calls in this revamp (existing GA4 instrumentation in `index.html` continues to fire route changes).

---

## Files touched

| File | Change |
|------|--------|
| `web/src/pages/LandingPage.tsx` | Full rewrite, target ≤400 LOC |
| `web/src/App.tsx` | Verify only — no edits expected |

**Not created**: no new files in `web/src/components/`. If a sub-component proves reusable post-launch, extract it then.
