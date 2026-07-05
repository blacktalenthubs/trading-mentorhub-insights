# Landing Page Redesign — Master Spec

**Status:** Draft for review · **Created:** 2026-07-05 · **Owner:** admin
**Reference mock:** `scratchpad/landing_redesign.html` (published Artifact)
**Companion truth docs (memory):** systems-vs-agents; landing-redesign pattern ground-truth.

---

## Overview
Redesign the public marketing landing (and align the public sub-pages) to reflect the platform's
**full, current** value for its real audience: **busy professionals with a day job** who want to
day-trade, swing, and find long-term winners **from one platform, without living on the charts**.
Education-first. Not financial advice. The page routes visitors to the **mobile and desktop apps**
and to a free trial. It is the foundation for marketing, social content, and paid campaigns.

## Problem
The live landing still sells the **old story** — "graded A/B/C setups + public EOD reports,
14 documented patterns." It omits almost everything built since: **swing trades, Trade Ideas,
Long Term Finders, the honest Performance page, the true role of the AI agents, and the apps.**
It also mis-states the pattern count (really 29 documented, ~1/3 retired) and risks **synthetic
win-rate claims** that contradict our own scored Performance data and our own "no synthetic win
rates" promise.

## Target audience
A working professional (day job, limited screen time) who is disciplined, wants to learn, and
trades day + swing setups and hunts long-term momentum — but cannot watch charts all day.

## Positioning (the spine of every section)
> **One platform to day-trade, swing, and find the next big winner — without living on the charts.**
> A rules-based **system** watches your levels and fires the setups; **AI agents** explain the why,
> triage to conviction, brief you at the open and close, and coach you on any symbol.
> **Education-first. Not financial advice.**

## Core values → sections (each must earn its place)
1. **Systems fire the alerts** — deterministic Pine → rules engine. Transparent, repeatable, *not a
   black box*. (Trust.)
2. **Agents = your analyst/coach** — explain each setup's thesis, triage HIGH/MUTE, AM+PM briefs,
   on-demand coach. (Insight + education.)
3. **The playbook** — the real, *currently-firing* patterns grouped Day / Swing / Trend. **No
   per-pattern win-rate claims.**
4. **Find the next winner** — Morning Focus (MoBO / RC-H), Trade Ideas (5 boards), Long Term Finders
   (ETF technique + dossier). (The MU/SNDK story.)
5. **Honest Performance** — outcomes scored against real price, shareable. (Transparency.)
6. **Education-first** — learn the why; free pattern library; risk-first. (The differentiator.)
7. **The apps** — mobile + desktop, downloadable. (Everywhere.)

## Non-negotiable constraints
- Education-first language throughout; explicit, visible **"not financial advice."**
- **Zero per-pattern win-rate claims** on marketing. All performance claims link to the live,
  scored Performance page. (Reconciles with the platform's own promise + real data.)
- Only reference patterns that **actually fire** (the kept set). Retired patterns are archived,
  never sold.
- Route to **real app downloads** (mobile + desktop).
- Reuse the existing design system (tokens, fonts, components); do not introduce a new visual
  language.

## Success criteria (measurable, technology-agnostic)
- **SC1** A first-time visitor can state *what it does* and *who it's for* within 30 seconds.
- **SC2** Every one of the 7 core values has a dedicated section a non-trader can understand.
- **SC3** No unverifiable performance claim appears; 100% of outcome claims resolve to the
  Performance page.
- **SC4** Clear, one-tap paths exist to: start free, download mobile, download desktop, explore
  patterns, view a live report.
- **SC5** The page reads cleanly on a phone (mobile-first); no horizontal scroll; hero legible
  without zoom.
- **SC6** The "find the next winner" story is explicit enough that a visitor names at least one
  discovery surface (Morning Focus / Trade Ideas / Long Term Finders) unprompted.

## Sub-specs (independently buildable — the "sub work")
| ID | Scope | Effort |
|----|-------|--------|
| **A** | Hero + positioning + app-download CTAs + nav | M |
| **B** | Value pillars — Systems, Agents, Day, Swing | M |
| **C** | The playbook (real patterns) + Education-first block | M |
| **D** | Find the next winner (discovery engine) | M |
| **E** | Apps download section (real deep links) | S |
| **F** | Proof + Pricing + How-it-works + Footer/disclaimers | M |
| **G** | Shared marketing components + any new tokens | S |
| **H** | Companion: prune/archive retired `/learn` patterns | M |

Build order: **G → A → B → C/D (parallel) → E → F**, with **H** in parallel (backend/content).

## Out of scope
- The authenticated app pages (separate redesign track).
- Pricing/plan changes (reuse current Free / Pro $49).
- New product features — the landing **describes what already exists**.

## Open decisions (assumptions taken — override anytime)
- **Retired `/learn` patterns → ARCHIVE with a badge** (SEO/history preserved; nothing dead is
  "sold"). Alt: hard-delete.
- **Win-rate policy → Performance-page-only** (no per-pattern numbers on marketing). *Strongly
  recommended; reconciles with real data + the platform's own promise.*
- **App links → placeholders** until the real iOS / Android / desktop URLs are provided.
