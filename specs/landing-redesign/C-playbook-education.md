# Sub-spec C — The Playbook (Patterns) + Education-First

Part of the Landing Redesign master spec.

## Goal
Show the real, currently-firing setups grouped by how they're traded, and make the education-first
promise concrete — without a single synthetic win-rate claim.

## What it shows
**Playbook** — header "Every setup we fire — and teach you to see." Three columns of pattern pills:
- **Day:** MA bounce (8/21/50/100/200) · PDL reclaim · PDL held · PDH breakout · 4h reclaim ·
  opening-range break · gap-and-go
- **Swing:** RSI-30 reclaim · RSI-70 · 5/20 EMA cross · weekly reclaim · multi-day double bottom ·
  10w/30w hold
- **Trend/position:** monthly reclaim · monthly-box breakout (MoBO) · prior-month-low held ·
  weekly-MA support
Footnote: "Retired setups are archived, not sold — you only get what actually fires. Every live
pattern has a free lesson: what it is, why it works, when it fails." + link to /learn.

**Education-first** — header "Learn the why, not just the what." Points: documented patterns taught
with real examples (free, no account); the reasoning on every alert; risk-first (a stop on every
setup). "Not financial advice" restated. CTA → pattern library.

## Requirements
- **C1** Pattern list = the **kept** set only (source of truth: `alert_config.py` ENABLED_RULES +
  `alert_type_config.py`); no retired patterns (see Sub-spec H).
- **C2** **No win-rate / % claims** on any pattern; outcome curiosity routes to Performance.
- **C3** Grouping = Day / Swing / Trend, matching the product's own style classification.
- **C4** Education section makes "we teach the reasoning" tangible (not a slogan).
- **C5** Pattern counts/stats, if shown at all, are pulled live — never hard-coded (kills the stale
  "14 patterns").

## Acceptance
- Every pattern shown maps to a live alert type; no dead pattern appears (SC3).
- No unverifiable number appears in the section.

## Reuse / build notes
- Replaces the current `PatternPreview`; reuses `.pill`, card styling.
- Ties to `LearnPage`/`PatternDetailPage`; depends on Sub-spec H for a clean catalog.

## Effort: M
