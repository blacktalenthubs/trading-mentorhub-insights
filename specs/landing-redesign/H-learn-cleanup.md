# Sub-spec H — Prune / Archive Retired `/learn` Patterns

Part of the Landing Redesign master spec. Runs in parallel (content/backend, not landing layout).

## Goal
Make the pattern library tell the truth: teach only the setups that actually fire; archive the
retired ones so the education-first promise holds and the landing can pull a live, accurate count.

## Background (code-verified 2026-07-05)
`api/app/data/pattern_content.py` documents **29 patterns**; a Phase-3a prune (2026-04-23) retired
~1/3 (gap-fill, inside-day, VWAP-loss, session-high double-top, consolidation-breakdown-short, HTF
S/R bounce/reject, index open strength, session-low double-bottom, support-breakdown, hourly
resistance rejection). These no longer fire (no Pine emits them, or removed from `ENABLED_RULES`)
but still appear in `/learn`.

## Requirements
- **H1** Determine the **live** set = documented patterns whose alert type is in `ENABLED_RULES`
  (`alert_config.py`) / a firing `alert_type_config` entry.
- **H2** For retired patterns: **archive** — mark `status: archived`, keep the page reachable
  (SEO/history) with a visible "archived / no longer a live signal" badge; drop from the default
  library grid and from any count. *(Decision: archive, not delete — override to hard-delete if
  preferred.)*
- **H3** Any pattern count/stat shown on the landing or Learn hub is computed from the **live** set
  at render time — never hard-coded. Kills the stale "14 patterns."
- **H4** Each live pattern retains full teaching content (what-is / why-works / when-fails) and its
  Day/Swing/Trend classification.
- **H5** No win-rate figure is presented as validated unless it comes from the real Performance
  scorer; otherwise remove or label as illustrative.

## Acceptance
- `/learn` default view shows only live patterns; archived ones are reachable but badged.
- The landing's pattern grouping (Sub-spec C) and any count match the live set exactly (SC3).
- No orphaned "documented but never fires" pattern appears as a current signal.

## Reuse / build notes
- Sources: `pattern_content.py`, `learn_content.py`, `alertRegistry.ts`, `alert_config.py`,
  `alert_type_config.py`. Add a `status` field to pattern content; filter in Learn + landing.

## Effort: M
