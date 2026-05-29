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

**Rules where the LEVEL provides structural risk control** (tight stop
right under the level limits loss regardless of volume, so volume floor
relaxes — but doesn't disappear entirely):

- `staged_pdl_held` / `pwl_held` / `pml_held` — defense from above. Stop
  sits ~30 bps under the low. Loss bounded if it fails. **Soft floor:
  `>= 0.8` — even quiet bars can be tradeable risk-defined entries.**
- `staged_pdl_reclaim` / `pwl_reclaim` / `pml_reclaim` — broken-and-
  recovered. Different than held: the level just failed, so the reclaim
  needs buyers to step in with conviction. **Soft floor: `>= 1.0` (a
  notch higher than held — still well below the continuation 1.2×).**
- `staged_mtd_avwap_held` / `pm_avwap` / `p2m_avwap` — AVWAP is slower
  decay than PDL but still acts as structural support. Soft floor:
  `>= 1.0` (just kills the dead-bar fires).

**Held vs reclaim distinction (PDL family).** The held subfamily defends
the level from above (close[1] > level); the reclaim subfamily recovers
a broken level (close[1] ≤ level, close > level). These are structurally
different events with different volume requirements:

- Held: tighter natural stop (low ≤ level by definition). Lower volume
  floor (0.8×) acceptable.
- Reclaim: bar low is the stop (can be wider). Need real conviction
  (1.0×) to validate the recovery.

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

### Phase 2.6 — AVWAP-family upgrade (MTD / PM / P2M held)

Same conversation, new finding. Today's six `staged_mtd_avwap_held` /
`staged_pm_avwap_held` / `staged_p2m_avwap_held` fires:

| Sym | Vol | Sess slope | Daily action | Outcome |
|---|---|---|---|---|
| PLTR | 2.05× | +1.47% | +8% | ✅ worked |
| MSFT | 2.47× | +0.10% | +3.47% | ✅ worked |
| AMZN | 1.73× | +0.19% | +0.79% | ✅ held |
| **LITE** | **5.98×** | +0.70% | **−4.62%** | ❌ rejected hard |
| GOOGL | 1.97× | −0.43% | rejected at AVWAP | ❌ rejected |
| AAOI | 3.21× | −1.07% | −6.01% | ❌ sold off |

GOOGL and AAOI fail the session-VWAP-slope gate (the same gate we
added to the breakout rules). LITE is the interesting case — slope
positive, volume strongest of the day, **but still failed**. The 5.98×
volume bar wasn't buyers defending — it was distribution. LITE was
already in a daily downtrend; the AVWAP test was sellers dumping into
the level, not buyers holding it.

**Two additional gates for AVWAP-held rules** beyond the session-VWAP
confluence we added to breakouts:

1. **Higher-timeframe trend filter.** `close > daily_ema21`. Confirms
   the stock is still in a daily-trend posture aligned with the AVWAP
   defense thesis. LITE failed this; PLTR/MSFT/AMZN passed.
2. **Real bullish candle body.** `(close - open) >= (high - low) × 0.4
   AND close > open`. The "held" bar must be a meaty green candle, not
   a doji that technically closed above. LITE's distribution bar
   wouldn't have qualified.

```
staged_mtd_avwap_held (final form):
   close[1] > level                            ← prior bar above (existing)
   AND low <= level                            ← wicked to it (existing)
   AND close >= level                          ← closed back above (existing)
   AND (close - level)/level * 10000 >= 25     ← 25 bps buffer (P2d)
   AND close > vwap                            ← intraday context (P2.6)
   AND vwap_slope_pct >= +0.05                 ← session strength (P2.6)
   AND close > daily_ema21                     ← higher-timeframe trend (P2.6)
   AND (close - open) >= (high - low) * 0.4    ← real body (P2.6)
   AND close > open                            ← bullish candle (P2.6)
   AND volume_ratio >= 1.0                     ← soft floor — kills dead bars
   AND minutes_since_session_open >= 15        ← slope warmup (P2.6)
```

Test on today's data: PLTR / MSFT / AMZN pass all gates → fire. LITE
fails the daily-EMA21 trend gate → suppressed. GOOGL / AAOI fail the
slope gate → suppressed. **3/3 winners retained, 3/3 losers killed.**
Identical logic for `staged_pm_avwap_held` and `staged_p2m_avwap_held`.

The real-body filter (FR-015) is interesting because it's a structural
quality check independent of volume. Could extend it to breakout and
gap-up rules too — distribution bars don't print meaty green bodies.
Punted to Phase 3 measurement: see if real-body gate helps elsewhere
in the data.

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
| FR-013 | AVWAP-held rules (staged_mtd_avwap_held / pm_avwap / p2m_avwap) require: VWAP slope + close > VWAP + close > daily_ema21 + real bullish body (close>open AND body ≥ 40% of range). Today's test: 3/3 winners retained, 3/3 losers killed. | P2.6 |
| FR-014 | Slope-dependent rules require minutes_since_session_open ≥ 15 (slope-warmup guard). Prevents early-session false slope from 1-3 bars of data. | P2.6 |
| FR-015 | Real-body filter (close > open AND body ≥ 40% of range) on AVWAP-held rules. Punted to Phase 3 measurement: validate whether same gate helps on breakout / gap-up rules. | P2.6 |
| FR-016 | Per-rule VWAP slope threshold lives in an env var (default +0.05%, breakouts may use +0.10%). Single tuning knob for entire alert sensitivity. | P2 |
| FR-017 | MA bounce family (ma_bounce_long_v3_ema8/21/50/200, _sma) uses pullback continuation gates: slope ≥ +0.05%, close > vwap, volume ≥ 1.2×. Today: 2/2 retained (CRWV, COHR), 5/5 killed (GOOGL ×2, AVGO, AAOI, INTC). | P2 |
| FR-018 | PDL/PWL/PML held — inverted slope floor (slope ≥ −0.5%, NOT positive) + bullish bar (close > open) + close in upper half of range ((close − low)/(high − low) ≥ 0.5) + volume ≥ 0.8×. Slope filter catches freefall sessions (today's AAOI at −1.07%); body filter catches dead-cat bounces. | P2 |
| FR-019 | PDL/PWL/PML reclaim — tighter slope floor (slope ≥ −0.3%) + same body filter as FR-018 + volume ≥ 1.0× (notch higher than held — broken-level recovery needs real conviction). | P2 |

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

## Why VWAP slope is the master gate

Across every rule family in this spec, VWAP slope keeps reappearing as
the primary session-strength filter. This isn't coincidence — it's
because VWAP slope is the single signal that captures **direction +
participation + session context** in one number. Every bar of the
session contributes to VWAP, weighted by how much volume traded. The
slope tells you where the volume-weighted average price is moving —
which is where institutional money is flowing.

Other signals describe individual bars:
- **Volume** tells you "there was conviction on this bar" — but doesn't
  tell you direction. A 5× volume bar can be accumulation or
  distribution (LITE today: distribution at 5.98× vol).
- **Price** tells you "where it ended up on this bar" — but not whether
  the session is structurally trending or chopping.
- **MAs** lag — they confirm trends after the fact.

**VWAP slope is the only signal that combines volume and price into a
session-wide directional indicator.** Positive slope means each
incremental dollar bought was at higher prices than the session average
— institutions accumulating. Negative slope means the opposite —
distribution.

Today's data demonstrated the asymmetry:
- 6/6 setups with slope ≥ +0.10% delivered moves (META, ORCL, NVDA,
  PLTR, SHOP, HOOD, MSFT)
- 6/6 setups with slope ≤ −0.30% chopped or failed (BTCUSD, NFLX,
  MRVL, AAOI, GOOGL, V)
- LITE was the one positive-slope failure, killed by daily downtrend

### Threshold as master sensitivity knob

The single `vwap_slope_pct_threshold` parameter (default +0.05%)
becomes the entire alert system's sensitivity knob:

| Threshold | Effect on today's universe |
|---|---|
| +0.10% | Strictest — only catches obvious momentum (kills MSFT at +0.10% close call, AMZN at +0.19%) |
| **+0.05%** | **Default — balanced (the ~6 "everything aligned" symbols + close calls)** |
| +0.02% | Looser — surfaces borderline trends (CRWV, NKE, AMZN borderline trends) |
| 0.00% | Permissive — any non-negative slope qualifies (lets in marginal sessions) |

The architecture allows **per-rule slope thresholds** too. Breakouts
could demand +0.10% (only chase obvious momentum); pullbacks +0.05%
(can buy borderline trends if structure aligns); AVWAP-held +0.05%.
Each threshold an env var, so tuning happens without code deploys.

### Every rule has a slope gate — the threshold differs by trade thesis

Earlier draft of this section said "PDL family opts out of slope" — that
was wrong. Slope matters universally; it's just applied differently for
reversal rules vs continuation rules.

For PDL defense, slope at the moment of the test is usually negative
(the session has been bleeding to make a new low — that's WHY price is
testing PDL). But **how negative** is what determines whether buyers
will step in:

- Slope **mildly negative** (−0.10% to −0.50%) → session bleeding but not
  crashing. Buyers step in at known support. PDL defense tends to work.
- Slope **strongly negative** (< −0.50%) → active selloff. Even known
  support gets vaporized. PDL "defense" is just a brief stop on the way
  down. Today's AAOI at slope −1.07% is the textbook freefall — failed.
- Slope **positive** → unusual to be at PDL. Rare scenario.

The asymmetry is **inverted threshold**, not absent threshold:

| Rule thesis | Slope gate | Why |
|---|---|---|
| Continuation (pullback, breakout, MA bounce, AVWAP held, gap-up) | `slope ≥ +0.05%` | Need session to be trending up — you're riding momentum |
| Support defense from above (PDL/PWL/PML held) | `slope ≥ −0.50%` | Slope can be negative, just not freefall — buyers willing to step in |
| Support recovery (PDL/PWL/PML reclaim) | `slope ≥ −0.30%` | Tighter floor — session needs to be recovering, not still crashing |

Same signal, three thresholds. Tunable independently per family via
env var. The philosophical anchor is universal:

> **Every rule has a slope gate. Continuation rules require positive
> slope; reversal rules require non-freefall slope. The slope is the
> session truth-teller for both — the threshold tells you which trade
> thesis you're betting on.**

That uniform-but-asymmetric framework is the architectural heart of v2.

## Final architecture — rule families and what's built in

After v2 ships, the alert universe organizes into **six rule families**,
each engineered around a distinct structural event. **Every family uses
VWAP slope as the session truth-teller — the threshold differs by trade
thesis (positive for continuation, mild-negative for reversal).**

| Family | Rules | Slope gate | Volume | Close>VWAP | Other |
|---|---|---|---|---|---|
| **Breakout above resistance** | `staged_pdh_break`, `pwh_break`, `pmh_break` | `≥ +0.05%` | `≥ 2.0×` | required | level break + MA stack |
| **Continuation pullback** | `pullback_long` (VWAP-anchored), MA bounce family (FR-017) | `≥ +0.05%` | `≥ 1.2×` | required | VWAP test + 1.5% PDH headroom + MA stack |
| **Gap-and-go** | `gap_up_continuation_long` | `≥ +0.05%` | `≥ 1.5×` | required | open > PDH + MA stack |
| **AVWAP defense** | `staged_mtd_avwap_held`, `pm_avwap_held`, `p2m_avwap_held` | `≥ +0.05%` | `≥ 1.0×` | required | close > daily EMA21 + real body + 15-min warmup |
| **Former-resistance defense** | `staged_pdh_held`, `pwh_held`, `pmh_held` | `≥ +0.05%` | `≥ 1.2×` | required | close buffer ≥ 25 bps |
| **Support defense (reversal)** | `staged_pdl_held`, `pwl_held`, `pml_held` (FR-018) | `≥ −0.50%` | `≥ 0.8×` | NOT required | bullish bar + close in upper half + 25 bps buffer |
| **Support recovery (reversal)** | `staged_pdl_reclaim`, `pwl_reclaim`, `pml_reclaim` (FR-019) | `≥ −0.30%` | `≥ 1.0×` | NOT required | bullish bar + close in upper half |

**The slope-gate threshold differs by family**, not the presence of the
gate itself. Five families demand positive slope (continuation thesis).
Two families (PDL/PWL/PML held + reclaim) demand non-freefall slope
(reversal thesis — you're betting the level holds against a bleeding
session, not a crashing one).

**Volume is asymmetric** (P2.5 refined). Continuation rules need 1.2–2.0×.
PDL family soft floors at 0.8× (held) and 1.0× (reclaim) — tight
structural stops protect downside but volume still has to confirm buyers
exist.

**"Close > VWAP" is required only for continuation rules.** Reversal
rules deliberately fire while price is below VWAP — that's the whole
point of catching the session low.

**Real bullish body filter** (FR-015) applies to AVWAP held, PDL held,
PDL reclaim, and similar where doji / distribution bars could otherwise
trigger the close-above-level condition. Catches the LITE distribution
case and the PDL dead-cat bounces.

**No standalone VWAP-only rule.** Bare VWAP reclaim without level
confluence is too noisy on its own. Breakout-family rules already capture
high-quality VWAP-cross events via geometry (PDH break + above VWAP
almost always co-occur). The pullback rewrite catches VWAP-as-support
intraday continuation.

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
