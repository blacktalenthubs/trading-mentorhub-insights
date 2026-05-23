# Implementation Plan: Day-Trade Entry Rules Redesign

**Branch**: `012-entry-rules-redesign` | **Date**: 2026-05-22 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `./spec.md`

## Summary

Replace today's 15+ noisy entry-alert types with a small, high-conviction set (≤ 6) gated on a strict uptrend filter and enriched with inline confluence annotation. All work happens in two layers:

1. **TradingView Pine scripts** — add the *zero-MAs-overhead* uptrend gate to `ma_ema_daily.pine`, retire open-line entry triggers, encode the dual-role behavior of prior highs/lows, add the higher-high chop gate for continuation entries, and pass the relevant nearby levels (MAs, PDH/PDL, MTD AVWAP) to the webhook in the alert payload so the backend can check for confluence.
2. **FastAPI webhook** — `tv_webhook.py` reads the new payload fields, runs confluence detection (within a small price band), and appends a single annotated message — no second alert. `alert_type_config` is pruned to the ≤ 6 routed entry types.

No new infrastructure. No LLM calls. Pure deterministic logic, all server-side already, just rewired. Spec 56's Python swing scanner becomes redundant (Pine on daily MAs is the swing scanner) and gets retired in a follow-up cleanup.

## Technical Context

**Language/Version**: Pine Script v5 (TradingView server-side) · Python 3.11 (FastAPI worker on Railway) · TypeScript 5 (React frontend — no changes this spec)
**Primary Dependencies**: TradingView (Pine + webhooks) · FastAPI · SQLAlchemy 2.x async · psycopg2 · python-telegram-bot · APScheduler · pandas (for AVWAP fallback if needed)
**Storage**: PostgreSQL on Railway (`alerts`, `alert_type_config`, `watchlist`, `users` tables — all existing)
**Testing**: pytest for FastAPI changes (`api/tests/`); manual chart verification + the existing ✓/✗ scorecard for Pine changes (Pine has no test framework — the EOD scorecard is the validation surface)
**Target Platform**: TradingView servers (Pine alerts fire server-side) → Railway-hosted FastAPI worker (webhook receives) → Telegram + DB
**Project Type**: Existing monorepo (`trade-analytics/`) with `api/` (FastAPI), `pine_scripts/active/` (Pine), `web/` (React). No new top-level directories.
**Performance Goals**: Webhook end-to-end < 1s (Telegram delivery). Confluence check < 50ms per alert (pure in-memory comparison, no external I/O). Pine alert evaluation on every bar close.
**Constraints**: Preserve existing cooldown/dedup pipeline (60-min identity dedup, session dedup, confluence-twin suppression). Zero Anthropic API spend (all deterministic). Single-user scope (`SCAN_USER_EMAIL=vbolofinde@gmail.com`).
**Scale/Scope**: ~30-50 watchlist symbols, projected ~5-25 alerts/day post-cut (down from 50-150). One Pine script touched (`ma_ema_daily.pine`), two backend files modified (`tv_webhook.py`, `alert_type_config.py`), one DB migration (deactivate retired types).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project's `constitution.md` is the unfilled template (placeholders only — no ratified principles). No formal gates apply. Spec 58 inherits the implicit project principles surfaced repeatedly in user feedback:

- **Minimal solutions** — lead with the smallest viable change; cut complexity hard. *(This plan touches one Pine file + two Python files + one DB migration. No new services, no new dependencies.)*
- **Manual validation phase** — surface candidates, do not auto-trade. *(Preserved — FR-012.)*
- **Wait for approval before code changes** — design + propose, do not preemptively edit. *(Plan only — no implementation in this command.)*

**Gate result: PASS** (no constitutional principles defined to violate).

## Project Structure

### Documentation (this feature)

```text
trade-analytics/specs/58-entry-rules-redesign/
├── spec.md                  # The requirements (already done)
├── spec.html                # Browser-friendly render of spec.md
├── plan.md                  # This file (Phase 2 plan)
├── research.md              # Phase 0 — decisions on open implementation choices
├── data-model.md            # Phase 1 — alert payload schema, entity field map
├── quickstart.md            # Phase 1 — how to validate end-to-end after deploy
├── contracts/
│   └── tv-webhook-payload.md  # JSON contract: Pine → /tv-webhook
└── checklists/
    └── requirements.md      # Spec quality checklist (already done)
```

### Source Code (existing `trade-analytics/` monorepo)

```text
trade-analytics/
├── pine_scripts/active/
│   ├── ma_ema_daily.pine    # PRIMARY edit — uptrend gate, MTD AVWAP, confluence payload
│   ├── levels_day_vwap.pine # SECONDARY edit — retire open-line entry alertconditions,
│   │                        #                   dual-role PDH/PDL/PWL/PWH (support-from-above only)
│   ├── open_line.pine       # No change — keep plot only (it's already visual-only after entries retire)
│   └── ...
├── api/app/
│   ├── routers/
│   │   └── tv_webhook.py    # PRIMARY edit — parse confluence_levels, run confluence check,
│   │                        #                 append confluence string to alert message
│   ├── models/
│   │   └── alert_type_config.py  # Update catalog: retire entries; keep visual/notice types
│   └── main.py              # ALTER TABLE migration to deactivate retired toggles (idempotent)
└── tests/
    └── test_tv_webhook_confluence.py  # NEW — unit tests for confluence detection
```

**Structure Decision**: Use the existing `trade-analytics/` repo as-is. No new directories. All changes localize to `pine_scripts/active/`, `api/app/routers/`, `api/app/models/`. The Python swing scanner (`analytics/swing_scanner.py`, `analytics/swing_quality.py`) is left in place by this spec — its retirement is a separate cleanup pass (deferred per spec 58 Assumptions).

## Complexity Tracking

> No constitutional violations. Table empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| *(none)*  |            |                                     |
