# Sub-spec O — Emerging Leaders Scout: the weekly themed agent drop (P2)

**Parent:** #64 Launch Value Master · **Pillar:** Find the names (discovery) · **Priority:** P2

## Overview
A **weekly, agent-delivered** shortlist of the ≤5 names **heating up inside the themes the user already trades** — the next MU / SNDK *within* Memory, Chips, Quantum, etc., before it's obvious — each with a one-line "why now," graded A/B/C, **pushed in-app** and surfaced for one-tap add-to-watchlist. This is **discovery delivered on a swing/trend rhythm**: the user opens it once a week (or gets the push), reads five names, adds the ones they believe, and moves on.

It is deliberately **thin**: it does not invent new scoring or new infra. It is the **cadence + themed-universe + narration + delivery** layer over signals that **B** and **M** already define, ridden on the **report push channel shipped 2026-06-23** ([[project_inapp_notifications]]).

## Relationship to B and M (no duplication)
The discovery funnel has three deliveries; O is the third:

| | What it is | Universe | Cadence | Surface |
|---|---|---|---|---|
| **B — Discovery Engine** | the discovery **signal library** + intraday "Movers Worth Watching" board | broad / emerging (sub-$5B admitted on $-vol spike) | intraday | a board you open |
| **M — Growth Leaders** | the **proven-leaders** board + fundamentals + buy-ready gate | curated leaders | scheduled scan | a board you open |
| **O — Emerging Leaders Scout** *(this)* | the **agent taps you weekly** with the few names emerging **inside your sectors** | tracked-sector holdings (~200, themed) | weekly | a **push** + a Discover section |

**O reuses, never re-derives:**
- **Stage 1→2 transition** ← `scanner.classify_weekly_stage()` (already server-side; the Weinstein 30wMA stage + slope/distance).
- **Volume-surge-on-consolidation** ← **B's signal #1** (accumulation tell).
- **Sector / group leadership** ← **B's signal #2** + premarket `compute_sector_breadth()` (the group-strength the brief already computes).
- **Relative strength vs SPY** ← the WkPos / M-Phase-1 RS metric (the one genuinely small add if not yet server-side: % return vs SPY over 1m/3m).
- **Delivery** ← `reports_store.publish()` → `market_reports` + APNs push (built tonight).
- **Add-to-watchlist** ← the existing conviction→watchlist→TV bridge ([[project_conviction_alert_bridge]]).

If B and M ship their scoring, **O is assembly + schedule + a narration prompt.**

## Problem (current state)
Discovery today is **review-rhythm, not tap-me rhythm.** B's board and M's board are surfaces the user must remember to open; the premarket/EOD reports are daily and tape-wide, not "what's emerging in *my* themes." A busy professional who trades Memory/Chips/Quantum has no weekly nudge that says *"SNDK is turning Stage 2 on 4× base volume while Memory leads — look now."* The signal exists in the data; nothing **delivers it on the swing-trader's weekly clock.**

## Target state
- Once a week, the agent **pushes** an "Emerging Leaders" drop: ≤5 names, each a one-line reason + an A/B/C grade.
- Every name is **inside a sector the user tracks** (themed, not random) and **not already on their watchlist** (it's discovery, not a re-rank of what they own).
- One tap adds a name to the watchlist → it begins throwing the trusted-core alerts → outcomes accrue.
- Surfaced in the **Discover / Conviction** section *and* delivered as a push — the user never has to remember to open a board.

## Scope

**Universe — tracked-sector holdings (~200 names), DECIDED 2026-06-23.**
- Built from the user's **watchlist groups** (`load_watchlist_groups` → Memory, Chips, Quantum, Space, Robotics, …) **extended** with an **admin-tunable per-sector seed list** (e.g. `Memory: MU, SNDK, WDC, STX, …`) editable in Settings — **manageable over hardcoded** ([[feedback_manageable_over_hardcoded]]), no new data dependency. *(Chosen over live ETF-holdings, which needs a holdings feed + the Alpaca/yfinance fetch issue resolved first — deferred to a later phase.)*
- Scan **excludes names already on the user's watchlist** — O surfaces what's *new*.

**Scoring (reuse — see table above).** Composite over four inputs: **Stage 1→2 · RS-vs-SPY · volume thrust · sector tailwind.** Output a transparent **A/B/C grade with the per-criterion breakdown** — grade and show, never a black box, never silently dropped ([[feedback_no_filter_before_data]]).

**Cadence — daily scan, event-driven push (DECIDED 2026-06-23).** The Stage 1→2 tell is a weekly-bar event, but volume/sector tailwind can shift sooner — and the scan is **free** (pure deterministic math, **zero LLM tokens**). So scan **daily** (mon-fri) but **push only when a NEW name enters the board** vs the prior snapshot — never on a fixed calendar drip. You're tapped on *change*, silent when nothing's new (scarcity is the edge; matches "tap me only when it matters" better than a Monday push that fires even if the list is identical). The first-ever seed never pushes.

**Delivery + surface.**
- Persist the snapshot (`screener_snapshot`, kind=`emerging`) every scan. **APNs push fires only on a new entrant** — "📈 New in your themes · SNDK — early Stage 2, Memory leads" (+N more) — deep-linking to Trade Ideas → Emerging (`{type:"emerging", route:"/trade-ideas?tab=emerging"}`). Broadcast to all registered iOS devices via the working live-alert APNs path (`apns.send_apns_push`); graceful no-op if APNs unconfigured.
- **Placement (DECIDED 2026-06-23): a "Emerging in your themes" section under the *Trade Ideas* tab**, alongside **Growth Leaders (M, "Long Term")** + **Conviction** — all discovery surfaces in one place. The board persists all week (not just at push time).

**Card anatomy (a scout card is discovery, NOT an entry card — no entry/stop yet; adding to the watchlist is what unlocks alerts):**
- Row 1: **ticker · sector tag · grade badge (A/B/C)**.
- Row 2: the **one-line "why now"** (e.g. "Stage 1→2 turn · 4.2× base vol · Memory leads").
- Row 3: the **transparent ✓/✗ row** across the four criteria (Stage turn · RS>SPY · Vol · Sector) — the visible teach (ties to Sub-spec C).
- Action: **one-tap `+ Add to watchlist`** → flips to "✓ Added — now routing your alerts" (the existing conviction→watchlist→TV bridge). Tap the row → drill into the chart.
- Two names from one sector renders as a tell (sector heat surfacing its leaders).

**Settings — the seed list.** Each tracked sector shows an **editable candidate-ticker pool** (`Memory: MU SNDK WDC STX [+ add]`), tunable live; a ticker added here enters the **next** scan with no redeploy.

**Manual-eval only.** Surfaced for the user to evaluate; **no auto-trade, no auto-add** ([[feedback_validation_phase]]).

## The data-chain payoff (why it earns its place)
`scout finds a themed name → user adds it → it throws trusted-core RC/weekly alerts → outcomes tracked → feeds the parked System Scorecard (#1)`. O **generates the data** the scorecard needs — so it sequences correctly *before* the scorecard, not after.

## Acceptance criteria
- **O-1:** The user receives an in-app **push only when a NEW name enters the board** (vs the prior snapshot) — never on a fixed schedule, and never on the first-ever seed. An unchanged board is silent.
- **O-2:** Every surfaced name is in a **sector the user tracks** and is **not already on their watchlist**.
- **O-3:** Each name shows a **transparent ✓/✗ breakdown** (Stage 1→2 · RS · volume · sector) — never a bare score.
- **O-4:** One tap **adds the name to the watchlist** (existing bridge), after which it routes the user's trusted-core alerts.
- **O-5:** The per-sector candidate pool is **admin-editable in Settings** — adding a ticker to a sector's seed list brings it into the next scan with no redeploy.
- **O-6:** The scan **reuses** `classify_weekly_stage` + `compute_sector_breadth` + B's volume/leadership signals — **no duplicate scoring engine** is introduced.
- **O-7:** The drop persists to `market_reports` (kind=`emerging_leaders`) and renders as an **"Emerging in your themes" section under Trade Ideas** (with Growth Leaders + Conviction), not Telegram-only; the weekly push deep-links to it.
- **O-8:** A scout card shows ticker · sector · grade · one-line "why now" · the ✓/✗ four-criteria row · a single `+ Add to watchlist` action — and carries **no entry/stop** (it's discovery, not a fired signal).

## Out of scope
- The **broad/emerging-universe** discovery (sub-$5B, $-vol-spike admission) — **Sub-spec B** owns it.
- **Proven-leader** ranking + fundamentals + buy-ready gate — **Sub-spec M** owns it.
- **Live ETF-holdings** universe — deferred phase (needs a holdings feed + Alpaca-401/yfinance-blocked fix, [[project_alpaca_401_keys]] · [[project_yfinance_cloud_blocked]]).
- Entry mechanics / targets / sizing — **WkPos** + Sub-spec **A** own those; O only points at the name.

## Phasing
- **Phase 1 — themed weekly board.** Watchlist-groups + seed-list universe; score on Stage 1→2 + sector tailwind + volume (all server-side today); render in Discover with add-to-watchlist. Ship without the RS add if needed.
- **Phase 2 — RS + push.** Add RS-vs-SPY to the composite; wire `reports_store.publish` + the weekly APNs push.
- **Phase 3 — feedback loop.** Once the Scorecard (#1) exists, label each past scout pick with its realized outcome (did it lead?) → tune the composite weights.

## Notes
Keystone: **O is the smallest of the discovery trio** because B and M do the hard scoring and tonight's work built the push pipe — O is the weekly themed *delivery* that makes discovery feel like a concierge tap instead of a board to remember. Ties to [[project_launch_value_master_spec]], [[project_conviction_alert_bridge]], [[project_inapp_notifications]], [[project_weekly_position_wkpos]], [[feedback_validation_phase]], [[feedback_manageable_over_hardcoded]]. Universe decision (tracked-sector holdings) + seed-list approach chosen by the user 2026-06-23.
