# Feature Specification: Swing Trade Qualification Criteria for the AI Scan

**Feature Branch**: `56-swing-trade-criteria`
**Created**: 2026-05-21
**Status**: Draft
**Input**: User description: "lets change how the ai SCAN determines swing trades. swing trades are momentum levels being defended by equity. a stock pulls back from a high to the 21 EMA and holds, or to the 50 EMA and holds and closes above — that qualifies for a swing trade. Even a close above the 100 EMA after a pullback. Coming from below and closing above a key EMA qualifies for a swing trade — e.g. TSLA pulled back from a high and closed above the 21 and 100 EMA, that's swing quality. Also, a stock closing above 30 RSI after a downtrend qualifies — e.g. NFLX moving up from 30 RSI."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Key-EMA defense flags a swing candidate (Priority: P1)

A stock the trader follows runs up, then pulls back. Instead of collapsing, it drifts down into a key moving average — the 21 EMA, or the 50 / 100 / 200 (EMA or SMA) — and that average holds: the candle tests it but closes back above it. That is a momentum level being defended by buyers, and it is a high-quality swing entry. In this story, the AI Scan recognises that pattern and flags the symbol as a swing candidate. It applies whether price held the EMA from above (a pullback that never decisively lost it) or closed back above an EMA it had slipped below (a reclaim). The TSLA example — pulled back from a high and closed back above the 21 and 100 EMA — qualifies.

**Why this priority**: This is the core of the redefinition — "swing trades are momentum levels being defended by equity." Without it the scan does not produce the swing setups the trader actually wants. It is the headline change.

**Independent Test**: Point the scan at a watchlist containing a stock that pulled back to a key EMA and closed back above it; confirm that stock is returned as a swing candidate, and that a stock which merely drifts sideways with no EMA interaction is not.

**Acceptance Scenarios**:

1. **Given** a stock in an uptrend that pulls back to its 21 EMA and the daily candle closes above the 21 EMA after testing it, **When** the scan evaluates the watchlist, **Then** the stock is returned as a swing candidate citing the 21 EMA.
2. **Given** a stock that had been trading below its 100 EMA and whose daily candle closes back above the 100 EMA, **When** the scan runs, **Then** the stock is returned as a swing candidate citing a 100 EMA reclaim.
3. **Given** a stock whose daily candle closes above more than one key EMA on the same day (e.g. 21 and 100), **When** the scan runs, **Then** it is returned once as a swing candidate citing every key EMA it recaptured.
4. **Given** a stock whose daily candle closes *below* the key EMA it pulled back to, **When** the scan runs, **Then** it is NOT returned as a swing candidate.

---

### User Story 2 - Oversold-RSI recovery flags a swing candidate (Priority: P1)

A stock has been in a downtrend and momentum has bottomed — its RSI fell to oversold (at or below 30). Then it turns: the daily RSI closes back above 30. That shift from oversold back into normal territory marks downtrend exhaustion and the start of a possible swing higher. In this story the AI Scan recognises that recovery and flags the symbol as a swing candidate. The NFLX example — moving up off 30 RSI — qualifies.

**Why this priority**: It is the second half of the new definition and catches a different class of swing setup (reversal from oversold) that the EMA rules in Story 1 do not — a stock deep in a downtrend has no EMA to "defend" yet. Equal priority because the trader explicitly named it as a qualifying path.

**Independent Test**: Point the scan at a watchlist containing a stock whose RSI was at or below 30 and has just closed back above 30; confirm it is returned as a swing candidate, and that a stock whose RSI is simply mid-range is not.

**Acceptance Scenarios**:

1. **Given** a stock that had a daily RSI at or below 30 within a recent downtrend, **When** its daily RSI closes back above 30, **Then** the scan returns it as a swing candidate citing the RSI recovery.
2. **Given** a stock whose RSI has been oscillating between 45 and 60 with no oversold dip, **When** the scan runs, **Then** it is NOT returned under the RSI rule.
3. **Given** a stock whose RSI is still at or below 30 (has not yet recovered), **When** the scan runs, **Then** it is NOT yet returned — the qualifying event is the close back above 30.

---

### User Story 3 - Each swing candidate shows why it qualified (Priority: P2)

When the scan returns a swing candidate, the trader needs to know *which* rule it met — which EMA was defended or reclaimed, or that it was an RSI recovery — so they can judge the setup themselves rather than trust a black box. In this story every swing candidate carries the qualifying rule and the specific level behind it.

**Why this priority**: The qualification (P1 stories) delivers value on its own; surfacing the reason makes the output trustworthy and reviewable. Valuable, but an enhancement layered on top.

**Independent Test**: Trigger a scan that produces swing candidates of each type; confirm each candidate states its rule (which key EMA, or RSI recovery) in plain language.

**Acceptance Scenarios**:

1. **Given** a swing candidate that qualified by closing above the 50 EMA, **When** the trader views it, **Then** it states the 50 EMA was the level defended/reclaimed.
2. **Given** a swing candidate that qualified by RSI recovery, **When** the trader views it, **Then** it states the RSI closed back above 30 after a downtrend.

---

### Edge Cases

- A stock satisfies both an EMA rule and the RSI rule on the same day — it is returned once, with both qualifying reasons recorded; it is never emitted twice.
- A stock closes above a key EMA while still in a clear downtrend (lower highs, price below the higher EMAs) — the EMA-defense rule requires a prior uptrend / pullback context, so a downtrend close-above-EMA does not qualify under the EMA rule; downtrend reversals are the RSI rule's job.
- A stock gaps up through a key EMA rather than drifting back to it — it closed above the EMA but never "defended" it; treated as a reclaim (qualifies) rather than a hold.
- Whipsaw: a stock closes above a key EMA one day and below it the next — each day is re-evaluated independently; the scan must not repeatedly re-flag the same unresolved setup (dedup over the session/day).
- RSI ticks above 30 intrabar but the daily candle closes with RSI back at/below 30 — does not qualify; qualification is decided on the daily close.
- A stock is below a key EMA and also has RSI recovering above 30 — both the reclaim rule and the RSI rule may fire; recorded as one candidate citing both.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The AI Scan MUST evaluate each watchlist symbol on the daily timeframe for swing-trade qualification.
- **FR-002**: A symbol MUST qualify as a swing candidate when, after a pullback from a recent high, its daily candle tests a key EMA and closes back above it (the EMA held — a momentum level defended).
- **FR-003**: A symbol MUST qualify as a swing candidate when its daily candle closes back above a key EMA it had been trading below (an EMA reclaim from below).
- **FR-004**: A symbol MUST qualify as a swing candidate when its daily RSI closes back above 30 after having been at or below 30 during a recent downtrend (oversold recovery).
- **FR-005**: The qualifying rules MUST be OR-combined — any single rule being met is sufficient for a symbol to be returned as a swing candidate.
- **FR-006**: The "key MAs" for the EMA-defense and EMA-reclaim rules MUST be seven daily moving averages: the **21 EMA**, and the **50 / 100 / 200 in both EMA and SMA form** (50 EMA, 50 SMA, 100 EMA, 100 SMA, 200 EMA, 200 SMA).
- **FR-007**: Each swing candidate MUST record which rule(s) it met and the specific level behind each — the EMA period(s) defended/reclaimed, and/or the RSI recovery — in plain language for the trader.
- **FR-008**: When a symbol satisfies multiple rules (or multiple key EMAs) on the same day, the scan MUST return it as a single swing candidate carrying all qualifying reasons, never as duplicates.
- **FR-009**: Swing candidates produced by these rules are long-biased — all three paths (EMA hold, EMA reclaim, RSI recovery) describe bullish / recovery setups.
- **FR-010**: The new criteria MUST replace the AI Scan's prior swing-trade qualification logic — they become the definition of a swing trade for the scan.
- **FR-011**: The EMA-defense and EMA-reclaim rules MUST require an uptrend / pullback context; a close above a key EMA inside a sustained downtrend MUST NOT qualify under the EMA rules.
- **FR-012**: The scan MUST continue to surface swing candidates through its existing swing output and run on its existing schedule — only the qualification logic changes.
- **FR-013**: The scan MUST re-evaluate symbols each run and MUST NOT repeatedly re-flag the same still-open swing setup within the same trading session.

### Key Entities *(include if feature involves data)*

- **Swing Candidate**: A symbol the scan has qualified as a swing trade for the current evaluation. Attributes: symbol, qualifying rule(s) met (EMA defense / EMA reclaim / RSI recovery), the specific level(s) (which key EMA period; or the RSI-30 recovery), direction (long), the daily close that triggered it, and the timestamp / session.
- **Key MA**: A daily moving average used as a momentum level — the 21 EMA, and the 50 / 100 / 200 in both EMA and SMA. A stock holding or reclaiming one of these is "defending a momentum level."
- **RSI (oversold/recovery)**: The daily relative-strength reading used to detect downtrend exhaustion — the 30 level is the oversold threshold whose recovery (close back above 30) qualifies a swing.
- **Watchlist**: The set of symbols the scan evaluates (existing entity — referenced, not redefined).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A stock that pulls back from a recent high and closes back above the 21, 50, or 100 EMA is returned as a swing candidate 100% of the time it occurs in the watchlist (e.g. the TSLA-style close above the 21 and 100 EMA).
- **SC-002**: A stock whose daily RSI closes back above 30 after a downtrend is returned as a swing candidate 100% of the time it occurs in the watchlist (e.g. the NFLX-style move up off 30 RSI).
- **SC-003**: Every swing candidate the scan returns states its qualifying rule and level in plain language — a trader can tell why it qualified without inspecting a chart.
- **SC-004**: A stock drifting sideways with no key-EMA interaction and no oversold RSI recovery is never returned as a swing candidate (zero false positives for the "no setup" case).
- **SC-005**: The same still-open swing setup is surfaced at most once per trading session — no repeat spam on whipsaw.
- **SC-006**: A trader reviewing a day's swing candidates agrees they are genuine momentum-defense or oversold-recovery setups in at least 80% of cases (qualitative review).

## Assumptions

- The scan operates on the **daily timeframe** for swing qualification — the trader's examples (TSLA, ORCL, NFLX) are all daily charts.
- **Key MAs are seven daily moving averages**: the 21 EMA, plus the 50 / 100 / 200 in both EMA and SMA form. The 8 EMA is too short-term for a swing momentum level; a 21 SMA is not paired (21 is a fast EMA period). Confirmed by the trader during planning.
- **RSI uses the standard 14-period** daily reading; **30** is the oversold threshold (both shown on the trader's charts).
- The new criteria **replace** the AI Scan's existing swing-determination logic rather than adding to it — the trader asked to "change how the AI Scan determines swing trades."
- Swing candidates are **long-only**; short swing setups are out of scope for this change.
- "Recent high" (for the pullback context) and "recent downtrend" (for the RSI rule) are bounded by a lookback window; the exact lookback length is a tuning detail to be settled in planning.
- "The EMA holds" means price tested the EMA (a wick or pullback into it) but the daily candle closed above it; the precise proximity tolerance is a tuning detail.
- Wiring swing candidates into any specific delivery channel (Telegram, Signals feed, focus list) is unchanged — this feature changes only *what qualifies*, not *how it is delivered*.
- The watchlist and the scan's schedule are existing capabilities reused as-is.
