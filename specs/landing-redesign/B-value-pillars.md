# Sub-spec B — Value Pillars

Part of the Landing Redesign master spec.

## Goal
In one scannable grid, show the platform's engine and the ways it works for a busy professional —
with the correct systems-vs-agents framing.

## What it shows
Section header: "The system watches your levels. The agents explain, triage, and coach."
Cards (each: icon, title, one plain-language paragraph):
1. **Day Trades** — "A rules-based system watches your levels — 4h reclaims, opening-range breaks,
   prior-day highs/lows — and fires the second one triggers, entry / stop / target drawn. Every
   alert carries an AI thesis."
2. **Swing Trades** — multi-day setups you can hold through a workday; momentum + RSI-managed.
3. **Performance** — which setups actually work, scored against real price; honest, shareable.
4. **The Agents = your analyst** — on top of the system: thesis on each setup, triage HIGH/MUTE,
   AM+PM briefs, on-demand coach. The analyst a busy pro doesn't have time to be.

(Trade Ideas + Long Term Finders live in Sub-spec D, not here, to avoid duplication.)

## Requirements
- **B1** Alerts/scans framed as **systems** (deterministic); AI framed as **explanation/curation**
  — never as the trigger. (Per systems-vs-agents truth.)
- **B2** No per-pattern win-rate numbers; Performance card links to the live page.
- **B3** Each card readable by a non-trader; ≤2 sentences.

## Acceptance
- A reader can, per card, say what it does and whether it's "the system" or "the AI" (SC2).
- Nothing claims AI generates or picks the trades.

## Reuse / build notes
- Replaces/extends the current `AIPillars` (3 pillars) — expand to this set; reuse card styling.
- Tokens: per-pillar accent tints (accent/bullish/purple).

## Effort: M
