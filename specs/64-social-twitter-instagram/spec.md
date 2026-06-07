# BusyTradersDesk — Social Media Launch: Twitter/X + Instagram

**Date:** 2026-06-07
**Status:** Draft for review
**Owner:** User + Claude
**Handle:** `@BusyTradersDesk` (consistent across X + Instagram)
**Builds on:** spec `33-social-media-launch` (prior playbook), `63-gtm-v1` (GTM baseline), `2026-05-27-landing-repositioning` (positioning), `27-replay-and-social-content` (content engine)

---

## Overview

The product is shipped and repositioned (2026-05-27) as a **research + education toolkit for
self-directed investors with day jobs** — three pillars: **Analysis · Education · Transparency**.
Over the weekend we added the **long-term layer**: a **weekly 30-week MA** trend strategy
(Stan-Weinstein-style stage analysis) plus **Pine scripts for long-term position entries**,
alongside the existing **short-term Pine-rule day-trade alerts** and daily/weekly swing scanner.

The blocker is distribution, not product. This spec defines the **Twitter/X + Instagram**
presence under one handle — `@BusyTradersDesk` — structured around three objectives the
business cares about: **education**, **short-term** trading, and **long-term** investing, all
delivered with **full transparency of strategies** and a strict **education-not-advice** posture.

## Objectives (what social must serve)

1. **Education first** — teach the documented patterns and the strategy logic, for busy
   professionals who want to learn, not be told what to buy.
2. **Short-term** — surface the day/swing setups the Pine indicators observe (graded A/B/C),
   framed as study material with entry / stop / target / invalidation.
3. **Long-term** — introduce the new weekly 30-week MA / stage-analysis position strategy,
   broadening reach beyond the day-trader niche.
4. **Transparency** — public EOD reports, real outcomes (MFE/MAE), losses shown beside wins.
5. **Compliance** — never cross into investment advice; protect the business legally.

## Core values (social DNA — every post inherits these)

| Value | What it means on social |
|-------|-------------------------|
| **You decide** | The desk surfaces the setup; you make the call. Never a recommendation. |
| **Radical transparency** | Public EOD reports; losses shown with equal detail to wins; real outcomes, not synthetic win rates. |
| **Education first** | Every observation links to a teachable, documented pattern. |
| **Built for busy professionals** | 30–60 min/day, not chart-all-day. |
| **No hype, faceless** | Data-dense terminal aesthetic; no guru persona; no rockets / "to the moon." |

## Product surface social draws from

| Objective | Pages / sources |
|-----------|-----------------|
| Education | `LearnPage` / `PatternDetailPage` (free 14-pattern library), `ReplayPage` (bar-by-bar replays) |
| Short-term | `FocusListPage` (Day = Pine-rule alerts, Swing = daily scanner), `ScannerPage`, In-Play screener, `PremarketPage` |
| Long-term | Weekly 30-week MA / stage-analysis layer + Pine position-entry scripts (specs 14, 38) |
| Transparency | `TrackRecordPage`, `PublicEODReportPage` (public, no login), `ScorecardPage`, Friday AI retrospective |

## Compliance posture (NON-NEGOTIABLE — applies to every post)

The product already uses compliant vocabulary; social must match it exactly.

1. **Vocabulary:** "observation / setup / analysis / level / study," — **never** "pick / buy /
   sell / recommendation / signal-to-act / guaranteed."
2. **Disclaimer placement:** in **both bios**, in a **pinned post**, and as a **text overlay**
   on every Reel and screenshot.
3. **Every setup shows entry + stop + invalidation** — framed as a *plan to study*, not a call to act.
4. **Losses shown with equal detail to wins** — the trust moat and the legal defense.
5. **No individualized advice in DMs/comments** — redirect "what should I buy?" to `/learn`.

Standard disclaimer string:
> *Educational and informational purposes only. Not investment advice or a recommendation to
> buy or sell any security. Past performance does not guarantee future results. Trading
> involves risk of loss.*

## Channel architecture

One handle, two distinct roles. This resolves the prior concern (spec 63) that Instagram was
"wrong demographic" — IG is not for day-trade signals, it carries the **education + long-term**
story, which is exactly the weekend additions.

| | **Twitter / X** — *the live desk* | **Instagram** — *the classroom* |
|---|---|---|
| Role | Real-time pulse, fintwit credibility, transparency receipts | Evergreen education, long-term investing, brand/aesthetic |
| Primary objective | Short-term + Transparency | Education + Long-term |
| Audience | Active fintwit, $cashtag traders, busy pros lurking markets | Busy professionals learning to invest; long-term "set-and-review" crowd |
| Cadence | 3–5 posts/day | 4–5 posts/week + daily stories |
| Formats | Text, screenshots, threads, scorecard cards | Carousels, Reels, infographics, story polls |

## Content pillars (one rotation = weeks of content)

| Pillar | Objective | Twitter | Instagram |
|--------|-----------|---------|-----------|
| 1. Pattern of the week | Education | Thread: what / why / how-it-fails + replay clip | 6-slide carousel from Pattern Library |
| 2. Today's setups (observed) | Short-term | A-grade observation cards w/ entry/stop/target | Story screenshots; "setup of the day" reel |
| 3. The long game (NEW) | Long-term | "$X testing its 30-week MA — stage analysis read" | Carousel: 30-week MA stage analysis + Pine teaser |
| 4. Receipts | Transparency | Daily EOD scorecard + weekly win/loss thread (losses shown) | Weekly "report card" graphic |
| 5. Discipline / WAIT | Education/Trust | "The scan said WAIT today — why that's the feature" | Reel: why no-trade days matter |

## Twitter/X — daily rhythm (lean, sustainable)

- **8:30 AM** — Premarket brief (reuse the generated brief)
- **~10:00 AM** — One A-grade observation card *(or a WAIT / discipline post)*
- **12:30 PM** — Education micro-post or long-term / 30-week-MA note
- **4:35 PM** — EOD scorecard (auto-generated from the public EOD report)
- **Fri 5 PM** — Weekly retrospective thread (wins **and** losses, per pattern)

**Bio:**
> Trade & invest research for people with day jobs. Documented patterns, A/B/C-graded
> setups, public EOD reports — short-term to long-term. Educational, not financial advice.
> 👇 tradingwithai.ai/tw

*(Positioning note: lead with the substance — patterns, strategies, transparency. Automated
scanning is a mechanism, not the headline; AI is one tool inside the desk, not the product.)*

## Instagram — weekly rhythm

- **Mon** — Pattern carousel (education)
- **Wed** — Long-term / 30-week-MA explainer carousel
- **Fri** — Weekly report-card graphic (transparency)
- **2× Reels/week** — 15–30s replay clip or pattern explainer
- **Daily stories** — setup screenshots, polls ("which level holds?"), link stickers to `/learn`

**Bio:**
> Learn the patterns. See the receipts. 📊 Trade & invest research for busy professionals ·
> Short-term + long-term · 📚 Free pattern library · Educational, not financial advice · 👇

## Leverage (already built — content factory)

- **Public EOD reports + Track Record** → daily/weekly receipt posts (zero extra work).
- **Replay engine** (`/replay/:id`) → screen-record for Reels/clips.
- **Premarket brief** → the 8:30 AM Twitter hook.
- **Pattern Library** (14 documented patterns) → 14+ weeks of education carousels/threads.
- **Spec 27 Phase 1** (auto stats-cards + social templates) → finish for a self-serve content pipeline.

## Visual identity (reuse existing brand kit)

- Background `#0a0b0d` · bullish green `#22c55e` · bearish red `#ef4444` · accent blue `#3b82f6` · amber for WAIT
- Display: Bricolage Grotesque · Data/mono: JetBrains Mono
- Logo: BusyTradersDesk wordmark + crosshair · faceless, terminal aesthetic

## 30-day launch sequence

- **Week 0** — Register `@BusyTradersDesk` on X + IG; set up both bios + pinned disclaimer post; brand kit.
- **Week 1** — Education-led: 1 pattern thread + 1 carousel + daily EOD scorecards. Build trust before promotion.
- **Week 2** — Introduce the **long-term / 30-week MA** angle (the differentiator).
- **Week 3** — Turn on transparency cadence (weekly retro thread + IG report card).
- **Week 4** — First soft CTA to the 3-day free trial, UTM-tagged (`/tw`, `/ig`).

## Attribution

Bio links use UTM short domains (per spec 33):
- `tradingwithai.ai/tw` → `?utm_source=twitter&utm_medium=bio`
- `tradingwithai.ai/ig` → `?utm_source=instagram&utm_medium=bio`

Attribution captured on signup, visible at `/admin`.

## Success metrics (30 days)

| Metric | Target |
|--------|--------|
| X followers | 500 |
| IG followers | 750 |
| IG education saves/shares | Track (compounding signal) |
| Link clicks (UTM) | 500+ |
| Free-trial signups attributed to social | 50+ |
| Posting consistency | X 3–5/day · IG 4–5/week |

## Hashtag pool (rotate 4–6 per post)

- Brand: `#busytradersdesk` `#tradingwithai`
- Category: `#aitrading` `#patterntrading` `#priceaction` `#swingtrade` `#daytrade` `#longterminvesting`
- Strategy: `#vwap` `#movingaverage` `#stageanalysis` `#30weekMA`
- Asset: `#SPY` `#NVDA` `#ETH` `#BTC`
- **Avoid:** `#ToTheMoon` `#Lambo` `#guru` `#financialfreedom` `#stockstobuy`

## Open decisions

1. **Naming consolidation** — `BusyTradersDesk` (brand) vs `tradesignalwithai.com` (domain) vs
   `tradingwithai.ai` (short links). Handle resolved to `@BusyTradersDesk`; confirm the public
   domain shown in bios.
2. **Founder voice vs faceless** — current default is faceless: the strategies, patterns, and
   transparent track record are the product, not a founder persona (and not "AI" as the headline). Confirm.
3. **Cross-post automation** — manual at launch; revisit Buffer/Make automation after week 4.

## Out of scope (v1)

- Paid ads, influencer sponsorships, TikTok, YouTube long-form (defer until organic proven).
- Direct in-app social posting (Spec 27 marks this out of scope; post manually for now).
