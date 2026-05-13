# Alert Inventory — Active Pine Indicators

**Snapshot as of 2026-05-12.** Source of truth for what fires from where, what reaches Telegram, what gets dropped, and why.

This file describes the **3 active Pine indicators** in `pine_scripts/active/` and the **backend gating layers** that filter their output before delivery.

---

## At a glance — what reaches Telegram

| Direction | Symbols | Caps / cooldowns |
|---|---|---|
| **BUY** | Every watchlist symbol | ETH MA bounces: 4h rolling cooldown per `(symbol, alert_type)`. Others: none. |
| **SHORT** | **SPY / QQQ only** (other symbol shorts dropped at the backend) | None |
| **NOTICE** | **SPY / QQQ only** (other symbol notices dropped at the backend) | 60-min dedup per `(symbol, direction, alert_type)` |

---

## Pine 1 — `ma-ema-daily`

**File**: `pine_scripts/active/ma_ema_daily.pine`
**Monitors**: 8 daily moving averages — EMA 8 / 21 / 50 / 100 / 200, SMA 50 / 100 / 200
**Alert taxonomy**: 4 event types × 8 MAs. The MA name is appended to the rule key (e.g. `tv_ma_bounce_long_v3_ema8`).

### Event types

| Rule prefix | Direction | Trigger |
|---|---|---|
| `ma_bounce_long_v3_<ma>` | BUY | Bar wicks the MA from above + closes back above on a green bar (strict_long) **OR** prev close was below MA, this bar's close is above (reclaim_long, e.g. gap-up recovery) |
| `ma_rejection_short_v3_<ma>` | SHORT | Symmetric short — wick into MA from below + closes back under, red bar |
| `ma_proximity_long_v3_<ma>` | NOTICE | Bar held NEAR an MA (within %) without touching, green close |
| `ma_proximity_short_v3_<ma>` | NOTICE | Symmetric short proximity |

### Examples
- `tv_ma_bounce_long_v3_ema8` — EMA 8 bounce (LONG)
- `tv_ma_bounce_long_v3_ema8_ema21` — Stacked EMA 8 + EMA 21 bounce
- `tv_ma_rejection_short_v3_ema21` — EMA 21 rejection (SHORT)
- `tv_ma_proximity_long_v3_ema100` — EMA 100 proximity (NOTICE)

### Total events
- 8 bounce-long (BUY) + 8 rejection-short (SHORT) + 8 proximity-long (NOTICE) + 8 proximity-short (NOTICE) = **32 distinct alert keys**
- Plus stacked-MA variants (`ema8_ema21` etc.)

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

Pine-gated to SPY / QQQ only. Require `fire_vwap_alerts=true` (default false; flip on the SPY 10m chart instance).

| Rule | Direction | Trigger |
|---|---|---|
| `vwap_reclaim_long` | NOTICE | Close back above VWAP after N consecutive bars below |
| `vwap_reject_short` | NOTICE | Close back below VWAP after N consecutive bars above |
| `vwap_support_hold` | NOTICE | Bar wicked down to VWAP (within 0.1%) + closed back above on green bar |

### Open-line NOTICEs

Pine-gated to SPY / QQQ only. Require `fire_open_alerts=true` (**default true** — safe because SPY/QQQ gate hardcoded).

One-shot per session each (state vars reset at next session open):

| Rule | Direction | Trigger |
|---|---|---|
| `open_lost` | NOTICE | First close below today's open, after price had been above earlier in the session |
| `open_reclaimed` | NOTICE | First close back above today's open, after the day already lost it |

---

## Pine 3 — `sb-trend` (Steve Burns trend stack)

**File**: `pine_scripts/active/steve_burns_trend.pine`
**Monitors**: EMA 5 / 10 / 20 stack + SMA 50 / 200 + Keltner Channels (20, 3.0, 10)
**Alert taxonomy**: 4 NOTICE events (off by default, opt-in via `fire_stack_alerts`)

### Visual layer (always on)

- **EMA 5 / 10 / 20** plotted as a fast-MA stack
- **SMA 50 / 200** for golden/death-cross context
- **Keltner Channels** (basis + upper + lower bands)
- **Background tint** when full stack is aligned (green = bullish stack, red = bearish stack)
- **▲ STACK+** triangle when bullish stack just forms, ▼ STACK- when bearish stack just forms
- **○ KC↑ / KC↓** circle markers when price closes outside the Keltner envelope

Bullish stack = `EMA5 > EMA10 > EMA20 AND close > SMA50 AND SMA50 > SMA200`. Reverse for bearish.

### Alert events (opt-in)

Enable `fire_stack_alerts=true` on the chart instance to receive these. All NOTICE direction.

| Rule | Triggers when | Direction |
|---|---|---|
| `sb_stack_long` | Bullish stack first forms (no prior bar had stack alignment) | NOTICE |
| `sb_stack_short` | Bearish stack first forms | NOTICE |
| `sb_kelt_break_long` | Close above Keltner upper band — momentum thrust | NOTICE |
| `sb_kelt_break_short` | Close below Keltner lower band | NOTICE |

Backend gating: like all NOTICEs, hard-gated to SPY/QQQ at the triage layer unless you want to widen the index-only filter. ETH MA cooldown doesn't apply (different alert taxonomy).

---

## Pine 4 — `levels-week-month`

**File**: `pine_scripts/active/levels_week_month.pine`
**Purpose**: Visual reference only — PWH / PWL / PMH / PML horizontal lines + optional weekly EMA 8 / 21.

**No alerts fire from this indicator.** Per 2026-05-06 unification: weekly/monthly level events are folded into the daily alert layer via `levels-day-vwap` (see staged events above with the D / W / M unification).

You can toggle this indicator off the chart without losing any alert signal.

---

## Backend gating — what happens between Pine and Telegram

Order of gates applied in the triage agent (`triage-agent/live.py`) after an alert hits the database:

1. **TV-webhook dedup** (in `api/app/routers/tv_webhook.py`) — same `(user, symbol, direction, alert_type)` within 60 minutes is suppressed. This is the primary rate-limiter for all TV-sourced alerts (BUY / SHORT / NOTICE).
2. **Non-index NOTICE drop** — any NOTICE-direction alert where `symbol` ∉ {SPY, QQQ} is dropped before triage. Audited as `NOTICE_NON_INDEX_DROPPED`.
3. **Global NOTICE mute** — if `MUTE_NOTICE_ALERTS=true`, all NOTICEs dropped. Default: `false` (NOTICEs delivered).
4. **ETH MA rolling cooldown** — if alert is an ETH MA bounce/rejection AND a prior fire of the same `(symbol, alert_type)` happened within the last 4 hours, drop. Audited as `MA_COOLDOWN_HIT`. (Strictly tighter than the 60-min webhook dedup for ETH.)
5. **Cost budget** — daily triage spend cap (default $1.50).
6. **Triage agent runs** — LLM evaluates sector confluence, index alignment, CVD, volume, cluster. Assigns verdict (HIGH / NORMAL / MUTE) + reason.
7. **Non-index SHORT gate** (in `analytics/intraday_rules.py`) — SHORT-direction alerts on non-SPY/QQQ symbols are dropped at the rule evaluation stage. Crypto path unaffected.
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
| `fire_open_alerts` | `true` | levels-day-vwap (SPY/QQQ hard-gated regardless) |
| `show_lines` / `show_open` / `show_vwap` / etc. | `true` | Visual toggles |

---

## What you'd see in Telegram on a typical day

- **9:30-16:00 ET (US RTH)**: BUY alerts on the equity watchlist as PDH breaks / MA bounces fire. SHORT alerts only on SPY/QQQ. NOTICE alerts on SPY/QQQ (VWAP + open events).
- **24/7 (crypto)**: BUY alerts on BTC-USD freely; ETH-USD throttled to one fire per `(symbol, MA)` every 4 hours.
- **Premarket / afterhours**: Mostly quiet. Premarket brief at 08:30 ET, EOD recap at 16:05 ET (gated by `ENABLE_PREMARKET_BRIEF` env flag).

---

## Audit trail — what's NOT in Telegram but visible in the EOD Report

Every dropped/muted alert still hits the database AND is audited with a verdict tag. The EOD Report (`/eod-report` in the UI) shows all of them so you can review what would have fired:

- `NOTICE_NON_INDEX_DROPPED` — non-SPY/QQQ NOTICE
- `NOTICE_MUTED` — NOTICE dropped by MUTE_NOTICE_ALERTS
- `MA_COOLDOWN_HIT` — ETH MA blocked by 4h cooldown
- TV-webhook 60-min dedup — logged but not stored as an alert row (suppressed at ingest)
- Backend-side filtered SHORTs (logged to triage logs, not as audit verdicts) — visible in EOD Report by direction filter

---

## Related files

- `pine_scripts/active/` — the 3 active Pine indicators
- `pine_scripts/archive/` — retired indicators (pivots-4h, old daily_ma_bounce_v3, etc.)
- `triage-agent/live.py` — backend gating + audit logic
- `triage-agent/.env.example` — env var reference with comments
- `analytics/intraday_rules.py` — SPY-regime gates + non-index SHORT filter
- `alert_config.py` — `SPY_SHORT_SYMBOLS = {"SPY", "QQQ"}` and related tier config
