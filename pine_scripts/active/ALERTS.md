# Alert Inventory — Active Pine Indicators

**Snapshot as of 2026-05-13.** Source of truth for what fires from where, what reaches Telegram, what gets dropped, and why.

This file describes the **4 active Pine indicators** in `pine_scripts/active/` and the **backend gating layers** that filter their output before delivery.

---

## At a glance — what reaches Telegram

| Direction | Symbols | Caps / cooldowns |
|---|---|---|
| **BUY** | Every watchlist symbol | ETH MA bounces: 4h rolling cooldown per `(symbol, alert_type)`. Others: none. |
| **SHORT** | **SPY / QQQ / AIQ / NDX only** (other symbol shorts dropped at the backend) | None |
| **NOTICE** | **SPY / QQQ / AIQ / NDX only** by default. Exceptions allowlisted to fire on all stocks: `htf_proximity_*` (HTF level approach heads-ups). | 60-min dedup per `(symbol, direction, alert_type)`; HTF proximity uses 120-min. |

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

**Alert types are TF-suffixed** (2026-05-16) — a weekly-high break fires `tv_staged_pwh_break`, a monthly-low reclaim fires `tv_staged_pml_reclaim`, etc. The Pine logic that *detects* the event is the same across TFs (it's "the level that was crossed"), only the emitted alert_type and Telegram label differ.

| Rule (D / W / M) | Triggered by | Direction |
|---|---|---|
| `staged_pdh_break` / `staged_pwh_break` / `staged_pmh_break` | Close above PDH / PWH / PMH | **BUY** |
| `staged_pdl_reclaim` / `staged_pwl_reclaim` / `staged_pml_reclaim` | Close back above PDL / PWL / PML | **BUY** |
| `staged_pdh_rejection` / `staged_pwh_rejection` / `staged_pmh_rejection` | Wick into PDH / PWH / PMH + close back under | **SHORT** |
| `staged_pdh_failed_short` / `staged_pwh_failed_short` / `staged_pmh_failed_short` | Closed above level then back below within sweep window | **SHORT** |
| `staged_pdl_break` / `staged_pwl_break` / `staged_pml_break` | Close below PDL / PWL / PML | **SHORT** |

**Sweep window** (for `staged_pdh_failed_short` and `staged_pdl_reclaim`'s sweep variant):
- **SPY / QQQ**: 200 bars (covers a full RTH session)
- All other symbols: 5 bars (default `sweep_window_bars` input)

### HTF level support hold + wick reclaim (2026-05-16)

When price is ABOVE a higher-timeframe level (acting as support), the following BUY alerts mirror the open-line lifecycle:

| Rule | Triggered by | Cadence |
|---|---|---|
| `pwh_held` / `pwl_held` / `pmh_held` / `pml_held` | Low tested within 0.2% above level, never crossed below, close green | Once per session per level (daily reset) |
| `pwh_wick_reclaim` / `pwl_wick_reclaim` / `pmh_wick_reclaim` / `pml_wick_reclaim` | Wick crossed below level, body held above, green bar bounce | Once per session per level (daily reset) |

State resets at session open (daily). Critical levels can be tested multiple times in the same week/month — Monday's PWH defense and Wednesday's PWH defense are independent meaningful events, each fires its own alert. State also resets when the level value itself changes (new week locks in PWH/PWL, new month for PMH/PML). All BUY direction, fire on all stocks. Exempt from `SYMBOL_SESSION_DEDUP`.

### HTF level proximity NOTICE (2026-05-16)

Heads-up alerts fired when close is within **0.5%** of a key weekly/monthly level (both sides — resistance approach from below, support approach from above).

| Rule | Trigger | Dedup |
|---|---|---|
| `htf_proximity_pwh` | close within 0.5% of PWH | 120 min |
| `htf_proximity_pwl` | close within 0.5% of PWL | 120 min |
| `htf_proximity_pmh` | close within 0.5% of PMH | 120 min |
| `htf_proximity_pml` | close within 0.5% of PML | 120 min |

NOTICE direction, fires on **all stocks** (allowlisted bypass of the index-only NOTICE filter), and **bypasses `MUTE_NOTICE_ALERTS`** — these are high-signal context the user wants delivered everywhere ("MSFT was rejected at PWH but I had no heads-up").

### VWAP NOTICEs

Pine-gated to SPY / QQQ / AIQ only. Require `fire_vwap_alerts=true` (default false; flip on the SPY 10m chart instance).

| Rule | Direction | Trigger |
|---|---|---|
| `vwap_reclaim_long` | NOTICE | Close back above VWAP after N consecutive bars below |
| `vwap_reject_short` | NOTICE | Close back below VWAP after N consecutive bars above |
| `vwap_support_hold` | NOTICE | Bar wicked down to VWAP (within 0.1%) + closed back above on green bar |

### Open-line events (fired from levels-day-vwap, visual layer in Pine 4)

The open-line ALERTS fire from this indicator (so we only burn one TV
watchlist alert slot for both PDH/PDL/VWAP and open events). The visual
plot + LOST/RECL diamond markers live in the separate `open-line` indicator
(Pine 4) so the visual layer can be toggled on/off independently.

| Rule | Direction | Symbols | Trigger |
|---|---|---|---|
| `open_held` | **BUY** | **All symbols** | Cleanest defense: low touched WITHIN 0.2% above today_open but **never crossed below**. Weakest of the three BUY signals (no real test). One-shot per session. Gated by `not ol_wick_dipped_today` — once any bar's low crosses below, this category is dead for the day. |
| `open_wick_reclaim` | **BUY** | **All symbols** | Wick **crossed below** today_open, body held above, green bar bounce. Mid-tier — real test happened, no close flip. One-shot per session. AAPL 2026-05-15 9:55 ET pattern. |
| `open_reclaimed` | **BUY** | **All symbols** | First close back above today's open after a close had previously gone below. Strongest open-line BUY (genuine lose-and-reclaim cycle). NVDA-style trend-day signal. Re-arms after fire (see below). |
| `open_lost` | NOTICE | SPY / QQQ / AIQ / NDX only | First close below today's open after holding above earlier. One-shot per session. Bearish session shift on the indexes. |

**State machine** (`ol_was_above_open` flag must be set — at least one bar earlier in the session had `close > today_open` — before any BUY open alert is eligible):

- `ol_wick_dipped_today` flips true the first time any bar's low crosses below today_open. Gates `open_held` (clean defense only fires while this is false).
- `ol_lost_today` flips true on first `close < today_open` after holding above. Gates `open_held` and `open_wick_reclaim` (both blocked once a close has flipped below — that's reclaim territory now).
- The three BUY events are mutually exclusive at the bar level: `open_held` requires `low >= today_open`, `open_wick_reclaim` requires `low < today_open AND close > today_open`, `open_reclaimed` requires `close[1] <= today_open AND close > today_open`.

**`open_reclaimed` re-arm (2026-05-15)**: After `open_reclaimed` fires, Pine resets `ol_lost_today=false` so a subsequent lose-and-reclaim cycle later in the session can fire too. Backend applies a **90-minute identity dedup** specifically for `tv_open_reclaimed` (rather than the standard 60-min) to collapse chop while letting distinct legs through.

**Session-dedup exemptions (2026-05-16)** — the following BUY alert types **bypass** `SYMBOL_SESSION_DEDUP` (one BUY per symbol per session) because they represent genuinely-distinct signals:
- `tv_open_reclaimed` — Pine re-arms; multi-leg reclaim days produce real second-leg setups.
- `tv_open_wick_reclaim` — different category from `open_held`; user wants both to surface when they happen on the same symbol.
- `tv_staged_pdh_break`, `tv_staged_pdl_reclaim` — structural levels vs prior day; if `open_held` fires in the AM and PDH breaks in the PM, both are actionable on different time-frame theses.

60-min identity dedup on `(symbol, direction, alert_type)` + confluence-twin suppression still apply to all of them.

`open_held` and `open_lost` remain fully gated by session-dedup (one-shot, no exemption).

### Inside-day flag

Every alert payload from this indicator carries an `inside_day` boolean. True when `today_open` sits between yesterday's PDH and PDL (no overnight gap). Inside days tend to range, so the triage agent uses this to degrade conviction on directional setups (PDH break, MA bounce, open_reclaimed/wick_reclaim/held) — the alert still fires, just with lower confidence in the Telegram message.

### Chart day-type badge (replaces stage badge)

The top-right table cell on the chart now shows a session-type classification instead of Stage 1/2/3/4. Seven mutually exclusive buckets based on today_open vs yesterday's PDH/PDL:

| Badge | Condition | Subline | Color | Trade bias hint |
|---|---|---|---|---|
| **GAP UP** | today_open > PDH (any gap) | `PDH X · mid Y` | Green | "longs at pullbacks" |
| **TEST PDH** | within 0.3% of PDH | `open at PDH X` | Yellow | "break-or-fail" |
| **INSIDE HIGH** | between midpoint and PDH | `mid Y · range PDL / PDH` | Aqua | "range, upper half" |
| **INSIDE MID** | near range midpoint | `mid Y · range PDL / PDH` | Blue | "range, fade extremes" |
| **INSIDE LOW** | between PDL and midpoint | `mid Y · range PDL / PDH` | Aqua | "range, lower half" |
| **TEST PDL** | within 0.3% of PDL | `open at PDL X` | Yellow | "bounce-or-break" |
| **GAP DOWN** | today_open < PDL | `PDL X · mid Y` | Red | "avoid longs, fade pops to mid" |

**Midpoint on GAP UP / GAP DOWN (2026-05-16)**: badge text now surfaces `mid` alongside the gap level — gap stocks frequently get pulled back to the midpoint (gap-up = midpoint support, gap-down = midpoint resistance), so having it visible in the badge keeps the level top-of-mind without needing to read the chart.

Stage logic is still computed internally and lives in the alert payload as `stage` (triage agent uses it for scoring). Just no longer the chart-badge focus — the day-type is more directly actionable for instinct trading.

### Gap-down recovery context tag

**2026-05-16**: when `staged_pdl_reclaim` fires on a day that opened below PDL (`is_gap_down=true`), Pine passes `gap_context=true` in the alert payload. The webhook prefixes the message with `🔄 GAP-DOWN RECOVERY —` so the triage agent renders the Telegram header as **"PDL reclaim — gap-down recovery ↑"** instead of plain "PDL reclaim". No behavior change — same entry, same stop, same targets — just a label upgrade so the trader knows the context (real recovery vs intraday PDL chop).

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

## Pine 3 — `levels-week-month`

**File**: `pine_scripts/active/levels_week_month.pine`
**Purpose**: Visual reference only — PWH / PWL / PMH / PML horizontal lines + optional weekly EMA 8 / 21.

**No alerts fire from this indicator.** Per 2026-05-06 unification: weekly/monthly level events are folded into the daily alert layer via `levels-day-vwap` (see staged events above with the D / W / M unification).

You can toggle this indicator off the chart without losing any alert signal.

---

## Pine 4 — `open-line` (visual only)

**File**: `pine_scripts/active/open_line.pine`
**Monitors**: Today's opening price (captured on the first bar of each session, held flat through the day)
**Alerts**: **None — visual layer only.** The open_lost / open_reclaimed alerts fire from `levels-day-vwap` (Pine 2 above).

This indicator exists so the open-line **visual** (the orange dashed line + LOST/RECL diamonds) can be toggled on/off independently of the PDH/PDL/VWAP layer. Alerts live in `levels-day-vwap` so we only burn one TV watchlist alert slot for everything in the levels family.

Why split: when reviewing PDH/PDL setups, sometimes you want the open line invisible for clarity, but the alerts should still fire. Splitting the visual from the alert source gives that toggle independence without doubling the TV watchlist-alert overhead.

---

## Backend gating — what happens between Pine and Telegram

Order of gates applied in the triage agent (`triage-agent/live.py`) after an alert hits the database:

1. **Symbol-session dedup** (in `api/app/routers/tv_webhook.py`, env flag `SYMBOL_SESSION_DEDUP=true` default) — only the **first** BUY/SHORT alert per `(user, symbol, direction, session_date)` fires; subsequent same-direction alerts for the same symbol that session are dropped regardless of `alert_type`. Opposite-direction alerts (BUY → SHORT) still pass — that's a regime change worth signaling. Primary noise reducer on chop days (e.g., ETH-USD bouncing off EMA5/EMA10/EMA21/EMA50/SMA50 fires ONE alert, not 5–11). **Exempt types** (`SESSION_DEDUP_EXEMPT_TYPES` set): `tv_open_reclaimed`, `tv_open_wick_reclaim`, `tv_staged_pdh_break`, `tv_staged_pdl_reclaim`, plus all weekly/monthly variants (`tv_staged_pwh_break` / `tv_staged_pwl_reclaim` / `tv_staged_pmh_break` / `tv_staged_pml_reclaim`) and HTF hold/wick (`tv_p{w,m}{h,l}_held` / `_wick_reclaim`) — these are either Pine-re-arming or structural-level events whose meaning is independent of any prior open-line alert. All other BUY alerts (`tv_open_held`, `tv_open_support_hold` legacy, `tv_ma_bounce_*`, etc.) still gated.

5. **Cross-level confluence dedup** (2026-05-16, in `api/app/routers/tv_webhook.py`, env vars `LEVEL_CONFLUENCE_WINDOW_MIN=30` and `LEVEL_CONFLUENCE_PCT=1.0`) — when a `staged_*_break` / `staged_*_reclaim` / `staged_*_rejection` / `staged_*_failed_short` alert fires on a symbol, any **same-side** level alert that arrives within 30 min AND within 1% of the prior alert's entry price is **suppressed**. First-fires-wins (which naturally favors daily reclaims for low-side and weekly breaks for high-side based on price geometry). Prevents the "PDL + PWL + PML all reclaim at the same recovery zone within 30 min" flood on confluence-heavy setups. Side detection: alert_type containing `_pdh_/_pwh_/_pmh_` = "high", `_pdl_/_pwl_/_pml_` = "low". The hold/wick_reclaim variants (`pwh_held`, `pwl_wick_reclaim`, etc.) are NOT included in this dedup — they have their own per-session cadence and serve a different role. **Audit**: suppressed alerts are logged with verdict `level_confluence_suppressed` in the worker log; in-memory only (process restart loses state, but within-bar fires arrive within seconds so this is fine in practice).

   **Example (MSTR Friday)**: `tv_staged_pdl_reclaim` fires at entry $175.28. If `tv_staged_pwl_reclaim` arrives 5 min later at entry $176.00 (PWL = $175.72), spread = $0.72 / $175.28 = 0.41% — within 1% → **suppressed**. EOD report on the way (V2) will show: "PDL reclaim delivered · PWL reclaim stacked-suppressed @ 0.41% spread".
2. **TV-webhook identity dedup** — same `(user, symbol, direction, alert_type)` within 60 minutes is suppressed. Secondary belt-and-suspenders against same-alert-type re-fires (mostly redundant with symbol-session dedup, useful when SYMBOL_SESSION_DEDUP is off).
3. **Non-index NOTICE drop** — any NOTICE-direction alert where `symbol` ∉ {SPY, QQQ, AIQ, NDX} is dropped before triage. Audited as `NOTICE_NON_INDEX_DROPPED`.
4. **Global NOTICE mute** — if `MUTE_NOTICE_ALERTS=true` (now **default true** as of 2026-05-15), all NOTICEs dropped from Telegram delivery. Audited as `NOTICE_MUTED`. EOD Report still shows them. Set env to `false` to re-enable NOTICE delivery on indexes (e.g., when you want `open_lost` or VWAP NOTICEs back).
5. **ETH MA rolling cooldown** — if alert is an ETH MA bounce/rejection AND a prior fire of the same `(symbol, alert_type)` happened within the last 4 hours, drop. Audited as `MA_COOLDOWN_HIT`. (Strictly tighter than the 60-min webhook dedup for ETH.)
6. **Cost budget** — daily triage spend cap (default $1.50).
7. **Triage agent runs** — LLM evaluates sector confluence, index alignment, CVD, volume, cluster. Assigns verdict (HIGH / NORMAL / MUTE) + reason.
8. **Non-index SHORT gate** (in `analytics/intraday_rules.py`) — SHORT-direction alerts on non-SPY/QQQ/AIQ/NDX symbols are dropped at the rule evaluation stage. Crypto path unaffected.
9. **Post mode filter** — `TRIAGE_POST_MODE=all` (default) sends everything; `high_only` / `high_mute` restricts.
10. **Telegram delivery** — format_unified renders the message; HIGH-conviction alerts get an inline chart.

---

## Env vars — what controls each gate

All on the Railway `triage-agent` service:

| Variable | Default | Purpose |
|---|---|---|
| `SYMBOL_SESSION_DEDUP` | `true` | One alert per `(user, symbol, direction, session_date)`. Set `false` to allow multiple same-direction alerts per symbol per day (legacy behavior, only 60-min identity dedup applies). |
| `MUTE_NOTICE_ALERTS` | `true` | All NOTICE alerts muted from Telegram by default (still hit DB / EOD Report). Set to `false` if you want them back. |
| `MA_COOLDOWN_HOURS` | `4` | Rolling cooldown window for MA alerts on capped symbols |
| `MA_COOLDOWN_SYMBOLS` | `ETH-USD` | Comma-separated list of symbols subject to MA cooldown |
| `TRIAGE_POST_MODE` | `all` | `all` / `high_only` / `high_mute` |
| `TRIAGE_DAILY_USD_CAP` | `1.50` | Daily LLM spend ceiling |

In Pine inputs (per chart instance):

| Input | Default | Pine |
|---|---|---|
| `fire_vwap_alerts` | `false` | levels-day-vwap (set true on SPY 10m chart) |
| `fire_proximity_alerts` | `false` | ma-ema-daily — MA proximity NOTICE alerts. Default off (was true) — was the primary NOTICE noise source. Re-enable per chart if needed. |
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
