# Scanner Redesign — open-above reclaim, confluence, entries-only

**Status:** Phase 1 shipped (PR #1118) · Phase 2 shipped (this spec) · **Type:** day-trade scanner
**Owner:** vbolofinde · **Date:** 2026-09-05

> This file is the repo copy of `scanner_redesign_spec.html`, which lived only on the
> trader's machine. Phase 1 was built against it and merged as #1118; Phase 2 is
> specified here in full because the original never covered the delivery layer in
> enough detail to build from.

## Problem

The scanner fired too much, and what it fired could not be trusted:

1. **Bounces can't tell support from resistance.** `check_ema_bounce_*` fired on ANY
   touch of a moving average, and `check_ma_ema_reclaim` fired on a cross-up from
   *below*. Neither looks at where the day OPENED, so a stock ramping UP into an MA
   from underneath produced a "support" long (MRVL / LITE-21 / STX false fires).
2. **Three alerts for one trade.** A double bottom, a 21 SMA reclaim and a 50 EMA
   reclaim at the same price sent three pushes for one entry.
3. **Noise around the entries.** Resistance notices, shorts and NOTICE-only levels
   were delivered alongside the trades.

## The rule

A level `L` fires **BUY** when:

```
day_open > L        (support — the day opened above it)
AND session_low ≤ L (wicked down to tag it)
AND last_close > L  (reclaimed — closed back above)
AND close is not already far above L   (staleness guard)
```

Entry = the reclaim close · Stop = 0.5% below the level (`MA_RECLAIM_STOP_OFFSET_PCT`,
then risk-capped by `_cap_risk`) · Long only. Staleness guard: skipped if the close is
already more than 1.5% above the level (`MA_RECLAIM_MAX_DISTANCE_PCT`).
Chart-validated 2026-09-04: LRCX 100 EMA qualifies; MRVL 21 EMA (opened below →
cross-up) is rejected.

## Scope

- **Universe:** hardcoded `SCANNER_UNIVERSE` (38 symbols, incl. BTC-USD / ETH-USD).
  Not the per-user watchlist — a fixed, controlled set while the redesign is validated.
- **Rules:** hardcoded `ENABLED_RULES`. The MA ladder is **8 / 21 / 50 / 100 / 200**
  for both SMA and EMA.
- **Delivery:** **global**. No per-user alert-type toggles, category preferences or
  min-score gate. The universe and the rule set are hardcoded, so what fires delivers.
- **Out of scope:** shorts, the TradingView webhook path (`tv_webhook.py` keeps its own
  routing and per-user prefs), swing rules, position sizing.

---

## Phase 1 — signal quality (shipped, PR #1118)

| # | Change | Where |
|---|--------|-------|
| 1.1 | `check_ma_reclaim` — the open-above reclaim, distinct from bounce and cross-up | `analytics/intraday_rules.py` |
| 1.2 | `_reclaim_pairs` routes the `ema_reclaim_*` / `ma_reclaim_*` rules through it | `analytics/intraday_rules.py` |
| 1.3 | `ema_bounce_*`, `ma_bounce_*`, `prior_day_low_bounce` removed from `ENABLED_RULES` | `alert_config.py` |
| 1.4 | Hardcoded 38-symbol `SCANNER_UNIVERSE` | `api/app/background/monitor.py` |
| 1.5 | Confluence merge — same-level BUYs within 0.2% collapse to one alert | `api/app/background/monitor.py` |
| 1.6 | 1 alert / stock / type / day (`_entry_type_day`) | `api/app/background/monitor.py` |
| 1.7 | Long-entries-only delivery; exit lifecycle kept, gated to open trades | `api/app/background/monitor.py` |

## Phase 2 — in-app push + Day/Swing feed UX (this spec)

Phase 1 shipped the signal quality. It did not ship to anyone: the alerts recorded to
the database and reached neither the feed nor the phone. Phase 2 closes that.

### 2.1 The scanner's alerts must appear in the feed

`isFeedSignal()` admitted only `ai_*` and `tv_*` alert types. The scanner writes the
bare rule key (`ma_reclaim_50`), so **every Phase-1 alert was filtered out of the
Signals feed, the Alert Log and the in-app notification alike.**

→ `isScannerEntry()` admits **exactly the redesign's live long-entry set — 14 types,
nothing aspirational**: the open-above MA ladder (`^(ma|ema)_reclaim_\d+$`, 10 types)
plus `prior_day_low_reclaim`, `prior_day_high_breakout`, `pdh_retest_hold` and
`multi_day_double_bottom`. Every one is in `ENABLED_RULES` and can actually fire — a
test enforces that, so a rule can't be added to the feed before it's enabled. Shorts,
resistance, weekly/monthly NOTICE rules and the deprecated `*_bounce_*` ladder stay
out.

`style_for()` resolves **all 14** to `day_trade` — including `ma_reclaim_200` and
`ema_reclaim_200`, which are NOT routed to Swing (`isSwingAlert` only marks the
`ma_bounce_long_v3_*200` TradingView family as swing). The scanner's entire entry set
lands in the **Day** feed; nothing from it reaches Swing.

Every one of the 14 has a plain-English description, so its feed card carries an
explanation subline: the ladder is described by rule in `describe_alert_type()` /
`setupBlurb()`, the four named types by explicit entries in `ALERT_TYPE_DESCRIPTIONS`
and the TS `NAMES` / `BLURB` maps.

### 2.2 Delivery is global

The per-user gate (`UserAlertTypePref` → `UserAlertCategoryPref` → `min_alert_score`)
silently muted the new reclaims for every user who had ever toggled the now-deprecated
bounce types: with ≥1 per-type row set, any type without an explicit row is OFF.
Phase 1 therefore delivered nothing.

→ The scanner path no longer reads those tables. `ENABLED_RULES` is the gate.
The Settings rows still exist and still drive the TradingView path.

### 2.3 Every suppression is recorded, not silent

The scanner wrote its alerts with `suppressed_reason = NULL` whether or not they
delivered, so the feed's "what actually sent" view was wrong, and the confluence
merge deleted its losers outright — no row, no audit.

→ The merge keeps the collapsed siblings, stamped
`confluence_collapsed:<winning_rule>`; the gate stamps `not_long_entry`,
`dedup_type_day`, `dedup_cooldown` or `dedup_zone`. The clean feed shows
`suppressed_reason IS NULL`; "Show collapsed" reveals the rest, labelled
"merged into 50 SMA Reclaim". Matches what `tv_webhook.py` already does.

A collapsed sibling records its row and nothing else: no ActiveEntry (the winner owns
the entry — a duplicate would fire the stop/target lifecycle twice), no AI narrative,
and it bypasses the level-dedup that would otherwise drop it before recording.

### 2.4 One name for a setup, everywhere

The iOS push read `"BUY SPY $769.00"` / `"Ma Reclaim 50"` — the raw enum, title-cased.

→ `_pretty_setup()` gains the ladder rule, and `_setup_name()` in monitor.py delegates
to it, so the feed, Telegram and the push all say **"50 SMA Reclaim"**:

```
Title:  SPY LONG · 50 SMA Reclaim
Body:   Entry $769.20 · Stop $766.10 · T1 $774.00 · Confluence: 21 SMA + 50 EMA
```

The merged alert names its factors in the message, and `Alert.confluence_label` carries
the compact form (`21 SMA + 50 EMA`) that `AlertCard` renders as "• Confluence: …".
Above 50 chars the label degrades to `×4 at $769.20` rather than truncating mid-word.
The in-app notification carries the same body and fires only for delivered alerts.

### 2.5 The SMA 8/21 reclaims are wired

Phase 1 added the `ma_reclaim_8` / `ma_reclaim_21` enums but nothing else: they were in
neither `_reclaim_pairs` nor `ENABLED_RULES`, and `prior_day` carried no `ma8` / `ma21`,
so the fast SMA reclaims could never fire.

→ `MA8` / `MA21` computed in `intraday_data.py` (both the Coinbase and the equity path),
extracted into `prior_day`, added to `_reclaim_pairs`, enabled in `ENABLED_RULES`.

### 2.6 The HTF bias gate is removed

`should_gate_long()` blocked every long whenever the 4h read was BEAR and the 1h had
not yet turned BULL. That is the shape of a washout — so the gate suppressed **the
first reclaim off a flush**, which is the setup this redesign exists to catch. It let
through only the later, more extended ones.

It was also solving, coarsely and by trend, the question `check_ma_reclaim` now answers
precisely and per setup: the day opened ABOVE the level, so the level was support, not
resistance being ramped into. Two filters for one problem, the older one blunter.

Worse, it was invisible: the gate `continue`d **before** the Alert row was written, so
unlike every Phase-2 suppression it left no row and no `suppressed_reason` — a signal
it ate could not be reviewed at all.

→ The gate is gone from the poll loop. The 1h/4h bias is still computed and still feeds
the 0–3 `confluence_score` (the Telegram 🟢/🟡 and the persisted column); it suppresses
nothing. `should_gate_long` / `should_gate_short` remain in `analytics/htf_bias.py`,
marked deprecated with their tests, as the record of the old behaviour — nothing calls
them. The `HTF_BIAS_GATE_ENABLED` env var keeps its name (Railway backward compat) and
now controls only whether the 1h/4h fetch happens at all.

**Expect more entries per session.** What still limits them: the open-above rule itself,
the 1.5% staleness guard, level-dedup, the confluence merge, 1/symbol/type/day, the
30-minute burst cooldown and the 30-minute zone cluster.

### 2.7 The final signal set (user, 2026-09)

**Delivered — nothing else reaches the phone.**

Longs (14), any symbol in `SCANNER_UNIVERSE`:
`ma_reclaim_8/21/50/100/200`, `ema_reclaim_8/21/50/100/200`, `prior_day_low_reclaim`,
`prior_day_high_breakout`, `pdh_retest_hold`, `multi_day_double_bottom`.

Shorts (7), **index-only** — `SHORT_UNIVERSE = {SPY, QQQ, SMH}`:
`pdh_rejection`, `ma_rejection_8/21/50`, `ema_rejection_8/21/50`.

`check_ma_rejection` is the exact mirror of `check_ma_reclaim`: the symbol must have
**opened BELOW** the level (so it was resistance overhead, not support being lost),
rallied up to tag it, and closed back below. Entry = the rejection close, stop 0.5%
above the level, same staleness guard. A short on any non-index symbol is recorded as
`short_not_index` and never sent.

**Stop and target hits are no longer delivered.** They stay in `ENABLED_RULES` so the
trade lifecycle and P&L tracking keep recording, but delivery stamps them
`exits_not_delivered`. Entries only.

**Retired from the set:** all nine weekly/monthly rules (they only ever became NOTICEs
with entry/stop/targets stripped — unreadable rows nobody could trade), plus
`ema_rejection_short` (the un-gated 9-MA catch-all, superseded by the open-below
ladder), `ema_overhead_resistance`, `pdh_failed_breakout`, `resistance_prior_high`,
`prior_day_low_breakdown` and `prior_day_low_resistance`.

`SMH` was added to `SCANNER_UNIVERSE` (39 symbols) — it was in the short set but not
the evaluated universe, so it could never have fired.

## Files

| File | Change |
|------|--------|
| `analytics/intraday_data.py` | MA8 / MA21 → `prior_day` |
| `analytics/intraday_rules.py` | SMA 8/21 in the reclaim ladder |
| `alert_config.py` | `ma_reclaim_8` / `ma_reclaim_21` enabled |
| `alerting/notifier.py` | `_pretty_setup` names the MA ladder |
| `api/app/background/monitor.py` | global delivery, confluence audit + label, suppressed_reason, push payload, HTF gate removed |
| `analytics/htf_bias.py` | gate helpers deprecated — scoring only |
| `api/app/models/alert_type_config.py` | `describe_alert_type` explains the ladder rules by regex + the six named scanner entries by table |
| `web/src/lib/alertFormat.ts` | `isScannerEntry`, ladder names + blurbs |
| `web/src/pages/TradingPageV2.tsx` | labels for the new suppression reasons |
| `web/src/hooks/useSignalNotifications.ts` | confluence in the body; suppressed alerts stay silent |

## Tests

`tests/test_ma_reclaim.py` (6) — the rule.
`tests/test_scanner_delivery.py` (12) — the merge keeps its audit rows, the label fits
its column, setup naming parity, SMA 8/21 wired end to end, and the feed contract:
every type `isScannerEntry()` admits resolves to `day_trade`, carries a description,
and is in `ENABLED_RULES`.

`test_intraday_rules.py`: 635 pass, 4 fail — the same 4 SPY-regime failures as on `main`.

## Deploy

1. Push to main — Railway deploys the worker, Streamlit Cloud the dashboard.
2. **Restart the Railway worker** — it caches `alert_config` / `intraday_rules` in
   memory, so the new rules and the global delivery only take effect on restart.
3. No Settings change is needed any more: delivery no longer reads per-user toggles.
4. Weekend crypto (BTC/ETH, 24/7) is the live validation target.

## Open

- The 38-symbol universe is hardcoded. Widening it back to the per-user watchlist is a
  later decision, once the redesign is validated.
- `_entry_count` (max 2 entries per symbol per session) is computed in monitor.py and
  never used. Left as-is — deciding whether the budget should exist is its own change.
