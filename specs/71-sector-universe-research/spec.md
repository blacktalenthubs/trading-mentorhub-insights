# Sector-Grouped Universe Research

**Status:** proposed · **Owner:** vbolofinde · **Date:** 2026-07-12

## Overview
A **Research / Universe** view — browse the full **leaders universe** (not just your 32-name watchlist),
**grouped by sector**, with the strongest sectors first, sortable by key factors, click any name for the
full research card + earnings. **Available to all users.** The daily workflow: *review the hot sectors,
drill into the leaders.*

## What already exists (reuse)
- **`symbol_fundamentals`** table — company/sector/market_cap, EPS TTM/FWD, EPS growth, P/E, margins,
  analyst recs + consensus, AI brief, `metrics_json`. **127 names today.**
- **`GET /fundamentals/{symbol}`** — full research for ANY symbol, fetches on-demand if missing.
- **`GET /fundamentals/watchlist`** — the caller's watchlist fundamentals.
- **`fundamentals_refresh.refresh_all`** — refreshes all distinct *watchlist* symbols.
- **`WatchlistPage`** (Symbols / Earnings / Research tabs) — the research card UI. **`GrowthLeadersPage`**
  — ranks the growth-leader universe on a fundamental scorecard.
- **Leaders universe** — `triage-agent/broad_universe.py` (~513) + the swing RS/IBD filter → the top leaders.

## The gaps → what to build
### 1. Data — widen fundamentals to the leaders universe (127 → ~500)
- A `refresh_universe(...)` that covers **all-watchlists ∪ leaders universe** (broad + RS top-N + IBD).
- Cheap fields (EPS, growth, P/E, margins, analyst recs, **earnings date**) via yfinance for all.
- **AI brief on-demand** (generated + cached when a user opens the name), NOT 500 upfront (cost).
- Schedule it (triage cron, e.g. nightly) so the sheet stays fresh.

### 2. Endpoint — `GET /fundamentals/universe`
- Returns **all** `symbol_fundamentals` rows (all users, authenticated — not gated to the caller's list).
- Shape: `{ sectors: [{ sector, strength, count, items: [FundamentalsItem…] }], last_refreshed_at }`.
- **`strength`** = sector aggregate (median RS / % above 50-DMA / % of names in an uptrend) so the frontend
  can rank sectors strongest-first. Sort of `items` is client-side.

### 3. Frontend — a "Research / Universe" view (all users)
- **Collapsible sector sections**, ranked by `strength` (hottest first) — the "which sectors today" read.
  Each header: sector name · strength bar · # leaders.
- Within a sector: a sortable table — **EPS growth · RS · P/E · % off 52w high · market cap** — plus a
  Buy/Hold tag where we have a view.
- Click a name → the existing **research card + earnings** (reuse WatchlistPage's card / the modal).
- **Search** across all names. Mounts as a top-level page (all users), not admin-gated.

## Acceptance
1. All users can open the Universe view and see the leaders **grouped by sector, strongest first**.
2. Any name → full research (numbers + analyst recs + earnings + AI brief on-demand).
3. Sort within a sector by EPS growth / RS / P/E / 52w / mkt cap.
4. Search finds any leader.

## Out of scope (later)
- Pre-generating AI briefs for all 500 (on-demand only).
- Per-user "sector of the day" assignment / reminders.
- Custom user groups beyond sector.

## Build order
1. `GET /fundamentals/universe` (grouped, all-users) — foundation the UI reads.
2. `refresh_universe` + schedule — populate the ~500 (fills over time; on-demand covers the rest).
3. The Research/Universe frontend page.

## Implementation map (for the autonomous build — where everything lives)
**Backend**
- `api/app/routers/fundamentals.py` — add `GET /universe`. Reuse `_to_item`, `SymbolFundamentals`,
  `FundamentalsResponse`/`FundamentalsItem` (`api/app/schemas/fundamentals.py`). Auth = `get_current_user`
  (NOT admin-gated). Query all `SymbolFundamentals` rows, group by `sector` (null → "Other"), compute
  `strength` per sector = median of a momentum proxy (parse `metrics_json` for vs-50DMA / 52w position;
  fall back to `eps_growth_pct` median). Sort sectors by `strength` desc. New schema:
  `UniverseResponse{ sectors: [SectorGroup{ sector, strength, count, items }], last_refreshed_at }`.
- `analytics/fundamentals_refresh.py` — add `refresh_universe(session_factory, *, with_ai=False)`:
  symbols = `_distinct_watchlist_symbols` ∪ leaders. Leaders come from `triage-agent/broad_universe.py`
  `BROAD_UNIVERSE` + the RS/IBD filter in `triage-agent/swing_scan.py` (`_rs_rank`, `_ibd_symbols`,
  `SWING_RS_TOPN`). If cross-import is awkward from `analytics/`, copy the leader-list build into a small
  shared helper or read `broad_universe.py` directly. `with_ai=False` (briefs on-demand).
- Schedule: `triage-agent/live.py` — add a nightly `add_job(_safe_fundamentals_universe, CronTrigger(...))`
  (mirror the existing `_safe_swing_scan` pattern), e.g. 02:00 ET.
- Per-symbol on-demand already works via `GET /fundamentals/{symbol}` (fetches if missing) — the UI uses it
  when a user opens a name not yet cached.

**Frontend** (`web/`)
- New page `web/src/pages/UniverseResearchPage.tsx`. Reuse: the research card from `WatchlistPage.tsx`
  (extract/share it), `ScreenerTable` (`web/src/components/ScreenerTable.tsx`) for the sortable sector
  tables, `GradeBadge` for tags, the earnings view from `WatchlistPage` Earnings tab.
- API hook in `web/src/api/hooks.ts` — `useUniverse()` → `GET /fundamentals/universe`; reuse the existing
  per-symbol fundamentals hook for the research card.
- Route in `web/src/App.tsx` (add `<Route path="research" …>`), nav entry in the sidebar (all users).
  Model the sector-section + sort UX on `GrowthLeadersPage.tsx`.
- Sector sections collapsible, ranked by `strength` desc; sort within by EPS growth / RS / P/E / 52w / mkt
  cap; click row → research card; top search box filters across all names.

**Verify**: `tsc -b` for the frontend (noUnusedLocals); backend imports cleanly; `/universe` returns the
127 current names grouped by sector (more as `refresh_universe` fills). Follow feedback: no admin gate,
mobile-friendly (`overflow-y-auto overflow-x-hidden` on the scroll root), every symbol clickable → chart.
