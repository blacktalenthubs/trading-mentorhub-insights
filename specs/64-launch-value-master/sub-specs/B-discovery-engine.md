# Sub-spec B — Discovery Engine: Find the Next Mover Early (P1)

**Parent:** #64 Launch Value Master · **Pillar:** Find the names · **Priority:** P1 (launch-critical)

## Overview
One surface that answers "**what's worth my attention today, and why?**" with a short, ranked list that catches momentum **at the base, not mid-move** — the next MU / SNDK / NBIS *before* it's obvious. The busy professional opens one board, reads ≤15 names each with a one-line reason, and moves on.

## Problem (current state)
The app is excellent at **review/confirmation** but weak at **early discovery.** Today's tools (Conviction screener of ~48 curated AI names, In-Play RVOL of ~1,200, Weekly Stage, AI Best Setups (watchlist-gated), Premarket gaps) surface names **20–50% into the move.** Missing signals:
- **Emerging-universe blindspot** — sub-$2B / sub-$5 names excluded by static weekly filters; the next mover is invisible until it's already large.
- **No volume-surge-on-consolidation** — the classic accumulation-ending tell (3–5× volume while price is tight).
- **No sector/group leadership** — when a sector heats, 1–2 names lead; the leader isn't isolated.
- **No multi-timeframe confluence scorer** — daily + weekly + monthly alignment, the hallmark of low-risk entries.
- **No accumulation (CVD/OBV)** signal — institutional buying near long-term support.
- **No pre-breakout "spring"** — above 50-MA, below 200-MA, tight range 2+ weeks, volume rising.
- **Focus list is review-only** — it doesn't shape what alerts fire.

## Target state
A **"Today's Movers Worth Watching"** board: ≤15 ranked names, each with a one-line "why now," refreshed intraday, that demonstrably catches at least some leaders **before +20%.** The user's focus list **shapes alert routing** (amplify focus names, suppress noise elsewhere).

## Scope

**Discovery signals (build, ranked by leverage):**
1. **Volume surge on tight consolidation** — today's volume ≥3× the 20-day avg while range is tight (accumulation → breakout). *Highest leverage.*
2. **Sector / group leadership** — classify by sector, compute relative strength per name vs sector + index; surface the 1–2 leaders. *Highest leverage.*
3. **Multi-timeframe confluence scorer** — score daily + weekly + monthly alignment (oversold-recovering, at higher-TF support, structure turning up).
4. **Accumulation (CVD / OBV)** — buy-vs-sell volume delta near long-term support over weeks.
5. **Pre-breakout spring** — above 50-MA / below 200-MA, range compressing, volume rising, time-in-range.
6. **Dynamic emerging universe** — admit names on a real intraday $-volume spike, not just the weekly static list.

**Ranking & presentation:**
- One board, ≤15 names, ranked by a composite early-momentum score.
- Each row: ticker, the **one-line "why now"** (e.g. "AI-chips sector leader · 4× volume on a 3-week base"), and a one-tap drill-in.
- Refreshes intraday; frozen snapshot off-hours.

**Integration:**
- **Focus list → alert routing**: alerts on focus-list names are amplified; low-conviction alerts on non-focus names are suppressed (wire the existing per-user focus list into the alert pipeline).

## Acceptance criteria
- **B-1:** A user with an empty watchlist opens one surface and sees ≤15 ranked names, each with a one-line reason.
- **B-2:** Early-catch: ≥1 of the week's top-5 actual movers appears on the board **before** it is up 20%.
- **B-3:** At least the two highest-leverage signals (volume-surge-on-consolidation, sector leadership) ship at launch.
- **B-4:** Adding a name to the focus list measurably changes which alerts route for that user.

## Out of scope
- Per-alert accuracy grading (Sub-spec A).
- The AI "analyze this name" service (Sub-spec F) — though the board should deep-link into it.

## Notes
This is the pillar that most directly answers "how do traders find the next big momentum stock." Ship the two leverage signals first; the rest are fast-follows. Reuses existing screener/scanner infra (`signal_engine`, `screener`, `conviction_screener`) plus new volume/sector/CVD layers.
