# BusyTradersDesk — Launch Value Master Spec (#64)

**Status:** Draft for review · **Type:** Master spec (spawns focused sub-specs) · **Created:** 2026-06-19

---

## Overview

A pre-launch audit and north star that holds every tab, alert, discovery surface, and AI service to a single test:

> **Does it save a busy professional time and make them a calmer, better trader?**

If a surface can't pass that test, it is cut. This spec captures the honest current state, defines the target state, and decomposes the work into small, independently shippable sub-specs.

## Why now

We are launching (TestFlight build live, PWA live). The product has grown to **~31 alert types (all off by default), ~20 pages (several dead or stubbed), a curated conviction screener, an education-framed landing page, and a working-but-unmetered AI layer.** The launch risk is **breadth over trust**: a first-time user can't tell what fires, why it fired, or what to do — the exact problem a busy professional hires us to remove. We launch on *trust and teaching*, not feature count.

## Who this is for

Self-directed **day + swing traders with day jobs**. They believe in trading and love it, but cannot watch charts during market hours. They want, in priority order:

1. A **short list of names worth attention today** — not a 1,200-row screener.
2. A **few high-trust alerts with the reasoning attached** — not an inbox of buy/sell calls.
3. To **actually learn the "why"** so they improve over time — education in the flow, not a separate course.
4. **AI to do the chart-staring** for them — analysis, thesis, journal review on demand.

They distrust signal-spam, synthetic win-rates, and tools that assume they have hours to study charts.

## Product principles (the bar every feature is judged against)

1. **Each surface earns its place or is cut.** A tab, alert, or section that neither saves time nor teaches is removed before launch.
2. **Trust over breadth.** Fewer, higher-conviction signals. Keep only proven entry systems; retire the noise.
3. **Levels are primary; structure confirms; moving averages are confluence — not standalone signals.**
4. **Buy support in an uptrend. Never buy a level approached from below (that's resistance). Don't chase breakouts — wait for the retest.** Levels are dual-role and the app must know which role a level is playing.
5. **Higher timeframes by default** (1h / 4h / daily). Less noise, less stress, better decisions — validated in live use.
6. **Every alert teaches.** The reasoning ships *with* the signal. Education lives in the flow, not behind a separate tab.
7. **Surface the few, not the firehose.** The next MU / SNDK should appear *early*, ranked, with the "why now."
8. **AI does the chart-staring.** The user's tokens buy analysis, thesis, and review — metered, transparent, valuable.
9. **Calm UX for busy people.** Glanceable, decision-first, mobile-first. No clutter, no homework.

---

## Current state — honest audit

### Tabs & UX
Six primary tabs (**Trading, Trade Ideas, Conviction, Watchlist, Premarket, Performance**) + Settings/Billing/Admin. All six have distinct, real value. **But:** ~9 dead page files still in the tree (`AlertsPage`, `ChartsPage`, `ScannerPage`, large `DashboardPage`, `ScorecardPage`, `HistoryPage`, `ImportPage`), 2 premium **stubs that do nothing** (`BacktestPage`, `PaperTradingPage`), the Trading page is a 99KB three-pane that competes for attention, and Performance is 5+ tabs deep. UX is *capable but dense* — not yet "glance and decide."

### Alerting
~31 alert types, **all off by default**. The audit's verdict on what's trusted vs. noise:
- **Trusted core (keep):** structural level **holds + reclaims** (PDH/PDL/PWH/PWL/PMH/PML), **4h RC + RC-H** (the cornerstone breakout-retest), **daily swing momentum** (RSI-70, 5/20 EMA cross, RSI-30–35 oversold), **gap-and-go**, **weekly RC**.
- **Noise / low-conviction (retire or demote to confluence-only):** standalone **MA bounce / rejection** (EMA tangle, backward-looking support test, per-symbol-allowlisted as a tacit admission of noise), **pullback continuation** (pure price-action, 5 gates to fire), **multi-period S/R** on individual names.
- **Accuracy gaps (the trust killers):**
  1. **Dual-role levels not enforced** — the system fires *long reclaims into resistance* (a level rallied up into from below). Confirmed live on SPCX: a long fired at the PDL as it got rejected. The `_held` rule has the `day_open > level` guard; the `_reclaim` rule does not.
  2. **No volume confluence** on level bounces — fires on any volume; real support has buyers stepping in (≥1.5×).
  3. **VWAP slope ignored** on holds/reclaims — panic free-fall bounces graded the same as accumulation bounces.
  4. **No per-symbol trend confirmation** — a PDH-held can fire while the *stock itself* is below its EMA50 / in a daily downtrend (only market-level SPY regime is gated, and that gate is off).
  5. **Gap context incomplete** — only applied to reclaim, not the rest of the gap-affected family.

### Discovery (finding the next momentum name)
Strong at **review/confirmation**, weak at **early discovery.** Today: Conviction screener (curated ~48 AI names + analyst + 50-MA persistence), In-Play RVOL screener (~1,200 names), Weekly Stage, AI Best Setups (watchlist-gated), Premarket gaps. **A trader finds names 20–50% into the move, not at the base.** Missing: emerging small-cap universe, **volume-surge-on-tight-consolidation** detection, **sector/group leadership** ranking, **multi-timeframe confluence** scoring, **accumulation (CVD)** signals, **pre-breakout spring** detection, and **focus-list → alert routing** (the focus list is review-only; it doesn't shape what fires).

### Education
The landing **already promises education-first** ("Analysis. Education. Transparency." · "Every signal links to a teachable pattern" · "not another inbox of buy/sell calls"), and a real 30-pattern library exists. **But the promise breaks at the moment of the alert:** a live alert delivers *setup data, not reasoning*. There is no "here's why THIS fired now," no post-trade **autopsy**, no **"why not"** for skipped setups, no inline **grade breakdown**, no **learn-bridge** from alert → pattern page, and no beginner glossary for terms like "VWAP slope."

### AI
Live: alert **narratives** (Haiku/Sonnet routed), **AI Trade Coach** (multi-turn, context-assembled), and scattered analysis buttons. Metering exists but is **feature-count, not token-based** (`usage_limits`: free = 3 `ai_query`/day), tiers exist (free/pro/elite), Stripe is scaffolded-not-wired, BYOK keys are **stored in plaintext.** There is **no unified generate() contract, no token telemetry, no visible quota meter.** AI is a feature, not yet a metered value product.

**The keystone we already own:** a Claude-based **triage agent** (`triage-agent/triage.py`) classifies *every* alert **HIGH / NORMAL / MUTE** per user using real context (sector confluence, index alignment, market bias, proximity, a safety override), owns the 8:30 ET **morning brief**, and owns **Telegram delivery** (`AGENT_OWNS_TELEGRAM`). It is the single highest-leverage existing asset — but **its reasoning is invisible to the user.** Making it visible and conversational delivers discovery, education, and the AI value menu from one place (see Sub-spec H).

### Landing / positioning
Positioning is **already right** (education-first, transparency, "for the hours you're not at one"). The gap is **claims vs. delivery** (education promised, not in the alert flow) and **no discovery hero** (the "find the next mover early" value isn't pitched).

---

## North star — target state at launch

- **Tabs:** dead code removed; every visible tab passes the value test; a **calm, decision-first** layout; mobile-first; the two stubs either built minimally or hidden.
- **Alerting:** only the **trusted core** ships on by default; the **dual-role resistance bug fixed**; **volume + slope + own-trend confluence** as soft grades (never silent drops — grade, don't hide); noise demoted to confluence-only.
- **Discovery:** a **"Movers worth your attention today"** surface that catches names *early* (volume surge + sector leadership + MTF confluence + accumulation), ranked, with a one-line "why now"; the **focus list shapes alert routing.**
- **Education:** **every alert teaches** — reasoning at delivery, grade breakdown, learn-bridge, autopsy after resolution, and "why not" for skips. The landing's promise becomes literally true.
- **AI:** a **token-metered AI value menu** (chart analysis, trade thesis, journal review, MTF synthesis, coach) through one unified, telemetered `generate()` contract, with a visible quota meter and encrypted BYOK.
- **Landing:** claims match delivery; add a **discovery + education** hero; keep the transparency spine.
- **UX:** one coherent visual system; glanceable cards; the right thing one tap away; nothing that demands chart homework.

---

## The value pillars → sub-specs

Each pillar becomes a small, independently shippable spec under `sub-specs/`. Priority = launch-criticality.

| # | Sub-spec | Pillar | Priority | One-line outcome |
|---|----------|--------|----------|------------------|
| A | **Alerting accuracy hardening** | Trust | **P1** | Keep only the proven entries; fix dual-role; grade by volume/slope/own-trend; retire noise. |
| B | **Discovery engine — find the next mover early** | Find the names | **P1** | A ranked "worth your attention today" board that catches momentum at the base, with "why now." |
| C | **Education-in-the-flow — every alert teaches** | Teach | **P1** | Reasoning at delivery + grade breakdown + learn-bridge + autopsy + "why not." |
| D | **Pattern playbook (canonical)** | Backbone | **P2** | The definitive kept-only-the-best pattern set for day / swing / trend, mapped to alerts + lessons. |
| E | **Tabs, IA & UX repositioning** | Calm UX | **P2** | Cut dead code; decision-first, mobile-first layout; each tab earns its place. |
| F | **AI services & token economy** | Monetizable value | **P2** | Unified generate(); token metering + telemetry + quota meter; the AI value menu; encrypted BYOK. |
| G | **Landing & positioning alignment** | Conversion | **P3** | Claims match delivery; add discovery + education hero; keep the transparency spine. |
| H | **Triage Agent → AI Concierge** | The connective AI layer | **P1** | Make the existing triage agent's reasoning visible + conversational; it powers B, C, and F from one asset. |

(Full scope, current-state, target-state, and acceptance criteria for each live in `sub-specs/`.)

---

## Acceptance criteria (master-level — product language, testable)

- **AC-1 (Trust):** On a fresh account, the default-on alert set contains **only the trusted core**; no alert can fire a long into a level being approached from below.
- **AC-2 (Teaching):** Every delivered alert carries a plain-English reason, a grade with its breakdown, and a one-tap link to the pattern lesson — verifiable on any fired alert in-app and in Telegram.
- **AC-3 (Discovery):** A user with zero watchlist setup can open one surface and see a **ranked short list (≤ ~15) of names worth attention today**, each with a one-line reason, refreshed intraday.
- **AC-4 (Value-per-tab):** Every tab visible in the nav demonstrably saves time or teaches; no dead-code page is reachable; no stub presents itself as a working feature.
- **AC-5 (AI value):** A user can spend metered tokens on at least three AI services (e.g., chart analysis, trade thesis, journal review), see their remaining balance, and the platform records token usage per call.
- **AC-6 (Calm):** A busy user can open the app on mobile and reach "what should I look at and why" in **≤ 2 taps**, with no horizontal scrolling or buried primary actions.
- **AC-7 (Honesty):** No synthetic win-rates anywhere; every performance number traces to real post-fire outcomes.

## Out of scope (this launch)

- Automated order execution / broker integration.
- Backtesting engine and paper-trading simulator (stubs stay hidden until real).
- Options-flow as a paid pillar (keep as context only).
- Non-US markets (Nigerian-stocks spec stays parked).
- Social / community features.

## Assumptions

- The **trusted core** (levels + 4h RC + daily swing momentum + gap-and-go) is the profitable spine; everything else must justify itself against it.
- The user's **validated trading philosophy** (levels primary, support-in-uptrend, dual-role, higher-TF, no chasing) is the product's point of view and should be visible in the language.
- We keep the **manual-validation stance**: grade and surface, never silently drop — the user decides.
- Token-metered AI is the primary near-term monetization beyond subscription tiers.
- Real-outcome tracking (entry+stop in every payload) is the proof layer that makes claims credible.
- We prefer **admin-tunable config over hardcoded** for thresholds, but avoid over-knobbing.

## Success criteria (measurable)

- **SC-1:** ≥ 80% of first-session users can correctly state, in their own words, *why* a sample alert fired (comprehension test) — education is landing.
- **SC-2:** ≤ 15 names on the daily discovery board, and ≥ 1 of the week's top-5 actual movers appears on it **before** it's up 20% (early-catch rate).
- **SC-3:** Default-on alerts produce **zero** "long into resistance" fires in a 2-week audit.
- **SC-4:** Median taps-to-decision on mobile ≤ 2; zero reachable dead pages.
- **SC-5:** ≥ 30% of active users try a token-metered AI service within their first week.
- **SC-6:** Alert volume per user drops while *acted-on* rate rises (trust up, noise down) over the first month.

## Open questions (for your review)

1. **Default-on set:** ship the full trusted core on by default, or start even tighter (e.g., 4h RC + level reclaims + swing momentum only) and let users add?
2. **Discovery scope at launch:** build the full early-discovery engine (volume-surge + sector leadership + MTF + accumulation), or ship the two highest-leverage signals first (volume-surge-on-consolidation + sector leadership)?
3. **Token economy:** keep the 3-tier subscription **and** add token packs, or fold AI into tier limits only at launch?
4. **MA alerts:** retire standalone MA bounce/rejection entirely, or keep strictly as a confluence flag on level alerts (your "EMA = confluence not signal" stance)?
5. **Stubs:** hide Backtest/Paper-trading until real, or cut them from the codebase now?

## Sub-spec index

- `sub-specs/A-alerting-accuracy.md`
- `sub-specs/B-discovery-engine.md`
- `sub-specs/C-education-in-flow.md`
- `sub-specs/D-pattern-playbook.md`
- `sub-specs/E-tabs-ia-ux.md`
- `sub-specs/F-ai-services-token-economy.md`
- `sub-specs/G-landing-positioning.md`
- `sub-specs/H-triage-agent-concierge.md` *(keystone — powers B, C, F)*
