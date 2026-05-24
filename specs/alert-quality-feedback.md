# Alert Quality — End-of-Week Feedback (2026-05-22)

Observations from a week of live use. **No fixes applied yet** — this is the
itemized backlog for the next refinement pass.

## North star

The system has **too many entry rules and is hard to trust**. Cut the entry
rule set to **5–6 high-conviction rules** — a stock firing should mean it is
genuinely worth looking at. The rules that survive share one principle:

> **Buy support in an uptrend; sell at resistance. Do not chase breakouts.**

---

## 1. MA/EMA alerts — uptrend-only

**Observed:** MA/EMA bounce alerts fire even when the MAs are stacked *above*
price (a downtrend) — pure noise.

**Want:** fire only when price is **above all the key EMAs/MAs** and pulls
back to one of them *from above* — a fully uptrending stock.
- ✅ NVDA pulling back from a high to the 21 EMA (price above the stack).
- ❌ ETH with every EMA stacked above price (price below the stack).

**Where:** the intraday MA-bounce alerts (`ma_ema_daily.pine`). This is the
same bullish-MA-stack gate the swing scanner (`swing_quality.py`) already
applies — extend it to the intraday alerts.

---

## 2. PDH / PWH / PMH — highs are dual-role

**Observed:** the system alerts "long at the PDH break" as price rises *into*
the level. But a high approached **from below is a target** (resistance), not
an entry.

**Want:** treat a high as a **support entry only when price retraces down to
it from above** (price was above the level, pulls back to it). A breakout is
not trusted unless price retraces to the level. Support entry, sell at
resistance.

**Where:** `levels_day_vwap.pine` — reframe `pdh_break` / `pwh_break` /
`pmh_break` from breakout-long toward retrace-to-support-long.

---

## 3. Open-line alerts — demote from entries

**Observed:** `open_reclaimed` / `open_held` / `open_wick_reclaim` are too
inconsistent — price chops chaotically around the open line. Example: INTC
today chopped the open line; the real support was the **PDH**.

**Want:** keep the open line as a **visual reference only** — do not use it as
an entry trigger. Entries belong at key MA/EMA, PDL, PDH support.

**Where:** retire the open-line *entry* alerts; keep the open-line plot.

---

## 4. Too many entry rules — cut to 5–6

**Observed:** the catalog has too many entry rules; a stock fires for many
reasons and none are fully trusted.

**Want:** **≤ 5–6 entry rules total.** Fewer, higher-conviction. A qualifying
stock is one worth looking at.

**Where:** prune the `alert_type_config` catalog hard during the redesign.

---

## 5. Use the TradingView MCP to study charts

When designing the simplified 5–6-rule set, use the TradingView MCP to pull
real charts and confirm which patterns earn a slot.

---

## Next step (when ready)

Redesign the entry rule set down to ~5–6 rules built on "buy support in an
uptrend." Candidate survivors to evaluate: pullback to a key EMA/MA in an
uptrend; retrace to PDH/PWH/PMH as support; PDL support / reclaim; the swing
bounce; RSI-30 (sell-off regime). This is a `/speckit-specify` candidate.
