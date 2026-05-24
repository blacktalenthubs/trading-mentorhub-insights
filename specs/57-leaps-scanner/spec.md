# Feature Specification: LEAPS Candidate Scanner

**Feature Branch**: `012-leaps-scanner`
**Created**: 2026-05-21
**Status**: Draft (parked — to be revisited after the current day/swing alert patterns are validated)
**Input**: User description: "A framework for buying long-dated call options (LEAPS) on high-conviction stocks — evaluate the trader's stored watchlist against the LEAPS entry criteria and surface qualifying stocks."

## Overview

LEAPS (long-dated call options) are a leveraged bet on a stock the trader already has deep conviction in. The framework: stock selection eliminates ~90% of bad trades; then a small set of *entry conditions* (multi-timeframe RSI, price at long-term support, favorable implied volatility, liquid options) tells the trader when alignment justifies stepping in. The goal is a handful of high-conviction entries per year — not frequent trading.

This feature is a **candidate scanner**: it evaluates the trader's curated watchlist against those entry criteria and surfaces the stocks currently sitting in a LEAPS-quality entry zone, with the reasons. It is an *entry-candidate* tool — it does not place trades, size positions, or manage exits.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See which watchlist stocks are at a LEAPS entry zone (Priority: P1)

The trader opens the LEAPS view and sees, in one place, every stock on their watchlist that is currently at a LEAPS-quality *stock entry* — price pulled back into long-term support with multi-timeframe RSI aligned (daily oversold, weekly stabilizing or curling up). Each candidate shows exactly why it qualified. The trader no longer chart-checks the whole watchlist by hand.

**Why this priority**: This is the framework's own "90%" — stock selection at the right level. It is fully deliverable with data the platform already computes (RSI, long-term moving averages, weekly/monthly levels) and the existing watchlist as the quality gate. It is the MVP: it alone answers "where should I be looking for a LEAP right now."

**Independent Test**: With a populated watchlist, run the scan on a day when at least one watchlist stock is oversold at long-term support — verify it appears as a candidate with its qualifying reasons, and a stock in an extended breakout does not.

**Acceptance Scenarios**:

1. **Given** a watchlist stock whose daily RSI is oversold, weekly RSI is stabilizing, and price is at a long-term support level, **When** the scan runs, **Then** the stock is surfaced as a LEAPS candidate citing those three conditions.
2. **Given** a watchlist stock in an extended breakout far above its support levels, **When** the scan runs, **Then** it is not surfaced as a candidate.
3. **Given** several stocks qualify at once, **When** the trader views the list, **Then** candidates are ranked by how strongly the conditions align.
4. **Given** a stock that is not on the watchlist, **When** the scan runs, **Then** it is never surfaced (the watchlist is the quality gate).

---

### User Story 2 - Contract & implied-volatility guidance for a candidate (Priority: P2)

For a qualifying stock, the trader sees a suggested LEAPS contract structure — long-dated (≥ 360 days to expiration), a starting strike roughly 10% out-of-the-money — plus whether implied volatility is favorable (low relative to its recent range) and whether the option chain is liquid enough to trade cleanly.

**Why this priority**: This is the options-specific layer. It turns a qualifying *stock* into an actionable *trade idea*. It depends on an options-data source (implied volatility, option-chain bid/ask/open-interest) that the platform does not have today — so it is a distinct, later increment, not part of the MVP.

**Independent Test**: For a known qualifying candidate, verify the suggested contract is ≥ 360 DTE and ~10% OTM, and that IV and liquidity are each labeled favorable or unfavorable against the stated definition.

**Acceptance Scenarios**:

1. **Given** a qualifying candidate, **When** the trader views it, **Then** a suggested contract (duration ≥ 360 DTE, strike ~10% OTM) is shown.
2. **Given** a candidate whose implied volatility is high relative to its recent range, **When** the trader views it, **Then** it is flagged as elevated IV (overpaying for premium).
3. **Given** a candidate whose option chain has wide spreads or thin open interest, **When** the trader views it, **Then** it is flagged as inadequate liquidity.
4. **Given** a candidate that meets the stock criteria but has elevated IV or thin liquidity, **When** the trader views it, **Then** it is shown but clearly marked as not fully actionable, with the unmet conditions named.

---

### User Story 3 - Record candidates and validate the criteria over time (Priority: P3)

Each surfaced candidate is recorded with the date and the conditions that qualified it. The trader can grade how a candidate played out, and review how the LEAPS criteria have performed over time — so the framework itself can be validated and refined before any of it is automated.

**Why this priority**: Consistent with the platform's manual-validation approach — catch setups, evaluate them, automate only once proven. It builds trust in the criteria but is not needed for the scanner to deliver value.

**Independent Test**: Surface a candidate, grade it after the fact, and confirm the grade and the performance summary persist and are retrievable later.

**Acceptance Scenarios**:

1. **Given** a candidate was surfaced, **When** the trader revisits a past date, **Then** the candidate and its qualifying conditions are still shown.
2. **Given** the trader graded several past candidates, **When** they open the performance summary, **Then** they see how candidates have performed grouped by their qualifying conditions.

---

### Edge Cases

- **Stock qualifies but options are unfavorable** — surfaced as a candidate, but marked not-fully-actionable with the unmet IV/liquidity conditions named (FR-014).
- **Insufficient price history** (e.g. a recent IPO) — a stock without enough history to compute a long-term moving average or weekly RSI is skipped; long-term support cannot be assessed without long history.
- **Empty watchlist** — the scan completes and surfaces nothing, with a clear empty state.
- **Many candidates at once** (broad market selloff) — all are surfaced, ranked by strength; the trader selects the few highest-conviction ones (the framework targets a handful of entries per year, not many).
- **Options data unavailable or stale** — User Story 2 fields show as unavailable; User Story 1 stock-level qualification is unaffected.
- **A stock keeps qualifying day after day** — it remains in the candidate list while it qualifies; it is not re-announced every day (one surfacing while the condition holds).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST evaluate every stock on the trader's watchlist when scanning for LEAPS candidates. The watchlist is the curated quality universe — only names the trader has already vetted and would own outright.
- **FR-002**: System MUST evaluate each stock's daily RSI for an oversold condition.
- **FR-003**: System MUST evaluate each stock's weekly RSI for stabilization or an upturn (curling up from low levels).
- **FR-004**: System MUST evaluate whether price is at a long-term support area — a major long-term moving average, a prior consolidation range, or a weekly/monthly level — and not in an extended breakout.
- **FR-005**: System MUST qualify a stock as a LEAPS candidate only when multi-timeframe RSI is aligned (daily oversold AND weekly stabilizing/up) AND price is at a long-term support area.
- **FR-006**: System MUST present each qualifying candidate with the explicit reasons it qualified — which timeframes' RSI aligned and which support level price is at.
- **FR-007**: System MUST rank candidates by alignment strength — the more conditions (and timeframes) that align, the stronger the candidate.
- **FR-008**: System MUST NOT surface a stock on momentum or extension alone; entering at extended breakouts is explicitly excluded.
- **FR-009**: System MUST run the candidate scan on a regular schedule and allow the trader to trigger it on demand.
- **FR-010**: System MUST NOT place, size, or auto-execute any trade. It surfaces candidates for the trader's manual evaluation only.
- **FR-011**: For a qualifying candidate, System MUST suggest a contract structure — long-dated (≥ 360 days to expiration) with a starting strike roughly 10% out-of-the-money. *(US2)*
- **FR-012**: System MUST assess implied volatility for a candidate and flag whether it is low relative to its recent range (favorable) or elevated (overpaying for premium). *(US2)*
- **FR-013**: System MUST assess the option chain's liquidity — bid/ask spread, open interest, volume — and flag inadequate liquidity. *(US2)*
- **FR-014**: System MUST mark a candidate as fully actionable only when the stock criteria, favorable IV, and adequate liquidity all align; otherwise it MUST surface the candidate with the unmet conditions named. *(US2)*
- **FR-015**: System MUST record each surfaced candidate with the date and the conditions that qualified it. *(US3)*
- **FR-016**: Trader MUST be able to grade a recorded candidate's outcome for later review. *(US3)*
- **FR-017**: System MUST report how candidate criteria have performed over time, grouped by qualifying condition, so the trader can validate and refine the framework. *(US3)*

### Key Entities

- **LEAPS Candidate**: a watchlist stock currently meeting the LEAPS entry criteria. Attributes: symbol, the qualifying conditions met (daily/weekly RSI states, the support level), alignment strength / rank, date surfaced; and (US2) a suggested contract, an IV assessment, a liquidity assessment, an actionable flag; and (US3) an outcome grade.
- **Watchlist**: the trader's curated universe of stocks worth owning long-term — the quality gate for every candidate.
- **Entry Criteria**: the configurable conditions a stock is measured against — RSI oversold/recovery thresholds, what counts as long-term support, and (US2) the IV and liquidity bars.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The trader can see, in a single view, every watchlist stock currently meeting the LEAPS entry criteria — each with its qualifying reasons — without checking any chart by hand.
- **SC-002**: 100% of the watchlist is evaluated on every scan.
- **SC-003**: A stock that enters a LEAPS entry zone is surfaced the same day it enters it, not days later.
- **SC-004**: On the trader's review, at least 80% of surfaced candidates are judged to be genuinely at a LEAPS-quality entry — a low false-positive rate, measured via candidate grading.
- **SC-005**: In normal market conditions the scan surfaces a focused list (single digits), not dozens — consistent with the framework's "fewer, higher-conviction entries" goal.
- **SC-006**: For each fully actionable candidate, the trader can see a suggested contract (duration + strike) and an IV/liquidity read without leaving the platform. *(US2)*

## Assumptions

- The **watchlist is the "stock quality" gate** — it represents stocks the trader has already researched and would own outright. The system does not assess fundamentals; presence on the watchlist satisfies the "deep conviction / would own for years" criterion.
- **"Long-term support"** is evaluated using the platform's existing level and moving-average data (long-term moving averages, weekly/monthly levels, prior consolidation ranges) — reusing the swing-scan / levels infrastructure rather than introducing new technical concepts.
- **Daily + weekly RSI** are the multi-timeframe set for v1. Additional timeframes (e.g. monthly) are out of scope for v1.
- **Options data — implied volatility and option-chain liquidity — is not currently available to the platform.** User Story 2 depends on adding an options-data source; this is a dependency for US2, not a blocker — User Story 1 (stock-level qualification) is fully deliverable without it.
- The scan runs **once daily after the close** (LEAPS setups evolve slowly; intraday cadence is unnecessary), plus on demand.
- The scanner **surfaces candidates only** — no auto-trading — consistent with the platform's manual-validation approach: catch setups, evaluate them, automate only after the criteria are proven.
- **Position sizing, profit-taking, theta management, and exits** (from the source framework) are the trader's responsibility and out of scope. This feature is an entry-candidate tool, not a position manager.
- The feature is **parked** — to be revisited and planned after the current day-trade and swing alert patterns have been validated.
