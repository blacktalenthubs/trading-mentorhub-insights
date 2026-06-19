# Sub-spec E — Tabs, Information Architecture & UX Repositioning (P2)

**Parent:** #64 Launch Value Master · **Pillar:** Calm UX · **Priority:** P2

## Overview
Reposition the product around **one calm question — "what should I look at, and why?"** Cut dead weight, make every tab earn its place, and design for a busy professional on a phone with two minutes: glanceable, decision-first, ≤2 taps to a decision. No clutter, no chart homework.

## Problem (current state)
The six primary tabs (Trading, Trade Ideas, Conviction, Watchlist, Premarket, Performance) all have real value, **but:**
- **~9 dead page files** still in the tree (`AlertsPage`, `ChartsPage`, `ScannerPage`, large `DashboardPage` (39KB), `ScorecardPage`, `HistoryPage`, `ImportPage`).
- **2 premium stubs that do nothing** (`BacktestPage`, `PaperTradingPage`) presented as features.
- **Trading page is a 99KB three-pane** that competes for attention on desktop and forces tab-switching on mobile.
- **Performance is 5+ tabs deep** — analytics buried.
- No single **"Today" home** — the user lands without an obvious "here's what matters now."

## Target state
- A **"Today" home** as the default authenticated landing: the discovery board (Sub-spec B) + the day's top alerts (A) + a one-glance market read. The answer to "what + why" is the first thing seen.
- Clean nav; every tab passes the value test; dead code gone; stubs hidden until real.
- One coherent visual system; mobile-first; ≤2 taps to a decision; no horizontal scroll, no buried primary action.

## Scope

**Cut / hide:**
- Remove the dead page files (keep route redirects for deep-link back-compat).
- Hide Backtest / Paper-trading until they actually do something (or cut).

**Restructure:**
- Add **"Today"** (home): discovery board + top alerts + market read (SPY/BTC healthy-weak, kept from the regime strip with the PDL number removed).
- Keep **Trading** but de-densify (the 99KB three-pane → focused, progressive disclosure; S/R management out of the cramped sidebar).
- Collapse **Performance** to a lighter default (real R-multiple by pattern up front; deeper analytics one tap down).
- Keep **Trade Ideas, Conviction, Watchlist, Premarket, Settings** — each already passes the value test; tighten labels and mobile layouts.

**UX system:**
- One card language (the alert card, the discovery row, the conviction row share a visual grammar).
- Mobile-first: bottom-tab nav, glanceable cards, primary action always visible (no horizontal scroll).
- Decision-first: every screen answers "what do I do and why" above the fold.

## Acceptance criteria
- **E-1:** Zero reachable dead pages; no stub presents as a working feature.
- **E-2:** Authenticated users land on "Today" and see the day's names + alerts + market read above the fold.
- **E-3:** Median taps-to-decision on mobile ≤ 2; no horizontal scrolling on any primary screen.
- **E-4:** Every nav tab passes the value test (saves time or teaches); none is redundant.

## Out of scope
- The *content* of the discovery board (B), alerts (A), and education (C) — this is their container and layout.
- Visual brand identity beyond a coherent component system (full rebrand is its own effort).

## Notes
Reuses the May-2026 consolidation (10+ pages → 6-menu). The big new move is the **"Today" home** so a busy user gets value in one glance, and the **dead-code cull** so nothing hollow ships at launch.
