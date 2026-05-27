# Landing Page Repositioning — Spec

**Date**: 2026-05-27
**Status**: Approved for implementation
**Owner**: User + Claude

## Why

Current landing positions TradeCoPilot as an AI alert/signal subscription service. After 6+ months of user research and product evolution, the actual value is broader:

- A **research toolkit** for self-directed investors with day jobs
- **Education** through pattern library + signal replays
- **Public transparency** via daily EOD reports

Selling as "alert service" creates legal exposure (implied financial advice) and undersells the educational + analytical value. Repositioning aligns marketing with reality and reduces legal risk.

## Target Audience

**Primary**: Busy professionals who want to manage their own self-directed brokerage accounts but can't watch markets 9-to-5.

**Secondary**: Active retail traders looking for structured analysis and a transparent track record to study.

**Not the audience**:
- Pure day-traders who watch every tick
- Beginners with no market exposure
- People seeking specific buy/sell recommendations

## Three Value Pillars

### 1. AI Market Analysis
Automated pattern scanning runs during market hours. Results are presented as observations (with entry, stop, target levels) — not commands. Users decide.

### 2. Pattern Education
Every signal is mapped to a documented pattern in the library. Users can study real historical examples via the replay feature.

### 3. Public Strategy Evaluation
Daily EOD reports show what triggered, what worked, what didn't, and why. Transparency is the differentiator — most alert services hide losses; we publish them.

## Positioning Shifts

| Dimension | Old | New |
|-----------|-----|-----|
| Identity | Alert subscription service | Research toolkit |
| Headline | "AI finds the trade. You decide." | "Market research for people with day jobs" |
| Primary CTA | "Start Free — 3 Day Pro Trial" | "Try free for 3 days — no card required" |
| Lead stat | "14 patterns" + win rate | "Public EOD report — see yesterday's signals" |
| Emphasis | Win rate / volume of alerts | Time saved + structured learning |

## Tone Guidelines

**Use**:
- "Research toolkit", "Analytical platform"
- "Self-directed investors"
- "Observations", "Analysis", "Setups"
- "For educational purposes"

**Avoid**:
- "Alerts", "Signals", "Picks", "Recommendations"
- "Win rate" as a headline metric
- Specific dollar/percentage performance claims
- High-pressure sales language

## Page Structure (top to bottom)

1. **Hero** — Headline + sub + low-pressure CTA + small disclaimer
2. **The Problem** — Empathy section addressing the busy-professional pain
3. **Three Pillars** — Grid showing AI Analysis / Education / EOD Reports
4. **EOD Report Preview** — Static example of what a daily report looks like
5. **Pattern Library Teaser** — Grid of 14+ patterns; tap to learn
6. **How It Works** — 3-step flow: watchlist → AI scan → EOD review
7. **Who This Is For / Not For** — Direct framing for self-selection
8. **Pricing** — Existing tiers, softened language
9. **Footer** — Legal disclaimers

## Legal Disclaimers (add throughout)

Add to footer, near pricing, and at bottom of hero:
- "For educational and informational purposes only."
- "Not investment advice. Not a recommendation to buy or sell securities."
- "Past performance does not guarantee future results."
- "Self-directed investors should conduct their own research before making investment decisions."

## What We Keep

- Existing dark visual theme
- Pattern Library page
- EOD Report page (link prominently)
- Track Record page (rename context to "EOD Reports archive")
- Pricing tiers (current structure)
- 3-day free trial mechanism

## What We Remove

- "AI finds the trade" framing
- Prominent win rate stat
- "24/7 crypto" as a headline
- Hard-sell trial language
- "Pattern Library" and "Track Record" as separate top-nav items if they crowd mobile

## Implementation Decisions

- Headline: "Market research for people with day jobs" (final)
- Crypto: keep mentioned in pillars but de-emphasize from hero
- EOD embed: static example for now; live embed is a future enhancement
- Pricing CTA: "Try free for 3 days — no card required"

## Out of Scope (for this iteration)

- Live EOD report data embed on landing
- Video demos
- Customer testimonials
- Comparison tables vs competitors
- Translation/i18n

## Success Criteria

After ship:
- Hero headline reflects "professional toolkit" positioning
- Three pillars visible above the fold on desktop
- EOD report prominence in mid-page
- Legal disclaimers visible in footer + near pricing
- Mobile: page reads cleanly without zoom
- No specific performance numbers as hero stats
