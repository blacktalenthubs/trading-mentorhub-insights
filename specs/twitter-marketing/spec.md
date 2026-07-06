# Twitter/X Marketing Agent — Spec

**Status:** Draft for review · **Created:** 2026-07-06 · **Owner:** admin (vbolofinde)

## Overview
An agent that turns the platform's **real daily data** (setups, honestly-scored performance, the
next-winner finder) into one **education-first, first-person** X post per day — drafted by AI, gated
by a human review step, posted to X, and measured by UTM attribution. Goal: start marketing with a
differentiated, transparent voice (not hype), and learn which content converts.

## Locked decisions (2026-07-06)
- **Review-first** — the agent DRAFTS; you approve/edit/reject; then it posts. (Auto-post later, once trusted.)
- **1 post/day**, rotating content pillars.
- **First-person founder** voice ("here's what I'm watching…"), honest / no-hype / teacher-not-guru.
- **X API** — not set up yet; you'll create the developer account (steps below), I build against it.

## Content pillars (the daily rotation — all from data that already exists)
| Pillar | Source | Angle |
|---|---|---|
| Morning setups | Today's Focus / Morning Focus | "names at a key level pre-market + why" |
| EOD transparency | Performance / EOD recap | "yesterday's calls, scored vs real price — what worked/didn't" |
| Pattern education | Pattern library + a real alert | "what's a 4h reclaim? today's example" |
| Next winner | Long Term Finders | "showing up across 3 thematic ETFs before the crowd" |
| Track-record proof | Performance-share link | "every alert, every outcome, public" |
| Market read | SPY 8/21 regime | "SPY under its 8/21 — weak tape" |

## Architecture (the pipeline)
`Scout (pull data) → Writer (Claude, first-person draft + UTM link) → Compliance editor (Claude, hard-gate)
→ [optional] Visual (chart/leaderboard image) → Review queue (admin) → you approve → Poster (X API) → Measure (UTM → Traffic Sources)`

---

## ▸ YOUR WORK (one-time setup + ongoing review)
1. **X Developer account** *(one-time, blocks the poster)* — at developer.x.com: create a Project + App →
   set User-auth to **Read and Write** → generate OAuth 1.0a keys (**API Key, API Secret, Access Token,
   Access Token Secret** — regenerate the access token/secret *after* enabling Write). Put them in Railway
   as `X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_SECRET`. (I never see the values.) Free tier
   (~1,500 posts/mo) covers 1/day.
2. **Voice input** *(one-time)* — 2–3 tweets/accounts whose tone you like, or a few lines in your words.
   Shapes the writer's prompt. (Default if not given: honest, no-hype, short, teacher-not-guru.)
3. **Own the X account** — the handle/bio/pinned; you own what's published.
4. **Daily review** *(ongoing, ~2 min/day)* — approve / edit / reject the day's draft in the admin queue.
   This is the review-first gate; nothing posts without it.
5. **Later decision** — when/if to flip specific pillars to auto-post.

## ▸ MY WORK (build)
- **A · Draft engine** *(no X API needed)* — pillar rotation, data pull from existing reports/performance/
  finders, first-person Writer (Claude), Compliance-editor pass, UTM link. Runs daily, saves a draft.
- **B · Review queue** — admin-console section: draft cards, approve / edit / reject, copy-to-clipboard
  (so you can post manually before the API is live).
- **C · X API poster** *(after you provide keys)* — the "Approve → post" integration (POST /2/tweets).
- **D · Daily scheduler** — cron on the triage worker (~7:30 ET so you review before the open).
- **E · Compliance ruleset + voice prompt** — the hard rules + your tone baked into the agent.
- **F · Attribution** — UTM per post → the Traffic Sources panel (mostly built already).
- **G · [optional] Chart/leaderboard image** — attach a StaticTradeChart / Performance image to a post.

---

## Compliance ruleset (the editor agent hard-gates every draft)
- Education-first framing; explicit **"not financial advice."**
- **No "buy X now"** / no directive calls that read as advice.
- **No invented win rates** — any performance claim links to the live Performance page.
- Only reference **real, delivered** setups (never fabricate a trade).
- Disclaimer line when a specific ticker is named.
- A draft that fails any rule is rewritten or dropped — never posted.

## Success criteria
- **SC1** A compliant, on-voice draft is ready for review every morning before the open.
- **SC2** You can approve/edit/reject in under 2 minutes; nothing posts unreviewed.
- **SC3** Every posted link carries a UTM, so Traffic Sources shows which pillar/post drives visits + signups.
- **SC4** Zero posts that read as financial advice or cite an unverifiable win rate.

## Build order & dependencies
1. **A + B** (draft engine + review queue) — buildable **now**, no X API. You post manually to start.
2. **E** (ruleset/voice) — folds into A; needs your voice input for the final tone.
3. **D** (scheduler) — after A works.
4. **C** (poster) — **blocked on your X dev account keys.**
5. **G** (image) — optional, last.

## Open inputs from you (to finalize)
- The **voice examples** (for E).
- The **X API keys** in Railway (for C) — on your timeline; A/B/D don't wait on it.
