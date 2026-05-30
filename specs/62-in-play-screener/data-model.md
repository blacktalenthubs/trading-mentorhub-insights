# Data Model: In-Play Volume Screener

## Table: `screener_universe`
Cached Layer-1 eligible names. Rebuilt weekly (or on demand).

| Field | Type | Notes |
|-------|------|-------|
| symbol | TEXT PK | US common stock ticker |
| market_cap | REAL | USD; > floor at build time |
| last_price | REAL | from build snapshot |
| avg_dollar_vol | REAL | trailing average $-volume/day |
| sector | TEXT NULL | for sector refine filter |
| rebuilt_at | TIMESTAMP | when this universe row was refreshed |

Validation: only rows passing cap/price/$-vol floors are inserted. Stale rows replaced on rebuild.

## Table: `screener_snapshot`
One row per in-play refresh. Endpoint reads the most recent.

| Field | Type | Notes |
|-------|------|-------|
| id | INTEGER PK AUTOINCREMENT | → SERIAL on Postgres |
| captured_at | TIMESTAMP | refresh time |
| market_open | INTEGER (bool) | true during RTH refresh |
| stale | INTEGER (bool) | true if data source degraded this cycle |
| top_n | INTEGER | N used for this snapshot |
| entries | JSON/TEXT | ordered list of In-Play Entry objects (below) |

Retention: keep latest + a short rolling history (e.g., last 50) for debugging; prune older.

### In-Play Entry (JSON object inside `entries`)
| Field | Type | Notes |
|-------|------|-------|
| rank | int | 1-based, by RVOL desc |
| symbol | str | |
| last_price | float | |
| pct_change | float | signed day % change |
| rvol | float | from `compute_rvol` |
| dollar_vol | float | today's $-volume |
| market_cap | float | from universe |
| sector | str? | |
| direction | "long" \| "short" \| "neutral" | trend bias (price vs 50 EMA) for refine filters |
| setup | object? | `{ pattern, entry, stop, target, conviction }` from signal_engine; null = no setup |
| refine | object | indicator inputs for client/server filtering: `{ above_ema50, above_vwap, rsi, rs_vs_spy, atr_pct }` |

## Settings (global defaults; optional per-user thresholds)
Stored in app config (defaults) with optional per-user override of `market_cap_floor` and `top_n`.

| Field | Type | Default | Bounds |
|-------|------|---------|--------|
| market_cap_floor | REAL | 2_000_000_000 | 50M – 1T |
| price_floor | REAL | 5 | 1 – 1000 |
| dollar_vol_floor | REAL | 20_000_000 | 1M – 1B |
| top_n | INTEGER | 30 | 10 – 100 |
| refresh_minutes | INTEGER | 10 | 5 – 30 |

## Presets (FR-9) — refine filter bundles
| Preset | Direction | Filters |
|--------|-----------|---------|
| Momentum Long (default) | long | above_ema50 AND above_vwap AND 50 ≤ rsi ≤ 70 AND rs_vs_spy > 0 |
| Pullback | long | above_ema50 AND 35 ≤ rsi ≤ 50 |
| Breakout | long | near 20-day high AND rvol ≥ 2 AND above_vwap |
| Short | short | below_ema50 AND below_vwap AND 30 ≤ rsi ≤ 50 |
| Any | any | (no refine filter; full energy-ranked shortlist) |

Presets are applied **after** ranking + pattern scan, never as a gate on the scan.
