# Sub-spec F — Proof, How-it-works, Pricing & Footer

Part of the Landing Redesign master spec.

## Goal
Close the page: prove it's transparent, show the 3-step flow, present pricing, and carry the legal
disclaimers.

## What it shows
- **How it works (3 steps):** 01 Build your watchlist (or start from Trade Ideas / Long Term
  Finders) · 02 The system watches all day (levels, momentum, 24/7 crypto) · 03 You get the setup +
  the AI read.
- **Proof / transparency:** "Every alert. Every outcome. Public." — the daily report + the scored
  Performance page + shareable performance link. Stat chips = descriptors, **not win rates**
  (e.g. "Scored vs real price," "Public daily reports," "Shareable").
- **Pricing:** Free ($0 — 5 symbols, top setups preview, pattern library, public reports) · Pro
  ($49/mo — unlimited watchlist, all agents, real-time alerts, Long Term Finders, Performance,
  apps). CTAs: Try free for 3 days.
- **Final CTA:** "Stop staring at charts. Let the desk watch for you." + Start free.
- **Footer:** brand, links (Pattern Library, Reports, Pricing, Terms, Privacy), **full legal
  disclosure block** (research/education, not investment advice, past performance, risk of loss).

## Requirements
- **F1** Proof stats are descriptive, never a numeric win-rate; deep-link to the live Performance /
  track-record pages.
- **F2** Pricing reuses the current plan data (no plan changes).
- **F3** "Not financial advice" + risk disclosure present in the footer and near the final CTA.
- **F4** The public Performance-share link is referenced as the transparency proof.

## Acceptance
- No unverifiable performance claim anywhere in the section (SC3).
- Disclaimers present and legible; pricing matches the live plans.

## Reuse / build notes
- Reuse `HowItWorks`, `Pricing`, `FinalCTA`, `Footer` section functions + `PricingPage` data.
- Proof ties to `PublicEODReportPage` / `TrackRecordPage` / the Performance-share page.

## Effort: M
