# BusyTradersDesk — Go-to-Market v1

**Date:** 2026-05-31
**Status:** Approved for implementation (3-week sprint)
**Owner:** User + Claude
**Builds on:** spec `2026-05-27-landing-repositioning` (positioning baseline)

---

## Overview

The product is shipped. 5 features landed this weekend (Grade A/B/C, real outcome backfill from Alpaca, live SPY regime gauge, Morning Brief enhancement, AI Friday Retrospective), on top of the weekly performance report, earnings tracker, swing scanner, and pattern library that already existed. The brand is `BusyTradersDesk`. Square billing is wired with Free / Pro / Premium tiers and a 3-day Pro trial.

The blocker isn't product — it's distribution. Today the platform has near-zero acquisition channel. This spec is a 3-week launch sequence that turns the product into a self-sustaining customer engine.

## Problem statement

A busy self-directed investor today either:
1. Pays $200/month for an alerts service that won't show its losing trades,
2. Stares at TradingView from their desk between meetings hoping to catch a setup,
3. Or gives up and parks money in index funds, leaving alpha on the table.

We can do better than (1) — every alert we fire is backed by real-outcome data, not synthetic targets. We can do better than (2) — Telegram + push + Morning Brief lets a busy pro plan their day in 60 seconds before work. We can do better than (3) — Grade A/B/C filter means even 5 minutes of attention a day delivers actionable setups.

But none of that matters until busy professionals know we exist.

## Target customer (sharpened)

**ICP — Primary:** Self-directed investor, age 30-50, full-time job in tech / finance / consulting / engineering, manages own brokerage account ($25k-$500k), watches markets 30-60 min/day total (mostly pre-market + lunch + post-close), already trades intraday/swing on the side but inconsistent results.

**Where they live:** X / Twitter (fintwit, $cashtag commentary), Substack (financial newsletters), Reddit r/investing & r/Daytrading, LinkedIn (financial career angle), select Discord servers.

**Not the audience (v1):**
- Pure scalpers who watch every tick
- People who want signals to copy blindly
- Day-traders trading prop accounts
- Beginners with no broker yet
- Anyone seeking guaranteed-win pitches

## Acceptance criteria

After the 3-week sprint:

- A new user arriving at the landing page understands within 10 seconds: what BTD does, who it's for, what they get free, what they get paid.
- 100 net signups during launch week (week 3).
- 2% landing-to-paid Pro conversion within 7 days of first visit (2 paying users per 100 visitors).
- 30%+ Pro retention at 30 days (industry benchmark for SaaS is 25-40%, we aim for top of band given the high-touch nature of the product).
- Weekly AI Retrospective converts into a public newsletter that drives both retention and acquisition (open rate ≥ 35%, click rate ≥ 5%).
- Friday-retro Telegram + Morning Brief Telegram together account for 80% of daily engagement (the two flagship recurring touches).

## Out of scope (v1)

- Paid ads at scale (Google, Meta, Reddit ads) — high upfront cost, slow payback, defer until organic funnel is proven.
- Influencer sponsorships — same reason.
- Mobile app store launch (Capacitor app is internal-only; App Store submission is its own spec).
- Affiliate / referral program v1 (already partial in `Referral` model — out of scope to push as a launch lever).
- Enterprise / B2B (single-seat consumer SaaS only).
- Podcasts / YouTube long-form — Shorts only in v1.
- TikTok / Instagram Reels — wrong demographic for ICP.

---

## Offer + pricing

| Tier | Price | What |
|---|---|---|
| **Free** | $0 | 5 watchlist, 3 AI alerts/day, today's history only, no grade filter, no AI retro |
| **Pro** | $39/mo | Unlimited watchlist, all alerts, 90-day history, Grade A/B/C filter, all Telegram + push, weekly AI retro, real-outcome backfill |
| **Premium** | $99/mo | Pro + Earnings T-7 notifications + AI Best Setups + (future) Movers screener |
| **Trial** | 3-day Pro, no card | Standard funnel |

> **Verify:** prices match Square config. If not, adjust this section before launch.

**Positioning angle for the price ladder:**
- Free = "taste — see how clean Grade A alerts look"
- Pro = "the daily-use tier" — the obvious upgrade after trial
- Premium = "the institutional tier" — AI + earnings + advanced screening

## Launch sequence (3-week sprint)

| Week | Theme | Outputs |
|---|---|---|
| **W1 — Polish** | Fix everything blocking conversion | Landing copy refresh · standalone `/pricing` route · onboarding wizard ("I'm a busy day trader / swing trader / both") · trial countdown in-app · Telegram 1-click setup · public EOD permalinks with OG preview images · watchlist latency fix |
| **W2 — Soft launch + content engine** | Get 10 real users + 3 launch assets | Email/DM 20 personal contacts who fit ICP · iterate on feedback · write 3 launch pieces (Substack long-form, X thread, Reddit r/investing post) · X profile + bio update · Product Hunt page in draft |
| **W3 — Open launch** | Convert audiences into trial signups | X launch thread Mon · Reddit r/investing post Tue · Substack publish Wed · Product Hunt launch Thu · Friday-retro emailed as week-1 newsletter to all signups |

## Channels (ranked by ICP fit)

1. **X / Twitter** — primary. Cash-tag traders, fintwit, daily Grade-A setup screenshots, weekly retro thread.
2. **Substack** — long-form weekly. SEO + email capture. Articles unpack one real Grade-A trade with screenshots, MFE, learned takeaway.
3. **Reddit r/investing, r/Daytrading** — value-first posts, no spam. Lead with "here's what we learned this week" framing.
4. **LinkedIn** — "self-directed investing for professionals" angle. Lower priority than X but high-signal audience.
5. **YouTube Shorts** — 30-60s chart walkthroughs of A-grade fires. Defer to W3+ if time permits.

## Funnel + conversion targets

```
Landing visit         → 100
Sign up (3-day trial) →  10  (10% landing → trial)
Activated (2+ logins) →   6  (60% trial → activated)
Convert to Pro        →   2  (33% activated → paid)
30-day retention      →   1.6 (80% paid → still paying at 30d)
```

**North-star metric:** weekly active paid Pros (WAP). Goal end of week 3: 20 WAP.

## UI / landing punch list (week 1 deliverables)

Each one is a blocker for paid traffic.

| Surface | Gap | Fix |
|---|---|---|
| Landing page | Copy + screenshots predate this weekend's features (Grade A/B/C, Real Worked %, Weekly tab, AI retro) | Refresh hero, feature grid, screenshots |
| `/pricing` route | Doesn't exist as standalone — embedded in landing | Standalone page so paid ads can deep-link |
| Onboarding wizard | "Which of 31 patterns do I want?" paralysis | "I'm a busy day trader / swing trader / both" → presets enabled |
| Trial countdown | No visible "2 days left in trial" reminder in-app | Banner or pill in nav |
| Telegram setup | 4-step process | One-click bot deep link with prefilled `/start` token |
| Public EOD permalinks | Exist but no shareable OG preview card image | Server-side render OG image with day's headline stats |
| Watchlist latency | Rows appear stale on first load (price column hydrates async, reflows) | Skeleton placeholders + pre-fetch live-prices on mount |

## Content plan (week 2 + 3)

Three launch assets, each tied to a real shipped feature:

1. **Substack — "How I scan 30+ stocks in 5 minutes a day"**
   Show the Morning Brief Telegram + the Trading page filtered to Grade A. Walk through 3 real Grade-A setups from last week with MFE outcomes.

2. **X thread — "Most alert services lie. Here's how we don't."**
   Public proof: screenshots of the Weekly tab's `Real Worked %` column for an old pattern, computed from Alpaca post-fire bars. Compare against "fictional T1/T2 win rates" most services publish.

3. **Reddit r/investing — "What 30,000 alerts taught us about volume + VWAP slope"**
   Data-driven analysis. Charts from `analytics/alert_outcomes.py` outputs. Plain prose, no sales pitch. End with a single soft link.

## Newsletter loop (week 3+ recurring)

The Friday AI Retrospective (shipped in feature 5 this weekend) becomes the weekly newsletter:
- Sent automatically Friday 5 PM ET via Telegram (already wired)
- Posted as Substack issue Saturday morning (manual repost initially, automate later)
- Drives **retention** for existing subs (sees their own wins/misses) and **acquisition** when shared publicly

## Success criteria (week 3 review)

If we hit these, GTM v1 is a success and we move to v2 (paid ads, affiliate, B2B exploration):
- ≥ 20 paying Pro users (acquired through launch)
- ≥ 35% newsletter open rate
- ≥ 1 organic feature mention (FinTwit shoutout, podcast invite, blog backlink)
- < $10 effective CAC (only soft costs in v1 — time + Substack/PH listings)
- Friday retro consistently sends and lands without manual intervention 3+ Fridays running

If we miss: do not scale spend. Diagnose where the funnel breaks (landing? trial? activation? trial-to-paid?) and iterate before paid spend.

## Open questions to confirm before W1 starts

1. **Pricing match Square?** Verify $39 / $99 in Square dashboard. Adjust if different.
2. **Personal soft-launch contacts:** do you have 20+ people who fit the ICP to message in W2?
3. **Substack/Medium account:** do we have one set up under the BusyTradersDesk brand? If not, create in W1.
4. **X/Twitter handle:** is `@busytradersdesk` claimed? If not, claim in W1.
5. **Email infra:** what's the From: address for transactional + newsletter? (Currently using `vbolofinde@gmail.com` SMTP — fine for transactional, needs `hello@busytradersdesk.com` or similar for newsletter brand consistency.)

---

## Phase plan

**W1 — Polish (Mon-Sat):**
- Mon-Tue: landing copy + screenshots refresh
- Wed: standalone `/pricing` route
- Thu: onboarding wizard
- Fri: trial countdown + Telegram 1-click + watchlist latency
- Sat: public EOD OG images

**W2 — Soft launch + content (Mon-Sat):**
- Mon: DM 20 personal contacts
- Tue-Wed: iterate on feedback from first 5 responders
- Thu: draft Substack long-form
- Fri: draft X thread + Reddit post
- Sat: draft Product Hunt page

**W3 — Open launch (Mon-Fri):**
- Mon 9am ET: X launch thread
- Tue 9am: Reddit r/investing post
- Wed: Substack publish + email blast to soft-launch list
- Thu 12:01am PT: Product Hunt launch (their cycle)
- Fri 5pm ET: Friday retro fires + repurposed as first newsletter issue
