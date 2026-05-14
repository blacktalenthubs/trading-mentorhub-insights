# Alert Inventory — Active Pine Indicators

**Snapshot as of 2026-05-13.** Source of truth for what fires from where, what reaches Telegram, what gets dropped, and why.

This file describes the **4 active Pine indicators** in `pine_scripts/active/` and the **backend gating layers** that filter their output before delivery.

---

## At a glance — what reaches Telegram

| Direction | Symbols | Caps / cooldowns |
|---|---|---|
| **BUY** | Every watchlist symbol | ETH MA bounces: 4h rolling cooldown per `(symbol, alert_type)`. Others: none. |
| **SHORT** | **SPY / QQQ / AIQ / NDX only** (other symbol shorts dropped at the backend) | None |
| **NOTICE** | **SPY / QQQ / AIQ / NDX only** (other symbol notices dropped at the backend) | 60-min dedup per `(symbol, direction, alert_type)` |

---

## Pine 1 — `ma-ema-daily`

**File**: `pine_scripts/active/ma_ema_daily.pine`
**Monitors**: 9 daily moving averages — EMA 5 / 10 / 21 / 50 / 100 / 200, SMA 50 / 100 / 200
**Alert taxonomy**: 4 event types × 9 MAs. The MA name is appended to the rule key (e.g. `tv_ma_bounce_long_v3_ema5`).

### Event types

| Rule prefix | Direction | Trigger |
|---|---|---|
| `ma_bounce_long_v3_<ma>` | BUY | Bar wicks the MA from above + closes back above on a green bar (strict_long) **OR** prev close was below MA, this bar's close is above (reclaim_long, e.g. gap-up recovery) |
| `ma_rejection_short_v3_<ma>` | SHORT | Symmetric short — wick into MA from below + closes back under, red bar |
| `ma_proximity_long_v3_<ma>` | NOTICE | Bar held NEAR an MA (within %) without touching, green close |
| `ma_proximity_short_v3_<ma>` | NOTICE | Symmetric short proximity |

### Examples
- `tv_ma_bounce_long_v3_ema5` — EMA 5 bounce (LONG) — fast short-term momentum
- `tv_ma_bounce_long_v3_ema5_ema10` — Stacked EMA 5 + EMA 10 bounce
- `tv_ma_rejection_short_v3_ema21` — EMA 21 rejection (SHORT)
- `tv_ma_proximity_long_v3_ema100` — EMA 100 proximity (NOTICE)

### Total events
- 9 bounce-long (BUY) + 9 rejection-short (SHORT) + 9 proximity-long (NOTICE) + 9 proximity-short (NOTICE) = **36 distinct alert keys**
- Plus stacked-MA variants (`ema5_ema10`, `ema5_ema21` etc.)

---

## Pine 2 — `levels-day-vwap`

**File**: `pine_scripts/active/levels_day_vwap.pine`
**Monitors**: PDH / PDL + PWH / PWL (internal) + PMH / PML (internal) + VWAP + today's opening price
**Alert taxonomy**: 5 staged level events + 3 VWAP events + 2 open-line events = **10 distinct alert keys**

### Staged level events (D / W / M unified)

Each event fires when price crosses ANY of the corresponding D/W/M levels. Direction varies by TF that triggered:

| Rule | Triggered by | Direction (D) | Direction (W/M) |
|---|---|---|---|
| `staged_pdh_break` | Close above PDH / PWH / PMH | **BUY** | NOTICE |
| `staged_pdl_reclaim` | Close back above PDL / PWL / PML | **BUY** | NOTICE |
| `staged_pdh_rejection` | Wick into PDH / PWH / PMH + close back under | **SHORT** | NOTICE |
| `staged_pdh_failed_short` | Closed above PDH / PWH / PMH then back below within sweep window | **SHORT** | NOTICE |
| `staged_pdl_break` | Close below PDL / PWL / PML | **SHORT** | NOTICE |

**Sweep window** (for `staged_pdh_failed_short` and `staged_pdl_reclaim`'s sweep variant):
- **SPY / QQQ**: 200 bars (covers a full RTH session)
- All other symbols: 5 bars (default `sweep_window_bars` input)

### VWAP NOTICEs

Pine-gated to SPY / QQQ / AIQ only. Require `fire_vwap_alerts=true` (default false; flip on the SPY 10m chart instance).

| Rule | Direction | Trigger |
|---|---|---|
| `vwap_reclaim_long` | NOTICE | Close back above VWAP after N consecutive bars below |
| `vwap_reject_short` | NOTICE | Close back below VWAP after N consecutive bars above |
| `vwap_support_hold` | NOTICE | Bar wicked down to VWAP (within 0.1%) + closed back above on green bar |

**Open-line alerts moved out.** As of 2026-05-13, `open_lost` and `open_reclaimed` live in the separate `open-line` indicator (Pine 4 below) so the visual layer can be toggled independently.

---

## Pine 3 — `levels-week-month`

**File**: `pine_scripts/active/levels_week_month.pine`
**Purpose**: Visual reference only — PWH / PWL / PMH / PML horizontal lines + optional weekly EMA 8 / 21.

**No alerts fire from this indicator.** Per 2026-05-06 unification: weekly/monthly level events are folded into the daily alert layer via `levels-day-vwap` (see staged events above with the D / W / M unification).

You can toggle this indicator off the chart without losing any alert signal.

---

## Pine 4 — `open-line`

**File**: `pine_scripts/active/open_line.pine`
**Monitors**: Today's opening price (captured on the first bar of each session, held flat through the day)
**Alert taxonomy**: 2 events.

Separated from `levels-day-vwap` (2026-05-13) so the open-line visual can be toggled independently. Backtest evidence: NVDA-style trend days establish themselves with the reclaim, weak names never reclaim — high signal-to-noise on the BUY direction.

| Rule | Direction | Symbols | Trigger |
|---|---|---|---|
| `open_reclaimed` | **BUY** | **All symbols** | First close back above today's open after having lost it. One-shot per session. |
| `open_lost` | NOTICE | SPY / QQQ / AIQ / NDX only | First close below today's open after holding above earlier in the session. One-shot per session. |

State machine: `was_above_open` flag must be set (price made a bar with `close > open` earlier in session) before `open_lost` is eligible. `open_lost_today` must be set before `open_reclaimed` is eligible. Both reset at the next session open.

Stops/targets:
- `open_reclaimed` BUY → stop at `min(low, low[1]) - atr_buffer`, T1 = +0.75%, T2 = +1.5% (triage agent re-ranks)
- `open_lost` NOTICE → stop at `max(high, high[1]) + atr_buffer`, T1 = -0.75%, T2 = -1.5%

### PDH/PDL confluence

When today's open sits within **0.3% of PDH or PDL** (gap-up/gap-down days), the open-line alert IS the level alert — `open_reclaimed` and `staged_pdh_break` would normally fire on the same bar. The payload carries `near_pdh` / `near_pdl` flags; the webhook uses these to **suppress the twin** within a 5-min window:

| First arrives | Second (twin) | Action |
|---|---|---|
| `open_reclaimed` (near_pdh=true) | `staged_pdh_break` | Twin suppressed. Message header: "Open + PDH confluence ↑" |
| `staged_pdh_break` | `open_reclaimed` (near_pdh=true) | Twin (open_reclaimed) suppressed. Message header: plain "PDH break" |
| `open_lost` (near_pdl=true) | `staged_pdl_break` | Twin suppressed. Message header: "Open + PDL confluence ↓" |
| `staged_pdl_break` | `open_lost` (near_pdl=true) | Twin (open_lost) suppressed. Message header: plain "PDL break" |

Audit log records `confluence_twin_suppressed` with the dropped alert_type for EOD Report visibility.

---

## Backend gating — what happens between Pine and Telegram

Order of gates applied in the triage agent (`triage-agent/live.py`) after an alert hits the database:

1. **TV-webhook dedup** (in `api/app/routers/tv_webhook.py`) — same `(user, symbol, direction, alert_type)` within 60 minutes is suppressed. This is the primary rate-limiter for all TV-sourced alerts (BUY / SHORT / NOTICE).
2. **Non-index NOTICE drop** — any NOTICE-direction alert where `symbol` ∉ {SPY, QQQ, AIQ, NDX} is dropped before triage. Audited as `NOTICE_NON_INDEX_DROPPED`.
3. **Global NOTICE mute** — if `MUTE_NOTICE_ALERTS=true`, all NOTICEs dropped. Default: `false` (NOTICEs delivered).
4. **ETH MA rolling cooldown** — if alert is an ETH MA bounce/rejection AND a prior fire of the same `(symbol, alert_type)` happened within the last 4 hours, drop. Audited as `MA_COOLDOWN_HIT`. (Strictly tighter than the 60-min webhook dedup for ETH.)
5. **Cost budget** — daily triage spend cap (default $1.50).
6. **Triage agent runs** — LLM evaluates sector confluence, index alignment, CVD, volume, cluster. Assigns verdict (HIGH / NORMAL / MUTE) + reason.
7. **Non-index SHORT gate** (in `analytics/intraday_rules.py`) — SHORT-direction alerts on non-SPY/QQQ/AIQ/NDX symbols are dropped at the rule evaluation stage. Crypto path unaffected.
8. **Post mode filter** — `TRIAGE_POST_MODE=all` (default) sends everything; `high_only` / `high_mute` restricts.
9. **Telegram delivery** — format_unified renders the message; HIGH-conviction alerts get an inline chart.

---

## Env vars — what controls each gate

All on the Railway `triage-agent` service:

| Variable | Default | Purpose |
|---|---|---|
| `MUTE_NOTICE_ALERTS` | `false` | Set `true` to mute all NOTICEs from Telegram |
| `MA_COOLDOWN_HOURS` | `4` | Rolling cooldown window for MA alerts on capped symbols |
| `MA_COOLDOWN_SYMBOLS` | `ETH-USD` | Comma-separated list of symbols subject to MA cooldown |
| `TRIAGE_POST_MODE` | `all` | `all` / `high_only` / `high_mute` |
| `TRIAGE_DAILY_USD_CAP` | `1.50` | Daily LLM spend ceiling |

In Pine inputs (per chart instance):

| Input | Default | Pine |
|---|---|---|
| `fire_vwap_alerts` | `false` | levels-day-vwap (set true on SPY 10m chart) |
| `show_open` / `show_markers` | `true` | open-line (visual toggles; alerts always fire when conditions met) |
| `show_lines` / `show_vwap` / etc. | `true` | levels-day-vwap visual toggles |

---

## What you'd see in Telegram on a typical day

- **9:30-16:00 ET (US RTH)**: BUY alerts on the equity watchlist as PDH breaks / MA bounces / open reclaims fire. SHORT alerts only on SPY/QQQ/AIQ/NDX. NOTICE alerts on SPY/QQQ/AIQ/NDX (VWAP + open_lost events).
- **24/7 (crypto)**: BUY alerts on BTC-USD freely; ETH-USD throttled to one fire per `(symbol, MA)` every 4 hours.
- **Premarket / afterhours**: Mostly quiet. Premarket brief at 08:30 ET, EOD recap at 16:05 ET (gated by `ENABLE_PREMARKET_BRIEF` env flag).

---

## Audit trail — what's NOT in Telegram but visible in the EOD Report

Every dropped/muted alert still hits the database AND is audited with a verdict tag. The EOD Report (`/eod-report` in the UI) shows all of them so you can review what would have fired:

- `NOTICE_NON_INDEX_DROPPED` — non-SPY/QQQ/AIQ/NDX NOTICE
- `NOTICE_MUTED` — NOTICE dropped by MUTE_NOTICE_ALERTS
- `MA_COOLDOWN_HIT` — ETH MA blocked by 4h cooldown
- TV-webhook 60-min dedup — logged but not stored as an alert row (suppressed at ingest)
- Backend-side filtered SHORTs (logged to triage logs, not as audit verdicts) — visible in EOD Report by direction filter

---

## Related files

- `pine_scripts/active/` — the 4 active Pine indicators
- `pine_scripts/archive/` — retired indicators (pivots-4h, old daily_ma_bounce_v3, etc.)
- `triage-agent/live.py` — backend gating + audit logic
- `triage-agent/.env.example` — env var reference with comments
- `analytics/intraday_rules.py` — SPY-regime gates + non-index SHORT filter
- `alert_config.py` — `SPY_SHORT_SYMBOLS = {"SPY", "QQQ", "AIQ", "NDX"}` and related tier config
