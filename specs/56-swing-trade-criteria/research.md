# Phase 0 Research: Swing Trade Qualification Criteria

No unresolved `NEEDS CLARIFICATION` markers. This records the design decisions, each grounded in the existing codebase.

## Existing system facts (verified)

- **The AI swing scan**: `analytics/ai_swing_scanner.py` — `swing_scan_cycle()` (`:356-546`). Runs every 15 min (`api/app/main.py` lifespan, job `ai_swing_scan`), market-hours gated. Loads watchlist symbols, calls `scan_swing(symbol, api_key)` (`:237-285`) per symbol.
- **Current qualification is LLM-driven**: `scan_swing` fetches 3-month daily bars + `fetch_prior_day` indicators, builds a prompt (`:92-193`), calls Claude Sonnet (`:267`, max 250 tokens, 20s timeout, prompt caching), parses LONG/SHORT/WAIT + entry/stop/T1/T2/conviction (`:199-231`).
- **Delivery**: a qualified candidate persists as an `Alert` row and sends Telegram via the scan's existing path; per-day dedup on `(symbol, direction, level_bucket, conviction)` (`:480-486`); per-tier `ai_swing_alerts_per_day` cap via `usage_limits` (`:528-539`).
- **Indicators already computed**: `analytics/intraday_data.py` `fetch_prior_day()` returns EMA 5/8/10/20/21/50/100/200, SMA (`ma`) 20/50/100/200, RSI14 + RSI14_prev, ATR14, prior close/open/high/low, prior week & month H/L. Helper `compute_rsi_series()` returns an RSI history.
- **Other swing code (out of scope)**: `analytics/swing_rules.py` (`evaluate_swing_rules`, EOD, pure-math — already has RSI-30 bounce, 50/200 MA holds, 200MA reclaim, 20EMA pullback) is **not scheduled** in `main.py`. `analytics/ai_best_setups.py` produces a separate on-demand `swing_trade_picks` list. Neither is the "AI Scan" the spec targets.

## Decision 1: Deterministic rules, not an LLM

- **Decision**: Replace the per-symbol Claude call in the swing scan with a deterministic pure function. Swing qualification becomes math over the daily series + indicators.
- **Rationale**: The trader has prescribed exact, mechanical rules (close above a key MA; RSI crosses 30). An LLM "judging" mechanical rules adds non-determinism, latency (20s/symbol timeout), and Anthropic cost for zero benefit — the answer is computable. Deterministic also makes the rules unit-testable and the spec's success criteria (100%-of-the-time) literally verifiable.
- **Alternatives considered**: Keep the LLM, rewrite the prompt to enforce the rules — rejected: still non-deterministic, still costs tokens, can't be unit-tested. Keep the LLM for a narrative only — out of scope; the spec asks to change *qualification*, not add narration.

## Decision 2: The key-MA set

- **Decision**: Seven daily MAs for the EMA-defense and EMA-reclaim rules — **21 EMA, 50 EMA, 50 SMA, 100 EMA, 100 SMA, 200 EMA, 200 SMA** (the planning input).
- **Rationale**: The trader explicitly listed 50/100/200 in both EMA and SMA and confirmed 200 is included; 21 EMA carries over from the spec's TSLA example. A 21 SMA is not paired — 21 is a fast EMA-style period. **All seven are already computed by `fetch_prior_day`** (`ema21/50/100/200`, `ma50/100/200`) — no new indicator work.
- **Alternatives considered**: 21/50/100 EMA only (the spec's first draft) — superseded by the trader's planning input. Adding the 8 EMA — rejected, too short-term for a swing momentum level.

## Decision 3: "Hold / defense" — what counts

- **Decision**: An MA is *held* on the daily bar when: the bar's **low came within a tolerance of the MA** (touched/tested it), the bar **closed above the MA**, and the symbol was **above that MA going into the bar** (a pullback into it, not a cross up through it).
- **Rationale**: This is the "momentum level being defended" pattern — price dipped to the average and buyers closed it back above. Mirrors the proven shape of `swing_rules.py`'s `check_swing_50ma_hold` / `check_swing_200ma_hold`.
- **Tuning parameter**: the proximity tolerance (the existing rules use ~0.5% for the 50 MA, ~1% for the 200 MA). Plan starts with a single ~1% tolerance; tunable, not a blocker.

## Decision 4: "Reclaim" — what counts

- **Decision**: An MA is *reclaimed* when the **prior daily close was below the MA and the current daily close is above it** — a close-flip from below to above.
- **Rationale**: The trader's "coming from below and close above key EMA qualifies." The TSLA example (pulled back, closed above 21 & 100) is a reclaim when price had slipped under those averages. Needs the MA value on both the current and prior bar — computable from the daily series; `fetch_prior_day` already provides current MAs and prior close.
- **Alternatives considered**: require N prior closes below — rejected as over-strict; a single-bar close-flip is the event.

## Decision 5: "Pullback from a recent high" — uptrend context for the MA rules

- **Decision**: The EMA defense/reclaim rules only fire when the symbol is in an **uptrend / pullback context**: price made a higher high within a recent lookback window AND is not in a sustained downtrend (e.g. price is above the 200-day MA, or the longer MAs are stacked bullishly).
- **Rationale**: FR-011 — a close above a key MA inside a downtrend is a dead-cat bounce, not a defended momentum level. The RSI rule (Decision 6) is the dedicated downtrend-reversal path; the MA rules need genuine prior strength.
- **Tuning parameters**: the recent-high lookback (~20 trading days) and the downtrend filter (above 200 MA / MA stacking). Tunable.

## Decision 6: "RSI recovery from oversold" — what counts

- **Decision**: The RSI rule fires when the daily **RSI(14) closes back above 30** having been **at or below 30 within a recent window** (the oversold downtrend).
- **Rationale**: The trader's "closing above 30 RSI after a downtrend" (NFLX). The qualifying event is the close-above-30; the recent ≤30 reading is the "downtrend" context. Needs the RSI series, not just the prior value — `compute_rsi_series()` already provides it.
- **Tuning parameter**: the oversold lookback window (~5-10 bars). Tunable.

## Decision 7: Entry / stop / targets for a qualified swing

- **Decision**: Derived deterministically — **entry = the qualifying daily close**; **stop = structural** (just below the defended/reclaimed MA, or below the qualifying candle's low, whichever is the tighter valid level; for the RSI rule, below the recent swing low); **targets = R-multiple projection** via the existing long-target helper.
- **Rationale**: The LLM previously produced these; with deterministic qualification they must be derived in code. Reuses the structural-stop pattern already in `swing_rules.py` and the existing target projection.

## Decision 8: Scope — what changes, what does not

- **Decision**: Only `ai_swing_scanner.py`'s **qualification** changes (the `scan_swing` LLM call → `evaluate_swing_quality`). Unchanged: watchlist loading, the 15-min schedule, market-hours/regime gating, per-day dedup, Telegram delivery, the `ai_swing_alerts_per_day` rate limit, and the `Alert`/`swing_trades` persistence.
- **Out of scope**: `swing_rules.py` (legacy EOD scanner, not scheduled), `ai_best_setups.py` swing picks (separate on-demand feature), and the day scanner. Aligning those to the new definition is a possible follow-up.
- **Rationale**: The spec targets "the AI Scan" — the live scheduled swing scanner. Keeping the blast radius to qualification-only is the safe, reviewable change for protected alert logic.
