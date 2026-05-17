# Spec 52 — Pattern Education with Live Examples (2026-05-16)

**Status**: Draft — buildable child of [Spec 48](../48-v3-cleanup-and-paid-ai-revamp/spec.md) (V3 manifest).
**Depends on**: [Spec 49 (V1 Cleanup)](../49-v1-cleanup/spec.md) — the `alerts` table consumed here is the V2 production source; cleanup must complete so the read path is stable.
**Coexists with**: [Spec 51 (Chart Critique)](../51-chart-critique/spec.md) — independent; shares tier-gating machinery; pattern taxonomies must stay consistent across both.
**Touches**: `web/src/pages/PatternDetailPage.tsx`, `web/src/pages/LearnDetailPage.tsx`, `web/src/components/ai/PatternEducation.tsx`, `PatternLibrary.tsx`, `data/pattern_content.py`, `api/app/routers/learn.py`.

## Why this spec exists

Every "AI trading platform" ships a pattern library. Almost all of them are static textbook content. The V2 product has something nobody else has: a live `alerts` table fed by Pine indicators that fires labeled setups every trading day. Joining the existing pattern library to that live alerts stream turns dead educational content into a living teaching surface: "here's the textbook Bull Flag — and here's the same setup, today, on NVDA." This is a small but disproportionately compelling differentiator and a strong Pro-tier sweetener.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — See live, today's examples for any pattern (Priority: P1)

A Pro-tier subscriber opens any pattern in the library. Below the textbook explanation they see a "live examples from this week" section populated from the `alerts` table: real fired alerts from the last 14 trading days that match the pattern, each with the chart, the timestamp, and a one-line annotation explaining what made the alert match. The list refreshes on page load — today's matches appear at the top.

**Why this priority**: This is the entire reason the spec exists. Static education exists everywhere; living examples don't.

**Independent Test**: For each of the top 5 most-fired patterns in the live alerts table, the corresponding `PatternDetailPage` shows ≥1 real fired alert from the prior 7 trading days, within 1 second of page load, with the chart, timestamp, and a one-line match annotation.

**Acceptance Scenarios**:

1. **Given** a Pro-tier subscriber on `PatternDetailPage` for a pattern that has recent matches, **When** they view the page, **Then** the live-examples section renders within 1 second showing alerts from the configured lookback window (default 14 trading days), most-recent-first.
2. **Given** each live example, **When** the subscriber views it, **Then** they see the ticker, the alert's chart (existing alert chart rendering), the timestamp, and a one-line annotation explaining the match (e.g., "broke PDH on rising volume, held above for 3 bars").
3. **Given** a live example is clicked, **When** the subscriber follows the link, **Then** they deep-link into the corresponding entry on `PublicEODReportPage` or `ReplayPage` (existing surfaces).

---

### User Story 2 — Graceful empty state for dormant patterns (Priority: P1)

A subscriber opens a pattern that has zero matches in the lookback window (e.g., it's a rare pattern, or the market hasn't produced one this week). Instead of empty silence, they see a clearly-labeled "no recent live examples — here's the textbook explanation" affordance, plus a link to the most recent historical match (if any exists in the wider alerts archive).

**Why this priority**: A landing-page-style "0 results" hole on every dormant pattern would feel broken. Empty states are not optional.

**Independent Test**: Identify a pattern with zero matches in the last 14 days. Open the page. Verify the empty-state copy renders and (if a historical match exists) the historical link resolves.

**Acceptance Scenarios**:

1. **Given** a pattern with zero matches in the configured lookback window, **When** a subscriber views the page, **Then** they see a "no recent live examples — here's the textbook explanation" affordance.
2. **Given** the same pattern has historical matches outside the lookback window, **When** the subscriber views the empty state, **Then** a "see the most recent match (older than 14 days)" link is visible and resolves to the historical alert.

---

### User Story 3 — Free-tier teaser, Pro-tier full access (Priority: P2)

Free-tier visitors see the count of recent live matches ("5 live examples this week") but the alert detail rendering (chart + annotation + deep link) is gated. A clear upgrade CTA replaces the alert list. This is enough to convey value and motivate upgrade without giving the feature away.

**Why this priority**: Without a tier gate, the Pro-tier sweetener stops working. Without a Free teaser, conversion craters.

**Independent Test**: Visit any pattern page in a Free account; verify the count is visible but the detailed alert list is replaced by an upgrade CTA. Upgrade; verify the alert list renders.

**Acceptance Scenarios**:

1. **Given** a Free-tier visitor, **When** they view a `PatternDetailPage` with live matches, **Then** they see the count of recent matches and an upgrade CTA in place of the detailed list.
2. **Given** the visitor upgrades to Pro, **When** they revisit the page, **Then** the detailed alert list renders within 1 second.

---

### Edge Cases

- **Pattern has matches but the matches are on halted or delisted symbols** — symbol state badge ("trade halted", "delisted") MUST be visible on the live example so the subscriber doesn't take it as "buyable setup right now."
- **A pattern has > 50 matches in the lookback window** — list is paginated or capped at a configurable limit (default 20 most recent) to keep the page snappy.
- **The `alerts` table is briefly unavailable** — page falls back to the textbook content with a small "live examples temporarily unavailable" notice rather than failing the whole page.
- **A pattern taxonomy mismatch** — Spec 51's `PATTERN_LIBRARY` and this spec's `pattern_content.py` MUST agree on pattern keys; FR-503 enforces this.
- **Mobile rendering** — live example chart thumbnails must remain readable at 360px viewport.
- **Sensitive symbol** (e.g., recently halted or major news event) — annotation should reflect the context rather than read as a neutral "buyable setup".

## Requirements *(mandatory)*

### Functional Requirements

#### Data join

- **FR-501**: `PatternDetailPage.tsx` MUST display a "live examples from this week" section populated by joining `data/pattern_content.py` to the `alerts` table on a configurable lookback window (default 14 trading days).
- **FR-502**: The join MUST be done via a new endpoint (e.g., `GET /api/v1/learn/patterns/:patternId/live-examples?lookback_days=N`) that returns the matching alerts ordered most-recent-first, capped at a configurable limit (default 20).
- **FR-503**: Pattern keys in `data/pattern_content.py` MUST match the alert-type vocabulary in `analytics/alert_types.py` (extracted in Spec 49 FR-407). Mismatches MUST cause a build-time error, not a silent empty live-examples section.

#### Rendering

- **FR-504**: Each live example MUST render: the ticker, the alert's chart (using existing alert chart rendering primitives like `StaticTradeChart.tsx`), the timestamp, and a one-line annotation explaining what made the alert match.
- **FR-505**: Each live example MUST deep-link to its corresponding entry on `PublicEODReportPage` or `ReplayPage`.
- **FR-506**: Live-example chart thumbnails MUST remain readable at viewports down to 360px wide.
- **FR-507**: For alerts on symbols that are halted, delisted, or under a known major-news event flag, a clearly-visible state badge MUST appear on the live example so the subscriber doesn't read it as "buyable setup right now."

#### Empty / failure states

- **FR-508**: When a pattern has zero matches in the configured lookback window, the page MUST render a "no recent live examples — here's the textbook explanation" affordance rather than empty silence.
- **FR-509**: When historical matches exist outside the lookback window for an empty-state pattern, a "see the most recent match (older than {N} days)" link MUST be visible and resolve to the historical alert.
- **FR-510**: When the `alerts` table read fails, the page MUST fall back to textbook content with a small "live examples temporarily unavailable" notice and MUST NOT fail the whole page.

#### Tier gating

- **FR-511**: Free-tier visitors MUST see the count of recent live matches ("5 live examples this week") visible, but the detailed alert list MUST be gated. An upgrade CTA MUST replace the detailed list.
- **FR-512**: Pro-tier subscribers MUST see the full detailed alert list per FR-501.
- **FR-513**: Tier gating MUST use the existing `tier.py` + `useFeatureGate.ts` machinery.

### Key Entities *(if applicable)*

- **Pattern (existing)**: A named chartist pattern in `data/pattern_content.py`. Carries display name, textbook explanation, and a `pattern_key` that matches the alert-type vocabulary from `alert_types.py`.
- **Pattern Live Match**: A read-only view joining a Pattern to recent rows from `alerts` where `alert_type` maps onto `pattern_key`. Returned by the new endpoint in FR-502.

## Success Criteria *(mandatory)*

- **SC-501**: For each of the top 5 most-fired patterns in the live alerts table, `PatternDetailPage` shows ≥1 real fired alert from the prior 7 trading days within 1 second of page load.
- **SC-502**: 0 cases of a pattern-taxonomy mismatch silently rendering an empty live-examples section; mismatches MUST raise a build-time error per FR-503.
- **SC-503**: For patterns with zero recent matches, ≥95% of usability-test participants correctly understand they are looking at a dormant pattern (not a broken page) after seeing the empty state.
- **SC-504**: 0 cases of a Free-tier user accessing detailed live-example alert content beyond the count teaser.
- **SC-505**: ≥5% of Free-tier visitors who land on a `PatternDetailPage` with live matches click the upgrade CTA, measured across the first 30 days after launch.
- **SC-506**: Live-example rendering remains usable at 360px viewport; verified by automated visual regression.
- **SC-507**: 100% of live examples on halted or delisted symbols display the state badge required by FR-507.

## Assumptions

- The `alerts` table and the `pattern_content.py` taxonomy can be aligned; if Spec 49's FR-407 alert-types extraction produces a different vocabulary than `pattern_content.py` expects, this spec re-aligns them rather than letting the mismatch silently break live examples.
- The existing alert chart rendering primitives (`StaticTradeChart.tsx` and friends) are suitable for the thumbnail render; no new chart-rendering work is required.
- Halted / delisted / major-news symbol state is available via an existing market-data path (`analytics/market_data.py` or similar). If not, FR-507 ships in a follow-up rather than blocking the rest.
- Tier definitions are coordinated with Spec 51's tier model; both use the same `tier.py` source of truth.
- Pagination beyond the default cap (20) is out of scope for v1; a "see more in EOD report" link is acceptable.
- The lookback window default is 14 trading days; operator-configurable per FR-501.
- Semantic search across patterns ("find me all flag-shaped patterns") is out of scope for v1.
