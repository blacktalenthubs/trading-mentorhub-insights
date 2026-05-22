# Quickstart: Swing Trade Qualification Criteria

Local verification for the new deterministic swing qualification. Steps map to the spec's user stories and success criteria.

## Prerequisites

- `trade-analytics/` repo on branch `56-swing-trade-criteria`.
- Python 3.11 env with the project deps (pandas, numpy, yfinance).
- No `ANTHROPIC_API_KEY` needed — the new swing qualification makes no LLM call.

## Unit verification (no network)

The qualification logic is a pure function — verify it with fixture daily series, no market data:

```bash
# from trade-analytics/
python3 -m pytest tests/test_swing_quality.py -v
```

`test_swing_quality.py` must cover:

- **US1 — EMA defense**: a fixture where the latest bar pulls back into the 50 EMA (low within tolerance, closes above, prior bars above it, uptrend) → result cites `ema_hold` / `EMA 50`. *(SC-001)*
- **US1 — reclaim**: prior close below the 100 SMA, current close above → cites `ema_reclaim` / `SMA 100`.
- **US1 — TSLA-style**: a bar that closes back above both the 21 EMA and the 100 EMA → one `SwingQualification` with two rule hits. *(SC-001, FR-008)*
- **US2 — NFLX-style RSI recovery**: RSI(14) ≤ 30 within the oversold window, latest bar closes with RSI > 30 → cites `rsi_recovery` / `RSI 30`. *(SC-002)*
- **US3 — summary**: every result's `summary` names the rule and level in plain language. *(SC-003)*
- **Uptrend gate**: a close above the 21 EMA inside a sustained downtrend → no MA hit. *(FR-011)*
- **No-setup control**: a sideways series with no MA interaction and no oversold RSI → `None`. *(SC-004)*
- **Determinism**: the same fixture evaluated twice → identical output.

## Integration check (the scan)

```bash
# from trade-analytics/
python3 -m pytest tests/ -q --continue-on-collection-errors
```

Confirm the existing alert / swing test suites still pass — the scan's watchlist loading, dedup, delivery, and rate-limit behaviour are unchanged.

## Live spot-check (optional, market data)

With a watchlist containing TSLA and NFLX, run one swing-scan cycle (or call `evaluate_swing_quality` directly against freshly fetched daily data) and confirm:

- A symbol that recently closed back above a key MA after a pullback is returned as a swing candidate, with the MA named.
- A symbol whose RSI just crossed back above 30 after a downtrend is returned, citing the RSI recovery.
- A symbol drifting sideways is not returned.
- No symbol triggers a Claude/Anthropic call from the swing path (qualification is now pure math).

## Done when

- `test_swing_quality.py` is green and covers every rule + the TSLA/NFLX cases + the no-setup control.
- The full backend suite shows no new failures versus the pre-change baseline.
- A scan run produces swing candidates whose `summary` states why each qualified (SC-003), and never duplicates a symbol within a session (SC-005).
