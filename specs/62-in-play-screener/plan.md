# Implementation Plan: In-Play Volume Screener

**Spec**: [spec.md](./spec.md)
**Branch**: 62-in-play-screener
**Created**: 2026-05-30

## Technical Context

> NOTE: This feature lives in the **React + FastAPI** app (not the legacy Streamlit
> dashboard). The shared `analytics/` package and dual-mode DB are reused.

| Item | Value |
|------|-------|
| Backend | FastAPI (`api/app`), async SQLAlchemy |
| Frontend | React + Vite + TypeScript (`web/`), TanStack Query |
| Shared analysis | `analytics/` package (`compute_rvol`, `signal_engine`) — importable from api |
| Database | SQLite (local) / Postgres (prod) via async SQLAlchemy (`api/app/database`) |
| Market Data | yfinance (Layer 1 universe screen) + alpaca-py (Layer 2 intraday volume) — both already installed |
| Scheduling | APScheduler job in the FastAPI process (market-hours refresh + weekly universe rebuild) |
| Deployment | Railway (FastAPI service serves `web/dist`) |

### Dependencies
- **No new packages.** `yfinance>=0.2.30` and `alpaca-py>=0.31.0` are already in `requirements.txt`.
- Requires `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` (already in env) for Layer 2 most-actives/quotes.
- APScheduler (already used by the worker) for the refresh jobs.

### Integration Points
- `analytics/intraday_data.py::compute_rvol` — RVOL ranking (reuse, no change).
- `analytics/signal_engine.py` — pattern/setup detection on the shortlist (**reuse read-only; protected file, not modified**).
- yfinance `EquityQuery`/`screen()` — Layer 1 market-cap + volume universe screen.
- alpaca-py `ScreenerClient.get_most_actives()` + quotes/bars — Layer 2 intraday volume.
- Frontend `TierGate` + TanStack Query hooks; `FocusListPage`/`FocusListView` for placement.

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| Protect Business Logic | **PASS** | `signal_engine.py` is reused **read-only** (call its public scan, no edits). No protected file is modified. The screener is a curation layer on top. |
| Test-Driven Development | **PASS (planned)** | New `tests/test_screener.py` written first: universe filtering, RVOL ordering, refine-filter/preset behavior, direction-awareness, market-hours gating, degraded-data fallback. No change to the 648+ baseline. |
| Local First | **PASS** | Build/test locally, verify `localhost:5173` + `/api/v1/screener/in-play`, kill local worker before prod eval. |
| Database Compatibility | **PASS** | New tables via async SQLAlchemy models + the existing `create_all` + idempotent `ALTER ... IF NOT EXISTS` lifespan pattern in `main.py`; works SQLite + Postgres. Snapshot stored as JSON column. |
| Alert Quality | **PASS (N/A)** | No alert logic touched; setups surfaced are exactly what `signal_engine` already produces. |
| Single Notification Channel | **PASS (N/A)** | v1 sends no notifications (the In-Play list is a UI view). Optional "new in-play setup" Telegram push is explicitly out of scope. |

## Solution Architecture

```
                       APScheduler (in FastAPI process)
                       ├── weekly: rebuild_universe()  ─────────────┐
                       └── ~10 min (market hours): refresh_in_play() │
                                                                     ▼
 yfinance EquityQuery ──► analytics/screener.py ◄── alpaca-py quotes/most-actives
   (mktcap/price/$vol)      build_universe()            (intraday volume)
                           rank_in_play()  ──► compute_rvol() [reuse]
                           scan_setups()   ──► signal_engine  [reuse, read-only]
                           apply_refine()  ──► EMA/RSI/VWAP/RS presets
                                   │
                                   ▼  persist
                    DB: screener_universe, screener_snapshot (JSON)
                                   │
        GET /api/v1/screener/in-play  ◄── api/app/routers/screener.py (reads latest snapshot)
                                   │
                          web/src/api/hooks.ts (useInPlay)
                                   ▼
        FocusListPage  [ My Ideas | In Play ]  ──► InPlayView.tsx ──► chart/detail
                                   │
                              TierGate (Pro+)
```

### Data Flow
1. **Weekly**: `rebuild_universe()` runs the yfinance cap/price/$-volume screen → upserts `screener_universe` (~1,200 rows) + `rebuilt_at`.
2. **Every ~10 min (market hours only)**: `refresh_in_play()` pulls intraday volume for the cached universe (Alpaca most-actives ∩ universe, plus quotes), computes `compute_rvol`, ranks top-N, runs `signal_engine` on the shortlist, attaches refine-filter inputs (EMA/RSI/VWAP/RS), and writes one `screener_snapshot` JSON row marked `market_open=true`.
3. **Market closed**: job no-ops; the last snapshot stays (served with `market_open=false`).
4. **Request**: endpoint returns the latest snapshot; `preset`/`direction`/`has_setup` query params apply refine filters server-side (cheap, on ≤N rows).
5. **Degraded**: if a refresh partially fails, keep the prior snapshot and set `stale=true`.

### Files to Modify

| File | Change | Risk |
|------|--------|------|
| `api/app/main.py` | Register screener router; register APScheduler jobs in lifespan; add `screener_*` tables to create_all/migrations | Med |
| `api/app/config.py` | Default thresholds (cap/price/$vol/top-N/cadence) as settings | Low |
| `web/src/App.tsx` | (none — In-Play lives under existing `/trade-ideas`) | Low |
| `web/src/pages/FocusListPage.tsx` | Add `My Ideas | In Play` segmented control | Low |
| `web/src/api/hooks.ts` | `useInPlay()` query hook | Low |

### Files to Add

| File | Purpose |
|------|---------|
| `analytics/screener.py` | Pure functions: `build_universe`, `rank_in_play`, `scan_setups`, `apply_refine_filters`, presets |
| `api/app/services/screener_service.py` | Orchestration, caching, scheduler callbacks, market-hours gate |
| `api/app/routers/screener.py` | `GET /screener/in-play`, `GET/PUT /screener/settings`, `POST /screener/universe/rebuild` (admin) |
| `api/app/models/screener.py` | SQLAlchemy models: `ScreenerUniverse`, `ScreenerSnapshot` |
| `api/app/schemas/screener.py` | Pydantic response/request schemas |
| `web/src/components/InPlayView.tsx` | The ranked, setup-aware list view + preset/has-setup controls |
| `web/src/pages/InPlay.types.ts` | TS types for the snapshot/entry |
| `tests/test_screener.py` | Unit/integration tests (TDD, written first) |

## Implementation Approach

### Phase 1: Foundation (data + universe)
1. `tests/test_screener.py` — write failing tests for `build_universe` filters and `rank_in_play` ordering (TDD).
2. `analytics/screener.py` — `build_universe()` via yfinance `EquityQuery` (cap/price/$vol), returns DataFrame; pin field names to installed yfinance.
3. `api/app/models/screener.py` + lifespan migration — `screener_universe`, `screener_snapshot` tables.
4. `api/app/services/screener_service.py::rebuild_universe()` — run screen, upsert universe, stamp `rebuilt_at`.

### Phase 2: Core logic (in-play ranking + setups + filters)
1. `rank_in_play()` — Alpaca most-actives ∩ universe + quotes → `compute_rvol` → sort RVOL desc, $vol tiebreaker → top-N.
2. `scan_setups()` — call `signal_engine` (read-only) on the shortlist; attach pattern/entry per symbol.
3. `apply_refine_filters()` + presets (Momentum Long default) — direction-aware; never gate the scan.
4. `refresh_in_play()` in the service — market-hours gate, compose snapshot JSON, persist, set `stale` on partial failure.
5. Register APScheduler jobs in `main.py` lifespan (weekly rebuild; ~10-min refresh during RTH).

### Phase 3: API + UI + gating
1. `api/app/routers/screener.py` + schemas — serve latest snapshot; apply query-param refine filters; admin rebuild.
2. `web/src/api/hooks.ts::useInPlay()` + types.
3. `web/src/components/InPlayView.tsx` — rows (symbol/price/%chg/RVOL chip/$vol/cap/setup badge), preset selector, "Has setup" toggle, market-state + staleness indicators, row → chart.
4. `web/src/pages/FocusListPage.tsx` — `My Ideas | In Play` segment; wrap In-Play in `TierGate` (Pro+) with a teaser for free.

## Test Plan

### Unit Tests
- [ ] `build_universe` excludes names below cap/price/$-volume floors; cap change resizes universe.
- [ ] `rank_in_play` orders by RVOL desc with $-volume tiebreaker; high-absolute/normal-RVOL ranks below low-absolute/high-RVOL.
- [ ] `apply_refine_filters` Momentum Long keeps above-50-EMA longs; Short preset surfaces below-50-EMA; clearing filters returns full shortlist (direction-aware).
- [ ] Market-hours gate: refresh no-ops when closed; snapshot marked `market_open=false`.
- [ ] Degraded path: forced data failure → prior snapshot served with `stale=true`, no exception.

### Integration Tests
- [ ] `GET /api/v1/screener/in-play` returns ≤ top-N entries with all required fields; `preset`/`has_setup`/`direction` params filter correctly.
- [ ] Free-tier request is gated; Pro+ returns data.
- [ ] `POST /screener/universe/rebuild` (admin) refreshes `rebuilt_at`.

### E2E Validation
1. **Setup**: local API + `ALPACA_*` keys; seed a small universe; run a manual `refresh_in_play()`.
2. **Action**: open `localhost:5173` → Trade Ideas → In Play during (or simulated) market hours.
3. **Verify**: ~30 ranked rows, RVOL chips, setup badges on names with patterns; toggle preset narrows; market-closed shows frozen labeled snapshot.
4. **Cleanup**: stop local scheduler; kill local processes before any prod check.

## Out of Scope
- Crypto, pre/post-market ranking, new paid data vendors (Polygon/FMP), per-watchlist personalization, automated execution, Telegram push of in-play setups — all per spec.
- Any modification to `signal_engine.py` or other protected files (read-only reuse only).

## Research Notes

_See [research.md](./research.md) — yfinance EquityQuery field validation, Alpaca screener entitlement, RVOL time-normalization reuse, snapshot storage choice._
