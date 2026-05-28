# Alert Quality v2 — Phased Plan

**Date:** 2026-05-28
**Status:** Approved for implementation (phased)
**Owner:** User + Claude
**Supersedes parts of:** spec 58 (entry rules redesign — re-introduces volume-gated breakout family that 58 retired)

---

## Overview

Today's TradingView alert log fired **679 alerts across 54 symbols**. Manual review
plus the data analysis confirmed two failure modes that aren't structural — they're
fixable with focused per-rule changes:

1. **Pullback noise** — 311 of 679 alerts (46%) were `pullback_long`. The rule has
   no level test, no volume floor, no headroom check. Today, 15 of 29 pullback_long
   fires on the user's curated list had `volume_ratio < 1.2`. NFLX/AVGO/CRWD/ONDS
   fired pullback alerts on bars with volume as low as 0.20–0.45×. These are noise.
2. **Missed high-conviction setups** — SPY broke PDH $751.38 with visible volume,
   MSFT gapped through PDH $415.94 with massive volume, ARM broke PDH with 4.65×
   volume, ONDS gapped over PDH at the open. **None of these fired any alert.**
   The breakout family was retired in spec 58 ("don't chase breakouts") but the
   retirement threw out the high-volume breakouts along with the weak ones.

The fix isn't more rules — it's better gates on the rules we have, plus three
rules to catch the breakouts/gaps that currently have zero coverage. Volume is
the conviction signal we already collect on every alert; we just don't use it.

## Problem statement

A user opening today's Telegram alert stream sees ~679 messages and has to triage
by feel — there's no signal-to-noise hierarchy. The 6 "everything aligned"
symbols (META, NVDA, ORCL, PLTR, SHOP, HOOD) were the easy money but got the
same prominence as 15 sub-1× volume pullback fires on AVGO. Meanwhile the biggest
moves of the day (MSFT gap-through, SPY PDH break) generated zero alerts.

## Acceptance criteria

After v2 ships:

- A symbol-day like today's META (3 alerts, all 5×+ volume, ascending VWAP) is
  delivered with the same per-rule prominence as today.
- A symbol-day like today's AVGO (23 alerts, avg 0.98× volume) is reduced to
  ≤ 3 deliveries — the ones with above-average volume + structure.
- A breakout like SPY through PDH 751.38 fires a `staged_pdh_break_vol` alert
  at the moment of the break, NOT a `pullback_long` on the bar after.
- A gap-and-go like ONDS opening above PDH fires `gap_up_continuation_long`
  within the first 30 minutes of session.
- A confluence event like HOOD breaking VWAP + PDH on the same bar produces
  ONE delivery tagged "CONFLUENCE: VWAP+PDH", not two independent alerts.
- Total daily alert count drops ~50% from the noise filtering alone; the
  remaining ~340 alerts are higher signal-density.

## Out of scope (for v2)

- AI-based conviction scoring or ML triage — defer until v2 noise reduction is
  validated on 2+ weeks of data.
- VWAP-based exit alerts. Entry-side only for now.
- Cross-symbol confluence (e.g., "BTC + ETH both fired PWL held simultaneously").
- Short-side rules. Pine remains long-only per spec 58 FR-007.
- Catalog UI changes — new alert types appear with default-OFF; user opts in
  per type in existing Settings → Alert Types.

## Architecture — phased delivery

### Phase 1 — server-side only (deploys today, fully reversible via env)

No Pine changes. All work in `api/app/routers/tv_webhook.py`. Two changes:

**P1a. Volume floor on pullback_long.** When an incoming TV alert has
`rule="pullback_long"` and `volume_ratio < VOLUME_FLOOR_PULLBACK`
(default `1.2`, env-overridable), persist the row to the `alerts` table
with `suppressed_reason="low_volume_pullback"` and skip the notify dispatch.
The alert is still recorded for EOD review on the Trades page; it just
doesn't ping Telegram/APNs.

Expected impact on today's data: **~165 of 311 pullback_long fires** would
be suppressed.

**P1b. Confluence collapser.** Extend the existing open-line twin
suppression (currently scoped to `open_*` family vs PDH/PDL twins) into a
general N-rule collapser:

- Bucket incoming alerts by `(symbol, floor(fired_at_minute / 10) * 10)`.
- When 2+ alerts land in the same bucket for the same symbol, pick the
  one with the highest base conviction (rule precedence: `*_break_vol` >
  `*_held` > `*_reclaim` > `pullback_long` > NOTICE), promote its
  Telegram message to include a "CONFLUENCE: A+B+C" tag with all rule
  names, and mark the suppressed rules with
  `suppressed_reason="confluence_collapsed_into:<primary_id>"`.

Expected impact: cleans up the HOOD-style "break VWAP + PDH on one
candle" double-fire problem; consolidates today's clusters where 3-4
rules fire on the same opening 10m bar.

### Phase 2 — Pine update (deploys after Phase 1 validates ~1 week)

Single coordinated push across `pine_scripts/active/ma_ema_daily.pine`
(pullback) and `pine_scripts/active/levels_day_vwap.pine` (staged + new
break/gap rules):

**P2a. VWAP-anchored pullback rewrite.** Replace the existing pullback
trigger:

```
pullback_long (NEW):
   uptrend_pass                                ← MA stack bullish (unchanged)
   AND low <= vwap                             ← bar's wick tested VWAP
   AND close > vwap                            ← closed back above
   AND vwap_slope_pct >= +0.05                 ← session is climbing
   AND volume_ratio >= 1.2                     ← real participation
   AND (pdh - close) / close >= 0.015          ← ≥1.5% headroom to PDH
```

**Rationale per gate:**
- VWAP anchor — replaces the level-agnostic "2 down bars + green resume"
  with a structural test. "Held VWAP from above" is concrete.
- Slope ≥ +0.05% — kills counter-trend buys on sessions where VWAP is
  bleeding down (today: BTCUSD, NFLX, MRVL, AAOI all `↓` bias).
- Volume ≥ 1.2× — proves participation on the hold.
- Headroom ≥ 1.5% — RKLB today fired pullback at $149.62 with PDH $151
  (0.92% headroom). R:R was 0.26 before slippage. Gate kills this trade.

**Payload addition:** `build_v3_payload` must emit `vwap`,
`vwap_slope_pct`, `above_vwap`, `stage`. Currently absent (per CSV audit,
0/311 pullback_long alerts today had these fields), which is why the
quality lens worked on staged_* but not on pullback_*. Two lines in the
payload builder. After this, EVERY alert has consistent context.

**P2b. PDH / PWH / PMH break with built-in VWAP + slope confluence.**
Three new alert types re-introducing the rule family spec 58 retired,
**with confluence baked INTO the rule** — not bolted on as separate
alerts that get collapsed server-side. The geometry makes this natural:
when PDH is overhead resistance during a session, intraday VWAP almost
always sits below PDH, so a bar that closes above PDH is necessarily
also above VWAP (or crossing it on the same bar). The "PDH break
without VWAP confirmation" scenario is rare and usually weak — exactly
the failure mode spec 58 was right to worry about.

```
staged_pdh_break (combined):
   close > pdh                    ← broke the level
   AND close[1] <= pdh            ← just broke this bar (no chasing)
   AND close > vwap               ← above intraday VWAP (confluence)
   AND vwap_slope_pct >= +0.05    ← session is climbing, not chopping
   AND volume_ratio >= 2.0        ← real money pushed through
   AND uptrend_pass               ← daily MA stack aligned
```

Identical logic for `staged_pwh_break` (weekly high) and
`staged_pmh_break` (monthly high). **Five orthogonal confirmations on
one bar** — level + intraday context + slope strength + participation +
daily trend. If any fails, no fire. When it fires, every layer of
structure is aligned. Catalog default-disabled; user opts in.

Today this would have caught MSFT through PDH $415.94, ARM through its
PDH on 4.65× vol, ONDS over PDH $11.06 on the open bar, and SPY through
$751.38 — every textbook breakout we missed because the rule didn't
exist. Today's flat-VWAP names (SPY slope −0.04%, SMH −0.11%, SPX
−0.06%) get filtered automatically by the slope gate.

Entry = current close. Stop = bar low − ATR buffer. T1 = next overhead
level (closest of PWH/PMH/EMA above). T2 = next-next.

**Design note — no standalone `vwap_reclaim_vol`:** earlier draft of
this spec proposed a separate VWAP reclaim rule. Dropped because the
confluence-into-breakout design above already captures the high-quality
VWAP-cross-with-volume events. A bare VWAP reclaim (without level
confluence) is too noisy on its own — VWAP gets crossed many times in a
session. The pullback_long rewrite (P2a, VWAP-anchored) covers the
"price tested VWAP and held" case for intraday continuation.

**P2c. Gap-up continuation.** New alert type for the ONDS pattern —
opened above PDH and continued, never retests so neither `_held` nor
`_break` fire:

```
gap_up_continuation_long:
   today_open > pdh                ← gapped over resistance at the bell
   AND high > today_open           ← made a higher high on this bar
   AND close > pdh                 ← still above PDH
   AND close > vwap                ← above intraday VWAP (confluence)
   AND vwap_slope_pct >= +0.05     ← session direction confirmed
   AND volume_ratio >= 1.5
   AND uptrend_pass
```

**Stop placement** (user direction 2026-05-28, applies to this rule
specifically): `stop = bar1_low - atr_buffer`, where `bar1_low` is the
lowest low of the first 15 minutes of session. NOT the alert bar's low.
The thesis is "gap-and-go through resistance"; the invalidation is
"price falls back to / below the opening range." A tighter alert-bar
stop would trade out on normal post-gap consolidation.

**P2d. Bare-touch + near-miss filter on `_held` rules.** Two-sided
adjustment to `staged_pdh_held`, `staged_pwh_held`, `staged_pmh_held`,
`staged_pdl_held`, `staged_pwl_held`, `staged_pml_held`:

```
Add:    AND (close - level) / level * 10000 >= 25       ← 25 bps close buffer
Change: low <= level   →   low <= level * 1.003          ← 30 bps near-miss
```

**Rationale:**
- Today's NFLX `staged_pwl_held` fired 3× at PWL $86.33 with close
  $86.33–$86.34 (close buffer 1.2–8 bps). MSFT `staged_pwl_held` close
  buffer 3.2 bps. These are price oscillating ON the level, not
  defending it. 25 bps minimum eliminates this entire class.
- Today's CELH approached PDL $30.77 with a low of ~$30.85 (about 25 bps
  ABOVE PDL). Strict `low <= pdl` missed it. The bounce to $33+ on the
  next bar was textbook. 30 bps tolerance catches it.

Net effect: rule becomes both tighter (on the close side) AND looser (on
the approach side). Today: eliminates ~18 bare-touch fires we measured,
catches an estimated 5-8 CELH-style near-misses we missed.

### Phase 2.5 — asymmetric volume gates by rule family

A universal volume floor is too blunt. **The same volume_ratio means
different things depending on what's above vs below the entry level.**
The structural risk of the rule should determine whether volume gating
applies, and at what threshold.

**Rules where volume IS the conviction proof** (no built-in risk floor —
volume must do the work):
- `pullback_long` — no specific structural stop until VWAP anchor is
  added; the entry is on momentum. Floor: `volume_ratio >= 1.2`.
- `staged_pdh_break` / `pwh` / `pmh` — breaking through resistance needs
  real participation to push over institutional supply. Floor: `>= 2.0`.
- `staged_pdh_held` / `pwh` / `pmh` — defending a former-resistance now
  acting as support; needs buyers showing up to hold the level. Floor:
  `>= 1.2`.
- `gap_up_continuation_long` — momentum-dependent; no level beneath the
  entry until the opening-range low. Floor: `>= 1.5`.

**Rules where the LEVEL IS the risk control** (volume floor unnecessary
— a tight stop right under the level limits loss regardless):
- `staged_pdl_held` / `pwl` / `pml` — stop sits ~30 bps under the low.
  If it fails, loss is small. Cheap to be wrong. Even quiet 0.4× volume
  fires are risk-defined trades. **No volume floor.**
- `staged_pdl_reclaim` / `pwl` / `pml` — same — stop = the prior wick
  low, tight by definition. **No volume floor.**
- `staged_mtd_avwap_held` / `pm_avwap` / `p2m_avwap` — AVWAP is slower
  decay than PDL but still acts as structural support. Soft floor:
  `>= 1.0` (just kills the dead-bar fires).

**Worked example from today.** ETH `staged_pdl_held` fired at vol
**0.38×** ($2,012.50 close, stop $2,011.30). Quiet bar — but if PDL
held, entry was 1× R with ~30 bps risk. If it broke, you'd be out for
~30 bps. That's a clean risk-defined trade even on low volume. By
contrast, AVGO `pullback_long` at vol **0.60×** ($423.50) had no defined
level, no defined stop reasoning beyond ATR, and no structural floor to
catch a bad outcome — that's just momentum noise on a quiet bar.

The asymmetric design captures this distinction directly. Volume gates
get applied per-rule-family, not as a global filter.

The close-buffer requirement (≥ 25 bps above level on `_held` rules,
P2d) STILL applies to all `_held` rules including PDL-side, because
that's a structural quality check (did the level actually hold) not a
volume check.

### Phase 3 — measurement (post-deploy, ongoing)

The Trades page redesign (shipped 2026-05-28) already gives us the
per-alert-type R-multiple feedback loop. Two weeks after P2 ships:

- Pull `/alerts/by-alert-type-performance` for the new rules and compare
  win rate vs the rules they replace
- Volume-gate thresholds can be tuned from data — if `staged_pdh_break_vol`
  at 2.0× misses too many real moves, drop to 1.7×. If pullback at 1.2× is
  still noisy, raise to 1.5×.
- Spec gets updated with the validated thresholds.

## Functional requirements

| ID | Requirement | Phase |
|---|---|---|
| FR-001 | pullback_long fires with vol_ratio < 1.2 must not deliver to Telegram/APNs; still persisted with suppressed_reason | P1 |
| FR-002 | 2+ alerts on same (symbol, 10-min bucket) collapse into one delivery with combined tag | P1 |
| FR-003 | Suppressed alerts must still appear on Trades page for EOD review | P1 |
| FR-004 | pullback_long Pine rewrite anchors to session VWAP and requires +0.05% slope, ≥1.2× volume, ≥1.5% PDH headroom | P2 |
| FR-005 | pullback_long payload includes vwap, vwap_slope_pct, above_vwap, stage | P2 |
| FR-006 | New: staged_pdh_break / pwh_break / pmh_break with built-in confluence — close > level, close > vwap, slope ≥ +0.05%, vol ≥ 2.0×, uptrend_pass | P2 |
| FR-007 | New: gap_up_continuation_long — open > PDH, close > PDH AND VWAP, slope ≥ +0.05%, vol ≥ 1.5×; stop = first-15m low | P2 |
| FR-008 | `_held` rules require close ≥ 25 bps above level | P2 |
| FR-009 | `_held` rules accept low within 30 bps of level (loosen strict touch) | P2 |
| FR-010 | All new alert types default-disabled in alert_type_config; user opts in per type | P2 |
| FR-011 | Volume gates asymmetric by rule family: resistance-side & no-level rules require volume; support-side level rules (PDL/PWL/PML) have no floor — level IS the risk | P2.5 |
| FR-012 | No standalone vwap_reclaim_vol rule. VWAP confluence is baked into staged_pdh_break / pwh / pmh and gap_up_continuation_long. Bare VWAP cross is too noisy to be its own trigger. | (design) |

## Non-functional requirements

- **NFR-001** No Pine change shall be deployed before Phase 1 noise reduction
  has run for ≥3 trading days without regressions.
- **NFR-002** Every gate threshold (`1.2`, `2.0`, `1.5%`, `25 bps`, `30 bps`,
  `+0.05%`) lives behind an env var or input field so it can be tuned without
  redeploying.
- **NFR-003** Suppressed alerts retain full payload + `suppressed_reason` for
  later analysis; nothing is silently dropped.
- **NFR-004** Every new alert type is added to `OBSOLETE_ALERT_TYPES` cleanup
  removed (i.e., `staged_pdh_break*` etc. come OFF the obsolete list when
  added to catalog, otherwise startup will delete them).

## Open questions

1. **Confluence collapsing — bucket size.** 10-minute bucket matches the Pine
   bar interval. Could go to 5-minute to be more precise, or 15-minute to be
   more permissive. Defaulting to 10 since that's the Pine native bar.
2. **Gap-up continuation — re-fire policy.** ONDS today might continue to make
   higher highs across multiple subsequent bars. Should the rule fire once
   per session (daily cap = 1) or each time it makes a new HH while still
   gapped above PDH? Recommendation: once per session per symbol — let the
   pullback rule catch the subsequent entries.
3. **Volume threshold for breakouts.** Spec 58's deepest concern was weak
   breakouts failing. Today's data (META 10.53×, ORCL 4.61×) suggests 2.0× is
   conservative — could be 1.7×. Defaulting to 2.0× for the first 2 weeks,
   re-evaluate on Trades-page R-multiple data.

## Final architecture — rule families and what's built in

After v2 ships, the alert universe shrinks to **four orthogonal rule
families**, each engineered around a distinct structural event with the
right confluence and volume gating baked in:

| Family | Rules | What's built in |
|---|---|---|
| **Breakout above resistance** | `staged_pdh_break`, `staged_pwh_break`, `staged_pmh_break` | level break + close > VWAP + VWAP slope ≥ +0.05% + volume ≥ 2.0 + MA stack |
| **Defense of support** | `staged_pdl_held`, `pwl_held`, `pml_held`, `staged_pdl_reclaim`, `pwl_reclaim`, `pml_reclaim` | level test (low ≤ level × 1.003) + close buffer ≥ 25 bps + MA stack — **no volume floor** (level IS the risk) |
| **Pullback continuation** | `pullback_long` (VWAP-anchored rewrite) | VWAP test (low ≤ vwap) + close > VWAP + slope ≥ +0.05% + volume ≥ 1.2 + PDH headroom ≥ 1.5% + MA stack |
| **Gap-and-go (new)** | `gap_up_continuation_long` | open > PDH + close > PDH + close > VWAP + slope ≥ +0.05% + volume ≥ 1.5 + MA stack |

**VWAP slope and "close > VWAP" appear in 3 of 4 families** because they
ARE the session-strength check. The 4th family (level defense) substitutes
structural risk (tight stop under level) for the slope gate.

**Volume gating is asymmetric on purpose** (P2.5). Resistance-side and
no-level rules need volume to confirm conviction. Support-side rules
don't — the structural stop is your protection regardless of how loud
the bar was.

**No standalone VWAP-only rule.** Bare VWAP reclaim without level
confluence is too noisy on its own. The breakout-family rules above
already capture every high-quality VWAP-cross event by virtue of the
geometry (PDH break + above VWAP almost always co-occur). The pullback
rewrite catches the VWAP-as-support intraday continuation.

## What's NOT in this spec

- Anything AI-driven. v2 is pure deterministic gates on existing data.
- Position-sizing or auto-execution. Entry alerts only.
- Cross-timeframe confirmation (e.g., "daily MA stack bullish AND 10m fired").
  Existing `uptrend_pass` gate handles the daily check; we don't add a
  weekly check.

## Data evidence (today, 2026-05-28)

- 679 total alerts across 54 symbols
- 311 (46%) were `pullback_long` — the top-volume table showed avg vol_ratio
  ranged from 0.58× (SMH) to 5.01× (META). 30%+ of alerts fired with
  vol_ratio < 1.0 (BELOW average).
- 18 `_held` alerts fired as bare touches (penetration <15% of bar range AND
  close <50 bps above level). NFLX, BTCUSD, MSFT lead this list.
- Zero `_break` alerts of any kind fired today (rule family retired in spec 58)
  even though MSFT, ARM, ONDS, and SPY each had textbook PDH breaks with
  visible volume.
- 6 symbols (META, ORCL, NVDA, PLTR, SHOP, HOOD) showed the "everything
  aligned" pattern: high max volume + ascending VWAP + price predominantly
  above VWAP. These were today's clean money.
