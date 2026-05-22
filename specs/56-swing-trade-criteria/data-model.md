# Phase 1 Data Model: Swing Trade Qualification

No database schema change. Qualified swing candidates persist through the AI scan's **existing** `Alert` path. This documents the in-memory structures the new qualification logic produces and the existing fields they map onto.

## Entity: SwingQualification (in-memory result)

The output of `evaluate_swing_quality()` for one symbol on the current daily bar. `None` when the symbol does not qualify.

| Field | Type | Notes |
|---|---|---|
| `symbol` | str | The evaluated symbol. |
| `direction` | str | Always `LONG` — all three rule families are bullish/recovery setups (FR-009). |
| `rules` | list[SwingRuleHit] | Every rule the bar satisfied — one or more. A symbol that hits several rules / MAs produces one qualification carrying all of them (FR-008). |
| `entry` | float | The qualifying daily close. |
| `stop` | float | Structural — just below the defended/reclaimed MA, or below the qualifying candle's low (RSI rule: below the recent swing low). |
| `target_1` | float | R-multiple projection from entry/stop (existing long-target helper). |
| `target_2` | float | Second R-multiple projection. |
| `close` | float | The daily close that triggered qualification. |
| `session_date` | str (ISO date) | The trading session evaluated. |
| `summary` | str | Plain-language "why it qualified" — composed from `rules` (FR-007), e.g. "Held the 50 EMA after a pullback; reclaimed the 100 SMA." |

## Sub-structure: SwingRuleHit

One qualifying rule the bar met. A `SwingQualification.rules` list holds one or more.

| Field | Type | Notes |
|---|---|---|
| `rule` | str (enum) | One of `ema_hold`, `ema_reclaim`, `rsi_recovery`. (`ema_*` covers both EMA and SMA — "ema" is the family name.) |
| `level` | str | The specific level. For MA rules: the MA name — `EMA 21`, `EMA 50`, `SMA 50`, `EMA 100`, `SMA 100`, `EMA 200`, `SMA 200`. For the RSI rule: `RSI 30`. |
| `detail` | str | Human-readable specifics — e.g. "low tested 50 EMA (within 1%), closed above" or "RSI closed 34, up from 27 two bars ago". |

### Rule semantics (validation rules from the spec)

- **`ema_hold`** — for a key MA: the bar's low came within the proximity tolerance of the MA, the close finished above the MA, and the symbol was above that MA going into the bar (pullback context). Requires the uptrend gate (below). FR-002.
- **`ema_reclaim`** — for a key MA: the prior daily close was below the MA and the current daily close is above it. Requires the uptrend gate. FR-003.
- **`rsi_recovery`** — daily RSI(14) closed above 30, having been at or below 30 within the recent oversold-lookback window. FR-004. Does **not** require the uptrend gate (it is the downtrend-reversal path).
- **Uptrend gate** (MA rules only) — the symbol made a higher high within the recent-high lookback and is not in a sustained downtrend; a close above an MA inside a downtrend does not qualify under the MA rules. FR-011.
- **OR-combination** — any single `SwingRuleHit` is sufficient for a `SwingQualification`. FR-005.
- **Single candidate per symbol per bar** — multiple hits merge into one `SwingQualification` with multiple `rules`; never emitted as duplicates. FR-008.

## The seven key MAs

| Level name | Indicator (from `fetch_prior_day`) |
|---|---|
| `EMA 21` | `ema21` |
| `EMA 50` | `ema50` |
| `SMA 50` | `ma50` |
| `EMA 100` | `ema100` |
| `SMA 100` | `ma100` |
| `EMA 200` | `ema200` |
| `SMA 200` | `ma200` |

All seven are already computed server-side — the qualification function consumes them, it does not recompute them.

## Mapping to the existing `Alert` row

A `SwingQualification` maps onto the `Alert` fields the scan already persists — no new columns:

| `Alert` field | From `SwingQualification` |
|---|---|
| `symbol` | `symbol` |
| `direction` | `direction` (`LONG` → the scan's BUY convention) |
| `alert_type` | the scan's existing swing alert type |
| `entry` / `stop` / `target_1` / `target_2` | `entry` / `stop` / `target_1` / `target_2` |
| `price` | `close` |
| `message` | `summary` (the plain-language reason — FR-007) |
| `session_date` | `session_date` |
| `setup_level` / `setup_condition` | the primary `SwingRuleHit` level / rule |

## Referenced existing entities (unchanged)

- **Watchlist** — `watchlist` / `WatchlistItem`. The scan's input symbol set.
- **Daily indicators** — produced by `intraday_data.fetch_prior_day()`; consumed read-only.
- **Swing alert quota** — `usage_limits`, feature `ai_swing_alerts`. Enforced by the scan unchanged.
