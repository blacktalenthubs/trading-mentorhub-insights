# Feature Specification: Persisted Daily Focus List from AI Best Setups

**Feature Branch**: `55-best-setup-focus-list`
**Created**: 2026-05-20
**Status**: Draft
**Input**: User description: "currently we have an ai feature which analyses watchlist and tells us best setup — we need to be able to use these recommendations for tomorrow's trade. At close of market today I run the best setup, the list provided becomes my focus list for tomorrow so I focus on best setups. Right now once I run it the output disappears after refresh. Need a better way to output and persist to the user. What is the AI cost for running this twice a day — before open and after close. Run before open → focus list based on best setups; toward EOD before close → see better swing setups. Make this feature better, useful output, persist recommendations so users don't have to ask AI more than twice a day when they only need details. Also bring this to a dedicated page so it's easier for users to analyse the outputs."

## Clarifications

### Session 2026-05-20

- Q: Best-setup criteria — documented in this spec, or deferred to the existing AI engine? → A: Defer the scoring/selection to the existing AI engine (this feature does NOT redefine it). But every saved recommendation MUST surface the qualifying criteria it met — entry trigger, conviction drivers — and whether it suits the day-trade window or a swing hold, so the trader can independently judge why it qualified as a "best setup".
- Q: How is a setup classified day-trade vs swing — by run window, or per-setup? → A: Each scan returns BOTH; every setup is tagged day-trade or swing per-setup by the engine. The run window does NOT change what the scan returns — it only sets the focus-list page's default emphasis (pre-open emphasizes day-trade setups, pre-close emphasizes swing setups).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Focus list persists and survives refresh (Priority: P1)

A trader runs the AI "Best Setups" scan across their watchlist. The ranked list of day-trade and swing candidates appears — but the moment they refresh the page or navigate away, it is gone, and they must spend another AI run to see it again. In this story, every completed scan is **saved**. After running it once, the trader can refresh, close the browser, return hours or a day later, and the same ranked recommendations are still there, labelled with when they were generated.

**Why this priority**: This is the headline pain — the output vanishes. Until the result is durable, nothing else matters; the trader cannot treat the list as a plan or a focus list for the next session.

**Independent Test**: Run the Best Setups scan, note the recommendations, refresh the page → the identical list is still displayed with a "generated at" timestamp, and no new AI run was consumed. Reopen the app the next morning → the prior list is still retrievable.

**Acceptance Scenarios**:

1. **Given** a trader has run the Best Setups scan, **When** they refresh the page, **Then** the same ranked recommendations are displayed without consuming another AI run.
2. **Given** a saved focus list from a prior session exists, **When** the trader returns the next day before running a new scan, **Then** the previous list is still viewable and clearly marked as a previous session's list.
3. **Given** a scan produced zero qualifying setups, **When** the result is saved, **Then** the trader sees an explicit "no setups found" record rather than a blank panel.

---

### User Story 2 - Dedicated focus-list page for review and analysis (Priority: P1)

Today the best setups render in a cramped side panel next to the chart. The trader wants a **dedicated page** where the focus list is the primary content — each recommendation laid out with its setup type, conviction, entry/stop/targets, the AI's reasoning, and a way to jump to the chart. This page is where they plan their session: review the candidates, decide which to focus on, and drill into details.

**Why this priority**: The user explicitly asked for this. A side panel is for glancing; a planning workflow needs a real page. Persistence (US1) only delivers value if there is a good place to consume it.

**Independent Test**: Navigate to the focus-list page → the most recent saved focus list is rendered as the main content, each recommendation expandable to full detail, with no AI run triggered just by viewing.

**Acceptance Scenarios**:

1. **Given** a saved focus list, **When** the trader opens the focus-list page, **Then** every recommendation is displayed with symbol, setup type, direction, conviction tier, entry/stop/T1/T2, and the AI's reasoning.
2. **Given** the trader is on the focus-list page, **When** they select a recommendation, **Then** they can view its chart and full detail without spending an AI run.
3. **Given** no scan has ever been run, **When** the trader opens the focus-list page, **Then** they see guidance prompting them to run their first scan.

---

### User Story 3 - Twice-daily cadence: pre-open and pre-close runs with window-based emphasis (Priority: P2)

The trader works in two windows. **Before the open**, they run the scan — it returns both day-trade and swing candidates, and the page emphasizes the day-trade-tagged setups they can act on today. **Toward the close**, they run it again — the same scan returns both, but the page now emphasizes the swing-tagged setups worth carrying into tomorrow. Each run is saved separately and labelled by its window, so the trader can see the pre-open and pre-close runs side by side. The system gently caps runs so the trader does not burn AI repeatedly when they only need to re-read saved details.

**Why this priority**: Persistence and the dedicated page (P1) deliver the core value on their own. The twice-daily framing organizes the feature into the trader's actual routine and controls AI cost — valuable, but an enhancement layered on top of P1.

**Independent Test**: Run a scan in the morning → saved and labelled as a pre-open run; the page emphasizes day-trade-tagged setups. Run again near close → saved separately as a pre-close run; the page emphasizes swing-tagged setups. Both runs are viewable; a third run the same day is blocked or clearly flagged as beyond the recommended cadence.

**Acceptance Scenarios**:

1. **Given** the trader runs a scan before market open, **When** it completes, **Then** it is saved and labelled as a pre-open run, and the focus-list page emphasizes the day-trade-tagged recommendations (swing-tagged ones still present).
2. **Given** the trader runs a scan before market close, **When** it completes, **Then** it is saved and labelled as a pre-close run, and the focus-list page emphasizes the swing-tagged recommendations (day-trade-tagged ones still present).
3. **Given** the trader has already run the recommended two scans for the day, **When** they attempt a third, **Then** the system explains the prior results are still saved and discourages an unnecessary run.
4. **Given** both a pre-open and a pre-close run exist for a day, **When** the trader views the focus-list page, **Then** both are accessible and distinguishable by window.

---

### Edge Cases

- A scan run mid-day (outside both windows) is still saved, labelled with its actual run time, but not tagged as the canonical pre-open or pre-close list.
- When the AI scan fails or times out, the trader sees a clear failure state and the previous saved list remains intact — a failed run never destroys a good list.
- When the watchlist is empty, the scan returns an explicit "add symbols to your watchlist" message rather than an empty result.
- A stale list (e.g. yesterday's, viewed today) is shown clearly marked as a previous session's list, with a prompt to run a fresh one.
- When the trader's plan/tier daily scan limit is already reached, all saved lists remain fully viewable; only generating a NEW scan is blocked, with the limit explained.
- As the market moves and entries get hit or invalidated, the saved list is treated as a snapshot at generation time — live re-evaluation is out of scope for v1 (see Assumptions).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST save every completed Best Setups scan result so it persists across page refreshes, navigation, and sessions.
- **FR-002**: System MUST display the most recent saved focus list without consuming an AI scan run.
- **FR-003**: System MUST record, for each saved scan, the date and time it was generated and the market window it falls in (pre-open, pre-close, or other).
- **FR-004**: System MUST retain saved focus lists as a browsable history so the trader can review prior sessions' lists.
- **FR-005**: System MUST provide a dedicated focus-list page where saved recommendations are the primary content.
- **FR-006**: Each recommendation MUST display its symbol, setup type, direction, conviction tier, entry, stop, target 1, target 2, and the AI's plain-language reasoning.
- **FR-007**: Users MUST be able to open a recommendation's chart and full detail from the focus-list page without triggering a new AI run.
- **FR-008**: System MUST tag every recommendation as day-trade or swing using the per-setup classification from the existing AI engine; a single scan returns both types within one focus list.
- **FR-015**: The focus-list page MUST set its default emphasis from the run's market window — a pre-open run emphasizes day-trade-tagged recommendations, a pre-close run emphasizes swing-tagged recommendations — while still showing both types.
- **FR-009**: System MUST clearly label a focus list as current vs. stale relative to the active trading session.
- **FR-010**: System MUST cap or discourage AI scan runs beyond the recommended twice-per-day cadence, while keeping all previously saved lists fully viewable when the cap is reached.
- **FR-011**: System MUST preserve the previous saved focus list if a new scan fails, so a failed run never leaves the trader with no list.
- **FR-012**: System MUST handle and clearly communicate the empty-watchlist and zero-setups-found cases as explicit saved states, not blank output.
- **FR-013**: System MUST make each saved scan's recommendations available for detail review on demand without re-invoking the AI.
- **FR-014**: Each recommendation MUST surface the qualifying criteria it met — the entry trigger, the conviction drivers, and whether the setup suits the day-trade window or a swing hold — so the trader can independently judge why it qualified. The scoring and selection are performed by the existing AI engine; this feature does NOT redefine that criteria, only makes it visible per recommendation.

### Key Entities *(include if feature involves data)*

- **Focus List**: A saved snapshot of one AI Best Setups scan, containing both day-trade and swing recommendations. Attributes: generation timestamp, market window (pre-open / pre-close / other), target trading-session date, owning user, overall status (has-setups / no-setups / failed).
- **Setup Recommendation**: A single ranked candidate within a Focus List. Attributes: symbol, setup type (e.g. PDL bounce, MA bounce, weekly-low confluence), trade horizon (day-trade / swing — tagged per-setup by the engine), direction, conviction tier (high / medium / low), entry / stop / target 1 / target 2, distance-to-entry, qualifying criteria met, supporting reasoning, supporting tags or levels.
- **Watchlist**: The set of symbols the scan analyzes (existing entity — referenced, not redefined).
- **Scan Run Quota**: The per-user, per-day allowance of AI scans, tracked to enforce the twice-daily cadence (existing concept — extended).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A focus list generated by a scan remains visible after a page refresh 100% of the time — zero loss of output.
- **SC-002**: A trader can review a previously generated focus list and drill into any recommendation's details with zero additional AI scan runs.
- **SC-003**: Traders invoke the AI scan no more than twice per trading day on average, down from repeated re-runs caused by lost output.
- **SC-004**: A trader can locate and open their current focus list from the dedicated page in under 10 seconds.
- **SC-005**: At least 30 days of focus-list history is retrievable for review.
- **SC-006**: A failed or empty scan never replaces or destroys a previously saved focus list (verified — 100%).
- **SC-007**: For a given day, the pre-open and pre-close lists are both distinguishable and accessible without ambiguity.

## Assumptions

- Scans are run **manually** by the trader (the user described "I run the best setup"); the system does not auto-schedule scans in v1, but it labels each run by the window it falls in and nudges toward the twice-daily cadence.
- The twice-daily cadence is **pre-open** (before the 09:30 ET open) and **pre-close** (the last hour before the 16:00 ET close). Both runs return day-trade and swing setups; the window determines only the focus-list page's default emphasis, not what the scan returns. Exact window boundaries are a tuning detail.
- A focus list is a **snapshot at generation time**. Live re-evaluation of whether entries are hit or invalidated as the market moves is out of scope for v1.
- Wiring the focus list into alert filtering (e.g. only alert on focus-list symbols) is out of scope for v1 — the focus list is a review/planning artifact.
- The existing AI Best Setups scan (day-trade + swing candidate generation across the watchlist) is reused as the generation engine; this feature adds persistence, a dedicated page, and cadence/labelling around it.
- Persistence is per-user; each trader sees only their own saved focus lists.
- Focus-list history is retained for at least 30 days; older lists may be pruned.
- The existing per-tier daily scan limit is the basis for the twice-daily cap.
- A mobile-optimized layout of the dedicated page is desirable but not required for v1.
