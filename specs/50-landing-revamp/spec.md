# Spec 50 — Landing & Internal Page Revamp (2026-05-16)

**Status**: Draft — buildable child of [Spec 48](../48-v3-cleanup-and-paid-ai-revamp/spec.md) (V3 manifest).
**Depends on**: nothing; can run in parallel with [Spec 49 (V1 Cleanup)](../49-v1-cleanup/spec.md). FR-205 (route consolidation) becomes safer once Spec 49's FR-404 (V1 React page deletion) lands, but landing copy + hero rework is independent.
**Touches**: `web/src/pages/LandingPage.tsx`, `web/src/App.tsx`, `web/src/pages/PublicEODReportPage.tsx`, `web/src/pages/TrackRecordPage.tsx` (consumer of the same `/api/v1/intel/public-track-record` stat).

## Why this spec exists

The current landing markets a product that no longer exists. Its "5 AI pillars" pitch (AI Coach, AI CoPilot, AI Scan, AI Review, AI Pattern Library) references the AI scanner that was retired in the V2 migration and the AI Coach that's also a deprecated surface. First-time visitors arrive expecting "AI scans the market and tells me what to trade," and either bounce confused or sign up for the wrong promise. The V2 product is a different, cleaner story: **TradingView's signal noise filtered into conviction-rated trade alerts, with an LLM second-pair-of-eyes on every one** — plus the AI Chart Critique and Pattern Education paid features arriving in 51 and 52. The landing should sell that, and the App.tsx route map should match.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Visitor understands the product in 15 seconds (Priority: P1)

A first-time visitor lands at `tradingwithai.ai`. Within 15 seconds of arriving they can articulate, in their own words, what the product does and what they would receive as a paying subscriber. The hero displays a single-sentence positioning; a live 90-day win-rate stat sits above the fold as proof; one primary CTA is unmistakable.

**Why this priority**: This is the entry to every other conversion path. Confusion here kills every downstream metric. Cheap to fix.

**Independent Test**: Five testers see the new landing for the first time on desktop and mobile. ≥4 can correctly explain within 15 seconds what the product does and what they would receive as a paying subscriber. None mistake the product for an "AI picks my trades" service.

**Acceptance Scenarios**:

1. **Given** the revamped landing, **When** a visitor arrives on desktop, **Then** the hero displays the one-sentence positioning ("TradingView's signal noise filtered into conviction-rated trade alerts, with an LLM second-pair-of-eyes on every one"), the live 90-day win-rate stat fetched from `/api/v1/intel/public-track-record?days=90`, and a single primary CTA.
2. **Given** the revamped landing on mobile (360px wide), **When** the visitor scrolls the hero into view, **Then** all three elements render correctly without horizontal scroll.
3. **Given** the hero stat fails to fetch (API timeout or zero data), **When** the visitor views the hero, **Then** a graceful fallback ("track record loading…") renders without breaking the layout; the page never shows "NaN%" or an empty stat slot.

---

### User Story 2 — "What you get" section markets the four V2 deliverables (Priority: P1)

Below the hero, the visitor sees a structured "what you get" section with four items in this order: Telegram conviction channel (with a real screenshot), the live EOD recap (deep-linked to `PublicEODReportPage`), the AI Chart Critique (new from Spec 51), Pattern Education with live examples (new from Spec 52). The retired AI-Scan pillar is absent. The retired AI-Coach pillar is absent.

**Why this priority**: The visitor's purchase decision hinges on understanding what's actually delivered. Listing dead pillars makes us look stale and dishonest.

**Independent Test**: In usability testing, ≥80% of visitors can name at least three of the four deliverables after reading the section once. None mention "AI scans the market" as a feature.

**Acceptance Scenarios**:

1. **Given** the "what you get" section, **When** a visitor scrolls to it, **Then** they see exactly the four items above, each with a one-line description and an inline visual (screenshot, sample, or chart).
2. **Given** the visitor clicks "live EOD recap", **When** the link resolves, **Then** they deep-link into the public `PublicEODReportPage` for the most recent trading day.
3. **Given** the visitor clicks "AI Chart Critique", **When** the link resolves, **Then** they arrive at the Chart Critique product page (post-Spec 51 launch) or, pre-launch, a "coming soon — join waitlist" surface.

---

### User Story 3 — Proof section runs on live data (Priority: P2)

The proof section under "what you get" shows live numbers: today's fired alerts count, the 90-day track-record breakdown by alert type, and a sample of last week's conviction-rated alerts pulled from the same data backing `TrackRecordPage`. No placeholder testimonials; no logos of companies we don't actually serve; no "9,576 engineers trust us" copy that we cannot verify.

**Why this priority**: Trust depends on verifiable proof. The product already produces verifiable proof — use it. P2 because the hero stat alone (US1) is enough to ship the landing; this strengthens it.

**Independent Test**: A visitor inspecting the proof section can click through to the underlying track-record page and reconcile every number shown.

**Acceptance Scenarios**:

1. **Given** the proof section, **When** the visitor reads it, **Then** every number shown is sourced from `/api/v1/intel/public-track-record` (or the same data backing `TrackRecordPage`) and is current as of the most recent trading session.
2. **Given** the visitor clicks any stat, **When** the link resolves, **Then** they arrive at the corresponding entry on `TrackRecordPage`.

---

### User Story 4 — Internal route map consolidated to V2-aligned pages (Priority: P1)

`App.tsx` routes only to V2-aligned pages. The V1 React pages no longer in use (`AlertsPage`, `ScannerPage`, `ChartsPage`, `ScorecardPage`, `HistoryPage`, `ImportPage`, `BacktestPage`, `PaperTradingPage`, `SwingTradesPage`, `AICoachPage`, `TradingPage` v1) are removed from the route map. Legacy URL paths `/scanner`, `/charts`, `/alerts` continue to redirect to `/trading` so deep links from prior emails and search engines still resolve.

**Why this priority**: The current `App.tsx` still references V1 pages (even if redirects mask them). Cleaning the route map is the prerequisite for Spec 49's FR-404 (V1 React page deletion).

**Independent Test**: Every public and protected route in the new `App.tsx` resolves to a V2-aligned page. The legacy redirect paths return HTTP 302 (or React Router redirect equivalent) to `/trading`.

**Acceptance Scenarios**:

1. **Given** the updated `App.tsx`, **When** a user navigates to `/scanner`, `/charts`, or `/alerts`, **Then** they are redirected to `/trading` and `TradingPageV2` loads.
2. **Given** the updated `App.tsx`, **When** an internal team member navigates to any V1 React page path that previously rendered (e.g., `/swing-trades`, `/import`), **Then** they see a 404 or are redirected to the dashboard, not a stale page.
3. **Given** the V3 paid-feature routes from Specs 51–54 launch, **When** they are added to `App.tsx`, **Then** they slot into the protected route group alongside `dashboard`, `trading`, `copilot`, etc. without re-introducing V1 imports.

---

### Edge Cases

- **Backend track-record endpoint returns zero data (cold start, holiday, post-cleanup)** — hero stat must render a graceful fallback per US1 AC3.
- **Visitor on a Hacker News spike** — landing must withstand a traffic burst without the API stat slowing the initial paint; SC-202 sets the latency floor.
- **A V3 paid feature mentioned in the "what you get" section is delayed past landing launch** — the section MUST gracefully label it as "coming soon" rather than vaporware-link; FR-203 covers this.
- **Mobile viewport at 320px (older devices)** — best-effort; spec floor is 360px (FR-204).
- **A visitor uses a screen reader** — hero copy and CTAs MUST have proper ARIA roles and alt text on screenshots; FR-207 covers this.
- **`PublicEODReportPage` link target is unavailable (Postgres slow)** — fallback to the previous trading day's recap rather than 404; FR-202b covers this.
- **An old `TrackRecordPage` URL with a specific date is shared and the date has no data** — landing-side proof should not link to broken date URLs; FR-303 covers this by only linking to dates with confirmed data.

## Requirements *(mandatory)*

### Functional Requirements

#### Hero

- **FR-201**: The `LandingPage.tsx` hero MUST display a single-sentence positioning: "TradingView's signal noise filtered into conviction-rated trade alerts, with an LLM second-pair-of-eyes on every one." No reference to "5 AI pillars" or to AI scanning the market for trades.
- **FR-202**: The hero MUST display a live 90-day win-rate stat fetched from `/api/v1/intel/public-track-record?days=90`, visible above the fold on desktop and on the first screen of mobile (≥360px viewport).
- **FR-202b**: If the public-track-record endpoint returns no data or times out, the hero MUST render a graceful fallback ("track record loading…") without breaking layout; the page MUST NOT show "NaN%" or an empty stat slot.

#### "What you get" section

- **FR-203**: The landing MUST display a structured "what you get" section listing exactly these four items in this order: (a) Telegram conviction channel (with a real Telegram screenshot), (b) live EOD recap (deep-linked to `PublicEODReportPage`), (c) AI Chart Critique (new — Spec 51), (d) Pattern Education with live examples (new — Spec 52). Pre-launch of (c) or (d), the section MUST label them "coming soon — join waitlist" rather than link to vaporware.

#### Proof section

- **FR-204**: The landing MUST include a proof section below "what you get" with live numbers (today's fired alerts count, 90-day track-record breakdown by alert type, sample of last week's conviction-rated alerts). All numbers MUST be sourced from the same data backing `TrackRecordPage`.
- **FR-205**: The proof section MUST NOT contain placeholder testimonials, logos of unaffiliated companies, or unverifiable user counts.

#### Mobile responsiveness

- **FR-206**: The landing MUST render correctly on viewports down to 360px wide with the primary CTA reachable without horizontal scroll.

#### Accessibility

- **FR-207**: Hero text, CTAs, and inline screenshots MUST have proper semantic HTML, ARIA roles, and alt text. The page MUST pass an automated accessibility scan (WCAG 2.2 AA).

#### Route map (App.tsx)

- **FR-208**: `App.tsx` MUST route only to V2-aligned pages. Specifically, the public route set MUST be exactly: `/`, `/learn`, `/learn/:cat`, `/learn/patterns/:patternId`, `/replay/:alertId`, `/public/eod-report[/:date[/:symbol]]`, `/track-record[/:date[/:symbol]]`, `/login`, `/register`, `/reset-password`. The protected route set (wrapped in `AppLayout`) MUST contain: `dashboard`, `trading` (`TradingPageV2`), `copilot` (`AICoPilotPage`), `review`, `eod-report`, `trades`, `settings`, `billing`, `admin`, `ai-updates`, `watchlist`, `premarket`. The V1 React pages listed in Spec 49 FR-404 MUST be removed from the route map.
- **FR-209**: Legacy redirects `/scanner`, `/charts`, `/alerts` → `/trading` MUST be retained so prior deep links resolve.
- **FR-210**: New V3 paid-feature routes from Specs 51 (`/chart-critique`), 53 (replay-with-coach), 54 (digest opt-in) MUST slot into the protected route group as they ship, without re-introducing V1 imports.

#### Brand consistency

- **FR-211**: All landing copy, screenshots, and metadata MUST use the V2 brand (`TradeCoPilot` / `tradingwithai.ai`). No reference to the legacy `TradeSignal` / `tradesignalwithai.com` brand except in a footer link governed by Spec 49 FR-417's decision.

### Key Entities *(if applicable)*

- **Hero Stat**: The live 90-day win-rate value rendered above the fold. Single source: `/api/v1/intel/public-track-record?days=90`.
- **What-you-get Item**: A pair of (headline, one-line description, inline visual) describing one of the four V2 deliverables.
- **Proof Stat**: A single live number on the proof section, sourced from `TrackRecordPage`'s underlying data.

## Success Criteria *(mandatory)*

- **SC-201**: In usability testing with ≥5 first-time visitors, ≥80% can correctly explain in their own words within 15 seconds what the product does and what they would receive as a paying subscriber.
- **SC-202**: The landing reaches first contentful paint in under 1.5 seconds on a cable-quality connection; the hero stat renders within 3 seconds even when the API is slow (graceful fallback per FR-202b).
- **SC-203**: 0 references to "AI scans the market," "5 AI pillars," or any retired V1 pillar on the live landing.
- **SC-204**: Landing passes an automated WCAG 2.2 AA accessibility scan with 0 critical violations.
- **SC-205**: 0 references to `tradesignalwithai.com` on the landing page DOM except as governed by Spec 49 FR-417's recorded decision.
- **SC-206**: All four "what you get" items either link to a live surface or display "coming soon — join waitlist" with a working waitlist form; 0 broken or vaporware links.
- **SC-207**: Bounce rate on the new landing ≤ bounce rate on the current landing across the first 30 days post-launch (tracked via GA4).

## Assumptions

- The current `/api/v1/intel/public-track-record` endpoint continues to return the same data shape. If Spec 49's cleanup changes that endpoint, this spec's hero stat work coordinates with it.
- The "coming soon" affordance for Specs 51 and 52 is acceptable for landing launch even before those specs ship.
- Brand finalization is complete (TradeCoPilot / tradingwithai.ai). If branding changes, this spec re-runs.
- The legacy `tradesignalwithai.com` decision is recorded in Spec 49 FR-417 and respected here.
- GA4 instrumentation already exists in the landing per the audit; SC-207 leverages it without new tracking work.
- Mobile floor is 360px; older devices below this are best-effort.
- This spec does not change the marketing copy on protected internal pages (Dashboard, Trading, etc.) beyond what FR-208's route consolidation requires.
