# Target & stop test — spec + results (before we change anything)

**Ask (2026-07-04, before bed):** spec how we compute targets today, and test whether an
ATR-based target improves things *before* implementing.

**TL;DR — the assumption was wrong.** Targets are **not** the lever; the **stops are too
tight** (57% of day trades get noise-stopped). ATR targets do *not* beat the current
next-level targets. Do **not** ship an ATR-target change — it doesn't help. The real,
testable lever is stop width (with fat-tail management). Details below.

---

## 1. How we compute targets TODAY (spec)

Backend-owned (`analytics/exit_plan.py` + `analytics/target_picker.py`; the Pine just fires a
dumb trigger). Per trade style:

| Style | Target today | Where |
|---|---|---|
| **Day** (levels, rc_4h, ORL, PDL/PDH, pullback…) | **nearest resistance LEVEL above entry** — picked from the chart's `nearby_levels` stack (skip within 0.3% of entry; cluster within 1% into a "wall"). Fallback = Pine's raw T1 (blue sky). | `target_picker.pick_target` → kind `"level"`; wired in `tv_webhook.py:~1890` |
| **Gap-and-go** | RSI 75+ (momentum exit, no price) | `exit_plan.build_exit_plan` |
| **Swing** | daily RSI 70 trim | `exit_plan` |
| **Long hold** | daily RSI 70 trim | `exit_plan` |
| **STOP (all)** | the reclaim / setup low below entry | Pine sends it |

Design note in the code: *"Targets are NEVER R-multiples — price moves to the next level."*
That's the philosophy we were testing.

**The suspected flaw:** the "next level" is sometimes 10%+ away (SNDK's target was 2280 on a
2070 entry = 40 R:R), so it's never reached intraday and the trade rides back to the stop.

---

## 2. Tests (methodology)

Replayed every **delivered DAY-trade alert with a valid stop+target** (n≈884, Jun 15–Jul 3)
against its **actual 5-min intraday path**. For each scheme, simulate a disciplined exit:
walk the bars from the alert time — take profit at the target (limit) if the high reaches it
*before* the low hits the stop; else take the stop; else exit at the close. Record the
**realized % per trade** (the expectancy of that scheme). ATR = ATR(14) from daily bars,
as-of the alert day (no lookahead). Scripts: `analytics/target_test.py` (+ inline stop test).

---

## 3. Results

### A. Target scheme (stop held at the current reclaim-low)
```
scheme         n   tgt-hit  win%   avg%    median%
current      884     21%    34%   -0.07%  -0.18%   ← nearest resistance level
atr0.75      884      4%    23%   -0.05%  -0.31%
atr1.0       884      1%    23%   -0.09%  -0.31%
atr1.5       884      0%    23%   -0.10%  -0.31%
atr_cap1.0   884     21%    34%   -0.07%  -0.18%   ← min(entry+1ATR, level) — ≈ identical to current
```
**ATR targets are FURTHER than the nearest level for most alerts** (the level is usually a
nearby PDH/EMA <1% up; 1 ATR is 2–4%), so they hit *less*, not more. Capping at 1 ATR barely
changes anything (the level is already inside 1 ATR almost always; the far outliers stopped
out regardless). **No target scheme is positive.**

### B. Stop width (current next-level target held; vary the stop)
```
stop         n   stopped%  win%   avg%    median%
current    884     57%     34%   -0.07%  -0.18%   ← reclaim-low = TOO TIGHT (noise-stopped)
0.5 ATR    884     13%     52%   -0.21%  +0.05%
1.0 ATR    884      2%     53%   -0.18%  +0.06%
1.5 ATR    884      0%     53%   -0.15%  +0.06%
```
Widening the stop to ~1 ATR **cuts stop-outs 57%→2% and lifts the win rate 34%→53%, flipping
the median from −0.18% to +0.06%** (most trades become small winners). BUT the **average**
worsens (−0.07% → −0.18%) because a wide stop occasionally eats a full reversal (the SOXL
−14.7% tail). Tight = frequent small losses; wide = mostly small wins + rare big ones.

---

## 4. What this means

1. **Don't ship an ATR target.** It doesn't beat the current next-level target and doesn't turn
   the book positive. The "targets too far" story was driven by a few outliers (SNDK), not the
   median trade — most targets are already a nearby level.
2. **The real leak is stop tightness.** A 57% stop-out rate means most day trades are killed by
   noise before they can work. That's the thing worth fixing.
3. **The stop-width fix is a genuine trade-off, not a free win.** Wider stops raise the win rate
   and median but add fat-tail losses — so any change must be paired with **position sizing**
   (risk a fixed $ so a wide-stop loss is capped) and/or a **disaster stop** beyond the ATR stop.

---

## 5. Recommended next tests (before implementing anything)

- **Wider stop + sizing:** stop at ~0.5–0.75 ATR with fixed-$ risk per trade → does capping the
  tail make the *average* positive, not just the median?
- **Wider stop + closer target combo:** 0.5 ATR stop + ~1 ATR target (the median winner) — the
  likely sweet spot; test the joint expectancy.
- **Partial + trail:** bank half at the level, trail the rest — the current test assumes a
  single all-or-nothing exit, which understates a managed trade.
- **Per-pattern:** reclaims/levels tolerate wider stops differently than MA-bounce/gap — slice
  the stop test by pattern.

**Caveats:** 3-week sample, one pullback-heavy regime, delivered-only, single mechanical exit
model (no trailing/partials). Directional, not a final backtest.
