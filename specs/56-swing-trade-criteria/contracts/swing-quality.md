# Contract: `evaluate_swing_quality()`

The swing scan is an internal scheduled service — it exposes no public API. Its one new interface is the deterministic qualification function in `analytics/swing_quality.py`, consumed by `ai_swing_scanner.py`. This is that function's contract.

## Function

```text
evaluate_swing_quality(symbol, daily, indicators, *, config=DEFAULT) -> SwingQualification | None
```

### Inputs

| Param | Type | Description |
|---|---|---|
| `symbol` | str | The symbol being evaluated. |
| `daily` | daily OHLC series | Recent daily candles (open/high/low/close/volume), most-recent last — enough history for the lookback windows (≥ ~210 bars to seat the 200 MA + lookbacks). The scan already fetches 3-month+ daily bars; `fetch_prior_day` fetches ~1y. |
| `indicators` | mapping | The indicator dict from `intraday_data.fetch_prior_day()` — must provide `ema21, ema50, ema100, ema200, ma50, ma100, ma200`, `rsi14`, and an RSI history (via `compute_rsi_series`). |
| `config` | tuning struct | Proximity tolerance, recent-high lookback, oversold lookback, downtrend filter. Defaults defined in the module; overridable for tests/tuning. |

### Output

- **`SwingQualification`** (see data-model.md) when the symbol meets ≥1 rule — carrying every rule hit, direction `LONG`, entry/stop/targets, and the plain-language `summary`.
- **`None`** when the symbol meets no rule.

### Behaviour (the contract)

1. **Pure & deterministic** — no I/O, no network, no LLM, no clock dependence beyond the bars passed in. Same inputs → same output.
2. **EMA/SMA hold** — for each of the seven key MAs: if the latest bar was above the MA going in, its low came within `config.tolerance` of the MA, and it closed above the MA → an `ema_hold` rule hit citing that MA. Gated by the uptrend check.
3. **EMA/SMA reclaim** — for each key MA: if the prior close was below the MA and the latest close is above it → an `ema_reclaim` hit citing that MA. Gated by the uptrend check.
4. **RSI recovery** — if RSI(14) is now above 30 and was ≤ 30 within `config.oversold_lookback` bars → an `rsi_recovery` hit. NOT gated by the uptrend check.
5. **Uptrend gate** — the MA rules (2, 3) only fire when the symbol made a higher high within `config.recent_high_lookback` and is not in a sustained downtrend; a close above an MA inside a downtrend yields no MA hit.
6. **Merge** — all rule hits for the bar collapse into ONE `SwingQualification`; never returns duplicates for the same symbol/bar.
7. **Entry/stop/targets** — entry = latest close; stop = structural (below the defended/reclaimed MA or the candle low; RSI rule → below the recent swing low); targets = R-multiple projection.
8. **No side effects** — persistence, dedup, Telegram, and rate-limiting remain the caller's (`swing_scan_cycle`) responsibility; this function only decides and describes.

## Caller integration (`ai_swing_scanner.py`)

`swing_scan_cycle` keeps watchlist loading, the 15-min schedule, market-hours/regime gating, dedup, Telegram delivery, and the `ai_swing_alerts_per_day` cap. The only change: per symbol, call `evaluate_swing_quality(...)` instead of `scan_swing(...)` (the LLM path). A non-`None` result flows into the existing `Alert` persist + notify path; `None` → skip.

## Contract test checklist

- A bar that pulls back into the 50 EMA (low within tolerance, closes above, was above it before, uptrend) → `ema_hold` citing `EMA 50`.
- A bar whose prior close was below the 100 SMA and current close is above → `ema_reclaim` citing `SMA 100`.
- A bar closing above two key MAs at once → one `SwingQualification`, two rule hits.
- RSI ≤ 30 two bars ago, now closes above 30 → `rsi_recovery`.
- RSI mid-range (never oversold) → no `rsi_recovery`.
- A close above the 21 EMA while in a sustained downtrend → no MA hit (uptrend gate); but if RSI also recovered, `rsi_recovery` still fires.
- A sideways symbol with no MA interaction and no oversold RSI → `None`.
- Same inputs called twice → identical output (determinism).
