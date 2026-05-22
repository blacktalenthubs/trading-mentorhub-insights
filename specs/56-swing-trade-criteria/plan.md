# Implementation Plan: Swing Trade Qualification Criteria for the AI Scan

**Branch**: `56-swing-trade-criteria` | **Date**: 2026-05-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `trade-analytics/specs/56-swing-trade-criteria/spec.md`

## Summary

The AI swing scanner (`analytics/ai_swing_scanner.py`, `swing_scan_cycle`, runs every 15 min) currently decides swing candidates by sending daily bars to Claude and letting the LLM judge. This feature replaces that judgement with **deterministic rules** the trader prescribed: a symbol is a swing candidate when its daily candle (a) holds or reclaims a **key MA** — the 21 EMA, or the 50/100/200 in EMA or SMA — after a pullback, or (b) its daily RSI closes back above 30 after an oversold downtrend. The qualification becomes a pure function; the LLM call is dropped from swing qualification (removes per-symbol Anthropic cost and non-determinism). Everything else about the scan — watchlist loading, 15-min schedule, dedup, Telegram delivery, rate limits — is unchanged.

## Technical Context

**Language/Version**: Python 3.11 (`trade-analytics/analytics/` + `trade-analytics/api/`)
**Primary Dependencies**: pandas / numpy (indicator math), yfinance + Coinbase REST (daily OHLC), APScheduler (the 15-min job), SQLAlchemy (alert persistence). Anthropic SDK is **removed from the swing-qualification path**.
**Storage**: existing `alerts` / `swing_trades` tables and `usage_limits` — reused, no schema change.
**Testing**: pytest (`trade-analytics/tests/`) — `test_swing_entries.py`, `test_swing_rules.py` are the existing swing-rule tests; a new `test_swing_quality.py` covers the new criteria.
**Target Platform**: Linux server (Railway) — the scheduled scanner inside the FastAPI worker process.
**Project Type**: Backend service — a scheduled analytics scanner. No UI, no new API surface.
**Performance Goals**: Per-symbol qualification is pure math over a daily series — sub-millisecond; the scan stays well within its 15-min budget and no longer waits on a 20s LLM call per symbol.
**Constraints**: Deterministic (same inputs → same result); reuse the indicators `intraday_data.fetch_prior_day` already computes; do not change the scan's schedule, delivery, dedup, or rate-limit behaviour.
**Scale/Scope**: Tens of watchlist symbols per scan, every 15 min during market hours.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is an unpopulated template — no formal gates. The **binding constraint is `trade-analytics/CLAUDE.md`**, which classes alert-trigger logic as protected business logic requiring impact analysis, full test coverage, and explicit user approval before change.

- **Explicit approval**: the spec (feature 56) is the user's written request to change this exact logic. PASS.
- **Impact analysis**: this plan + research.md are the impact analysis — what changes (swing *qualification* only), what does not (schedule, dedup, delivery, rate limit, the day scanner, `swing_rules.py` EOD, `ai_best_setups.py`). PASS.
- **Test coverage**: a new `test_swing_quality.py` covers every rule; the existing swing/alert suites must still pass. PASS.
- **No protected file edited blindly**: `ai_swing_scanner.py` is touched deliberately and is the subject of the approved spec; `intraday_rules.py`, `signal_engine.py`, `monitor.py`, `worker.py`, `alerting/*` are NOT modified. PASS.

Post-Phase 1 re-check: no new violations — one new pure module, one wiring change in the scanner, one test file. PASS.

## Project Structure

### Documentation (this feature)

```text
trade-analytics/specs/56-swing-trade-criteria/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── swing-quality.md # Phase 1 — the evaluate_swing_quality() function contract
├── checklists/
│   └── requirements.md  # From /speckit-specify
└── tasks.md             # Phase 2 (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
trade-analytics/
├── analytics/
│   ├── swing_quality.py        # NEW — deterministic swing-qualification rules
│   ├── ai_swing_scanner.py     # MODIFIED — swing_scan_cycle uses swing_quality
│   │                           #   instead of the per-symbol LLM call
│   └── intraday_data.py        # REUSED unchanged — fetch_prior_day already
│                               #   computes EMA 21/50/100/200, MA 50/100/200,
│                               #   RSI14 (+ helpers compute_rsi_series)
└── tests/
    └── test_swing_quality.py   # NEW — rule coverage incl. TSLA / NFLX cases
```

**Structure decision**: Backend analytics change. New deterministic logic lives in its own pure module (`analytics/swing_quality.py`) so it is unit-testable in isolation; `ai_swing_scanner.py` keeps ownership of orchestration (watchlist, schedule, dedup, delivery) and simply calls the new module for qualification.

## Phase 0: Outline & Research

See [research.md](./research.md). Key decisions resolved there:

- **Deterministic, not LLM** — the trader prescribed exact rules, so swing qualification becomes a pure function; the Claude call is removed from the swing path.
- **Key MA set** — 21 EMA + 50/100/200 in both EMA and SMA = seven MAs (per the planning input); all seven are already computed by `fetch_prior_day`.
- **"Hold/defense", "reclaim", "pullback-from-high", "downtrend", and the uptrend gate** — each given a concrete, testable definition with a tuning parameter.
- **Scope** — only `ai_swing_scanner.py`'s qualification changes; the legacy `swing_rules.py` EOD scanner and `ai_best_setups.py` swing picks are out of scope.

There are no open `NEEDS CLARIFICATION` markers — the spec's two scope assumptions plus the planning input fully determine the design; tolerances are tuning parameters, not blockers.

## Phase 1: Design & Contracts

- **Data model**: [data-model.md](./data-model.md) — the in-memory **Swing Candidate** / qualification-result structure (no DB schema change; output still persists through the existing `Alert` path).
- **Contract**: [contracts/swing-quality.md](./contracts/swing-quality.md) — the `evaluate_swing_quality()` function contract: inputs (daily series + indicators), output (qualification result or none), and the rule semantics.
- **Quickstart**: [quickstart.md](./quickstart.md) — local verification against the TSLA (EMA defense/reclaim) and NFLX (RSI recovery) cases plus a no-setup control.
- **Agent context**: `CLAUDE.md` updated to point at this plan.

## Phase 2: Planning Approach

`/speckit-tasks` will decompose this. Expected groupings:

1. **Indicator inputs** — confirm/extend `fetch_prior_day` exposes all seven MAs + the RSI series the rules need (it already computes them; verify shape).
2. **`swing_quality.py`** — the three rule families: EMA/SMA defense (hold), EMA/SMA reclaim, RSI-30 recovery; the uptrend gate for the MA rules; merge multi-rule hits into one candidate.
3. **Entry / stop / targets** — derive deterministically (entry = qualifying close; stop = structural, below the defended MA / candle low; targets via the existing R-projection helper).
4. **Wire into `swing_scan_cycle`** — replace `scan_swing` (the LLM call) with `evaluate_swing_quality`; keep watchlist load, schedule, dedup, Telegram, rate limit.
5. **Tests** — `test_swing_quality.py`: each rule, the uptrend gate, multi-rule merge, TSLA/NFLX fixtures, no-setup control.
6. **Regression** — run the full pytest suite; confirm the alert/swing suites still pass.

## Complexity Tracking

No constitution violations. The design removes complexity (drops an LLM call and its prompt, caching, parsing, and timeout handling from the swing path) in exchange for one small pure module. No new tables, no new endpoints, no new dependencies.
