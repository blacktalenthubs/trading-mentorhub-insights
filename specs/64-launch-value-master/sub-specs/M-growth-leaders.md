# Sub-spec M — Growth Leaders: the Mathematical Growth-Stock Framework (P2)

**Parent:** #64 Launch Value Master · **Pillar:** Find the names (conviction) · **Priority:** P2

## Overview
One ranked board of the **proven growth leaders** — the names that currently fit the profile of the best-performing growth stocks of all time — each with a **transparent ✓/✗ scorecard** (why it's a leader) and a **"ready to buy now?"** gate. The user opens it, sees the ≤15 names that pass the math, and knows *which* are also giving an entry today.

This is the **conviction** half of discovery. It is **NOT** Sub-spec B (B catches the *next* mover *early*, at the base, sub-$5B). M ranks the **already-proven leaders** and times the buy. They're two ends of the same funnel: B finds them young, M holds the winners and buys their pullbacks.

**M REPLACES the old WkStage weekly-stage scanner** (decision 2026-06-20). WkStage spanned two roles, both now superseded: its **alerts** are already retired/obsolete; its **chart indicator** role → **WkPos** (the better weekly chart tool — Stage 2 + RS + 52wH + accumulation + actionable held/reclaim/breakout entries); its **scanner** role (rank Stage-2 names) → **M** (the same ranking, richer — adds the fundamental + leadership layer + the BUY-READY gate). So WkStage is retired entirely.

**M and WkPos are a PAIR, not duplicates** — different layers: **M = the board** ("which long-term names lead", a ranked list under Trade Ideas); **WkPos = the chart** ("when/where to enter THIS name", the weekly overlay + entry alert). M's technical score *reuses WkPos's metrics*; WkPos then times the entry on a name M surfaced. Board → chart → entry.

## The framework (from the founder's "Mathematical Growth Stock Framework")
A name is a **Growth Leader** when it scores across three layers:

**1. Fundamental (the growth math)**
- Revenue growth **> 30% and accelerating** (QoQ acceleration, not just high)
- Strong **earnings momentum** (EPS growth + positive surprises)
- **High gross margins** (durable unit economics)
- Strong **ROIC / capital efficiency**
- Large **growth runway** (big TAM, early in penetration)

**2. Business leadership (the moat)**
- **Durable competitive advantage** (platform, network, switching cost)
- **Institutional demand** (being accumulated, not distributed)

**3. Technical (relative-strength leadership + timing)**
- **Stage 2 uptrend** (price above a rising 30w MA)
- **Relative-strength leadership** (RS line vs SPY rising — outperforming)
- Near the **52-week high** (leaders lead)

**Pre-buy confirmation (the "ready now?" gate)** — only when a Leader is *also*:
- Stage 2 ✓ · RS leadership ✓
- **Breakout/range volume > 40% above the 20-day average**
- **Entry within ~3% of the breakout point** (not extended)
- **Positive expected value** on the risk/reward (entry → target vs stop)

## Why this fits — most of it already exists
| Layer | Data we already have |
|---|---|
| Revenue growth, margins, 52w range | `symbol_fundamentals` JSON decision-metrics blob |
| EPS growth | `symbol_fundamentals.eps_growth_pct` (fwd vs ttm) |
| Earnings momentum / surprises | `earnings` (estimate vs actual) |
| Stage 2, RS vs SPY, % off 52wH, accumulation | **WkPos** computes all four (Sub-spec relationship below) |
| Breakout volume vs 20d avg | price data (RVOL — already in the In-Play screener) |
| Entry timing / pullback | **WkPos** entries (held/reclaim/breakout) |

**Gaps to source later:** ROIC / capital efficiency, durable-moat classification, true institutional ownership (proxy with accumulation + RS until then).

## Placement + data pipeline (reuse the conviction rails)
**Placement:** a **"Long Term"** section under the **Trade Ideas** tab — the long-horizon sibling of the day/swing ideas.

**Pipeline — mirror the existing conviction screener exactly (no new infra):**
- **Scoring:** a `growth_screener.py` of pure score/rank functions, like `conviction_screener.py` (`evaluate_conviction` / `rank_conviction`). Unit-tested in isolation.
- **Orchestrate:** `screener_service._gather_growth()` mirroring `_gather_conviction()` — loop the universe, score, rank.
- **Store:** `_save_snapshot(kind="growth")` → the same `screener_snapshot` table (+ history selector), exactly like `kind="conviction"`.
- **Serve:** `/screener/growth` (+ `/growth/history`) mirroring `/screener/conviction`; a `GrowthLeadersPage.tsx` like `ConvictionPage.tsx`.

**Data sourcing — DON'T repeat conviction's yfinance dependency in prod.** The conviction scan pulls fundamentals/analyst via **yfinance** (`.info` + `.history`), which is **cloud-blocked on Railway** ([[project_yfinance_cloud_blocked]]) — so it only works where yfinance runs (local/scheduled) and analyst data degrades in prod. Growth Leaders should instead:
- **Fundamental layer** ← the **`symbol_fundamentals` table** (already populated: eps_growth_pct + the revenue-growth/margins JSON) + `earnings` (momentum) — no yfinance at scan time.
- **Technical layer** ← **Alpaca daily** (Stage 2 / RS vs SPY / % off 52wH / accumulation — the WkPos metrics), via the existing `intraday_data.py` Alpaca helpers.
- Run the scan on a schedule (like conviction); the UI reads the latest snapshot.

## The surfaces
1. **Growth Leaders board** — ranked ≤15 names by a composite Leader score, each row a one-glance ✓/✗ on the 8 criteria (mirrors the founder's tweet format) + a **"BUY-READY"** badge when the pre-buy gate passes.
2. **Per-name scorecard** — the full breakdown (rev growth, earnings, margin, ROIC, runway, moat, institutional, RS), so the user *learns why* (ties to Sub-spec C education-in-flow).
3. **Buy-ready handoff** — when a Leader gives a **WkPos** entry (10w/30w hold/reclaim/breakout in Stage 2) AND the pre-buy gate passes, it surfaces as a high-conviction signal. The Leader board is the *what*; WkPos is the *when*.

## Scope / phasing
- **Phase 1 — Technical leadership board.** Rank the universe on the data we have today: Stage 2 + RS-vs-SPY + % off 52wH + accumulation (the WkPos metrics, computed server-side over the universe). Ship the board with the technical half only.
- **Phase 2 — Fundamental layer.** Fold in `symbol_fundamentals` (revenue growth + acceleration, EPS growth, gross margin) + `earnings` momentum → the composite Leader score + the ✓/✗ scorecard.
- **Phase 3 — Buy-ready gate.** Breakout volume > 40% × 20d avg + entry ≤ 3% from breakout + positive EV; wire the WkPos entry handoff → "BUY-READY" badge.
- **Phase 4 — Hard data.** ROIC / capital efficiency, moat classification (AI-assisted), institutional ownership feed.

## Acceptance criteria
- **M-1:** A ranked Growth Leaders board (≤15) renders from the existing universe, scored on the available fundamental + technical criteria.
- **M-2:** Every name shows a transparent ✓/✗ scorecard for each criterion — never a black-box score (grade-and-show, [[feedback_no_filter_before_data]]).
- **M-3:** A name flips to **BUY-READY** only when the pre-buy gate passes (Stage 2 + RS + breakout vol >40% + entry ≤3% + positive EV).
- **M-4:** A BUY-READY Leader that also fires a WkPos entry is surfaced as the highest-conviction signal (the board × the entry).
- **M-5:** Criteria we can't yet measure (ROIC, moat, institutional) are shown as "—/pending", not faked.
- **M-6:** Lives as a **"Long Term" section under Trade Ideas**, served from a `kind="growth"` `screener_snapshot` (same rails as conviction). The scan sources fundamentals from `symbol_fundamentals` + `earnings` and technicals from **Alpaca daily** — **no yfinance at scan time** (Railway-safe), unlike the current conviction scan.

## Out of scope
- Early/emerging discovery (sub-$5B, base-volume-surge) — Sub-spec **B**.
- The entry mechanics + targets — **WkPos** + Sub-spec **A** own those; M consumes them.
- Auto-trading / sizing — surfaced for the user to act on (manual-validation philosophy, [[feedback_validation_phase]]).

## Notes
The keystone insight: **WkPos already computes the technical leadership half** (Stage 2 / RS / 52wH / accumulation), and `symbol_fundamentals` + `earnings` hold most of the fundamental half — so Phase 1+2 is largely *assembly + ranking*, not new data. Positions M as the conviction board that the WkPos entry then times. Ties to [[project_weekly_position_wkpos]], [[feedback_level_anchored_targets]] (RS-as-#1-edge), [[project_launch_value_master_spec]]. Founder framing: the names that currently fit the all-time-great growth-stock profile (NVDA, PLTR, CRWD, MELI, VRT, LLY, CRDO, APP, NET, NU as of 2026-06).
