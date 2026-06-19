# Sub-spec J — UI Redesign & Design System: the new layout for every page (P1)

**Parent:** #64 Launch Value Master · **Pillar:** Calm, polished UX · **Priority:** P1 (do before any rebuild) · **Supersedes the layout work in Sub-spec E** (E keeps the dead-code cull + IA decisions; J defines how it all looks)

## Overview
A ground-up visual redesign that turns a capable-but-dense app into a **calm, polished, glance-and-act** product a wide audience can use on day one. This spec defines the new information architecture, the design system (one component language), and the layout of **every page** — with wireframes — so the prototype (built next in AIDesigner) is exact, not improvised.

## Design principles (the feel)
1. **Glance and act.** The answer to "what do I look at and why" is above the fold on every screen.
2. **One card language.** Alerts, discovery rows, conviction rows, and ideas all share one visual grammar — learn it once.
3. **Decision-first, not data-first.** Numbers support a decision; they never *are* the screen.
4. **Mobile-first.** Designed for a phone in two minutes; the desktop is the same system, wider.
5. **Calm dark theme.** Restrained palette; color means something (green=long/support, red=short/resistance, amber=caution) — never decoration.
6. **Progressive disclosure.** Show the verdict; one tap reveals the reasoning, the chart, the lesson.
7. **Polished, not busy.** Generous spacing, clear hierarchy, no competing panes fighting for attention.

## New information architecture

```
PUBLIC                          AUTHENTICATED (bottom nav on mobile, sidebar on desktop)
├─ Landing  (redesign, G)       ┌─ TODAY        ← NEW home: the day in one screen
├─ Learn    (pattern library)   ├─ Discover     ← NEW: the ranked "worth watching" board (B)
├─ Pricing                      ├─ Trading      ← de-densified chart workspace
├─ Track Record (public EOD)    ├─ Ideas        ← Trade Ideas (social + AI scans)
└─ Login / Register / Onboard   ├─ Conviction   ← analyst+trend swing candidates
                                ├─ Watchlist    ← symbols + earnings
                                ├─ Performance  ← real outcomes per pattern (+ EOD review, I)
                                └─ More ▸        Premarket · Settings · Billing · (Admin)
```
Six primary destinations, the rest under **More** — a busy user never hunts. **Premarket** folds into **Today** (the morning read) and stays reachable under More.

## Design system (the foundation everything inherits)

**Color (dark):** surface ramp (bg → surface-1/2/3 → border-subtle); **bullish** green, **bearish** red, **warning** amber, **accent** (brand) for primary actions; muted/faint grays for secondary text. Color is semantic only.
**Type:** one sans family; a tight scale (display / title / body / caption / mono for prices). Prices always monospace so columns align.
**Spacing:** an 8pt grid; generous card padding; one consistent radius.
**Components (the kit):**
- **Signal/Alert card** (the hero component — see below)
- **Discovery row** (ticker · why-now line · score chip)
- **Conviction/Idea row** (ticker · thesis · grade)
- **Level chip** (a labeled price line: "PDH 405.94")
- **Grade chip** (A/B/C with a one-tap breakdown)
- **Market-read strip** (SPY/BTC HEALTHY·WEAK, no PDL number)
- **Posture banner** ("🛡 Stops on every position · NORMAL")
- **Bottom-sheet** for detail (chart, reasoning, lesson) on mobile

## The signal/alert card — redesigned (the most-seen surface)

```
┌──────────────────────────────────────────────┐
│  NVDA   LONG   [A]            RC-H · 4h   2m   │   ← ticker · side · grade · pattern · age
│  Reclaimed the broken high at 210 and held    │   ← plain-English WHY (education-in-flow, C)
│  Entry 210.40   Target 213.73 (PDH)   Stop 208│   ← entry · ONE target labeled w/ its level · stop
│  ───────────────────────────────────────────  │
│  ▸ Why grade A   ▸ See chart   ▸ Learn RC-H    │   ← progressive disclosure (grade breakdown, chart, lesson)
│  [ Took it ]                          ▲ 1.3R   │   ← one-tap EOD capture (I) · live R to target
└──────────────────────────────────────────────┘
```
Every card *teaches* (the why), shows a *real-level target* (A-9), and captures the outcome in one tap (I). This single component carries pillars A, C, and I.

## Page-by-page layout

### TODAY (new home — the whole point)
```
┌───────────────────────────────────────────────┐
│  Good morning, B.   Market: SPY HEALTHY · BTC ↓ │  market-read strip
│  🛡 Stops on every position · NORMAL             │  posture
├───────────────────────────────────────────────┤
│  WORTH WATCHING TODAY            (Discover →)    │  top 3–5 from the discovery board (B)
│  • NBIS  AI-chip leader · 4× vol on a base      │
│  • MU    breakout-retest forming                │
├───────────────────────────────────────────────┤
│  LIVE SIGNALS                   (all →)         │  the 2–3 freshest high-grade cards (A/C)
│  [ NVDA RC-H card ]  [ MU level-reclaim card ]  │
├───────────────────────────────────────────────┤
│  YOUR DAY                                       │  open positions you marked Took + EOD nudge (I)
└───────────────────────────────────────────────┘
```
Two-tap rule satisfied: open app → see the few names + the live signals + your day.

### DISCOVER (new — Sub-spec B)
Ranked list (≤15) of discovery rows; each: ticker · one-line why-now · score chip · sparkline. Filter chips (sector leaders / volume surge / pre-breakout). Tap → bottom-sheet with chart + "analyze with AI" (F).

### TRADING (de-densified)
Single focal **chart** (levels + the active alert's E/S/**T**-labeled lines, A-9); a slim **right rail** that is *one* of {Signals · AI · Levels} via segmented control (not 3 panes competing); watchlist collapses to a strip. Mobile: chart full-screen, signals in a bottom-sheet.

### IDEAS · CONVICTION · WATCHLIST (shared row grammar)
- **Ideas:** two chips (Social buzz · AI scans) → idea rows.
- **Conviction:** grouped by theme → conviction rows (ticker · thesis · grade · add-to-watchlist).
- **Watchlist:** grouped symbols + an Earnings chip; clean add/remove.

### PERFORMANCE (simplified + EOD, Sub-spec I)
Default view = **per-pattern real win-rate / avg-R** (the answer to "what works") up front; **EOD Review** prompt for today's alerts (Took / entry / exit, ≤2 taps); deeper slices (by symbol, weekly) one tap down — not 5 tabs deep.

### SETTINGS
Sectioned + calm: Telegram · Alert types · Symbol lists · AI/tokens (F) · Account. (Already close; just apply the system.)

### PUBLIC: LANDING (G) + LEARN
- **Landing:** hero = "find the few, get alerts that teach, let AI do the staring"; three value heroes; transparency spine.
- **Learn:** the pattern library in the new card grammar; every alert deep-links here (C).

## The clean-out
Remove the dead pages (AlertsPage, ChartsPage, ScannerPage, the 39KB DashboardPage, ScorecardPage, HistoryPage, ImportPage); hide the Backtest/Paper-trading stubs until real (Sub-spec E). Nothing hollow ships.

## Mobile
Bottom tab bar (Today · Discover · Trading · Performance · More); every primary action thumb-reachable; detail in bottom-sheets; **no horizontal scroll** anywhere; cards stack single-column.

## Acceptance criteria
- **J-1:** Every page is laid out in this spec with a wireframe; no page is "TBD."
- **J-2:** One documented design system (color/type/spacing/components) that every page uses.
- **J-3:** The signal card carries the WHY (C), a real-level target (A-9), and one-tap Took (I).
- **J-4:** Today home answers "what do I look at + why" above the fold, ≤2 taps, on mobile.
- **J-5:** Dead pages removed; stubs hidden; no horizontal scroll on any primary screen.
- **J-6:** A clickable prototype of the key screens (Today, Discover, Trading, Signal card, Performance) exists for review before any production rebuild.

## Prototype plan (next step — together)
Build the visual, clickable prototype in **AIDesigner** (the aidesigner-frontend workflow), screen by screen, starting with **Today → Signal card → Discover → Trading**, refining live to your taste, then capturing the artifacts and the repo-native adoption path. The spec above is the brief AIDesigner builds from.

## Out of scope
- Production implementation (this is design + prototype; the build follows once approved).
- Brand identity overhaul beyond a coherent system (logo/marks are a separate effort).

## Notes
This is the container the other pillars live in: A's level-targets, C's teaching, B's discovery, F's AI menu, and I's EOD capture all surface *through* this system. Lock the layout here, prototype it in AIDesigner, then rebuild once — never twice.
