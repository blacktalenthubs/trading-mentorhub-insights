# Phase 0 Research: In-Play Volume Screener

## R1 — Layer 1 universe source (market-cap + volume screen)

**Decision**: Use yfinance `EquityQuery` / `screen()` to build the capped universe weekly,
filtering on market cap + day volume + region, then apply price and dollar-volume floors in
pandas.

**Rationale**: yfinance is already a dependency; its equity screener pushes the market-cap +
volume filter server-side (Yahoo), returning a few hundred names per page sorted by volume —
exactly the Layer-1 narrowing we need, at zero new cost. Runs weekly so latency/unofficial-API
risk is low-impact.

**Alternatives considered**:
- FMP `/stock-screener` (clean `marketCapMoreThan`+`volumeMoreThan`) — paid, deferred (no new vendor v1).
- Polygon full-market snapshot — best reliability, paid, deferred.
- Maintaining a static index-constituent list (S&P/Russell 1000) — simplest but misses
  mid-caps and needs its own cap source; kept as a fallback if yfinance screen proves flaky.

**Open validation (do at impl)**: pin exact field names against the installed `yfinance 0.2.x`
(`intradaymarketcap`, `dayvolume`, `region`, `exchange`) and `screen()` vs `Screener` API
shape — these have drifted across yfinance versions. Wrap in a thin adapter so a field rename
is a one-line fix.

## R2 — Layer 2 intraday volume source

**Decision**: Alpaca (`alpaca-py` `ScreenerClient.get_most_actives`) for the day's most-active
names, intersected with the cached universe; pull latest quotes/bars for cumulative volume +
last price + % change.

**Rationale**: Already installed and credentialed (`ALPACA_API_KEY/SECRET`). Most-actives is a
purpose-built, low-cost call; intersecting with the universe applies our cap/liquidity gate.
Quotes give the intraday cumulative volume `compute_rvol` needs.

**Alternatives considered**:
- yfinance intraday `download()` per symbol — works but heavier/slower for ~1,200 names; use
  as fallback for symbols Alpaca doesn't cover.
- Polygon snapshot (one call, whole market) — deferred (paid).

**Open validation**: confirm most-actives + market-data quotes are covered by the current
Alpaca data entitlement (IEX free tier vs SIP). If most-actives breadth is too small, rank the
universe directly from batched quotes instead of starting from most-actives.

## R3 — RVOL computation

**Decision**: Reuse `analytics/intraday_data.py::compute_rvol` (time-of-day-normalized RVOL,
10-day lookback) for ranking. No new RVOL definition.

**Rationale**: Consistency with existing alerts (Constitution: reuse over reinvent), already
time-normalized which is essential for fair intraday ranking. Dollar volume is the tiebreaker.

**Alternatives considered**: a fresh cumulative-vs-ADV ratio — rejected (duplicate logic, drift
risk).

## R4 — Setup detection on the shortlist

**Decision**: Call `analytics/signal_engine.py` (public scan) read-only on the top-N shortlist;
attach detected pattern/entry per symbol. **No modification to signal_engine** (protected).

**Rationale**: The 14 documented patterns already live there; the screener only feeds candidates
in and reads results out. Scanning ≤N (~30–50) names every 10 min is cheap.

**Alternatives considered**: scanning the whole universe — rejected (cost + the cap exists
precisely to avoid this).

## R5 — Snapshot & universe storage

**Decision**: Two async-SQLAlchemy tables in the shared DB:
- `screener_universe` — one row per eligible symbol (cap, price, avg $-vol, sector, rebuilt_at).
- `screener_snapshot` — one row per refresh, `entries` as a JSON column, plus `captured_at`,
  `market_open`, `stale`. Endpoint serves the most recent row.

**Rationale**: JSON snapshot avoids per-entry schema churn and is a single fast read for the
endpoint. SQLAlchemy handles SQLite+Postgres (Constitution: DB compatibility). Durable across
restarts; an in-memory cache layer fronts it for hot reads.

**Alternatives considered**: in-memory only — rejected (lost on restart, not shareable across
processes); normalized per-entry rows — rejected (overkill for a 30-row ephemeral list).

## R6 — Scheduling & market-hours gate

**Decision**: Run both jobs (weekly universe rebuild; ~10-min in-play refresh) via APScheduler
**inside the FastAPI process** lifespan. The refresh job early-returns when the US market is
closed (regular hours only).

**Rationale**: Keeps compute next to the SQLAlchemy session + analytics imports the api already
has; the endpoint stays a pure read. APScheduler is already used elsewhere in the stack.

**Alternatives considered**: the separate Railway alert worker — rejected (uses the legacy
`db.py` layer and is dedicated to alerting; mixing concerns adds risk). Cron — rejected (extra
infra).

**Open validation**: confirm only one api instance runs the scheduler (avoid duplicate refreshes
if scaled to multiple replicas); guard with a simple DB advisory lock / "last refresh" check.

## Resolved unknowns
- Tier gating → **Pro+** (FR-10), free sees teaser. (Product decision, confirmed default.)
- Global vs per-user list → **global snapshot**; per-user limited to thresholds. (FR assumption.)
- Default preset → **Momentum Long** (above 50 EMA · above VWAP · RSI 50–70 · RS > SPY).
