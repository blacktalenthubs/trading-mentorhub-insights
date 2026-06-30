# Spec 67 — Alert Dedup by Price + Time

**One-pager · 2026-06-29 · status: proposed**

## Overview
Collapse repeat alerts so a user gets **one actionable signal per setup**, not the same
idea re-fired across timeframes as price drifts. Dedup on the two things that actually
matter — **price (entry) and time** — and scope it so the intraday flood is thinned while
weekly/monthly **levels always fire**.

## Problem
On a normal day (2026-06-29, 1 account), the Pine fired **276 day-trade longs**. A single
name re-alerts every few minutes around its levels:
- **ALAB fired 3 longs at 9:35:00–9:35:05** at 407.09 / 396.45 / 396.27 — same instant, same
  price, three cards.
- **AMZN, ANET, ONTO** each fired 6–7 times *chasing higher* as they ran.
- **UCTT** fired 5× in 2h (high break → reclaim → low reclaim → weekly), all one bullish idea.

There is no per-symbol cooldown today — only a same-*bar* collapse. So the feed is unreadable
and the real entry is buried. Swing/long-term do **not** have this problem: 43 swing names →
only 10 fired >1; 16 long-term names → only 3 fired >1 (the Pine already latches them per
week/month). `monthly_rc` fired **once all day** (UPST) — proof a level event is rare and must
never be suppressed.

Explicitly **not** the problem here: the SPY gate (separate; a delivery control) and the A/B/C
grade (not trusted, ignored for dedup).

## Acceptance criteria
1. Day-trade longs on a name collapse to the **earliest, best-priced** entry plus genuine
   lower re-entries — target **≥ 60% fewer** day-trade fires (today: 276 → ~99).
2. The kept alert is always the **best entry seen** (lowest for a long), never a chase.
3. **Every** weekly/monthly/level alert (`weekly_rc`, `monthly_rc`, `cml_*`, `pml_*`,
   `weekly_10w/30w_*`, `staged_pwl/pml_held`, `monthly_box`, `mobo_rch`) still fires — 0
   suppressed by this feature.
4. Suppressed alerts are **recorded** (with reason), so the feed can show "+N collapsed".

## The solution — two layers, scoped by style
`style_for(alert_type)` decides treatment.

### A. Day-trade (`style == day_trade`) — entry-ratchet + 30-min cooldown
Per **symbol × direction × SIDE × session**, track `last_fire_time` and `best_entry`.
A candidate fires only if **both**:
1. **Time** — ≥ **30 min** since the last fired alert on this symbol+direction+side,
   else suppress `dedup_cooldown`.
2. **Price** — entry strictly **better** than `best_entry` on its side, else suppress
   `dedup_chase`.

**SIDE split (critical — INTC 2026-06-29):** dip-buys and breakouts anchor SEPARATELY.
`low` side = support reclaims / dip-buys (prior-LOW reclaim, MA bounce, *_held) → better =
**lower**. `high` side = breakouts / high reclaims (prior-HIGH break `*_hrec`, gap-up,
`reclaim_long`) → better = **higher** (a new breakout high). Without this, a morning dip
ratchets the anchor down (INTC EMA @122) and then EATS the afternoon PDH break @131.77 (the
A-grade winner that ran to 141) as a "chase". With it, the dip AND the breakout both fire.

On fire: update `last_fire_time` and ratchet `best_entry`. State is **derived from today's
already-persisted alerts** (no in-memory cache → survives restarts).

*Result on real data:* ALAB 3@9:35 → 1; UCTT 5 → 2 (119.77 + the lower 116.34 reclaim 54m
later); chase-ups (AMZN/ONTO) → 1. **276 → 99 (−64%).**

### B. Swing + Long-term — levels always fire, merge only same-price duplicates
- **Never** apply ratchet/cooldown to level types — they always fire (criterion 3).
- **Price-zone merge:** if a swing/long-term alert lands within **±0.5%** of another
  already-fired swing/long-term alert on the same symbol this session, merge into **one**
  card — keep the **level** alert as primary (`weekly_rc`/`PWL`), attach the other as
  confluence. Folds the real duplicates: WULF `weekly_rc 24.44` + `EMA50 24.41`; IREN
  `EMA200 45.18` + `PWL 45.05`. Reason on the merged-away row: `dedup_price_zone`.

The MA-bounce family is the only swing/long-term duplicator; the price-zone merge folds it
into the coincident level instead of muting it.

## Architecture
One gate in the **persist loop** in `api/app/routers/tv_webhook.py`, alongside the existing
SPY / focus gates. Order: known-type → same-bar collapse → **dedup gate (new)** → type-enabled
→ SPY gate → … . The dedup gate runs **before** the SPY/type gates so the "+N collapsed" count
is accurate regardless of delivery. Suppressed rows are persisted via the existing
`suppressed_reason` path with the new reasons; `delivered = suppressed_reason is None` already
holds. New frontend: a "+N collapsed" affordance on the primary card (optional, follow-up).

## Functional requirements
- **FR1** Compute `style` per alert; route day-trade to layer A, swing/long-term to layer B.
- **FR2** Layer A: suppress `dedup_cooldown` within 30 min; suppress `dedup_chase` if not a
  better entry; otherwise fire and update state.
- **FR3** Layer B: never gate level types; merge same-symbol swing/long-term within ±0.5%
  this session into one (`dedup_price_zone`), level alert wins.
- **FR4** Persist every suppressed alert with its reason; never silently drop.
- **FR5** Knobs (admin-config, not hardcoded): cooldown minutes (default **30**), price-zone
  pct (default **0.5%**). Per the "manageable over hardcoded" rule.
- **FR6** Suppressed alerts are a **retained analysis dataset**, not waste. Each keeps its
  `suppressed_reason` + the **anchor it lost to** (kept alert id / best_entry) so we can,
  offline: (a) tune the knobs by counting collapses at N minutes / X%, (b) **validate the
  ratchet** — compare `mfe_r`/`mae_r`/`ret_eod_pct` of the *kept* vs the *suppressed* entries
  on the same name (if the cut re-entries outperform, the rule is wrong), (c) flag
  **over-collapse** — a `dedup_chase` row that later ran = a missed add. Outcomes already
  backfill via the existing self-heal cron, so collapsed rows get scored too. Surfaced as a
  "Dedup impact" cut in the EOD report (follow-up), live as "+N collapsed" on the card.

- **FR7** UI visibility — dedup drops are **hidden from the default feed** (else the collapse
  is pointless) but **never lost**: the kept card shows a **"+N collapsed"** chip that expands
  the dropped siblings (entry · time · reason · the anchor it lost to), plus a rail-level
  **"Show collapsed"** toggle for a full audit view. This fixes today's gap where
  `confluence_collapsed` simply vanishes with no way to inspect it. Matches the track≠deliver
  model — clean by default, one tap to see everything.

- **FR8** Label-forward, non-destructive — the gate only labels **new** alerts at fire time;
  it **never back-writes** `suppressed_reason` onto already-recorded rows. Today's history
  (real reasons like `spy_market_gate` / `confluence_collapsed`) is the source of truth and
  stays intact. Validation/tuning against historical data runs **read-only** (a sim/backtest);
  if a persisted collapse view is wanted, materialize it in a **separate** derived table
  (e.g. `dedup_sim`, keyed by alert id), re-runnable as the knobs change — the `alerts` table
  is never overwritten.

## Non-functional
- Pure DB-derived state (no cache) → correct across worker restarts / replicas.
- Adds one indexed query per alert (`user_id, symbol, session_date, direction`) — negligible.
- Direction-aware (long ratchet = lowest; short mirror = highest) for future short use.

## Out of scope
- SPY market gate (separate delivery control — revisit later as relative-strength exemption).
- A/B/C grade (untrusted; not used here).
- Symbol-grouped feed UI (separate; pairs well but ships independently).

## Decisions (locked 2026-06-29)
1. Cooldown window = **30 min** to start; iterate from live data.
2. **MA-bounce family is deduped like day-trade** (all EMAs) — they are *not* special levels,
   so they go through the entry+time ratchet. Only the true level types stay exempt.
3. Reset boundary = **per session** (no overnight carry).
4. Scope this first build to the **core gate** (FR1, FR2, FR4, FR8) — day-trade + MA entry+time
   dedup, persisted non-destructively. The swing/long-term price-zone merge (FR3), the
   "+N collapsed" UI (FR7), and the EOD dedup-impact view (FR6 surfacing) are fast-follows.

**Dedup set** = `style==day_trade` ∪ `ma_bounce_long_v3_*`.
**Always-fire (exempt)** = `weekly_rc, monthly_rc, cml_held, cml_reclaim, pml_held,
staged_pwl_held, staged_pml_held, weekly_10w_*, weekly_30w_*, monthly_box, mobo_rch,
rsi_oversold, rsi_70, swing_rsi_30, ema_5_20_cross`.
