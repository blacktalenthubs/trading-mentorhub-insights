# TV Alert v2 — Routing, NOTICE System, and New Patterns

**Status:** Draft — awaiting review
**Date:** 2026-05-05
**Owner:** mentorhub
**Builds on:** [`spec.md`](./spec.md) (Phase 5a TV ingest)

---

## Why this exists

After 2 days of live alert volume (2026-05-04, 2026-05-05) we have enough
real data to identify a clear gap: **alerts fire correctly but routing
doesn't match the user's actual trading style.** Today (2026-05-05) was
"an amazing day" — 24 alerts, 15 took, mostly winners. But 7 of 9 skipped
alerts were SHORTS that the user would never have taken regardless of
quality, because they don't single-name short.

The fix isn't more alert types — it's smarter delivery rules and a
NOTICE channel for context-only signals.

This spec also captures three pattern additions surfaced during the same
review: gap-and-go stop sizing, weekly levels, and conviction scoring on
sweep+reclaim setups.

> **User comments are welcome inline. Add `> COMMENT:` lines anywhere.**

---

## User trading style (validated 2026-05-05)

These rules are **inputs** to the spec, not proposals. They reflect the
user's existing process:

- **Long-bias.** Rarely shorts.
- **SPY-only shorts.** Never single-name shorts.
- **SPY short triggers**: `staged_pdh_rejection`, `staged_pdl_break`,
  `vwap_reject_short` — when SPY rejects PDH, breaks PDL, or loses VWAP.
- **SPY 8/21 daily EMAs gate equity longs.** SPY > 8/21 → long-bias mode;
  SPY < 8 → reduce; SPY < 21 → tactical only.
- **Wide stops are uninvestable** — but with a key exception:
  - Mid-session breakouts: stop must be ≤ 2% from entry, otherwise skip
  - **Gap-and-go context: stop is the first 5–10 min bar's low** inside
    the gap, not yesterday's swing. With this stop, gap-and-go trades
    almost always come in under 2% naturally — no special-case skip needed.
  - MU today: alert had stop $591 (5.5%) from $626 entry, but the gap-up
    first-10min low was ~$618 — proper stop = 1.4% risk. The detection
    needs to know "this is a gap-and-go" before computing the stop.
- **Stage 3/4 — informational, not a hard gate.**
  - User doesn't auto-skip longs in Stage 3/4 if a quality setup fires.
  - Stage label gives **context**: in Stage 3 (topping), be quicker to
    take T1 / smaller size. In Stage 4 (declining), only take strong
    sweep+reclaim setups.
  - Stage gating in this spec = include the stage in the Telegram message
    body so the user reads the regime alongside the entry. Don't suppress.

> COMMENT (user):

---

## Goals

1. Reduce skip volume by routing low-relevance alerts away from Telegram
2. Add a NOTICE channel for "FYI, watch this" alerts that don't ping urgently
3. Catch patterns currently mispriced or missed (gap-and-go, weekly levels)
4. Keep good alerts firing exactly as they do today (no behavior changes
   for ACTION-direction alerts that match the user's style)

## Non-goals

- Changing the actual *detection* logic of any working alert (v3 MA
  detection, staged PDH/PDL events, etc.)
- Adding more alert types beyond what's listed below
- Multi-user personalization — these rules are user-specific for now;
  generalizing to per-user prefs is a v3 concern

> COMMENT (user):

---

## Section A — Alert routing (the noise filter)

### A1. SPY 8/21 EMA long-bias gate

**Rule:** When SPY's daily close is above both the 8 and 21 EMAs:
- Non-SPY SHORT alerts → **suppressed** (no Telegram, no DB row)
- SPY SHORT alerts → only ACTION if rule is in the SPY short whitelist
  (see A2); otherwise NOTICE

When SPY closes below its daily 8 OR 21 EMA:
- All shorts (incl single-name) restored to ACTION routing
- Longs still allowed but the user manually reduces sizing

**Where the SPY 8/21 state comes from:**
- Cached snapshot of SPY's daily 8 EMA + 21 EMA values, refreshed every
  5 min via yfinance (or every webhook hit, cached in-memory)
- Compare current SPY price (or last close) to those values

> COMMENT (user):

---

### A2. SPY short whitelist

**Rule:** When `direction == "SHORT"` and `symbol == "SPY"`:

| `rule` value | Routing |
|--------------|---------|
| `staged_pdh_rejection` | **ACTION** |
| `staged_pdl_break` | **ACTION** |
| `vwap_reject_short` | **ACTION** |
| `vwap_loses_long` (price loses VWAP from above) | **ACTION** *(new — see notes)* |
| any other SHORT rule on SPY | NOTICE |

**SPY VWAP short — only `vwap_reject_short`** (after live test):

| Event | When | Status |
|-------|------|--------|
| `vwap_reject_short` | Price approaches VWAP from below, gets rejected back down — VWAP acting as resistance, `vwap_setup_bars` (default 3) of below-VWAP closes required first | Live in `staged_v2.pine` |
| ~~`vwap_lose_short`~~ | ~~Price was above VWAP during session, then breaks down through it~~ | **REMOVED 2026-05-05** |

`vwap_lose_short` was implemented and tested same-day. Live AAPL 1h chart
showed 7 LOSE VWAP labels in a single session because candle bodies
routinely brush VWAP in chop — single bar-close cross has no signal.
The `vwap_setup_bars` confirmation that makes `vwap_reject_short` clean
doesn't apply to a "lose" event (price was just above, no setup phase).
Removed from Pine, backend whitelist, and tests.

> COMMENT (user):

---

### A3. Stop-too-wide filter (sequenced after gap-and-go detection)

**Order of operations is critical:**
1. Pine detects the alert event (e.g., `staged_pdh_break`)
2. Pine checks gap-and-go context (see C1) — if true, computes stop =
   first 5–10 min bar low inside the gap; if false, computes stop =
   swing-low / ATR (existing logic)
3. **Backend webhook then applies the wide-stop filter on the *final*
   stop value:** if `(entry - stop) / entry > 0.02`, suppress the alert.

This means the wide-stop filter is the safety net catching cases where
*even with* gap-aware stops, the risk is still too wide (e.g., a stock
gapped huge and the first-bar low is itself 3% away). Almost never trips
on a healthy gap-and-go; only catches genuine outliers.

**Why this matters:** MU today fired with $591 stop because gap-and-go
detection didn't exist yet. Once C1 ships, the same alert would fire
with stop ~$618 (1.4% risk) and pass the filter. Without C1, this filter
alone would suppress MU — losing a +11% winner.

**Tunable:** threshold defaults to 2.0%; widens to e.g. 4% for crypto
symbols (per-symbol config map).

> COMMENT (user):

---

### A4. ~~Opposite-direction lockout~~ — DROPPED

**Status: removed from spec after user review (2026-05-05).**

**User's reasoning (correct):**
1. When SPY > 8/21, A1 already suppresses non-SPY shorts entirely. So
   the LONG alert that follows wouldn't have a SHORT to conflict with —
   nothing to lock out.
2. When SPY < 8/21, both directions are legitimate — and the alerts
   carry real information about what's happening at the level. A SHORT
   firing then a LONG firing 20 min later **is the story**: short
   failed, level held, buyers stepped in, reclaim worked. Suppressing
   the LONG would hide exactly the signal worth seeing.
3. The "noise" we were trying to suppress was a symptom of A1 not being
   in place. A1 fixes the actual problem.

**Implication:** A1 is the load-bearing change. Once shipped, the
META-style sequence we feared (short → long within minutes) becomes
*welcome* information rather than noise.

> COMMENT (user):

---

### A5. Stage label — context only, not a routing gate

**Revised after user review:** Stage doesn't gate alerts. It enriches them.

**Rule:** Include the symbol's current Minervini stage label in every
Telegram alert body. User reads stage alongside entry/stop/T1/T2 and
makes the sizing/take-T1-quick decision themselves.

**Telegram body example:**
```
🟢 LONG AAPL — staged_pdh_break
Entry $280.77 · Stop $280.45 · T1 $281.41 · T2 $281.73
Stage: 2 ADVANCING — full size OK
```

vs.

```
🟢 LONG GOOGL — staged_pdh_break
Entry $387.38 · Stop $385.20 · T1 $388.94 · T2 $389.50
Stage: 3 TOPPING — half size, take T1 quickly
```

**Why this works better than gating:**
- User keeps full discretion (Stage 3 setups can still be amazing)
- No risk of stage-label lag silently suppressing a good alert
- Signals the user can interpret faster ("topping → trim quick")

**Source:** The staged Pine already computes the stage label
(`stage` field is in the webhook payload). Telegram formatter just
needs to include it.

**Stage → guidance text mapping:**

| Stage | Guidance text |
|-------|---------------|
| 1 BASING | wait for breakout; sweeps only |
| 2 ADVANCING | full size OK, longs preferred |
| 3 TOPPING | half size, take T1 quickly |
| 4 DECLINING | only sweep+reclaim setups; small size |
| TRANSITIONING | half size, sweeps only |

> COMMENT (user):

---

## Section B — NOTICE system (the FYI channel)

### B1. Status of existing NOTICE infrastructure

| Channel | Where | State |
|---------|-------|-------|
| VWAP reclaim/reject NOTICE | `prior_day_levels_staged_v2.pine` | Built (commit `f4b9c13`), default `false`, **needs toggle on per chart** |
| MA proximity NOTICE | `daily_ma_bounce_v3.pine` (active branch) | **Uncommitted** — sitting in working tree, not deployed |
| EMA overhead resistance NOTICE | `analytics/intraday_rules.py` (rule engine) | Built (commit `983902a`), goes through `worker.py` poll loop, separate from TV/webhook path |

User reports zero NOTICE alerts received today. Either none of the toggles
are on, or NOTICE direction isn't being routed to Telegram. Needs an
audit before adding more.

> COMMENT (user):

---

### B2. NOTICE alerts to surface

What should fire as NOTICE (informational, 📍 prefix in Telegram):

| Event | Use case | Current state |
|-------|----------|---------------|
| **EMA/MA support proximity** | Equity holding within 0.3% above MA, never tested it (ORCL gap-up case) | Implemented in v3, not deployed |
| **EMA/MA overhead resistance** | Equity within 0.3% below MA, approaching from underneath | Partly in rule engine — confirm path |
| **PDH approach** | Equity within 0.3% of PDH | New — add to `staged_v2` |
| **PDL approach** | Equity within 0.3% of PDL | New — add to `staged_v2` |
| **VWAP reclaim/reject** | Existing | Toggle on per chart |
| **Stage transition** | Minervini stage label flips | New — out of scope for v1 of this spec |

> COMMENT (user):

---

### B3. NOTICE delivery format

**Rule:** Telegram messages with `direction == "NOTICE"` get a `📍` prefix
in the title:

```
📍 NOTICE — AAPL near EMA50 ($278.40)
Approached from above without testing. Stage 2.
```

vs. ACTION alerts:

```
🟢 LONG AAPL — staged_pdh_break
Entry $280.77 · Stop $280.45 · T1 $281.41 · T2 $281.73
```

Same Telegram chat, easy to scroll past. Not worth a second chat for the
volume we're talking about (~5-15 NOTICEs/day estimated).

> COMMENT (user):

---

## Section C — New patterns

### C1. Gap-and-go (Option B — modify `staged_pdh_break`)

**Pattern:** Stock gaps up at open above PDH, holds the gap, runs.

**Detection (added to existing `staged_pdh_break`):**

```
gap_up = today_open >= pdh * 1.005       # opened ≥0.5% above PDH
gap_held = bar_1_low > pdh                # first bar's low never wicked below PDH
```

**First-bar timeframe:** user said "5 to 10 mins low establish in the
gap." Use the **first 10-minute bar's low** as the stop anchor when gap
context is true. (10-min bar = better signal-to-noise than 5-min, faster
than 15-min, and the user's mental model.) The detection runs on close
of bar 1 of the trading session.

When `gap_up AND gap_held` is true at the time of a `staged_pdh_break`
alert: switch the stop calculation:

| Condition | Stop |
|-----------|------|
| Gap-and-go context | First-bar low (tight, ~1-2%) |
| Normal mid-session PDH break | Existing logic (swing low / ATR) |

**MU today validates:** alert fired at $626.59, gap context was true
(opened $620 well above PDH), first-bar low was ~$618. With gap-aware
stop, the alert would have been entry $626.59, stop $618 = 1.4% risk —
workable. Instead got stop $591 (5.5%) from swing-low logic.

**Decision criteria for the alert payload:** include `gap_context: true`
boolean in the v2 payload so backend knows which stop logic was applied,
and Telegram message text says "Gap-and-go context — tight stop" so user
recognizes the setup.

> COMMENT (user):

---

### C2. Weekly levels

**Add to `prior_day_levels_staged_v2.pine`** (consider renaming to
`prior_levels_staged_v2.pine` since it'd cover daily + weekly):

| Level | Pine | Use |
|-------|------|-----|
| **PWH** (Prior Week High) | `request.security(syminfo.tickerid, "W", high[1])` | Major resistance |
| **PWL** (Prior Week Low) | `request.security(syminfo.tickerid, "W", low[1])` | Major support |
| **Weekly 8 EMA** | `request.security(syminfo.tickerid, "W", ta.ema(close, 8)[1])` | HTF trend |
| **Weekly 21 EMA** | `request.security(syminfo.tickerid, "W", ta.ema(close, 21)[1])` | HTF trend, slower |

**Detection events** (mirror PDH/PDL taxonomy):

- `staged_pwh_break` — equity breaks above PWH on volume
- `staged_pwh_rejection` — equity rejects PWH from below
- `staged_pwl_reclaim` — equity reclaims PWL from below (sweep+reclaim)
- `staged_pwl_break` — equity loses PWL on volume
- `weekly_ema_bounce_8` / `weekly_ema_bounce_21` — defense of weekly EMA

**Routing:** weekly events default to ACTION when matching style
(longs in long-bias mode), NOTICE when counter-trend.

> COMMENT (user):

---

### C4. Target sizing fix (T1/T2 structural hierarchy)

**Problem:** `staged_v2.pine` uses pure R-multiples (`entry ± 2R / 3R`)
for `pdh_break` and `pdl_break` events. R scales with stop width, so:
- **Tight stops** (AAPL/SPY today, 0.11% R) → T1/T2 inside intraday
  noise. AAPL fired T1 at $281.41 but ran to $284 (3R blown past T2).
- **Wide stops** (MU gap-and-go, 5.5% R) → T1/T2 unreachable. T1 at
  $696 needs an 11% intraday move.

**Fix — structural-first hierarchy with ATH fallback:**

For each direction, try in order, use first match within 3% of entry:

| Priority | T1 source | Why |
|---|---|---|
| 1 | Next structural overhead/support: PWH/PWL, daily MA above/below, weekly MA above/below | Real prior trader behavior |
| 2 | Next round number ($5 increment for px > $200, $1 for $50-200, $0.50 < $50) | Psychological magnetism — works at ATH where no historical level exists |
| 3 | Entry ± 1× daily ATR (intraday-scaled) | Scales with symbol's typical volatility |
| 4 | Entry × 1.0075 (0.75% floor) | Last resort, never tighter than this |

**T2** = max(T1 + 0.5 × (T1 − entry), T1 × 1.005) — always ≥ 0.5%
beyond T1.

**Minimum target distance** = 0.5% (hard floor regardless of source).

**Today's validation:**

| Symbol | Old T1 | New T1 (hierarchy) | New T2 | Actual move |
|---|---|---|---|---|
| AAPL | $281.41 | **$283.77** (ATR) | **$285** (round) | $284 ✓ |
| SPY | $722.92 | **$725** (round) | **$727.28** (ATR) | $725 ✓ |
| META | $605.70 | **$605** (round) | **$610** (next round) | $605-606 ✓ |
| MU | $696.30 | **$640** (PWH) | **$650** | ~$651 ✓ |

All four would have been *reachable* exit points.

**Implementation note:** Pine helper function:

```pine
next_round_above(float price) =>
    incr = price > 200 ? 5.0 : (price > 50 ? 1.0 : 0.5)
    math.ceil(price / incr) * incr

t1_long_hierarchy(float e, float pwh, float ma_above, float atr_d) =>
    structural = na(pwh) ? ma_above : (na(ma_above) ? pwh : math.min(pwh, ma_above))
    not na(structural) and structural > e and (structural - e) / e <= 0.03 ? structural :
      max(next_round_above(e), e + atr_d, e * 1.0075, e * 1.005)
```

Symmetric for shorts (use `next_round_below`, flip MA/PWL logic).

> COMMENT (user):

---

### C3. Conviction scoring on sweep+reclaim

**Bug:** Today's META `staged_pdl_reclaim` alerts came tagged
`Conviction: LOW/25` because the *reclaim bar* had only 1.15× avg volume
— but the volume that mattered was on the *break bar* before the sweep.

**Fix:** when `rule == "staged_pdl_reclaim"` or `staged_pdh_rejection`,
read `volume_ratio` and `cvd_delta` from the SWEEP bar (the bar that
generated the SWEEP+ marker), not the reclaim bar.

**Implementation note:** requires the Pine to expose the sweep bar's
volume in the payload, or backend reaches into intraday data to find it.

> COMMENT (user):

---

## Section D — Operational

### D1. Sector brief reliability

**Already shipped 2026-05-04** (commit `cd55dd7`):
- `misfire_grace_time=600` so a Railway restart within 10 min of 8:45 ET
  doesn't drop the cron
- `STARTED` and `DONE sent=N/M` log markers for verification

**Verification path:** tomorrow 2026-05-06 at 8:45 ET ±10 min, run:
```
railway logs --service worker --filter "Sector brief"
```
Expected: `STARTED` then `DONE sent=N/M`. If absent, deeper investigation.

> COMMENT (user):

---

## Suggested ship order (revised after review)

1. **A1 + A2** (routing logic + SPY short whitelist) — biggest noise
   cut, one-file change in `tv_webhook.py`. Ships first.
2. **B1** (audit existing NOTICEs — toggle VWAP NOTICE on, commit
   proximity NOTICE, verify rule-engine NOTICE delivery path).
3. **B3** (📍 prefix on NOTICE messages) — Telegram template change.
4. **A5** (stage label in Telegram body) — small formatter change once
   we confirm the `stage` field is in the payload.
5. **C1** (gap-and-go detection + first-10min stop) — Pine change to
   `staged_v2`, requires re-paste on TV charts.
6. **C4** (target sizing hierarchy: structural → round → ATR → floor) —
   ship in same Pine re-paste as C1 since both edit staged_v2 stop/target
   math. **Note:** depends on C2 (weekly levels) for full PWH/PWL data;
   pre-C2 it falls back to round/ATR for ATH cases — still better than
   current pure-R-multiple math.
7. **A3** (wide-stop filter) — backend gate, **must ship after C1+C4**
   so gap-and-go and properly-sized alerts pass through before the
   filter sees them.
8. **C2** (weekly levels — PWH/PWL/weekly EMAs) — extends `staged_v2`
   Pine, requires re-paste. After this, C4's full hierarchy is live.
9. **B2** (PDH/PDL approach NOTICE, support proximity NOTICE) — net-new
   Pine code in `staged_v2` and v3.
10. **C3** (conviction scoring on sweep+reclaim) — Pine + payload work,
    polish item.

Note: A4 (opposite-direction lockout) was **dropped** during review —
A1 covers the case it was meant to solve.

## Open questions

1. **A1 SPY state source** — yfinance every 5 min cached, or query
   on every webhook? Latency/cost tradeoff.
2. **A5 stage source** — payload extension vs. TV data API?
3. **B2 NOTICE volume estimate** — need a few days of data after B1
   audit to size whether 📍 prefix is enough or we eventually need a
   second chat.
4. **C1 first-bar source** — 15m or 5m timeframe defines "first bar"?
5. **C2 weekly events** — combine with daily events in same Pine, or
   separate `weekly_levels.pine`?

> COMMENT (user):

---

## Out of scope (deferred)

- Multi-user personalization — these are user-specific rules; gener-
  alizing requires a per-user preferences table
- Backtesting framework for routing rules — qualitative review for now
- Removing rule-engine alerts in favor of pure TV — not yet, parallel
  paths give us a fallback
- Crypto-specific rules (ETH levels) — current rules apply, monitor

---

**End of spec.** Add `> COMMENT (user):` lines anywhere above; I'll fold
your edits in before we move to plan docs.
