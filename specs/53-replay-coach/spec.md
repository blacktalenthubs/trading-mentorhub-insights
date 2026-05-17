# Spec 53 — Personalized Replay Coach (2026-05-16)

**Status**: Draft — buildable child of [Spec 48](../48-v3-cleanup-and-paid-ai-revamp/spec.md) (V3 manifest).
**Depends on**: [Spec 49 (V1 Cleanup)](../49-v1-cleanup/spec.md) AND [Spec 51 (Chart Critique)](../51-chart-critique/spec.md) — Replay Coach reuses Spec 51's analysis engine.
**Touches**: `web/src/pages/ReplayPage.tsx`, `web/src/components/ChartReplay.tsx`, `analytics/chart_analyzer.py` (extension, shared with Spec 51).

## Why this spec exists

The product already has `ReplayPage.tsx` and `ChartReplay.tsx` — a bar-by-bar replay of any prior alert. It's a one-shot post-mortem today. Replay Coach extends it into a coaching loop: as the trader steps forward through the replay, an AI commentary track surfaces actionable observations at meaningful bars ("here's where a trader would add," "this candle should have changed your bias," "this was a false signal because…"). Same analysis engine as Spec 51, different surface. Strong retention feature for serious users; value-per-user is high; volume is lower than Chart Critique because it's a Pro+ tier upsell on a less frequently visited surface.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Coach commentary appears at meaningful bars during replay (Priority: P1)

A Pro+-tier subscriber opens any prior alert in `ReplayPage.tsx`, plays through the bar-by-bar replay, and at meaningful bars sees an AI commentary line appear on a "coach" track. Each line names a specific actionable observation that a beginner would not catch unaided. The commentary is generated lazily on first replay open (cached thereafter so subsequent steps don't repeatedly call the LLM).

**Why this priority**: This is the entire feature. Without commentary at meaningful bars, the replay is just a slower chart viewer.

**Independent Test**: Open 5 historical alerts (mix of winners and losers). For each, verify ≥3 distinct AI commentary lines appear at meaningful bars and at least one names a specific actionable observation a beginner would miss.

**Acceptance Scenarios**:

1. **Given** a Pro+-tier subscriber opens any alert on `ReplayPage`, **When** the replay loads, **Then** within 10 seconds the commentary track is populated for that replay's bar range.
2. **Given** the subscriber steps forward in the replay, **When** a coach commentary line is bound to the current bar, **Then** it appears within 1 second of the bar advance.
3. **Given** the subscriber returns to a previously-played replay, **When** they open it, **Then** the cached commentary track loads within 1 second (no LLM re-call).
4. **Given** the commentary generation fails (vision provider error), **When** the subscriber opens the replay, **Then** the base replay still functions and a clearly-labeled "coach unavailable — try again later" notice appears.

---

### User Story 2 — Pro (not Pro+) sees upgrade gate (Priority: P1)

A Pro-tier subscriber opens any alert on `ReplayPage`. The base replay is fully functional (they already pay for it via Pro), but the "coach" commentary track is replaced with an upgrade card pointing to Pro+. No commentary content leaks to the lower tier.

**Why this priority**: Without a clean tier gate, Replay Coach can't be a paid feature. Without the gate landing alongside US1, leaked content trains users to expect it free.

**Independent Test**: From a Pro account, open any replay; verify the base replay works and the coach track shows the upgrade card, not any LLM-generated content.

**Acceptance Scenarios**:

1. **Given** a Pro-tier (not Pro+) subscriber, **When** they open `ReplayPage`, **Then** the base replay functions normally and the coach track is replaced with an upgrade card.
2. **Given** the upgrade card, **When** the subscriber clicks it, **Then** they are routed to the Pro+ upgrade flow.

---

### User Story 3 — Free-tier sees no replay access at all (Priority: P2)

A Free-tier visitor following a deep link to `ReplayPage` sees a paywall before the replay is rendered. Replay access (including the base replay surface) is a paid feature, not just Coach.

**Why this priority**: Aligns Replay access with the rest of the paid surface. P2 because base replay access could ship to Free as a P3 nice-to-have without breaking Coach economics; this spec is conservative.

**Independent Test**: From a Free account, click any replay deep link; verify a paywall renders before the replay surface.

**Acceptance Scenarios**:

1. **Given** a Free-tier visitor follows a replay deep link, **When** the page loads, **Then** they see a paywall before any replay content renders.

---

### Edge Cases

- **Very long replay (e.g., 500+ bars)** — commentary generation may be expensive; engine produces commentary only at bars flagged "meaningful" (bias change, S/R touch, volume spike) rather than every bar. Cap configurable per replay.
- **Replay for an alert that was MUTEd by the triage agent** — replay still works; commentary acknowledges the mute reason in its first line.
- **Replay for a very old alert (data outside retention)** — surface a clear "replay data unavailable" rather than partial render.
- **Subscriber rapidly steps through replay** — commentary debounces; only the latest displayed bar's commentary is fetched/cached.
- **Engine produces zero meaningful commentary lines** — minimum-floor message ("clean trend continuation — nothing structurally interesting at meaningful bars") so the coach track is never blank.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-701**: The existing `ChartReplay.tsx` MUST gain a "coach" commentary track populated by Spec 51's analysis engine (extended to per-bar commentary rather than whole-chart analysis).
- **FR-702**: Commentary MUST be generated lazily on first replay open and cached server-side per replay; subsequent opens MUST NOT re-call the LLM unless the user explicitly requests regeneration.
- **FR-703**: Commentary MUST appear within 1 second of the bar advance when bound to the current bar; the full commentary track for a replay MUST be available within 10 seconds of replay open.
- **FR-704**: Commentary lines MUST only fire at "meaningful" bars (bias change, S/R touch, volume spike, MA reclaim/reject) rather than every bar; the meaningful-bar detector is shared with the alert engine and is operator-tunable.
- **FR-705**: When zero meaningful bars are detected, the coach track MUST surface a minimum-floor message (e.g., "clean trend continuation — nothing structurally interesting at meaningful bars") so it is never blank.
- **FR-706**: The Replay Coach feature MUST be gated to a Pro+ tier higher than the base Replay surface, via the existing `tier.py` + `useFeatureGate.ts` machinery. Pro-tier users MUST see an upgrade card in place of the coach track; the base replay MUST remain fully functional for Pro.
- **FR-707**: Free-tier visitors following a replay deep link MUST see a paywall before any replay content renders.
- **FR-708**: When commentary generation fails (vision provider error per Spec 51), the base replay MUST still function and a clearly-labeled "coach unavailable — try again later" notice MUST appear. The failed generation MUST NOT count against the user's Spec 51 Chart Critique quota.

### Key Entities *(if applicable)*

- **Replay Commentary Track**: An ordered list of (bar_index, commentary_text) pairs bound to a specific replay. Generated lazily; cached server-side.
- **Meaningful Bar Marker**: A flag attached to a bar in a replay indicating it's a candidate for a commentary line (bias change, S/R touch, volume spike, MA event).

## Success Criteria *(mandatory)*

- **SC-701**: For 5 historical alerts in a representative sample (mix of winners and losers), ≥3 distinct AI commentary lines appear at meaningful bars per replay, and at least one names a specific actionable observation a beginner would miss.
- **SC-702**: Full commentary track is available within 10 seconds of replay open for 90% of replays in test.
- **SC-703**: Per-bar commentary display latency is under 1 second in 95% of bar-advance events (cache hit).
- **SC-704**: 0 cases of Pro-tier users accessing Coach commentary content (only the upgrade card renders).
- **SC-705**: 0 cases of Free-tier users accessing the base replay surface beyond the paywall.
- **SC-706**: 0 cases of a Coach failure decrementing Spec 51's Chart Critique quota.

## Assumptions

- Spec 51's analysis engine (`analytics/chart_analyzer.py` extended) can be adapted to per-bar commentary. If the existing whole-chart prompt doesn't decompose cleanly, this spec accepts a focused per-bar prompt variant added to the engine.
- Caching commentary server-side per replay is acceptable (replays are immutable historical artifacts; the commentary doesn't go stale).
- The "meaningful bar" detector is an extension of existing alert-emission logic; new logic added here is operator-tunable.
- Tier model is coordinated with Specs 51 and 11 (Interview Copilot billing patterns echoed where relevant). Pro+ tier definition is operator-configurable.
- A future spec may extend Coach with user-uploaded charts (post-mortem your own trade); v1 is replay-of-existing-alerts only.
- The replay UI is not redesigned in this spec; the coach track is an additive layer on the existing `ChartReplay.tsx` component.
