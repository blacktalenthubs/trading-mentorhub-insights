# Feature Specification: Day-Trade Entry Rules Redesign

**Feature Branch**: `012-entry-rules-redesign`
**Created**: 2026-05-22
**Status**: Draft (parked — to be planned when the trader returns to it)
**Input**: User description: "Redesign the day-trade intraday entry rules — the system has too many entry alert types and is hard to trust. Shrink to ~5-6 high-conviction rules built on: buy support in an uptrend, sell at resistance; never chase breakouts."

## Overview

The intraday day-trade alert system has accumulated too many entry rules (~15+ alert types) and fires too much low-quality noise — a week of live evaluation showed the trader cannot trust it. This redesign collapses the entry rules to a small, high-conviction set (≤ 6) built on one principle:

> **Buy support in an uptrend; sell at resistance. Never chase breakouts.**

A stock that fires an entry should be genuinely worth looking at. Validated by chart research (see `trade-analytics/specs/alert-quality-feedback.md`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Only uptrend stocks, only support pullbacks (Priority: P1)

The trader gets a moving-average pullback entry **only** when the stock is in a confirmed uptrend — its MA stack is bullish-ordered and price is not below the whole stack — and price has pulled back to a key MA and held. A stock with its MAs stacked above price (a downtrend) produces no entry at all.

**Why this priority**: This is the foundation and the single biggest noise cut. Most of today's MA/EMA-alert noise comes from firing on downtrend stocks; gating every entry on a real uptrend removes it. It is the MVP — it alone makes the feed materially more trustworthy.

**Independent Test**: Run against a stock with a bullish-ordered MA stack pulling back to a key MA → it fires, citing the MA. Run against a stock whose MAs are stacked above price → it fires nothing.

**Acceptance Scenarios**:

1. **Given** a stock with price **above every key MA** (zero MAs overhead), **When** price pulls back to a key MA and closes back above it, **Then** a Buy-1 entry fires citing that MA.
2. **Given** a stock with **any MA overhead** (even just one), **When** price touches or closes above any other MA, **Then** no entry fires — the overhead MA caps the runway.
3. **Given** any entry fires, **When** the trader reads it, **Then** it names the rule and the support level it is based on.

---

### User Story 2 - Buy 2: reclaimed-high support, chop-filtered (Priority: P2)

For a strong uptrend where price is above all its MAs — so there is no MA close enough to pull back to — the trader still gets an entry: when price pulls back to a **reclaimed prior high** (a PDH/PWH/PMH that price is now above, acting as support) and holds it. This entry only fires while the stock is still making new session highs (the chop filter).

**Why this priority**: It catches the entries Buy 1 structurally misses — the best trending names never pull back to a MA. Validated on real bar data (INTC held its PDH as support on every bar of the session). It builds on US1's uptrend concept.

**Independent Test**: A stock above all MAs, still making higher highs, pulls back to a reclaimed PDH that holds → a Buy-2 entry fires. The same stock after it stops making new session highs → no entry.

**Acceptance Scenarios**:

1. **Given** a stock in a strong uptrend (price above all MAs) still making new session highs, **When** price pulls back to a reclaimed prior high (PDH/PWH/PMH it is above) and holds, **Then** a Buy-2 entry fires citing that level as support.
2. **Given** a stock rising *into* a prior high from below, **When** it reaches that high, **Then** no long entry fires — the high is a target/resistance, not an entry.
3. **Given** a stock that has stopped making new session highs, **When** price pulls back to a level, **Then** no continuation entry fires (chop filter).

---

### User Story 3 - Shrink the catalog; retire the open-line entries (Priority: P3)

The entry-rule catalog is cut to ≤ 6 rules. The open-line alerts are removed as entry triggers — the open line stays only as a chart visual. Breakout-into-resistance entries (a long fired as price rises into a prior high) are removed.

**Why this priority**: The cleanup that delivers the "small, trustworthy set" end state. It depends on US1 + US2 existing as the replacement.

**Independent Test**: Count the entry-rule types — ≤ 6. Confirm no entry fires from the open line, and no long fires from price breaking into a prior high from below.

**Acceptance Scenarios**:

1. **Given** the redesigned system, **When** the entry-rule catalog is listed, **Then** it contains no more than 6 entry rules.
2. **Given** price is chopping around the day's open line, **When** it crosses the open line, **Then** no entry fires (open line is visual-only).
3. **Given** price breaks above a prior high from below, **When** the break occurs, **Then** no breakout long fires.

---

### Edge Cases

- **Strong uptrend, no MA pullback and no reclaimed high nearby** → no entry. Acceptable — not every trending stock offers a clean entry; the goal is quality, not coverage.
- **Trend breaks mid-session** (MA stack inverts, or price drops below the stack) → no further entries on that stock.
- **Price hovering exactly at a prior high** → resolved by the dual-role rule: if price was above the level it is support; if below, it is resistance.
- **Many stocks qualify on a strong-market day** → all surfaced, ranked by conviction; the trader picks the few highest.
- **A stock makes one new high then reverses** → the higher-high gate keeps it eligible only while new highs continue; the reversal stops further continuation entries.
- **Confluent supports** (a key MA sitting right next to a prior low, or two MAs clustered) → **one** entry alert, with the confluence flagged inline in the message. Two close support levels do NOT trigger two alerts (the AVGO case, 2026-05-22).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST classify a stock as an uptrend ONLY when price is **above every key moving average** (the 8/21/50/100/200 EMA and the 50/100/200 SMA) — i.e., **zero MAs overhead as resistance**. Any MA above current price disqualifies the stock as an uptrend, no matter how the MAs themselves are ordered. (Validated 2026-05-22 against the day's 8 MA alerts: this single rule blocks 6 of 8 — PLTR/MSFT×2/META/V/MSTR — and keeps AAOI + AVGO, the only two with clean runway.)
- **FR-002**: System MUST fire a Buy-1 entry only when the stock is in an uptrend AND price has pulled back to a key MA from above and closed back above it.
- **FR-003**: System MUST NOT fire any **MA-based entry** (MA bounce / pullback continuation) on a stock with any moving average overhead. **Level-based entries** (PDH/PDL/PWH/PWL/PMH/PML reclaim or hold) MAY fire regardless of MA stack — in downtrend regimes, the trader plays the levels with the overhead MAs as **targets / resistance**, not as entry blockers. (Refined 2026-05-23 — original FR-003 blocked all entries on downtrend stocks; SWMR/PLTR demonstrated this filtered out valid level plays. The MA stack determines *which class of entry* applies; it does not silence the stock entirely.)
- **FR-004**: System MUST fire a Buy-2 entry when price pulls back to a reclaimed prior high (a PDH/PWH/PMH that price is currently above) and holds it as support. The held-from-above pattern itself (price was above the level on the prior bar, retraces to it, closes back above) encodes the relevant precondition — **no separate uptrend gate is required**. (Refined 2026-05-23 — original FR-004 required "strong uptrend" which over-filtered: in downtrend regimes, a stock briefly above a prior high and holding it is a valid reversal play, e.g., SWMR holding WH 38.06 with overhead MA stack.)
- **FR-005**: System MUST treat a prior high (PDH/PWH/PMH) as an entry level ONLY as support — only when price was above it and retraced down to it. It MUST NOT fire a long when price is rising into a prior high from below.
- **FR-006**: The higher-high chop gate (30-min new-session-high requirement) MUST be applied to Buy-2 entries **only in uptrend regimes** (price above every key MA). In downtrend regimes, Buy-2 alerts are reversal plays — the chop gate (a continuation filter) does NOT apply, and a stale 30-min-without-a-new-high condition MUST NOT suppress them. (Refined 2026-05-23 — original FR-006 was scoped too broadly; chop gate exists to silence late-day chop in trending stocks, not to filter reversal setups.)
- **FR-007**: System MUST NOT use the day's open line as an entry trigger; the open line remains a visual chart reference only.
- **FR-008**: System MUST present a total day-trade entry-rule set of no more than 6 rules.
- **FR-009**: Every entry alert MUST state which rule fired and the support level it is based on.
- **FR-010**: Every entry MUST carry an entry price, a structural stop, and targets (existing behavior preserved).
- **FR-011**: An entry's targets MUST be set to the next structural resistance above the entry (the nearest prior high) — encoding "sell at resistance."
- **FR-012**: System MUST surface entry candidates for the trader's manual evaluation only — no auto-trading.
- **FR-013**: When an entry's support level is **confluent** with another support — a second key MA, a reclaimed prior high (PDH/PWH/PMH), a prior low (PDL/PWL/PML), or a **monthly anchored VWAP** (MTD or prior-month) — within a small price band, the alert MUST flag the confluence inline in its message (e.g., *"EMA 21 bounce · confluent with PDL $410.50 · MTD AVWAP $420.92"*). Confluence MUST be surfaced as an annotation on a single entry alert — it MUST NOT trigger a second alert for the same setup. (Validation examples, 2026-05-22: AVGO — daily 21 EMA $413.02 confluent with PDL $410.50, one EMA 21 alert covered both; AAOI — daily 21 EMA $171.47 confluent with weekly 21 EMA and MTD AVWAP $180.28 — a triple-confluence bounce that was the strongest setup of the day.)

### Key Entities

- **Entry Rule**: one of the ≤ 6 high-conviction setups (Buy 1 — MA hold; Buy 2 — reclaimed-high support; and the few others retained). Each has a trigger condition, the support it is based on, and the gates (uptrend, chop) it must pass.
- **Trend State**: a stock's classification from its MA stack — uptrend (bullish-ordered, price not below the stack) or not.
- **Support Level**: the price level an entry is based on — a key MA, or a reclaimed prior high (PDH/PWH/PMH) that price is above. A prior high is **dual-role**: a target/resistance when approached from below, support when retraced to from above. Multiple supports can cluster in the same narrow price band — a key MA confluent with a prior low (PDL/PWL/PML), or two MAs close together — strengthening the setup; the entry alert names the confluence inline instead of firing a separate alert. **In downtrend regimes** (refined FR-003), an overhead MA is **dual-role too** — it is *target / resistance* for level-based entries (PDH/PDL/PWH/PWL/PMH/PML reclaim or hold), not an entry blocker. The trader plays the level; the MAs above tell them where to take profits.
- **Chop Gate**: the higher-high check — continuation entries fire only while the stock is still making new session highs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The day-trade entry-rule set is **≤ 6 rules** (down from ~15+).
- **SC-002**: **No entry fires on a stock whose MAs are stacked above price** (a downtrend) — verified against the chart.
- **SC-003**: **No entry fires from the open line, and no long fires from a breakout into a prior high from below.**
- **SC-004**: On the trader's review (the ✓/✗ scorecard), **at least 70% of surfaced entries are judged genuinely worth looking at** — a materially higher rate than the current rules.
- **SC-005**: **Delivered entry-alert volume drops by at least 50%** versus the current system, while genuine trending setups are still caught.
- **SC-006**: Every entry alert names its rule and its support level, so the trader can judge it without opening the chart.

## Assumptions

- The MA stack uses the platform's existing daily 8/21/50/100/200 moving averages.
- "Reclaimed prior high" uses the existing PDH / PWH / PMH levels.
- The higher-high chop gate uses the current session's high.
- **Scope unifies day-trade and swing**: tonight's research (2026-05-22) confirmed the Pine MA-bounce script (`ma_ema_daily.pine`) already fires off **daily** MAs — i.e., it is functionally the swing scanner too (AAOI's daily-21-EMA bounce alert that fired today is a swing-quality entry). The Python `swing_scanner.py` built in spec 56 is redundant with Pine and will be retired. So this spec's entry-rule framework (uptrend gate, Buy 1, Buy 2, confluence annotation) applies to **both day-trade and swing entries** — the only difference is the timeframe of the MA/AVWAP being defended.
- **Still out of scope**: the RSI-30 sell-off rule (separate behavior, manually evaluated for now).
- Open-line alerts are removed as **entry** triggers; the open line stays as a chart visual. Whether non-routed recording of any retired rule continues is a planning detail.
- This redesign **replaces** the current entry-rule catalog — alert-type toggles for retired rules are removed.
- The system surfaces entry candidates for manual evaluation — no auto-trading — consistent with the platform's current validation phase.
- Feature is **parked** — to be planned (`/speckit-clarify` → `/speckit-plan`) when the trader returns to it.
