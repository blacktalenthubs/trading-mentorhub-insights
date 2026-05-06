# Plan — Pine batch (C1 + C4 + C2 + `vwap_lose_short`)

**Spec:** [`specs/41-tv-trading-system/v2-routing-notices-patterns.md`](../specs/41-tv-trading-system/v2-routing-notices-patterns.md)
**Spec items covered:** C1 (gap-and-go), C4 (target hierarchy), C2 (weekly levels), part of A2 (`vwap_lose_short` event).
**Defer to follow-up:** B2 (PDH/PDL approach NOTICE), C3 (conviction on sweep+reclaim) — both nice-to-haves; ship after this batch is validated.

## Why one batch

User wants Pine ready for tomorrow's session — single TV re-paste tonight is much less friction than three. Files modified:

| File | Spec items | Re-paste required |
|------|-----------|-------------------|
| `pine_scripts/active/prior_day_levels_staged_v2.pine` | C1, C2, C4, vwap_lose_short | Yes — re-paste into TV indicator slot |
| `pine_scripts/active/daily_ma_bounce_v3.pine` | (already modified earlier in session — proximity NOTICE) | Yes — re-paste |

## What changes in `staged_v2.pine`

### 1. Weekly levels (C2)

Add request.security for prior week high/low + weekly EMAs:

```pine
[pwh, pwl] = request.security(syminfo.tickerid, "W", [high[1], low[1]],
                              lookahead = barmerge.lookahead_on)
wema8  = request.security(syminfo.tickerid, "W", ta.ema(close, 8)[1],
                          lookahead = barmerge.lookahead_on)
wema21 = request.security(syminfo.tickerid, "W", ta.ema(close, 21)[1],
                          lookahead = barmerge.lookahead_on)
```

Plot PWH/PWL in lighter colors than PDH/PDL (visual hierarchy: thinner /
dashed). Weekly EMAs as thin lines.

Detection events (mirror PDH/PDL):
- `pwh_break`, `pwh_rejection`, `pwl_break`, `pwl_reclaim` — all on close

### 2. Target hierarchy (C4)

Add helper functions:

```pine
next_round_above(float p) =>
    incr = p > 200 ? 5.0 : (p > 50 ? 1.0 : 0.5)
    math.ceil(p / incr) * incr

next_round_below(float p) =>
    incr = p > 200 ? 5.0 : (p > 50 ? 1.0 : 0.5)
    math.floor(p / incr) * incr

// Returns nearest valid level above entry within 3% (na if none)
nearest_above(float e, float l1, float l2) =>
    a1 = not na(l1) and l1 > e and (l1 - e) / e <= 0.03 ? l1 : 9e15
    a2 = not na(l2) and l2 > e and (l2 - e) / e <= 0.03 ? l2 : 9e15
    r  = math.min(a1, a2)
    r == 9e15 ? na : r

// T1 hierarchy: structural overhead → round → ATR/2 → 0.75% floor
t1_long_hier(float e, float l1, float l2, float atr_d) =>
    s = nearest_above(e, l1, l2)
    not na(s) ? s :
      (next_round_above(e) > e * 1.005 ? next_round_above(e) :
       (e + atr_d * 0.5 > e * 1.005 ? e + atr_d * 0.5 :
        e * 1.0075))

// T2: 0.5x extension beyond T1, minimum 0.5% beyond T1
t2_extend_long(float e, float t1) =>
    math.max(t1 + (t1 - e) * 0.5, t1 * 1.005)
```

Symmetric `nearest_below`, `t1_short_hier`, `t2_extend_short`.

Per-event T1/T2 selection:

| Event | LONG t1 candidates | SHORT t1 candidates |
|-------|--------------------|---------------------|
| `staged_pdh_break` | PWH, then round/ATR/floor | n/a |
| `staged_pdh_rejection` | n/a | VWAP, PWL |
| `staged_pdl_break` | n/a | PWL, then round/ATR/floor |
| `staged_pdl_reclaim` | PDH, then PWH | n/a |
| `staged_pwh_break` | round above PWH (no level above) | n/a |
| `staged_pwh_rejection` | n/a | PDH (or VWAP if below entry) |
| `staged_pwl_reclaim` | PDL, then PDH | n/a |
| `staged_pwl_break` | n/a | round below PWL |

### 3. Gap-and-go (C1)

Track today's open and first 10-min bar low at session start:

```pine
// "First bar" definition: 10 min from session open
session_open = ta.change(time("D")) != 0  // true on first bar of trading day
var float today_open = na
var float bar1_low   = na
var int   session_first_bar = na

if session_open
    today_open := open
    bar1_low := low
    session_first_bar := bar_index
else if not na(session_first_bar) and (time - time[bar_index - session_first_bar]) <= 10 * 60 * 1000
    // Still within first 10 minutes — track running low
    bar1_low := math.min(bar1_low, low)

// Gap context — at any time during session
gap_up      = not na(today_open) and not na(pdh) and today_open >= pdh * 1.005
gap_held    = not na(bar1_low) and not na(pdh) and bar1_low > pdh
gap_context = gap_up and gap_held
```

In `staged_pdh_break` alert:

```pine
if pdh_break
    e   = close
    s_default = pdh - atr_buffer
    s   = gap_context and not na(bar1_low) ? bar1_low - atr_buffer * 0.5 : s_default
    rsk = e - s
    t1  = t1_long_hier(e, pwh, na, atr14_d)
    t2  = t2_extend_long(e, t1)
    alert(build_payload_v2("staged_pdh_break", "BUY", e, s, t1, t2,
                           gap_context, volume_ratio, cvd_slope_n, bearish_div),
          alert.freq_once_per_bar_close)
```

`gap_context` is added to payload (extra positional arg in
`build_payload_v2`); backend reads it and adds "Gap-and-go context — tight
stop" line to Telegram body.

### 4. `vwap_lose_short` event (A2 dependency)

Backend already whitelists this rule. Pine emission:

```pine
vwap_lose_short = not na(vwap_v) and not na(close[1]) \
                   and close[1] >= vwap_v and close < vwap_v and close < open
if fire_vwap_alerts and vwap_lose_short
    e = close
    s = math.max(high, high[1]) + atr_buffer
    rsk = s - e
    t1 = t1_short_hier(e, pdl, pwl, atr14_d)
    t2 = t2_extend_short(e, t1)
    alert(build_payload_v2("vwap_lose_short", "NOTICE", e, s, t1, t2,
                           false, volume_ratio, cvd_slope_n, bullish_div),
          alert.freq_once_per_bar_close)
```

Direction defaults to NOTICE per the existing VWAP alert pattern; backend
A2 whitelist promotes it to ACTION when symbol is SPY.

**Note**: this fires only when `fire_vwap_alerts=true` is toggled on the chart. User must enable on SPY chart specifically.

### 5. Payload builder gets `gap_context`

```pine
build_payload_v2(rule, direction,
                 entry_p, stop_p, t1_p, t2_p,
                 gap_ctx_v,         // NEW
                 vr, cvd_d, cvd_div) =>
    '...existing fields...'
      + '","gap_context":"' + (gap_ctx_v ? "true" : "false")
      + '...rest...'
```

Backend `payload_to_alert_signal` adapter doesn't need a code change —
extra fields are ignored. Telegram template change comes in a separate
follow-up to actually use the field.

## What changes in `daily_ma_bounce_v3.pine`

Already modified earlier this session — has proximity NOTICE for all
8 MAs. Just needs to be **committed** so it's part of the same
"re-paste tomorrow morning" batch.

No further code changes tonight on v3.

## Test plan (Pine — limited automation)

Pine has no offline compiler, so verification is:

1. **Syntax read-through** — manual diff review against Pine v5 docs;
   look for `na` handling, `var` declarations, function arity.
2. **Backend test impact** — re-run `pytest tests/test_tv_webhook.py`.
   Should still pass (62/62) since payload changes are additive.
3. **TV manual paste test** — user pastes into a non-prod chart slot
   first, confirms no compile errors, before replacing prod indicator.

## Risk + rollback

- **Pine compile error risk:** medium. New helpers + var tracking are
  the most common failure mode. Mitigation: keep new code in clearly
  separated sections so compile error message points at known territory.
- **Behavior risk:** higher than backend changes. New T1/T2 math touches
  existing alerts. If something's wrong with the hierarchy on Day 1,
  every alert tomorrow could mis-target.
- **Rollback:** revert `staged_v2.pine` to today's HEAD via `git revert`,
  re-paste the old version into TV. Effective in 5 min.

## Validation tomorrow morning

Pre-market checklist:
1. Paste new `staged_v2.pine` into TV → verify no compile errors
2. Paste new `daily_ma_bounce_v3.pine` (proximity NOTICE) → verify
3. Spot-check chart visuals: PWH/PWL lines visible, weekly EMAs visible
4. First alert: confirm payload includes `gap_context` field
5. First gap-and-go (if any): confirm tight stop + structural T1
6. End of day: review CSV — did target hierarchy give reachable T1s?

## Out of scope tonight (deferred)

- **B2 PDH/PDL approach NOTICE** — small addition, can ship later this week
- **C3 conviction on sweep+reclaim** — needs Pine state to track break-bar
  volume; safer to ship after C1/C2/C4 stable
- **Renaming `staged_v2.pine` → `prior_levels_staged_v2.pine`** — nice
  to have but breaks existing chart references; defer
