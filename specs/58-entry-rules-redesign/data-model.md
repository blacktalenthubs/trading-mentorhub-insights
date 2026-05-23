# Data Model — Spec 58

**Date**: 2026-05-22

This is a behavior change, not a schema migration. Existing tables (`alerts`, `alert_type_config`, `watchlist`, `users`) are unchanged. The only mutation is on `alert_type_config` (soft-disable retired types). The "data" added by this spec lives in the **alert webhook payload** — see [contracts/tv-webhook-payload.md](./contracts/tv-webhook-payload.md).

## Entities (from the spec, mapped to data)

### Entry Rule
A row in `alert_type_config`. After this spec, the routed entry rules are:

| `alert_type` (DB) | Family | Description |
|---|---|---|
| `tv_ma_bounce_long_v3_ema8` | Buy 1 | EMA 8 pullback hold (when uptrend gate passes) |
| `tv_ma_bounce_long_v3_ema21` | Buy 1 | EMA 21 pullback hold |
| `tv_ma_bounce_long_v3_ema50` | Buy 1 | EMA 50 pullback hold |
| `tv_ma_bounce_long_v3_ema100` | Buy 1 | EMA 100 pullback hold |
| `tv_ma_bounce_long_v3_ema200` | Buy 1 | EMA 200 pullback hold |
| `tv_ma_bounce_long_v3_sma` | Buy 1 | Grouped SMA 50/100/200 pullback hold |
| `tv_staged_pdh_held` *(NEW)* | Buy 2a | PDH defended as support from above |
| `tv_staged_pwh_held` *(NEW)* | Buy 2a | PWH defended as support from above |
| `tv_staged_pmh_held` *(NEW)* | Buy 2a | PMH defended as support from above |
| `tv_staged_pdl_reclaim` | Buy 2b | PDL lost then reclaimed |
| `tv_staged_pwl_reclaim` | Buy 2b | PWL lost then reclaimed |
| `tv_staged_pml_reclaim` | Buy 2b | PML lost then reclaimed |
| `tv_htf_support_held` | HTF | Long-term level held on a pullback |

**Fields per row** (existing schema):
- `id` (PK)
- `alert_type` (unique, indexed) — e.g. `tv_ma_bounce_long_v3_ema21`
- `label` — human-readable name shown in Settings UI
- `category` — grouping label (Settings UI section)
- `enabled` (bool) — toggle controlling whether webhook routes to Telegram
- `updated_at`

**State transitions**:
- New entry types (`*_held`): inserted with `default_enabled=False` (consistent with the project rule "new alert types default OFF").
- Retired entry types: `enabled := false` via migration. The catalog entry still exists for audit; the legacy rows in `alerts` keep their `alert_type` for historical context.

---

### Trend State
Not persisted — computed per bar in Pine. Surfaced in the webhook payload as a single boolean (`uptrend_pass`) plus the `overhead_mas` list (which key MAs sit above the current price).

**Computation** (Pine, every bar):
```
uptrend_pass = (close > EMA8) AND (close > EMA21) AND (close > EMA50)
             AND (close > SMA50) AND (close > EMA100) AND (close > SMA100)
             AND (close > EMA200) AND (close > SMA200)
overhead_mas = [name for (name, value) in seven_mas if close < value]
```

When `uptrend_pass = false`, **no entry alert fires** (gate failure short-circuits). This is the FR-001 enforcement point.

---

### Support Level
Three classes, all included in the alert payload as `nearby_levels`:

| Class | Source | Examples |
|---|---|---|
| **Moving Average** | Pine `ta.ema()` / `ta.sma()` | EMA 8/21/50/100/200, SMA 50/100/200 |
| **Prior-period level** | Pine `request.security()` from D/W/M | PDH/PDL/PWH/PWL/PMH/PML |
| **Anchored VWAP** | Pine accumulator from month start | `mtd_avwap` |

Each level in the payload is `{ "kind": "<key>", "value": <float>, "label": "<display>" }`.

The webhook performs confluence detection as: *for each pair (entry_level, other_level) in payload, if `|entry_level − other_level| / entry_level < 0.01`, both are confluent — annotate.*

---

### Chop Gate
Pine-side state — not persisted. For each Buy-2 alert candidate, Pine checks:
```
session_high_now = ta.highest(high, bars_since_session_open)
last_new_high_time = time when session_high_now last increased
chop_gate_pass = (current_time - last_new_high_time) <= 30 minutes
```

Used only for Buy-2 (prior-high held / prior-low reclaim / HTF held) alerts — Buy-1 MA bounce is exempt (it is itself a continuation signal, regardless of recent higher-highs).

---

## Validation rules (Pine-side, before `alert()` fires)

| Rule | Source FR | Implementation |
|------|-----------|----------------|
| Uptrend gate (zero overhead MAs) | FR-001 | All 7 MAs must be ≤ close |
| Buy 1 only on MA pullback hold | FR-002 | day's low ≤ MA ≤ close AND prev_close ≥ prev_MA |
| Block any entry on overhead MA | FR-003 | `uptrend_pass = false` blocks all entries |
| Buy 2 only on reclaimed support hold | FR-004, FR-005 | level held from above (price was > level on prior bar; pulled back to ≤ level intraday; closed ≥ level) |
| Chop gate on Buy 2 | FR-006 | `chop_gate_pass = true` required |
| No open-line entries | FR-007 | `alertcondition()` calls removed from `open_line.pine` (plots stay) |
| Targets = next structural resistance | FR-011 | Pine uses the existing `target_1` / `target_2` logic — verify mapping to "next prior high above entry" |

## Validation rules (FastAPI-side, in `tv_webhook.py`)

| Rule | Source FR | Implementation |
|------|-----------|----------------|
| Honor `enabled` flag | FR-008 | Existing `_is_allowed_alert_type()` continues; retired types now have `enabled=false` so they fail the gate |
| Annotate confluence on single alert | FR-013 | New function `_format_confluence(entry_level, nearby_levels)` produces the "confluent with X, Y" string; appended to `sig.message` before persist + notify |
| Surface only — no auto-trading | FR-012 | No new fields or hooks for auto-execution |

---

## Out of scope (data-wise)

- No new tables.
- No changes to `alerts` schema (the alert message text carries the confluence info inline).
- No changes to `users`, `watchlist`, `cooldowns`, `usage_limits`.
- React frontend: no schema changes; the message rendering already shows the full text of `Alert.message`, so the confluence annotation appears automatically in the existing signal feed.
