# Feature Specification: In-Play Volume Screener

**Status**: Draft
**Created**: 2026-05-30
**Author**: Victor B (blacktalenthubs)

## Overview

The In-Play Volume Screener automatically surfaces the small set of US stocks that are
"in play" today — trading on unusually high volume during market hours — so a busy,
self-directed trader sees roughly 30 actionable names instead of thousands. Each name on
the curated list is enriched with the structural context that matters (relative volume,
dollar volume, market cap, % change) and is run through the existing pattern scanner so
the trader can immediately see which of the day's movers also has a documented setup
forming. The goal is to answer one question fast: *"Where should I even look today?"*

## Problem Statement

There are ~8,000 tradable US stocks. A trader with a day job cannot scan them, and a
static personal watchlist misses the names that come alive on a given day (earnings,
news, rotation). Most "most active" lists are dominated by the same mega-caps every day
and don't reveal where *fresh* opportunity is. The trader needs the platform to do the
filtering: cap the universe to liquid, tradable names, then rank by what is *unusual today*,
and hand back a short, ranked, setup-aware list. Today the product only scans a
user-curated watchlist; it has no market-wide "what's moving on volume right now" view.

## Processing Pipeline (end-to-end)

```
~8,000 US stocks
   │  Layer 1 — liquidity gate (market cap, price, $-volume)        [weekly]
   ▼
~1,200 tradable names (cached universe)
   │  Layer 2 — energy rank (RVOL desc, $-volume tiebreaker)        [every ~10 min]
   ▼
top ~30–50 "in play today"
   │  Pattern scanner (existing signal_engine — the 14 setups)      ← detects entries
   ▼
setup-aware shortlist
   │  Layer 3 — refine filters / preset (above 50 EMA, VWAP, RSI…)  [optional, user-toggle]
   ▼
the trader's curated, ranked, setup-aware list  →  UI ("In Play")
```

The pattern scanner runs on the energy-ranked shortlist (not the whole market — that is
what makes scanning affordable, and not behind the Layer-3 filters — so a strong setup is
never hidden by a stray indicator value). Layer-3 refine filters narrow/sort the result to
the trader's style.

## Functional Requirements

### FR-1: Capped, liquid universe
- The system maintains a universe of US common stocks filtered by a **market-cap floor**,
  a **share-price floor**, and an **average dollar-volume floor**, reducing ~8,000 tickers
  to a liquid subset (target ~1,000–1,500 names).
- Market cap is the primary universe-narrowing lever and MUST be adjustable.
- Acceptance: With default thresholds the universe contains only names above all three
  floors; lowering/raising the market-cap floor measurably grows/shrinks the universe;
  no name below the price or dollar-volume floor appears.

### FR-2: "In-play" ranking by relative volume
- During market hours the system ranks the universe by **relative volume** (today's
  volume vs. a time-of-day-adjusted average), using **dollar volume** as the tiebreaker,
  and returns the **top N** (configurable, default ~30).
- Ranking is direction-agnostic: a name moving on heavy volume qualifies whether it is up
  or down on the day (the row shows the signed % change).
- Acceptance: Given known intraday volume data, the returned list is ordered by relative
  volume descending; changing N changes the list length; a name with high absolute volume
  but normal relative volume ranks below a name with lower absolute but higher relative
  volume.

### FR-3: Market-hours-aware refresh
- The in-play list refreshes automatically on a fixed cadence (target every 5–15 minutes)
  **only during regular US market hours**, and is not recomputed when the market is closed.
- When the market is closed, the system serves the most recent in-play snapshot, clearly
  labeled with its capture time and "market closed" state.
- Acceptance: During market hours the list timestamp advances on each refresh; outside
  market hours the timestamp is frozen and the closed state is indicated.

### FR-4: Setup-aware shortlist
- Each name on the in-play list is run through the existing pattern scanner, and the row
  surfaces whether a documented setup/entry was detected (and which pattern), reusing the
  same analysis the rest of the product already uses.
- Acceptance: A name on the list that currently matches a documented pattern shows the
  pattern and entry context; a name with no current setup is still listed (as a mover)
  but clearly marked "no setup."

### FR-5: In-Play UI surface
- A dedicated view ("In Play" / "Movers") displays the ranked list with, per row:
  symbol, last price, signed % change, relative volume, dollar volume, market cap, and
  detected setup/entry (if any).
- The list is sortable and each row links to the existing chart/detail view for that symbol.
- Acceptance: The view renders the ranked rows with all listed fields; tapping a row opens
  that symbol's chart/analysis.

### FR-6: Configurable thresholds
- The trader (or an admin default) can adjust the market-cap floor and the top-N count
  within sensible bounds; changes take effect on the next refresh.
- Acceptance: Adjusting market-cap floor or N changes subsequent results; out-of-bound
  values are rejected with a clear message.

### FR-7: Universe freshness & caching
- The capped universe is cached and refreshed on a slow cadence (target weekly) rather
  than recomputed on every request, so the frequent in-play ranking stays fast.
- The system records when the universe was last rebuilt and can rebuild on demand.
- Acceptance: In-play requests do not trigger a full universe rebuild; the universe
  rebuild timestamp is visible; an on-demand rebuild refreshes it.

### FR-8: Degraded-data handling
- If the live volume source is unavailable or returns incomplete data, the system serves
  the last good snapshot with a staleness indicator rather than an empty or erroring view.
- Acceptance: With the data source forced to fail, the view shows the last snapshot plus a
  visible "data may be delayed/stale" indicator and does not crash.

### FR-9: Configurable multi-factor refine filters (presets)
- After the energy rank and pattern scan, the trader can narrow/sort the shortlist by
  optional **refine filters** that reuse existing indicators: trend (price vs EMA 20/50/200,
  MA stack), RSI band, VWAP position, relative strength vs SPY/sector, ATR%/ADR%, sector,
  and an earnings-proximity flag.
- Filters are shipped as named **presets** (e.g., Momentum Long, Pullback, Breakout, Short),
  with **Momentum Long** (price above 50 EMA · above VWAP · RSI 50–70 · RS > SPY) as default.
- Refine filters are **optional** (never a hard prerequisite for the pattern scan) and
  **direction-aware**: long-biased presets must not silently drop short setups, and vice versa.
- Acceptance: Selecting a preset narrows/sorts the visible list accordingly; clearing all
  filters returns the full energy-ranked shortlist; a long preset still allows short setups
  to be viewed via the Short preset or "Any" direction.

### FR-10: Access & tiering
- The In-Play view is a paid capability (Pro and above), consistent with other scanner
  features; lower tiers see a locked teaser prompting upgrade.
- Acceptance: A Pro+ account sees the live list; a free account sees the gated teaser, not
  the data.

## Non-Functional Requirements

### Performance
- A request for the current in-play list returns in a time consistent with the rest of the
  app's data views (the trader perceives it as immediate, not a multi-second wait), because
  ranking runs against the pre-cached universe rather than scanning the whole market live.

### Reliability
- A failure in the slow universe rebuild must not take down the frequent in-play ranking.
- Repeated refreshes must not duplicate or thrash; one authoritative snapshot is served to
  all viewers per refresh window.

## User Scenarios

### Scenario 1: Morning "where do I look" (primary flow)
**Actor**: Busy self-directed trader, mid-morning between meetings
**Trigger**: Opens the In-Play view during market hours
**Steps**:
1. The trader opens "In Play."
2. The system shows ~30 names ranked by relative volume, each with price, % change, RVOL,
   dollar volume, market cap, and any detected setup.
3. The trader scans for names that are both moving on volume AND show a setup.
4. The trader taps a promising name to open its chart and decide on an entry.
**Expected Outcome**: Within a minute the trader has a short, ranked, setup-aware list and a
specific name to investigate — without scanning the whole market.

### Scenario 2: Tightening the universe
**Actor**: Trader who only trades large caps
**Trigger**: Raises the market-cap floor (e.g., to $10B)
**Steps**:
1. The trader raises the market-cap floor in settings.
2. On the next refresh, the in-play list reflects only larger names.
**Expected Outcome**: The list is narrowed to the trader's preferred size segment.

### Scenario 3: After hours
**Actor**: Trader reviewing in the evening
**Trigger**: Opens In-Play with the market closed
**Steps**:
1. The trader opens "In Play."
2. The system shows the final snapshot of the day, labeled with capture time and "market closed."
**Expected Outcome**: The trader reviews the day's movers without the system implying live data.

## UX / Design Notes

- **Placement**: In-Play is a **segmented view inside the existing "Trade Ideas" surface**
  (two pills: `My Ideas | In Play`), not a new primary nav item — the nav was recently
  consolidated and "Trade Ideas" is already a curated-opportunity list. Reuse the existing
  list/row and signal-card presentation patterns rather than inventing a new layout.
- **Row content** (mobile-first): symbol · last price · signed % change · RVOL chip ·
  $-volume · market cap · setup badge (pattern name or "no setup"). The **RVOL chip is the
  primary visual hook** (it answers "why is this here").
- **Controls**: a preset selector (FR-9) and a "Has setup" toggle above the list; a
  refresh timestamp + market-open/closed state indicator.
- **States**: live (refreshing), market-closed (frozen snapshot, labeled), stale-data
  (last snapshot + warning), and short/empty list (shown as-is, not an error).
- **Navigation**: tapping a row opens that symbol's existing chart/detail view.
- Detailed visual design (spacing, exact components) is produced in the design/plan phase,
  optionally via a mockup pass before implementation.

## Key Entities

| Entity | Description | Key Fields |
|--------|-------------|------------|
| Universe | The cached, capped set of liquid US stocks eligible for ranking | symbol, market cap, last price, average dollar volume, last rebuilt timestamp |
| In-Play Entry | One ranked row in the current in-play snapshot | symbol, last price, % change, relative volume, dollar volume, market cap, detected setup/pattern, rank |
| In-Play Snapshot | The ranked top-N list at a point in time | capture timestamp, market-open state, entries, source-staleness flag |
| Screener Settings | Configurable thresholds | market-cap floor, price floor, dollar-volume floor, top-N, refresh cadence |

## Success Criteria

- [ ] A trader can go from "open the view" to "a specific name worth charting" in under one minute.
- [ ] The in-play list contains at most the configured N names (default ~30), never the full market.
- [ ] Raising the market-cap floor demonstrably reduces the number of candidate names.
- [ ] At least the day's genuine high-relative-volume movers appear on the list (validated
      against an independent movers source on sample days).
- [ ] Every listed name shows whether a documented setup is currently detected.
- [ ] The list visibly refreshes during market hours and visibly freezes (with a closed
      label) outside market hours.
- [ ] When the live data source fails, the view still renders the last snapshot with a
      staleness indicator (no empty screen, no error page).

## Edge Cases

- **Same mega-caps every day**: relative-volume ranking (not raw volume) must prevent the
  list from being a static roster of the largest names.
- **Up vs. down movers**: heavy-volume decliners qualify and are shown with negative % change.
- **Thin/halted/penny names**: excluded by the price and dollar-volume floors; a halted
  name should not appear as a live setup.
- **Early session**: in the first minutes of the day, time-of-day-adjusted relative volume
  can be noisy; the system should avoid presenting an unstable list as high-confidence.
- **Universe staleness**: if the weekly rebuild hasn't run, a recently delisted or merged
  name could appear; rows that no longer resolve to live data are dropped from the snapshot.
- **Empty result**: on an unusually quiet day, if too few names clear the bar, the list may
  be shorter than N — that is acceptable and shown as-is.
- **Direction-aware presets**: a long-biased preset (e.g., above 50 EMA) must not remove
  short setups from existence — they remain reachable via the Short/Any selection so the
  direction-agnostic ranking (FR-2) is preserved.

## Assumptions

- "Market hours" means regular US trading hours (no pre/post-market in v1).
- The in-play list is **market-wide and global** (the same ranked snapshot for all viewers),
  not filtered to a user's personal watchlist; per-user tuning is limited to thresholds.
- Relative volume reuses the platform's existing relative-volume calculation rather than a
  new definition, for consistency with current alerts.
- Setup detection reuses the existing pattern scanner rather than introducing new patterns.
- Default thresholds: market cap > $2B, price > $5, average dollar volume > ~$20M/day,
  top N ≈ 30, refresh ≈ every 10 minutes — all adjustable.
- Data is sourced from the platform's existing market-data providers; no new paid vendor is
  required for v1 (reliability upgrades are a future consideration).

## Constraints

- Must reuse the existing relative-volume computation and pattern scanner; this feature is
  an assembly/curation layer, not a reimplementation of analysis.
- Must not introduce a new paid data vendor for v1.
- Must respect the platform's existing market-data rate limits; the capped-universe +
  cached-snapshot design exists specifically to stay within them.
- Educational/informational framing only — the in-play list and any detected setup are
  observations, not buy/sell recommendations (consistent with the rest of the product).

## Scope

### In Scope
- A capped, cached US-stock universe with a configurable market-cap (and price/dollar-volume) floor.
- A market-hours, relative-volume-ranked top-N "in play" snapshot with a refresh cadence.
- Running the shortlist through the existing pattern scanner and surfacing detected setups.
- Optional, direction-aware refine filters shipped as named presets (FR-9).
- Access gating to paid tiers with a teaser for free users (FR-10).
- A backend endpoint serving the current in-play snapshot.
- An In-Play segmented view inside the existing Trade Ideas surface, linking into charts.

### Out of Scope
- Crypto (stocks are the v1 focus; crypto remains secondary and handled elsewhere).
- Pre-market / after-hours volume ranking.
- New paid data vendors (Polygon/FMP) — future reliability upgrade only.
- New pattern definitions or changes to existing alert/scanner business logic.
- Personalized, per-watchlist filtering of the in-play list (global snapshot only in v1).
- Automated trade execution.

## Clarifications

_Added during `/speckit.clarify` sessions_
