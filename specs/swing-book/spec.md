# Swing Book — Entry & Exit Spec

**Status:** Draft for review · **Created:** 2026-07-07 · **Owner:** admin (vbolofinde)

## Why this spec
We just redefined *swing* to mean **sustained, multi-day** setups (held while the thesis is good),
separate from *day* trades (out by the close). But the **exit engine doesn't know that yet** — several
swing setups are currently handed a **Day exit** (a single "next resistance" price target), which
throws away the entire point of a swing. This spec pins down **proper entry, stop, and exit** for
every setup in the swing book, on one consistent philosophy, and names the gaps to close.

## The 7 setups
| Group | Setups |
|---|---|
| **A — Weekly levels** | Weekly RC · PWL held · PWH break |
| **B — Longer-term** | 10w held · 30w held · Monthly RC |
| **C — Weekly scanners** | Character Change · Buying in Bases |

## Universal philosophy (same DNA as the day book)
1. **Entry — defend a level FROM ABOVE.** Buy a *reclaim* or *hold* of support, never a rally up
   into resistance. The one exception is **PWH break** (a breakout *through* resistance + retest).
2. **Stop — lose the level you bought → OUT.** The **reclaim low** (the wick that undercut the
   level), or a **weekly close below the anchor MA** for the MA setups. Small, structural, honest.
3. **Exit — let winners run; don't trim early** (tested — early trims hurt). Trim at **RSI 70**
   (use the *weekly* RSI for weekly/monthly setups) and **trail the anchor** (10w / 30w / 5-week EMA).
4. **Hold — Swing = days→weeks · Long = weeks→months.** The stop, not the clock, ends the trade.

## Per-setup: entry, stop, exit
| Setup | Trigger | Entry | Stop | Target / Exit | Hold |
|---|---|---|---|---|---|
| **Weekly RC** | undercut the PWL, close back above (genuine reclaim) | the **PWL** (the level) | the reclaim week's low (wick under PWL) | first obj = **PWH**; trim **weekly RSI 70**; trail 10w | Swing |
| **PWL held** | tags the PWL *from above*, never breaks, closes above | the **PWL** | below the hold/tag low | same as Weekly RC | Swing |
| **PWH break** | close **above** the PWH after being below (+ retest) | the **PWH** (breakout/retest) | back below the PWH (breakout fails) | measured move (PWH + prior-week range) or weekly RSI 70; trail 10w | Swing |
| **10w held** | tags the 10-week MA, closes above | the **10w MA** / close | a **weekly close below** the 10w | trim RSI 70; trail the 10w | Position |
| **30w held** | tags the 30-week MA, closes above | the **30w MA** / close | a **weekly close below** the 30w | trim RSI 70; trail the 30w (or 10w) | Long |
| **Monthly RC** | undercut the PML, close back above (monthly reclaim) | the **PML** | the reclaim month's low | first obj = **PMH**; trim **monthly RSI 70**; trail 10w | Long |
| **Character Change** | downtrend → vol surge + first 10w reclaim + higher swing low | the reclaim week's **close** | below the **30w MA** (or trigger-week low) | runner — trail the 10w; +2R; trim RSI 70 | Long |
| **Buying in Bases** | proven uptrend digesting, tight base, higher lows, vol drying | the **buy zone** (higher-low pivot +1% — buy the *pullback*, not the top) | ~3% below the pivot | the **base high** (breakout level), then trail the 10w; trim RSI 70 | Swing |

## The gaps to close (why the exits are wrong today)
`analytics/exit_plan.py → trade_style()` currently routes:
- **Weekly RC · PWL held · PWH break → "Day"** (falls through to the default) → gets a *next-resistance*
  Day exit. **Wrong** — these are weekly swings; they should trim at RSI 70 and trail the 10w.
- **Character Change · Buying in Bases → "Day"** (not matched) → same problem. Should be **Swing**.
- **10w/30w held · Monthly RC → "Long hold"** ✅ correct already.
- **Buying in Bases target** should be the **base high**, not RSI — it's a breakout objective, not an
  overbought trim (special-case it).

**Proposed fix (pending approval):** extend `trade_style()` so `weekly_rc`, `staged_pwl`, `staged_pwh`,
`character_change` → **Swing**; `base_buy` → **Swing** with a base-high target override. No day-book
changes.

## Validation status
| Setup | Backtested edge | Status |
|---|---|---|
| Character Change | +0.48R (in→out holds) | ✅ validated |
| Buying in Bases | +0.22R (rock-solid OOS) | ✅ validated |
| Weekly RC (low) | +0.21R | ✅ validated (2026-07-07) |
| Weekly RC (high/PWH) | +0.19R | ✅ validated |
| Monthly RC | +0.27R low / +0.32R high | ✅ validated |
| **PWL held · PWH break** | — | ⚠️ live but not separately backtested |
| **10w held · 30w held** | — | ⚠️ live but not separately backtested |

## Open questions for review
1. **PWL held vs Weekly RC** — keep both, or is "held" just a weaker "reclaim"? (Both defend the PWL;
   held = tagged from above, reclaim = undercut & reclaimed. Merge or keep distinct?)
2. **Validate the un-backtested three** (PWL held, PWH break, 10w/30w held) before we lean on them,
   same R-based method as the rest?
3. **Weekly RSI 70 vs daily** for the trim on weekly setups — confirm we key the trim off the *weekly*
   RSI (slower, fewer false trims) for A/B, and monthly RSI for Monthly RC.

## Out of scope
- No Pine changes (these fire from levels the Pines already send + the two Python scanners).
- No day-book changes.

---

## Decisions & additions (2026-07-07)

### Reclaims are DAY-trade tools (not swings)
A reclaim of a *level* is an event, not a hold-for-days pattern (tested: bare weekly RC ≈ +0.2R,
+4%/8w, 58% still up — a modest bounce, not a sustained trend). So **weekly_rc · PWL held · monthly_rc
moved to the DAY book** across style_for / classify / trade_style (shipped). They remain useful
*intraday* entries; the Performance page evaluates them over time. Trend-MA holds stay swing — an MA
is a trend, a static level is an event.

### Monthly MA hold/reclaim — ADDED to the swing book (validated)
| Setup | Expectancy | +6mo | Held @6mo |
|---|---|---|---|
| Monthly **M8** hold/reclaim (uptrend) | **+0.36R** | +8.6% | 65% |
| Monthly **M21** hold (uptrend) | **+0.36R** | +8.7% | — |

Stronger than the reclaims and genuinely holds (65% still up at 6 months). The **MoBO pine already
computes M8/M21/M50/M100/M200**, so the levels exist. GOOGL/GEV/AMZN reclaiming the M8 are the live
examples. **Tier 1 swing (position).**
- **Trigger:** pullback tags the monthly 8-EMA (or 21-EMA), closes back above, in an uptrend (above a
  rising monthly 21-EMA).
- **Entry:** the monthly MA · **Stop:** a monthly close below it (~2–3%) · **Exit:** trim monthly RSI 70,
  trail the M8/M21.
- **Build:** a Python EOD monthly-bar detector on the master universe (same shape as swing_scan.py),
  emits a `monthly_ma_hold` swing type. No Pine change needed.

### Redefined swing catalog (current)
**Tier 1 (validated / high-conviction):** Buying in Bases · Character Change · Monthly MA hold ·
20-EMA trend pullback · 5/20 cross · 10w/30w held.
**Tier 1 (to validate before leaning on):** PWH break · monthly M50/M100/M200 holds.
**Candidates to backtest:** VCP / tight-base breakout · Power earnings gap · High-tight flag · RS-line new high.
**Moved OUT (now day):** Weekly RC · PWL held · Monthly RC.
