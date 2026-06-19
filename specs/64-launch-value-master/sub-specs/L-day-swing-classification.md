# Sub-spec L — Day-trade vs Swing classification (at fire time) (P1)

**Parent:** #64 Launch Value Master · **Pillars:** A (alerting) · **Priority:** P1

## Overview
Every tradeable alert should be tagged **DAY** or **SWINGABLE** at the moment it fires, so the user instantly knows the intended hold and which target/stop frame applies. The classification is **dynamic** — read from the chart state at fire time (RSI position + which EMA the entry sits on), not just the alert's type.

## Problem (current state — evaluated 2026-06-19)
Send path: Pine `alert()` → `tv_webhook.py` → `AlertSignal` → `notifier.py` (Telegram).
1. **No RSI in the payload.** `build_payload_v2` carries `interval`, entry/stop/targets, `overhead_mas`, `nearby_levels` (EMA values), `uptrend_pass`, `vwap_slope` — but **not RSI**. RSI is the primary classification signal, so it must be added.
2. **Classification is static, by type.** `_is_swing_alert()` (in `tv_webhook.py`) flags `{rsi_70, ema_5_20_cross, rsi_oversold}` + slow-MA (50/100/200) bounces as swing — and uses it **only** to exempt them from the SPY-vs-PDL day-trade gate. It is **not** shown to the user and does **not** drive targets/stops.
3. **No user-facing tag.** The Telegram label / card never says DAY vs SWINGABLE.
4. **Swing mechanics not implemented.** The swing exit (RSI 70–75 **or** prior-day-low break) and the **daily-trailing stop** (each day's low becomes the new stop, raised daily) don't exist.

Sub-spec **K** reserves a static `classification: day|swing|trend` registry field (the per-type baseline). This spec (L) is the **dynamic refinement** on top of that baseline, plus the swing target/stop behavior.

## Classification — read at fire time
**Inputs:** (1) **RSI** (daily) at the fire bar, (2) **which EMA the entry sits on** (is the entry at the 21 / 50 / 200 EMA?), (3) the alert type's **registry baseline** (Sub-spec K).

> Note: the daily MA stack in code is **8 / 21 / 50 / 100 / 200 EMA + 50 / 100 / 200 SMA**. "20" and "21" are the same idea — the code carries **21**, so the slow-EMA classification keys off the **21** (and 50 / 200). The literal `20` only appears inside the `ema_5_20_cross` swing signal, which is classified by its type regardless.

**The alert type already names the EMA** (`ma_bounce_long_v3_ema50`, `..._ema21`, `..._ema200`). So there's **no EMA-location math / tolerance to compute** — the existing EMA bounce alerts already work; we're just **re-tagging the slow-EMA ones as swing.** Classification keys off the **type** + RSI + the K baseline.

### SWINGABLE when:
- It's a **bounce/hold off a slow EMA — 21 / 50 / 100 / 200** (`ma_bounce_long_v3_ema21/50/100/200`, the matching SMAs), OR the type's K-baseline is `swing` (`rsi_oversold`, `ema_5_20_cross`, `weekly_rc`).
- **Target** = **RSI 70–75**, OR a **break of the prior-day low** (preferred exit).
- **Stop** = **prior-day-low trailing**: **day 1 = that morning's low**; **every day after = the prior day's low**, raised daily. Exit on a break below it.

### DAY TRADE when:
- A **core level entry** — `*_held` (PDL/PDH/PWH/PWL), `4h RC / RC-H`, `orl_held`, `gap_up_continuation`, `*_proximity`, and the **fast 8-EMA** bounce.
- **Frame:** intraday; **target** per Sub-spec A (nearest level → else RSI/EOD); **stop** = the morning low.

### RSI refinement — just a tag, the user decides
- An entry firing with **RSI already > 70** = **extended** → tag **DAY** (momentum chase, EOD/morning-low frame), but set `swing_eligible = true`: strong-momentum names run 70 → 80+ (SNDK has hit 83), so the **user can choose to swing it.** It's only a tag — no behavior change, the user makes the call.

### Output
A `trade_type` (`day` | `swing`) + a `swing_eligible` boolean, carried through payload → `AlertSignal` → the Telegram label / card ("DAY" / "SWINGABLE" / "DAY · swing-eligible").

## What must be added
1. **RSI (daily) in the Pine payload** — add to `build_payload_v2`; the swing payloads already compute it, just emit the number.
2. **A classifier** (backend) reading **alert type + RSI + K baseline** → `trade_type` + `swing_eligible`. (No EMA-location computation — the type already names the EMA. Extends the existing `_is_swing_alert`, adding the 21-EMA to the swing set.)
3. **Surface the tag** in the notifier label, the card, and EOD review.
4. **Swing lifecycle** — the **prior-day-low trailing stop** (day 1 = morning low; after = prior-day low, raised daily) + the RSI 70–75 exit (ties to Sub-spec A's `target_rsi`).

## Acceptance criteria
- **L-1:** Every tradeable alert carries `trade_type` (`day`|`swing`) + `swing_eligible`, set at fire time.
- **L-2:** Classification reads **alert type (which already names the EMA) + RSI + registry baseline** — no EMA-location math.
- **L-3:** A bounce/hold off a **21/50/100/200 EMA** (the `ma_bounce_*_ema21/50/100/200` types) classifies **SWING**, with target = **RSI 70–75 or a prior-day-low break**.
- **L-4:** Swing stop = a **prior-day-low trailing stop** — day 1 = the morning low; every day after = the prior day's low, raised daily.
- **L-5:** An entry firing at **RSI > 70** tags **DAY** but flags `swing_eligible` (the user can hold if momentum stays strong).
- **L-6:** The DAY/SWINGABLE tag is visible on the alert (Telegram + card + EOD).

## Out of scope
- The **static registry classification field** and taxonomy consistency — Sub-spec **K** owns the per-type baseline.
- **Target math per entry type** — Sub-spec **A** (this spec only routes which target *frame* applies).
- The day-trade target *types* themselves (level / RSI / EOD) — defined in Sub-spec A.

## Notes
RSI in the payload is the single missing input — everything else (EMA locations, type) is already available. Ties to [[feedback_level_anchored_targets]] (the target frames), Sub-spec A (targets), Sub-spec K (registry baseline), and the day-trade-is-core-levels / swing-is-EMA-bounce philosophy.
