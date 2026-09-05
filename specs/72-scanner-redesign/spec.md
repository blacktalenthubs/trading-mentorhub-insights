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

Entry = the level · Stop = below the reclaim wick · Long only.
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

→ `isScannerEntry()` admits the scanner's long-entry rules: the MA ladder
(`^(ma|ema)_(reclaim|bounce)_\d+$`) plus `prior_day_low_reclaim`,
`prior_day_high_breakout`, `pdh_retest_hold`, `multi_day_double_bottom`,
`inside_day_reclaim`, `vwap_reclaim`. Shorts, resistance and weekly/monthly NOTICE
rules stay out — the redesign delivers long entries, and the feed shows the trade set.
`style_for()` already classifies all of them as `day_trade`, so they land in the **Day**
feed; the 200-level swing rules keep their Swing bucket.

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

## Files

| File | Change |
|------|--------|
| `analytics/intraday_data.py` | MA8 / MA21 → `prior_day` |
| `analytics/intraday_rules.py` | SMA 8/21 in the reclaim ladder |
| `alert_config.py` | `ma_reclaim_8` / `ma_reclaim_21` enabled |
| `alerting/notifier.py` | `_pretty_setup` names the MA ladder |
| `api/app/background/monitor.py` | global delivery, confluence audit + label, suppressed_reason, push payload |
| `api/app/models/alert_type_config.py` | `describe_alert_type` explains the ladder rules |
| `web/src/lib/alertFormat.ts` | `isScannerEntry`, ladder names + blurbs |
| `web/src/pages/TradingPageV2.tsx` | labels for the new suppression reasons |
| `web/src/hooks/useSignalNotifications.ts` | confluence in the body; suppressed alerts stay silent |

## Tests

`tests/test_ma_reclaim.py` (6) — the rule.
`tests/test_scanner_delivery.py` (9) — the merge keeps its audit rows, the label fits
its column, setup naming parity, SMA 8/21 wired end to end.

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
