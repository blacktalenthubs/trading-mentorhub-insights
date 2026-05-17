# Spec 48 — V3 Cleanup & Paid AI Revamp (Product Overview)

**Status**: **Non-buildable manifest.** Decomposed 2026-05-16 into six buildable child specs (49–54). Do NOT run further `/speckit-plan` or `/speckit-tasks` against this file directly.
**Originally written**: 2026-05-16 as a single multi-workstream strategy spec; decomposed the same day once it became clear that three workstreams in one document were harder to track per-sprint and would invite scope creep into any single workstream's planning session.
**Companion**: [Spec 46 (Stable State Reference)](../46-stable-state-reference/spec.md) is the V1 baseline; this V3 manifest formally supersedes parts of 46 via Spec 49's FR-416.

---

## What this document is

A pointer to the six feature-domain specs that, together, deliver the V3 revamp. Each child is independently planned and shipped. This overview preserves the framing — versioning context, positioning, build-order rationale — so a reader landing on the project for the first time can understand the V3 story and then dive into any buildable spec.

## The V3 thesis in one paragraph

V1 was "AI scans the market and picks your trades" via a yfinance-polled Streamlit dashboard, a rule-engine, and a Claude scanner stack. It was abandoned because scanner accuracy was unreliable and the surface couldn't scale. V2 (live today) is the opposite: TradingView Pine indicators fire alerts → FastAPI webhook → Postgres dedup → a separate triage-agent runs each alert through Claude Haiku for conviction rating → routed to Telegram. V3 is the cleanup and commercial buildout of V2: delete the V1 vestiges, reposition the product around what V2 actually delivers, and ship the first paid AI features that are *not* trade-picking — on-demand chart critique, pattern education with live examples, replay coaching, and a daily conviction-report email.

**The one-sentence positioning:** "TradingView's signal noise filtered into conviction-rated trade alerts, with an LLM second-pair-of-eyes on every one — plus on-demand AI chart analysis and pattern education." Every decision in the children below follows from that positioning.

## Decomposition into buildable specs

| # | Spec | Domain | Build cluster |
|---|------|--------|---------------|
| **49** | [v1-cleanup](../49-v1-cleanup/spec.md) | Tier 1–4 deletions + `intraday_rules.py` extraction + CLAUDE.md rewrite + Spec 46 supersedence + legacy domain decision | Foundation — must complete before 51/52/53/54 |
| **50** | [landing-revamp](../50-landing-revamp/spec.md) | Landing positioning rework + App.tsx route consolidation + live-data proof | Parallel with 49 |
| **51** | [chart-critique](../51-chart-critique/spec.md) | The headline paid AI feature — paste/capture chart, structured analysis in <15s | After 49; parallel with 52 |
| **52** | [pattern-education-live](../52-pattern-education-live/spec.md) | Pattern library joined to the live `alerts` table | After 49; parallel with 51 |
| **53** | [replay-coach](../53-replay-coach/spec.md) | AI commentary track on existing `ReplayPage` | After 51 (reuses 51's engine) |
| **54** | [conviction-report-email](../54-conviction-report-email/spec.md) | Daily email digest repackaging `triage-agent/eod.py` output | After 49; independent of 51/52/53 |

## Cross-cutting decisions (apply to every child)

These belong here so each child doesn't repeat the disclaimer:

- **No revival of "AI picks the trades."** The Pine + triage pipeline IS the product. Any child that drifts back toward AI-scanner territory is a strategy violation.
- **No new Streamlit dashboard.** The React app at `tradingwithai.ai` is the user surface.
- **No real-money brokerage integration in v3.** V1 paper-trading is being deleted in Spec 49; v3 does not replace it.
- **No backtesting service in v3.** V1 `BacktestPage` is being deleted in Spec 49; v3 does not replace it.
- **No multi-account / team / institutional pricing in v3.** Future spec.
- **No mobile-native (non-Capacitor) iOS or Android in v3.**
- **Tier model is shared.** Free / Pro / Pro+ definitions and dollar amounts are operator-configurable but consistent across 51, 52, 53, 54.
- **All paid-feature LLM calls go through the same provider abstraction** already used by the triage agent. Adding a new provider abstraction is out of scope for v3.

## Recommended build order

A pragmatic sequence for a small team. Each step assumes its predecessors are merged and stable.

1. **49 v1-cleanup** — foundation. Required prerequisite for everything else.
2. **50 landing-revamp** — parallel with 49. Landing copy doesn't depend on cleanup completing; FR-205's route consolidation does, but the hero/proof/sections work is independent.
3. **51 chart-critique** AND **52 pattern-education-live** in parallel — different teams or different days of the same engineer. Both depend on cleanup; neither depends on the other.
4. **54 conviction-report-email** — can start as early as 51 (independent of 51/52/53), or slot into a quieter sprint window. Pure repackaging; low engineering cost.
5. **53 replay-coach** — depends on 51's engine; build last among the paid features.

Each step ends in a working, end-to-end demo of that capability.

## Cross-cutting product success criteria

These outcomes span multiple children and are not owned by any single spec. The metrics inside child specs (SC-1xx through SC-7xx) are the testable detail; the items below are the strategic targets.

- **PSC-1**: After the full V3 revamp, repo tracked LOC is reduced by ≥15% (owned by Spec 49 SC-101).
- **PSC-2**: First-time visitors can articulate the product's value in ≤15 seconds with ≥80% accuracy in usability testing (owned by Spec 50 SC-201).
- **PSC-3**: For ≥70% of a reviewer-audited 30-chart sample, the dominant bias is correctly identified at launch (owned by Spec 51 SC-302).
- **PSC-4**: Top 5 most-fired patterns each have ≥1 live example from the prior 7 trading days visible on their detail page (owned by Spec 52 SC-501).
- **PSC-5**: 0 plaintext leakage of credentials in any email digest (owned by Spec 54 SC-602).
- **PSC-6**: ≥10% conversion rate from Chart Critique paywall to paid upgrade within 7 days of block (owned by Spec 51 SC-303).
- **PSC-7**: Outside agents reading only the rewritten CLAUDE.md correctly identify the V2 protected-files list with ≥95% accuracy (owned by Spec 49 SC-105).

## Cross-spec coordination (with existing trade-analytics specs)

- **Spec 46 (Stable State Reference)** — explicitly superseded; Spec 49 FR-416 enforces the notice.
- **Spec 47 (Platform Rebrand v2)** — completed work; Spec 50 extends the rebrand into landing positioning.
- **Spec 32 (Copilot Education)** — adjacent; Spec 52's live-examples affordance is the V3 evolution of the static education shipped in 32.
- **Spec 21 (AI Chart Analysis)** — earlier exploration; Spec 51 is the production V3 implementation.
- **Specs 38 / 39 / 40 (AI swing / signal / coach)** — V1-era; superseded by Spec 49's deletions.

## Original input (preserved for record)

This spec started 2026-05-16 from a user prompt: *"lets understand what we have today in the trading analytics and the next direction to pursue for market value and all the dead code we need to remove (lots of initial focus was on AI picking the trades but we abandoned that for pines base solutions, so those AI alerting are dead code), but we also still add/enhance some AI features that people can pay for — chart analysis, education base on charts etc. evaluate current code base and come up with core features and what to revamp from landing page, internals pages and focus core features for market value."* The audit conducted that day produced the dead-code inventory and the feature-seam mapping that this manifest decomposes into 49–54.
