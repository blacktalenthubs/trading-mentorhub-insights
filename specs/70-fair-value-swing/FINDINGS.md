# Fair Value Swing — entry research + backtest (pre-code)

**Status:** research · **Owner:** vbolofinde · **Date:** 2026-07-12
**Visual:** `pine_scripts/visual/fair_value_swing.pine` (eyeball first — NOT wired to alerts)

## The idea
A structural, low-stress **swing/position** system built on the **THT Fair Value Bands** (20-period
SMA basis ± 2σ) read on the **weekly + monthly**. The basis (middle band) = **fair value**; it does
triple duty:
- **Trend filter** — a *rising* basis = uptrend. Flat/falling = no pullback trade.
- **Entry reference** — %B says discount (lower band) / fair (middle) / premium (upper). Buy at fair,
  never at a premium.
- **Ride & exit** — trail the rising basis; a close below it ends the trade.

## The three entries (one idea, three states vs. a rising fair value)
1. **A · hold** — price *tags* a rising basis and holds (low touches the line, closes back above,
   lower-middle band). Shallowest, best continuation. Ex: AAPL wk 06-22 (low 273.75 @ basis ~276 → +11%).
2. **C · reclaim** — closes back *above* a rising basis after being below it (the turn).
3. **B · base** — coils in the **lower band** with a **non-falling** basis (early accumulation).
   Ex: AMD wk 02-02 @ 208 → +167%.

**Rising fair value is MANDATORY for the pullback buys (A/C)** (user, 2026-07-12). B (basing) allows a
flat line. Extended names (high %B / far above the basis) are **skipped** — that's a chase (ZETA +17%).

## Stop / target (band-native)
- **STOP** = the floor beneath you — the **lower band / recent swing low**, whichever is nearer —
  **floored at ~3%** so ultra-tight stops don't blow up on a gap week. **Never the basis** (it noise-
  stops winners: AMD closed below the basis at -1% then ran +167%).
- **You keep the stop small by buying low in the band** — at %B ≤ ~0.40 the floor is 3–8% away.
  If the floor is >~8% away, the entry is too high → skip. This is what caps the loss (the -13% trades
  were all high-%B reclaims).
- **TARGET** — T1 = the **upper band** (take a partial); runner = **trail the rising basis**, exit on a
  close below it. The trail is where the big rides live.

## Backtest (6y weekly, 540 names = S&P 500 + Nasdaq 100 + master, ~5,200 trades)
Rules: entry on the signal close · stop = swing-low (≤8% only, floored 3%) · T1 = upper band ·
trail = rising basis after T1/1R.

| Variant | N | Win% | avg R | med R | hit T1 | med hold | note |
|---|---|---|---|---|---|---|---|
| A · hold  | 2,348 | 40% | **+0.44** | −0.76 | 35% | 6w | fat-tail rides (VST +49R, MSTR +39R) |
| C · reclaim | 23 | 48% | +0.54 | −0.24 | 70% | 9w | rare on weekly |
| B · base  | 2,807 | 51% | **+0.49** | **+0.08** | 22% | 4w | steadiest, positive median |
| **ALL**   | 5,178 | 46% | **+0.47** | −0.35 | — | 5w | positive expectancy |

**Read:** classic "let winners run" — win rate <50% but **positive expectancy** because the trail lets
the big moves (COIN +214%, SOXL +312%, AMD +167%) pay for the many small stops. **B-base is the steady
producer; A-hold is the home-run engine.** Exit mix: ~53% trailed out (in profit), ~43% stopped.

## Open refinements (before wiring alerts)
- Floor the stop at ~3% (a few −20R+ tails came from 1% swing-low stops on gap weeks). Done in the pine.
- Validate rising-vs-flat basis for B (pullback buys already require rising per user).
- Decide realistic partial-at-T1 vs. full-ride sizing.
- Cross-check weekly vs. monthly cadence (monthly = fewer, bigger; weekly = the timing).

## Next
1. **USER eyeballs** `fair_value_swing.pine` on AMZN / AMD / NVDA / AAPL / COHR — do the A/C/B markers
   land on the right bars (AAPL 06-22 = A, AMD base = B)?
2. On pass → wire the survivors into the **swing pine** (the renamed `levels_day`), pine-driven, no job.
