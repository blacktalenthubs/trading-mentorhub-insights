# Alert Audit — 2026-05-19

Review doc capturing the alert/dedup state **after this session's changes**
(PDH/PDL allow-list, SPY-only SHORT gate, EMA 8 swap, R-band dedup,
weekly/monthly disable, 60-min candle pings).

> **NOTE:** These changes are **not yet committed or deployed**. Today's
> live alerts still reflect the old code until this ships.

Leave comments inline — use `<!-- comment -->` or just write under each
section. Search for `👉 COMMENT` markers for the open decisions.

---

## 1. Active Pine scripts

| Pine file | Fires alerts? | Role |
|---|---|---|
| `levels_day_vwap.pine` | ✅ yes | PDH/PDL + open-line + VWAP + weekly/monthly events |
| `ma_ema_daily.pine` | ✅ yes | MA bounce / rejection / proximity |
| `open_line.pine` | ❌ no | visual only |
| `levels_week_month.pine` | ❌ no | visual only (PWH/PWL/PMH/PML lines) |
| `spy_regime.pine` | ❌ no | visual only (regime badge) |
| `toggle_wicks.pine` | ❌ no | visual only |
| `double_tops_bottoms.pine` | ❌ no | visual only (new — daily DT/DB lines) |

---

## 2. Every alert/notice the Pine emits

Legend — **Backend delivers?**: ✅ reaches Telegram · ❌ dropped by backend allow-list / SHORT gate.

| # | Rule name | Source | Dir | Fires when | Pine toggle | Pine default | Backend delivers? |
|---|---|---|---|---|---|---|---|
| 1 | `staged_pdh_break` | levels_day_vwap | BUY | Price breaks above PDH | always (daily) | ON | ✅ |
| 2 | `staged_pdh_rejection` | levels_day_vwap | SHORT | Price tests PDH, rejected | always (daily) | ON | ✅ SPY only |
| 3 | `staged_pdh_failed_short` | levels_day_vwap | SHORT | Failed PDH breakout, reverses | always (daily) | ON | ✅ SPY only |
| 4 | `staged_pdl_break` | levels_day_vwap | SHORT | Price breaks below PDL | always (daily) | ON | ✅ SPY only |
| 5 | `staged_pdl_reclaim` | levels_day_vwap | BUY | Price reclaims above PDL | always (daily) | ON | ✅ |
| 6 | `staged_pwh_break` / `pmh_break` | levels_day_vwap | BUY | Weekly/Monthly high broken | `fire_htf_staged` | OFF | ❌ |
| 7 | `staged_pwh_rejection` / `pmh_rejection` | levels_day_vwap | SHORT | Weekly/Monthly high rejected | `fire_htf_staged` | OFF | ❌ |
| 8 | `staged_pwh_failed_short` / `pmh_failed_short` | levels_day_vwap | SHORT | Weekly/Monthly failed breakout | `fire_htf_staged` | OFF | ❌ |
| 9 | `staged_pwl_break` / `pml_break` | levels_day_vwap | SHORT | Weekly/Monthly low broken | `fire_htf_staged` | OFF | ❌ |
| 10 | `staged_pwl_reclaim` / `pml_reclaim` | levels_day_vwap | BUY | Weekly/Monthly low reclaimed | `fire_htf_staged` | OFF | ❌ |
| 11 | `open_lost` | levels_day_vwap | NOTICE | Open line lost (index symbols only) | `fire_open_alerts` | OFF | ❌ |
| 12 | `open_reclaimed` | levels_day_vwap | BUY | Full close-flip reclaim of open | `fire_open_alerts` | OFF | ❌ |
| 13 | `open_held` | levels_day_vwap | BUY | Open line defended | `fire_open_alerts` | OFF | ❌ |
| 14 | `open_wick_reclaim` | levels_day_vwap | BUY | Wick below open, reclaimed | `fire_open_alerts` | OFF | ❌ |
| 15 | `vwap_reclaim_long` | levels_day_vwap | NOTICE | VWAP reclaimed (SPY/QQQ only) | `fire_vwap_alerts` | OFF | ❌ |
| 16 | `vwap_reject_short` | levels_day_vwap | NOTICE | VWAP rejected from above | `fire_vwap_alerts` | OFF | ❌ |
| 17 | `vwap_support_hold` | levels_day_vwap | NOTICE | VWAP defended on pullback | `fire_vwap_alerts` | OFF | ❌ |
| 18 | `pwh_held` / `pwh_wick_reclaim` | levels_day_vwap | BUY | Prior-week high held / wick-reclaimed | `fire_htf_alerts` | OFF | ❌ |
| 19 | `pwl_held` / `pwl_wick_reclaim` | levels_day_vwap | BUY | Prior-week low held / wick-reclaimed | `fire_htf_alerts` | OFF | ❌ |
| 20 | `pmh_held` / `pmh_wick_reclaim` | levels_day_vwap | BUY | Prior-month high held / wick-reclaimed | `fire_htf_alerts` | OFF | ❌ |
| 21 | `pml_held` / `pml_wick_reclaim` | levels_day_vwap | BUY | Prior-month low held / wick-reclaimed | `fire_htf_alerts` | OFF | ❌ |
| 22 | `htf_proximity_pwh/pwl/pmh/pml` | levels_day_vwap | NOTICE | Price near a weekly/monthly level | `fire_htf_alerts` | OFF | ❌ |
| 23 | `ma_bounce_long_v3` | ma_ema_daily | BUY | Bounce/reclaim of any daily MA | `fire_alerts` | ON | ✅ |
| 24 | `ma_rejection_short_v3` | ma_ema_daily | SHORT | Rejection/loss of any daily MA | `fire_alerts` | ON | ❌ see §5 |
| 25 | `ma_proximity_long_v3` | ma_ema_daily | NOTICE | Bar holds near MA without touching (long) | `fire_proximity_alerts` | ON | ❌ |
| 26 | `ma_proximity_short_v3` | ma_ema_daily | NOTICE | Bar holds near MA without touching (short) | `fire_proximity_alerts` | ON | ❌ |

MA set monitored by `ma_ema_daily` (rows 23–26): **EMA 8 / 21 / 50 / 100 / 200, SMA 50 / 100 / 200**
(EMA 5 + EMA 10 were merged into a single EMA 8 on 2026-05-19.)

👉 COMMENT — anything in rows 6–22 / 24–26 you actually want back on?

---

## 3. Backend allow-list

Only these reach Telegram. Everything else dropped at `tv_webhook.py`.

**Exact match:**
- `tv_staged_pdh_break`
- `tv_staged_pdh_rejection`
- `tv_staged_pdh_failed_short`
- `tv_staged_pdl_break`
- `tv_staged_pdl_reclaim`

**Prefix match (any MA-tag suffix):**
- `tv_ma_bounce_long_v3*`
- `tv_ma_rejection_short_v3*`

👉 COMMENT — allow-list correct? Add/remove anything?

---

## 4. SHORT gate

| Symbol | Direction | Result |
|---|---|---|
| Any | BUY / NOTICE | pass |
| SPY | SHORT, in whitelist (`pdh_rejection`, `pdh_failed_short`, `pdl_break`) | ACTION |
| SPY | SHORT, other (incl. MA rejection) | DROP |
| Non-SPY | SHORT | DROP |

👉 COMMENT — keep SPY-only? Should SPY MA rejection SHORT fire (currently no)?

---

## 5. Dedup layers (in order)

| # | Layer | Behavior |
|---|---|---|
| 0 | Allow-list filter | Drops non-PDH/PDL, non-MA-family types |
| 1 | SHORT routing gate | Drops non-SPY shorts + non-whitelisted SPY shorts |
| 2 | Confluence twin | Collapses `open_*`+`staged_*` twins within 5 min (mostly dead now) |
| 3 | Cross-level confluence | PDL+PWL near same price within 30 min → suppress 2nd (mostly dead now) |
| 4 | Symbol-session dedup | ANY same `(user, symbol, direction)` this session → drop. The 3 SPY SHORT rules are exempted so each fires independently. |
| 5 | Identity dedup + R-band | Same `(user, symbol, direction, alert_type)` within a time window. Level alerts also get the R-distance check below. |

### Identity dedup windows

| Alert type | Window |
|---|---|
| Most types | 60 min |
| `staged_pdh_rejection`, `staged_pdh_failed_short`, `staged_pdl_break` | 16h (once per session) |

### R-band check (`_is_chop_refire`)

For level alerts (PDH/PDL break/reclaim): when the same type re-fires —
- new entry **within 1R** of prior entry (`R = |prior_entry − prior_stop|`) → suppress as chop
- new entry **≥ 1R away** → allow as a fresh re-test

👉 COMMENT — is once-per-session (16h) right for SPY shorts? Is the 1R band tight/loose enough?

---

## 6. Net result — what reaches Telegram

| Symbol | Direction | Delivered alert types |
|---|---|---|
| Any | BUY | `staged_pdh_break`, `staged_pdl_reclaim`, `ma_bounce_long_v3` (any MA) |
| SPY | SHORT | `staged_pdh_rejection`, `staged_pdh_failed_short`, `staged_pdl_break` |
| Non-SPY | SHORT | (none) |

**Pine emits ~26 rule families → backend narrows to 6 delivered combinations.**

---

## 7. Known wrinkle

`ma_rejection_short_v3` (row 24) fires from Pine and passes the allow-list,
but is then dropped by the SHORT gate on **every** symbol (non-SPY by the
gate; SPY because MA rejection isn't in the 3-rule SPY whitelist). It's
wasted webhook traffic — logged and dropped.

👉 COMMENT — options:
- (a) leave it (harmless, just noise in logs)
- (b) remove `tv_ma_rejection_short_v3` from the allow-list prefixes (bounce-only)
- (c) add MA rejection to the SPY SHORT whitelist so SPY MA rejections fire

---

## 8. Non-alert: 60-min candle-close pings

Telegram pings (not trade alerts), Mon-Fri, market hours:

| Time (ET) | Body |
|---|---|
| 10:30 / 11:30 / 12:30 / 13:30 / 14:30 | "60-min candle N closed" |
| 15:30 | "60-min candle 6 closed — FINAL 30 MIN remaining" |

Switched from 65-min on 2026-05-19.

👉 COMMENT — schedule good? Keep the "FINAL 30 MIN" framing?

---

## 9. Review comments → proposed fixes (2026-05-19)

Captured from user comments. **Nothing implemented yet** — confirm/refine
each row, then we build.

### S0 — CORE PRINCIPLE: position-relative levels (the root fix)

> User insight 2026-05-19: *"high side can be support or resistance —
> relative to price position. Reason we have so many false alerts: we are
> not tracking direction. If price touches PMH/PWH we just say LONG, but
> that may be a trend running from a low INTO that level."*

**A level's NAME ≠ its ROLE.** "PWH" just means *prior-week high* — where
the level came from. Whether it's support or resistance RIGHT NOW depends
only on where price sits relative to it:

| Price vs level | Level's role | Valid setup |
|---|---|---|
| Price **ABOVE** level | **SUPPORT** | Pull back DOWN to it, wick + hold → **LONG bounce** |
| Price **BELOW** level | **RESISTANCE** | Rally UP into it, reject → **SHORT** (SPY only) / level is a **TARGET** for a long taken lower |
| Price crosses UP through it | breakout — level **flips** resistance→support | bullish |
| Price crosses DOWN through it | breakdown — level **flips** support→resistance | bearish |

**This applies uniformly to ALL levels:** PDH, PDL, PWH, PWL, PMH, PML,
and every MA (EMA 8/21/50/100/200, SMA 50/100/200).

**The bug today:** `pwh_held` / `pmh_held` / `pwl_held` / `pml_held` and
the MA `reclaim_long` mode are **direction-blind** — they fire LONG whenever
price touches the level, ignoring whether price is above (support) or
below (resistance) it.

**MSFT example:** price ran from PWL 400.88 → up into PWH 428.17 + PMH
433.70. Price was BELOW both → they were RESISTANCE. Current code fired
LONG on the touch. Correct: that's a rally INTO resistance — not a bounce.

**The fix (all in Pine — "control from pines, easier to understand"):**
Every level alert must first classify the level as support/resistance by
price position, THEN decide direction:
- support tested + held → LONG
- resistance tested + rejected → SHORT (SPY) or NOTICE/target (equity)
- no more "touched a high → LONG" blind firing

👉 COMMENT — confirm this is the model. Everything below (S1, S2) is just
this principle applied to specific level families.

---

### S1 — Collapse weekly/monthly level events into ONE alert  ✅ answered

| | |
|---|---|
| **You said** | "staged_pwl_reclaim / pml_reclaim / HELD should be one alert" + "better we control from pines" |
| **ANSWERED** | (a) Not "high side vs low side" — every level classified support/resistance by **position** (see S0). (b) Collapse in **Pine**, not backend. (c) Fold the daily PDL/PDH into the combined alert too — "makes sense". |
| **Resolved behavior** | Per bar, per symbol: gather every level being tested (PDH/PDL/PWH/PWL/PMH/PML). Classify each as support or resistance by price position. Emit **ONE LONG alert** if support level(s) held, **ONE SHORT/NOTICE alert** if resistance level(s) rejected — each listing all levels involved (e.g. "Held support: PDL 105.02 + PWL 104.80"). |
| **Open Q** | none — ready to build once S0 confirmed. |

### S2 — MA/EMA support-vs-resistance + MAs-as-targets  ✅ answered

| | |
|---|---|
| **You said** | "from above = support. from below = resistance. no short on equity except SPY. use MA as targets if equity has MA/EMA above price." |
| **ANSWERED** | • Same S0 principle applied to MAs.<br>• Equity: resistance test from below → **no SHORT** (SPY only).<br>• Equity with MAs above price → those MAs become **TARGETS** (T1/T2/T3) on the BUY.<br>• `reclaim_long` (BUY on any upward MA cross) → **DELETE** — under S0, grinding up into overhead MAs is moving through resistance, not a bounce. MA BUY fires only on `strict_long` (price drops DOWN to the MA from above and holds). |
| **INTC** | Rallied off PWL 105 → into 8EMA ≈ 112.38 = resistance / first target. Not a buy at the cross. |
| **MU** | Same — rallied off PWL 706 → overhead MAs = resistance/targets. |
| **Open Q** | none — `reclaim_long` deletion is implied by S0; flag if you disagree. |

### S3 — Enable MA proximity alerts as NOTICE  ✅ answered

| | |
|---|---|
| **You said** | "proximity should be notice alerts not long or short" |
| **Resolved behavior** | Add `tv_ma_proximity_long_v3` + `tv_ma_proximity_short_v3` to the backend allow-list, both delivered as **NOTICE**. Pine already emits NOTICE — backend allow-list change only. |
| **Open Q** | none — ready to build. |

### Quick-reference — BUILT 2026-05-20

| ID | Suggestion | Status |
|---|---|---|
| S0 | Position-relative level classification | ✅ confirmed + applied in S1/S2 |
| S1 | Collapse HTF level alerts | ✅ BUILT — 8 hold/wick → 1 `htf_support_held`; 4 proximity → 1 `htf_proximity` |
| S2 | MA position-relative logic | ✅ BUILT — deleted `reclaim_long`+`lose_short`; MAs above/below = targets |
| S3 | MA proximity as NOTICE | ✅ BUILT — backend allow-list |

### Follow-ups — BUILT 2026-05-20

| Item | Status |
|---|---|
| **Merge staged ↔ HTF held** | ✅ BUILT — as *suppression*: `htf_support_held` / `htf_proximity` don't fire when a staged event fired the same bar (staged is the primary signal). One alert per bar, not two. |
| **Re-enable staged weekly/monthly** | ✅ BUILT — `fire_htf_staged` → true; 10 W/M staged types added to backend allow-list; 6 W/M SHORT structural rules added to the SPY SHORT whitelist + 16h once-per-session dedup. |

SPY SHORT whitelist is now **9 structural rules** (daily + weekly + monthly
rejection/failed_short/break) — "SPY shorts at any structural level" applied
across all three timeframes. Each fires at most once per session.
