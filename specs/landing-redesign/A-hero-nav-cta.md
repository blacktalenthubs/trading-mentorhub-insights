# Sub-spec A — Hero, Nav & App CTAs

Part of the Landing Redesign master spec.

## Goal
The first screen makes the positioning unmistakable in one glance and offers every primary path:
start free, download the apps, see a live report.

## What it shows
- **Nav:** brand (BusyTradersDesk), links (How it works · Patterns · Track Record · Pricing),
  Sign in + Start free. Sticky, blurred.
- **Hero headline:** "One platform to day-trade, swing, and find the next big winner — without
  living on the charts."
- **Sub-head:** "A disciplined, rules-based system watches your levels. The moment a setup fires
  you get the entry, stop, target — then an AI agent explains the why. Educational, never
  financial advice."
- **Badge:** "Built for professionals with a day job."
- **CTAs:** Start free — 3 days (primary) · See a live daily report (secondary).
- **App badges:** iOS · Android · Mac & Windows (link to Sub-spec E targets).
- **Trust line:** "No card required · For educational & informational purposes only."
- **Hero visual (2 cards):** left = a real alert card (entry/stop/target + "why"); right = "…then
  the AI reads it for you" (thesis · triage · brief · coach). Shows system→alert, agent→insight.

## Requirements
- **A1** Headline + sub-head communicate day + swing + long-term + one-platform + education, no
  jargon.
- **A2** The systems-vs-agents split is visible in the hero (system fires, AI explains) — never
  "AI picks your trades."
- **A3** App-download entry points present in the hero (badges), wired to Sub-spec E.
- **A4** "Not financial advice" visible above the fold.
- **A5** No performance/win-rate numbers in the hero.

## Acceptance
- A visitor reading only the hero can state the audience and the one-platform promise (SC1).
- All four primary paths (free trial, mobile, desktop, live report) are reachable from screen one.
- Renders cleanly on a 375px-wide phone; no horizontal scroll.

## Reuse / build notes
- `LandingPage.tsx` → the `Hero` + `LandingNav` section functions; `StickyLandingCTA`.
- Tokens: accent/purple gradient, bullish CTA glow. Fonts already set.

## Effort: M
